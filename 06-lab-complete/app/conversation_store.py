"""Redis-backed conversation storage with an in-memory fallback for local development."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import redis


logger = logging.getLogger(__name__)


class ConversationStore:
    """Persist conversation history and lightweight user profile data."""

    def __init__(self, redis_url: str, ttl_seconds: int, max_turns: int) -> None:
        self.redis_url = redis_url
        self.ttl_seconds = ttl_seconds
        self.max_messages = max(2, max_turns * 2)
        self._redis = self._connect_redis(redis_url)
        self._memory_store: dict[str, dict] = {}

    def _connect_redis(self, redis_url: str) -> redis.Redis | None:
        if not redis_url:
            return None
        try:
            client = redis.from_url(redis_url, decode_responses=True)
            client.ping()
            logger.info("conversation_store.connected_to_redis")
            return client
        except Exception:
            logger.warning("conversation_store.redis_unavailable_falling_back_to_memory")
            return None

    def backend(self) -> str:
        return "redis" if self._redis else "memory"

    def is_ready(self) -> bool:
        if not self._redis:
            return False
        try:
            self._redis.ping()
            return True
        except Exception:
            logger.warning("conversation_store.redis_ping_failed")
            return False

    def _session_key(self, user_id: str) -> str:
        return f"agent:session:{user_id}"

    def _default_session(self) -> dict:
        return {"history": [], "profile": {}, "updated_at": None}

    def get_session(self, user_id: str) -> dict:
        if self._redis:
            raw = self._redis.get(self._session_key(user_id))
            if raw:
                session = json.loads(raw)
                session.setdefault("history", [])
                session.setdefault("profile", {})
                return session
            return self._default_session()

        session = self._memory_store.get(user_id)
        if session is None:
            session = self._default_session()
            self._memory_store[user_id] = session
        return {
            "history": list(session.get("history", [])),
            "profile": dict(session.get("profile", {})),
            "updated_at": session.get("updated_at"),
        }

    def save_session(self, user_id: str, session: dict) -> None:
        session["history"] = session.get("history", [])[-self.max_messages :]
        session["updated_at"] = datetime.now(timezone.utc).isoformat()

        if self._redis:
            self._redis.setex(self._session_key(user_id), self.ttl_seconds, json.dumps(session))
            return

        self._memory_store[user_id] = session

    def append_message(self, user_id: str, role: str, content: str) -> dict:
        session = self.get_session(user_id)
        history = session.setdefault("history", [])
        history.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.save_session(user_id, session)
        return session

    def update_profile(self, user_id: str, **fields: str) -> dict:
        session = self.get_session(user_id)
        profile = session.setdefault("profile", {})
        for key, value in fields.items():
            if value:
                profile[key] = value
        self.save_session(user_id, session)
        return session

    def clear(self, user_id: str) -> None:
        if self._redis:
            self._redis.delete(self._session_key(user_id))
            return
        self._memory_store.pop(user_id, None)
