"""Final production-ready FastAPI app for the Day 12 lab."""

from __future__ import annotations

import json
import logging
import re
import signal
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.auth import (
    authenticate_demo_user,
    create_access_token,
    verify_api_key,
    verify_bearer_token,
)
from app.config import settings
from app.conversation_store import ConversationStore
from app.cost_guard import CostGuard
from app.rate_limiter import RateLimiter
from utils.mock_llm import ask as llm_ask


logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO), format="%(message)s")
logger = logging.getLogger(__name__)

START_TIME = time.time()
INSTANCE_ID = f"agent-{uuid.uuid4().hex[:8]}"
conversation_store = ConversationStore(
    redis_url=settings.redis_url,
    ttl_seconds=settings.session_ttl_seconds,
    max_turns=settings.history_turn_limit,
)
rate_limiter = RateLimiter(
    redis_url=settings.redis_url,
    max_requests=settings.rate_limit_per_minute,
    window_seconds=settings.rate_limit_window_seconds,
)
cost_guard = CostGuard(
    redis_url=settings.redis_url,
    monthly_budget_usd=settings.monthly_budget_usd,
    global_monthly_budget_usd=settings.global_monthly_budget_usd,
)
service_state = {
    "ready": False,
    "shutting_down": False,
    "request_count": 0,
    "error_count": 0,
}

NAME_PATTERNS = [
    re.compile(r"\bmy name is (?P<name>[A-Za-z][A-Za-z '\-]{0,48})", re.IGNORECASE),
    re.compile(r"\bi am (?P<name>[A-Za-z][A-Za-z '\-]{0,48})", re.IGNORECASE),
]


def log_event(level: int, event: str, **fields: object) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "app": settings.app_name,
        "env": settings.environment,
        "instance_id": INSTANCE_ID,
        **fields,
    }
    logger.log(level, json.dumps(payload, ensure_ascii=True))


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()) * 2)


def find_name_in_text(text: str) -> str | None:
    for pattern in NAME_PATTERNS:
        match = pattern.search(text.strip())
        if match:
            return match.group("name").strip(" .,!?\t")
    return None


def previous_user_message(history: list[dict]) -> str | None:
    user_messages = [item["content"] for item in history if item.get("role") == "user"]
    if not user_messages:
        return None
    return user_messages[-1]


def answer_from_history(question: str, history: list[dict], profile: dict[str, str]) -> str | None:
    normalized = question.strip().lower()
    stored_name = profile.get("name")

    if stored_name and any(
        phrase in normalized
        for phrase in ("what is my name", "do you remember my name", "what's my name")
    ):
        return f"Your name is {stored_name}. I remembered it from this conversation."

    if any(phrase in normalized for phrase in ("what did i just say", "what was my last message")):
        last_message = previous_user_message(history)
        if last_message:
            return f"Your previous message was: '{last_message}'."
        return "This is your first message in the conversation, so there is no earlier message yet."

    if any(phrase in normalized for phrase in ("how many messages", "how many questions", "conversation summary")):
        user_turns = sum(1 for item in history if item.get("role") == "user")
        if "summary" in normalized and history:
            recent_topics = ", ".join(
                item["content"][:40].strip() for item in history[-3:] if item.get("role") == "user"
            )
            return f"You have sent {user_turns} message(s) so far. Recent topics: {recent_topics}."
        return f"You have sent {user_turns} message(s) before this one."

    return None


def generate_answer(question: str, history: list[dict], profile: dict[str, str]) -> tuple[str, str | None]:
    extracted_name = find_name_in_text(question)
    if extracted_name:
        return (
            f"Nice to meet you, {extracted_name}. I will remember your name for this session.",
            extracted_name,
        )

    contextual_answer = answer_from_history(question, history, profile)
    if contextual_answer:
        return contextual_answer, None

    base_answer = llm_ask(question)
    if history:
        recent_user_topics = [item["content"] for item in history if item.get("role") == "user"][-2:]
        if recent_user_topics:
            joined_topics = " | ".join(recent_user_topics)
            return f"{base_answer} Context from earlier messages: {joined_topics}", None
    return base_answer, None


@asynccontextmanager
async def lifespan(_: FastAPI):
    log_event(
        logging.INFO,
        "startup",
        version=settings.app_version,
        storage_backend=conversation_store.backend(),
        rate_limit_backend=rate_limiter.backend(),
        cost_backend=cost_guard.backend(),
    )
    service_state["ready"] = True
    yield
    service_state["ready"] = False
    log_event(logging.INFO, "shutdown")


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    lifespan=lifespan,
    docs_url="/docs" if settings.environment != "production" else None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "X-API-Key"],
)


@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = uuid.uuid4().hex[:12]
    request.state.request_id = request_id
    service_state["request_count"] += 1
    started_at = time.time()

    try:
        response = await call_next(request)
    except Exception:
        service_state["error_count"] += 1
        log_event(
            logging.ERROR,
            "unhandled_exception",
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )
        raise

    duration_ms = round((time.time() - started_at) * 1000, 2)
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Instance-ID"] = INSTANCE_ID
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Cache-Control"] = "no-store"

    log_event(
        logging.INFO,
        "request_completed",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "message": "Request validation failed.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    service_state["error_count"] += 1
    log_event(
        logging.ERROR,
        "internal_error",
        request_id=getattr(request.state, "request_id", None),
        path=request.url.path,
        error_type=exc.__class__.__name__,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error.",
            "request_id": getattr(request.state, "request_id", None),
        },
    )


class AskRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=100, description="Stable user identifier.")
    question: str = Field(..., min_length=1, max_length=2000, description="Question for the agent.")


class AskResponse(BaseModel):
    user_id: str
    question: str
    answer: str
    model: str
    conversation_turns: int
    storage_backend: str
    instance_id: str
    usage: dict[str, float | int | str]
    timestamp: str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=100)
    password: str = Field(..., min_length=1, max_length=100)


@app.get("/", tags=["Info"])
def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "storage_backend": conversation_store.backend(),
        "endpoints": {
            "ask": "POST /ask",
            "history": "GET /users/{user_id}/history",
            "health": "GET /health",
            "ready": "GET /ready",
            "metrics": "GET /metrics",
        },
    }


@app.post("/auth/token", tags=["Security"])
def issue_demo_token(body: LoginRequest):
    user = authenticate_demo_user(body.username, body.password)
    token = create_access_token(subject=user["username"], role=user["role"])
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_in_minutes": settings.access_token_expire_minutes,
    }


@app.get("/auth/me", tags=["Security"])
def auth_me(user: dict[str, str] = Depends(verify_bearer_token)):
    return user


@app.post("/ask", response_model=AskResponse, tags=["Agent"])
def ask_agent(
    body: AskRequest,
    response: Response,
    request: Request,
    _: str = Depends(verify_api_key),
):
    if service_state["shutting_down"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service is shutting down. Retry in a few seconds.",
        )

    if settings.environment == "production" and settings.require_redis_in_production:
        if conversation_store.backend() != "redis" or not conversation_store.is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis is required for stateless production mode.",
            )

    rate_status = rate_limiter.check(body.user_id)
    response.headers["X-RateLimit-Limit"] = str(rate_status.limit)
    response.headers["X-RateLimit-Remaining"] = str(rate_status.remaining)
    response.headers["X-RateLimit-Reset"] = str(rate_status.reset_at_epoch)
    response.headers["X-Storage-Backend"] = conversation_store.backend()

    estimated_input_tokens = estimate_tokens(body.question)
    estimated_input_cost = cost_guard.estimate_cost(estimated_input_tokens, 0)
    cost_guard.check_budget(body.user_id, estimated_cost_usd=estimated_input_cost)

    session = conversation_store.get_session(body.user_id)
    history = session.get("history", [])
    profile = session.get("profile", {})
    answer, extracted_name = generate_answer(body.question, history, profile)

    if extracted_name:
        conversation_store.update_profile(body.user_id, name=extracted_name)

    conversation_store.append_message(body.user_id, "user", body.question)
    conversation_store.append_message(body.user_id, "assistant", answer)

    output_tokens = estimate_tokens(answer)
    usage = cost_guard.record_usage(body.user_id, estimated_input_tokens, output_tokens)

    log_event(
        logging.INFO,
        "agent_response",
        request_id=getattr(request.state, "request_id", None),
        user_id=body.user_id,
        question_length=len(body.question),
        storage_backend=conversation_store.backend(),
    )

    updated_session = conversation_store.get_session(body.user_id)
    return AskResponse(
        user_id=body.user_id,
        question=body.question,
        answer=answer,
        model=settings.llm_model,
        conversation_turns=sum(1 for item in updated_session.get("history", []) if item["role"] == "user"),
        storage_backend=conversation_store.backend(),
        instance_id=INSTANCE_ID,
        usage={
            "month": usage.month,
            "requests": usage.requests,
            "cost_usd": usage.cost_usd,
            "budget_usd": usage.budget_usd,
            "budget_remaining_usd": usage.budget_remaining_usd,
            "budget_used_pct": usage.budget_used_pct,
        },
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@app.get("/users/{user_id}/history", tags=["Agent"])
def get_history(user_id: str, _: str = Depends(verify_api_key)):
    session = conversation_store.get_session(user_id)
    return {
        "user_id": user_id,
        "history": session.get("history", []),
        "profile": session.get("profile", {}),
        "storage_backend": conversation_store.backend(),
    }


@app.delete("/users/{user_id}/history", tags=["Agent"])
def clear_history(user_id: str, _: str = Depends(verify_api_key)):
    conversation_store.clear(user_id)
    return {"cleared": True, "user_id": user_id}


@app.get("/health", tags=["Operations"])
def health():
    redis_ready = conversation_store.is_ready()
    status_label = "ok"
    if settings.require_redis_in_production and settings.environment == "production" and not redis_ready:
        status_label = "degraded"

    return {
        "status": status_label,
        "app": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "total_requests": service_state["request_count"],
        "checks": {
            "redis": redis_ready,
            "conversation_store": conversation_store.backend(),
            "rate_limiter": rate_limiter.backend(),
            "cost_guard": cost_guard.backend(),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready", tags=["Operations"])
def ready():
    if not service_state["ready"] or service_state["shutting_down"]:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Service not ready.")

    if settings.environment == "production" and settings.require_redis_in_production:
        if not conversation_store.is_ready():
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Redis dependency is not ready.",
            )

    return {
        "ready": True,
        "instance_id": INSTANCE_ID,
        "storage_backend": conversation_store.backend(),
    }


@app.get("/metrics", tags=["Operations"])
def metrics(_: str = Depends(verify_api_key)):
    return {
        "instance_id": INSTANCE_ID,
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "total_requests": service_state["request_count"],
        "error_count": service_state["error_count"],
        "storage_backend": conversation_store.backend(),
        "rate_limit_backend": rate_limiter.backend(),
        "cost_backend": cost_guard.backend(),
        "monthly_budget_usd": settings.monthly_budget_usd,
        "global_monthly_budget_usd": settings.global_monthly_budget_usd,
    }


def _handle_signal(signum, _frame):
    service_state["shutting_down"] = True
    service_state["ready"] = False
    log_event(logging.INFO, "signal_received", signum=signum)


signal.signal(signal.SIGTERM, _handle_signal)
signal.signal(signal.SIGINT, _handle_signal)


if __name__ == "__main__":
    log_event(logging.INFO, "boot", host=settings.host, port=settings.port)
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        timeout_graceful_shutdown=30,
    )
