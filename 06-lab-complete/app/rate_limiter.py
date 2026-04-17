"""Sliding-window rate limiter with Redis persistence for multi-instance deployments."""

from __future__ import annotations

import logging
import math
import time
import uuid
from collections import defaultdict, deque
from dataclasses import dataclass

import redis
from fastapi import HTTPException, status


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RateLimitStatus:
    limit: int
    remaining: int
    reset_at_epoch: int
    retry_after_seconds: int


class RateLimiter:
    """Apply per-user request limits across either Redis or local memory."""

    def __init__(self, redis_url: str, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._redis = self._connect_redis(redis_url)
        self._windows: dict[str, deque[float]] = defaultdict(deque)

    def _connect_redis(self, redis_url: str) -> redis.Redis | None:
        if not redis_url:
            return None
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("rate_limiter.connected_to_redis")
            return client
        except Exception:
            logger.warning("rate_limiter.redis_unavailable_falling_back_to_memory")
            return None

    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def _raise_limit(self, retry_after_seconds: int, remaining: int = 0) -> None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "limit": self.max_requests,
                "window_seconds": self.window_seconds,
                "retry_after_seconds": retry_after_seconds,
            },
            headers={
                "Retry-After": str(retry_after_seconds),
                "X-RateLimit-Limit": str(self.max_requests),
                "X-RateLimit-Remaining": str(remaining),
            },
        )

    def _check_memory(self, identifier: str) -> RateLimitStatus:
        now = time.time()
        window = self._windows[identifier]
        while window and window[0] <= now - self.window_seconds:
            window.popleft()

        if len(window) >= self.max_requests:
            oldest = window[0]
            retry_after = max(1, math.ceil(oldest + self.window_seconds - now))
            self._raise_limit(retry_after)

        window.append(now)
        remaining = self.max_requests - len(window)
        return RateLimitStatus(
            limit=self.max_requests,
            remaining=remaining,
            reset_at_epoch=math.ceil(now + self.window_seconds),
            retry_after_seconds=0,
        )

    def _check_redis(self, identifier: str) -> RateLimitStatus:
        assert self._redis is not None

        key = f"agent:rate_limit:{identifier}"
        now_ms = int(time.time() * 1000)
        window_start = now_ms - (self.window_seconds * 1000)

        pipe = self._redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zcard(key)
        _, current_count = pipe.execute()

        if int(current_count) >= self.max_requests:
            oldest = self._redis.zrange(key, 0, 0, withscores=True)
            retry_after = self.window_seconds
            if oldest:
                retry_after = max(
                    1,
                    math.ceil((oldest[0][1] + (self.window_seconds * 1000) - now_ms) / 1000),
                )
            self._raise_limit(retry_after)

        member = f"{now_ms}:{uuid.uuid4().hex}"
        pipe = self._redis.pipeline()
        pipe.zadd(key, {member: now_ms})
        pipe.expire(key, self.window_seconds)
        pipe.zcard(key)
        _, _, count_after = pipe.execute()

        remaining = max(0, self.max_requests - int(count_after))
        return RateLimitStatus(
            limit=self.max_requests,
            remaining=remaining,
            reset_at_epoch=math.ceil(time.time() + self.window_seconds),
            retry_after_seconds=0,
        )

    def check(self, identifier: str) -> RateLimitStatus:
        if self._redis:
            return self._check_redis(identifier)
        return self._check_memory(identifier)
