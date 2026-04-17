"""Budget protection with Redis persistence and safe local fallback."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import redis
from fastapi import HTTPException, status


logger = logging.getLogger(__name__)

INPUT_COST_PER_1K_TOKENS = 0.00015
OUTPUT_COST_PER_1K_TOKENS = 0.0006


@dataclass(slots=True)
class UsageSummary:
    user_id: str
    month: str
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float
    budget_usd: float
    global_cost_usd: float
    global_budget_usd: float

    @property
    def budget_remaining_usd(self) -> float:
        return round(max(0.0, self.budget_usd - self.cost_usd), 6)

    @property
    def budget_used_pct(self) -> float:
        if self.budget_usd <= 0:
            return 0.0
        return round((self.cost_usd / self.budget_usd) * 100, 1)


class CostGuard:
    """Track spending per user and globally for the current month."""

    def __init__(
        self,
        redis_url: str,
        monthly_budget_usd: float,
        global_monthly_budget_usd: float,
    ) -> None:
        self.monthly_budget_usd = monthly_budget_usd
        self.global_monthly_budget_usd = global_monthly_budget_usd
        self._redis = self._connect_redis(redis_url)
        self._memory_usage: dict[tuple[str, str], dict[str, float]] = {}
        self._memory_global: dict[str, float] = {}

    def _connect_redis(self, redis_url: str) -> redis.Redis | None:
        if not redis_url:
            return None
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("cost_guard.connected_to_redis")
            return client
        except Exception:
            logger.warning("cost_guard.redis_unavailable_falling_back_to_memory")
            return None

    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    @staticmethod
    def current_month() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m")

    @staticmethod
    def estimate_cost(input_tokens: int, output_tokens: int) -> float:
        input_cost = (input_tokens / 1000) * INPUT_COST_PER_1K_TOKENS
        output_cost = (output_tokens / 1000) * OUTPUT_COST_PER_1K_TOKENS
        return round(input_cost + output_cost, 6)

    def _user_key(self, user_id: str, month: str) -> str:
        return f"agent:cost:user:{month}:{user_id}"

    def _global_key(self, month: str) -> str:
        return f"agent:cost:global:{month}"

    def _ttl_seconds(self) -> int:
        return 35 * 24 * 60 * 60

    def get_usage(self, user_id: str) -> UsageSummary:
        month = self.current_month()

        if self._redis:
            user_key = self._user_key(user_id, month)
            global_key = self._global_key(month)
            raw_user = self._redis.hgetall(user_key)
            global_cost = float(self._redis.get(global_key) or 0.0)

            return UsageSummary(
                user_id=user_id,
                month=month,
                requests=int(raw_user.get("requests", 0)),
                input_tokens=int(raw_user.get("input_tokens", 0)),
                output_tokens=int(raw_user.get("output_tokens", 0)),
                cost_usd=round(float(raw_user.get("cost_usd", 0.0)), 6),
                budget_usd=self.monthly_budget_usd,
                global_cost_usd=round(global_cost, 6),
                global_budget_usd=self.global_monthly_budget_usd,
            )

        usage = self._memory_usage.get((month, user_id), {})
        global_cost = self._memory_global.get(month, 0.0)
        return UsageSummary(
            user_id=user_id,
            month=month,
            requests=int(usage.get("requests", 0)),
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
            cost_usd=round(float(usage.get("cost_usd", 0.0)), 6),
            budget_usd=self.monthly_budget_usd,
            global_cost_usd=round(global_cost, 6),
            global_budget_usd=self.global_monthly_budget_usd,
        )

    def check_budget(self, user_id: str, estimated_cost_usd: float = 0.0) -> UsageSummary:
        usage = self.get_usage(user_id)
        projected_user_cost = usage.cost_usd + estimated_cost_usd
        projected_global_cost = usage.global_cost_usd + estimated_cost_usd

        if projected_user_cost > self.monthly_budget_usd:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "Monthly budget exceeded",
                    "budget_usd": self.monthly_budget_usd,
                    "used_usd": usage.cost_usd,
                    "projected_usd": round(projected_user_cost, 6),
                    "resets_at": "start of next UTC month",
                },
            )

        if self.global_monthly_budget_usd > 0 and projected_global_cost > self.global_monthly_budget_usd:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Service budget exhausted for the current month.",
            )

        return usage

    def record_usage(self, user_id: str, input_tokens: int, output_tokens: int) -> UsageSummary:
        month = self.current_month()
        added_cost = self.estimate_cost(input_tokens, output_tokens)

        if self._redis:
            user_key = self._user_key(user_id, month)
            global_key = self._global_key(month)
            pipe = self._redis.pipeline()
            pipe.hincrby(user_key, "requests", 1)
            pipe.hincrby(user_key, "input_tokens", input_tokens)
            pipe.hincrby(user_key, "output_tokens", output_tokens)
            pipe.hincrbyfloat(user_key, "cost_usd", added_cost)
            pipe.expire(user_key, self._ttl_seconds())
            pipe.incrbyfloat(global_key, added_cost)
            pipe.expire(global_key, self._ttl_seconds())
            pipe.execute()
            return self.get_usage(user_id)

        key = (month, user_id)
        usage = self._memory_usage.setdefault(
            key,
            {"requests": 0, "input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0},
        )
        usage["requests"] += 1
        usage["input_tokens"] += input_tokens
        usage["output_tokens"] += output_tokens
        usage["cost_usd"] = round(float(usage["cost_usd"]) + added_cost, 6)
        self._memory_global[month] = round(self._memory_global.get(month, 0.0) + added_cost, 6)
        return self.get_usage(user_id)
