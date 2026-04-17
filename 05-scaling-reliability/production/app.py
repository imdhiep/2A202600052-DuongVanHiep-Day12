"""
ADVANCED — Stateless Agent với Redis-backed sessions.

Mục tiêu:
  1. Không lưu conversation state trong memory
  2. Health/readiness phản ánh đúng tình trạng Redis
  3. Graceful shutdown: ngừng nhận request mới, chờ request đang chạy xong
  4. Hỗ trợ nhiều instances phía sau load balancer
"""

from __future__ import annotations

import json
import logging
import os
import signal
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from utils.mock_llm import ask

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

START_TIME = time.time()
INSTANCE_ID = os.getenv("INSTANCE_ID", f"instance-{uuid.uuid4().hex[:6]}")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
MAX_HISTORY_MESSAGES = 20

_redis: redis.Redis | None = None
_is_ready = False
_shutting_down = False
_in_flight_requests = 0


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    session_id: str | None = None


def _session_key(session_id: str) -> str:
    return f"session:{session_id}"


def redis_client() -> redis.Redis:
    if _redis is None:
        raise HTTPException(status_code=503, detail="Redis not connected")
    return _redis


def require_serving_ready() -> None:
    if _shutting_down:
        raise HTTPException(status_code=503, detail="Instance is shutting down")
    if not _is_ready:
        raise HTTPException(status_code=503, detail="Instance not ready")


def load_session(session_id: str) -> dict:
    raw = redis_client().get(_session_key(session_id))
    if not raw:
        return {"history": []}
    session = json.loads(raw)
    session.setdefault("history", [])
    return session


def save_session(session_id: str, session: dict) -> None:
    session["history"] = session.get("history", [])[-MAX_HISTORY_MESSAGES:]
    session["updated_at"] = datetime.now(timezone.utc).isoformat()
    redis_client().setex(
        _session_key(session_id),
        SESSION_TTL_SECONDS,
        json.dumps(session),
    )


def append_to_history(session_id: str, role: str, content: str) -> dict:
    session = load_session(session_id)
    history = session.setdefault("history", [])
    history.append(
        {
            "role": role,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
    save_session(session_id, session)
    return session


def handle_sigterm(signum, frame):
    global _shutting_down, _is_ready
    _shutting_down = True
    _is_ready = False
    logger.info("Received signal %s. Marking instance as not ready.", signum)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis, _is_ready, _shutting_down

    logger.info("Starting instance %s", INSTANCE_ID)
    logger.info("Connecting to Redis at %s", REDIS_URL)
    _redis = redis.from_url(REDIS_URL, decode_responses=True)
    _redis.ping()
    _shutting_down = False
    _is_ready = True
    logger.info("Instance %s is ready", INSTANCE_ID)

    try:
        yield
    finally:
        _shutting_down = True
        _is_ready = False
        wait_seconds = 0
        timeout_seconds = 30
        while _in_flight_requests > 0 and wait_seconds < timeout_seconds:
            logger.info("Waiting for %s in-flight requests...", _in_flight_requests)
            time.sleep(1)
            wait_seconds += 1
        if _redis is not None:
            _redis.close()
        logger.info("Instance %s shutdown complete", INSTANCE_ID)


signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigterm)

app = FastAPI(
    title="Stateless Agent",
    version="4.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def track_requests(request: Request, call_next):
    global _in_flight_requests

    if _shutting_down and request.url.path not in {"/health", "/ready"}:
        return JSONResponse(
            status_code=503,
            content={"detail": "Instance is shutting down"},
        )

    _in_flight_requests += 1
    try:
        response = await call_next(request)
        return response
    finally:
        _in_flight_requests -= 1


@app.get("/")
def root():
    return {
        "message": "Stateless agent is running",
        "instance_id": INSTANCE_ID,
    }


@app.post("/chat")
async def chat(body: ChatRequest):
    require_serving_ready()

    session_id = body.session_id or str(uuid.uuid4())
    session = append_to_history(session_id, "user", body.question)
    user_turn = len([msg for msg in session["history"] if msg["role"] == "user"])

    answer = ask(body.question)
    append_to_history(session_id, "assistant", answer)

    return {
        "session_id": session_id,
        "question": body.question,
        "answer": answer,
        "turn": user_turn,
        "served_by": INSTANCE_ID,
        "storage": "redis",
    }


@app.get("/chat/{session_id}/history")
def get_history(session_id: str):
    require_serving_ready()
    session = load_session(session_id)
    history = session.get("history", [])
    if not history:
        raise HTTPException(404, f"Session {session_id} not found or expired")
    return {
        "session_id": session_id,
        "messages": history,
        "count": len(history),
        "served_by": INSTANCE_ID,
    }


@app.delete("/chat/{session_id}")
def delete_session(session_id: str):
    require_serving_ready()
    deleted = redis_client().delete(_session_key(session_id))
    return {"deleted": bool(deleted), "session_id": session_id}


@app.get("/health")
def health():
    redis_ok = False
    if _redis is not None:
        try:
            _redis.ping()
            redis_ok = True
        except redis.RedisError:
            redis_ok = False

    status = "ok" if redis_ok else "degraded"
    return {
        "status": status,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 1),
        "storage": "redis",
        "redis_connected": redis_ok,
        "shutting_down": _shutting_down,
    }


@app.get("/ready")
def ready():
    if _shutting_down or not _is_ready:
        raise HTTPException(status_code=503, detail="Instance not ready")
    try:
        redis_client().ping()
    except redis.RedisError as exc:
        raise HTTPException(status_code=503, detail="Redis not available") from exc
    return {
        "ready": True,
        "instance_id": INSTANCE_ID,
        "in_flight_requests": _in_flight_requests,
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    logger.info("Starting stateless agent on port %s", port)
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=port,
        timeout_graceful_shutdown=30,
    )
