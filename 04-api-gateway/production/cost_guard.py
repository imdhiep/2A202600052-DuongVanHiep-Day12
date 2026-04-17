"""
Cost Guard with Redis-backed monthly budgets.

Exercise 4.4 yêu cầu:
- Mỗi user có budget $10/tháng
- Lưu spending trong Redis
- Tự reset khi sang tháng mới
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import redis
from fastapi import HTTPException

MONTHLY_BUDGET_USD = float(os.getenv("MONTHLY_BUDGET_USD", "10"))
GLOBAL_MONTHLY_BUDGET_USD = float(os.getenv("GLOBAL_MONTHLY_BUDGET_USD", "100"))
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

PRICE_PER_1K_INPUT_TOKENS = 0.00015
PRICE_PER_1K_OUTPUT_TOKENS = 0.0006
_redis_client: redis.Redis | None = None


def redis_client() -> redis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis_client


def current_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def budget_key(user_id: str, month: str | None = None) -> str:
    return f"budget:{user_id}:{month or current_month()}"


def global_budget_key(month: str | None = None) -> str:
    return f"budget:global:{month or current_month()}"


def budget_ttl_seconds() -> int:
    return 32 * 24 * 3600


def estimate_cost(input_tokens: int, output_tokens: int) -> float:
    input_cost = (input_tokens / 1000) * PRICE_PER_1K_INPUT_TOKENS
    output_cost = (output_tokens / 1000) * PRICE_PER_1K_OUTPUT_TOKENS
    return round(input_cost + output_cost, 6)


def get_spending(user_id: str) -> float:
    value = redis_client().get(budget_key(user_id))
    return round(float(value or 0.0), 6)


def get_global_spending() -> float:
    value = redis_client().get(global_budget_key())
    return round(float(value or 0.0), 6)


def check_budget(user_id: str, estimated_cost: float) -> bool:
    """
    Return True nếu còn budget, False nếu vượt.

    Logic:
    - Mỗi user có budget $10/tháng
    - Track spending trong Redis
    - Reset đầu tháng (thông qua key theo YYYY-MM)
    """
    client = redis_client()
    month = current_month()
    user_key = budget_key(user_id, month)
    global_key = global_budget_key(month)

    with client.pipeline() as pipe:
        while True:
            try:
                pipe.watch(user_key, global_key)
                current_user = float(pipe.get(user_key) or 0.0)
                current_global = float(pipe.get(global_key) or 0.0)

                if current_user + estimated_cost > MONTHLY_BUDGET_USD:
                    pipe.unwatch()
                    return False

                if current_global + estimated_cost > GLOBAL_MONTHLY_BUDGET_USD:
                    pipe.unwatch()
                    return False

                pipe.multi()
                pipe.incrbyfloat(user_key, estimated_cost)
                pipe.expire(user_key, budget_ttl_seconds())
                pipe.incrbyfloat(global_key, estimated_cost)
                pipe.expire(global_key, budget_ttl_seconds())
                pipe.execute()
                return True
            except redis.WatchError:
                continue


def enforce_budget(user_id: str, estimated_cost: float) -> dict:
    try:
        allowed = check_budget(user_id, estimated_cost)
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Budget store unavailable. Try again later.",
        ) from exc

    if not allowed:
        used = get_spending(user_id)
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Monthly budget exceeded",
                "budget_usd": MONTHLY_BUDGET_USD,
                "used_usd": used,
                "requested_usd": round(estimated_cost, 6),
                "resets_at": "start of next UTC month",
            },
        )

    used = get_spending(user_id)
    global_used = get_global_spending()
    return {
        "month": current_month(),
        "used_usd": used,
        "remaining_usd": round(max(0.0, MONTHLY_BUDGET_USD - used), 6),
        "budget_usd": MONTHLY_BUDGET_USD,
        "global_used_usd": global_used,
        "global_budget_usd": GLOBAL_MONTHLY_BUDGET_USD,
    }


def get_usage(user_id: str) -> dict:
    try:
        used = get_spending(user_id)
        global_used = get_global_spending()
    except redis.RedisError as exc:
        raise HTTPException(
            status_code=503,
            detail="Budget store unavailable. Try again later.",
        ) from exc

    return {
        "user_id": user_id,
        "month": current_month(),
        "used_usd": used,
        "remaining_usd": round(max(0.0, MONTHLY_BUDGET_USD - used), 6),
        "budget_usd": MONTHLY_BUDGET_USD,
        "global_used_usd": global_used,
        "global_budget_usd": GLOBAL_MONTHLY_BUDGET_USD,
    }
