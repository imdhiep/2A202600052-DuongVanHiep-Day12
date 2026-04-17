"""Authentication helpers for API key and optional JWT admin flows."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import APIKeyHeader, HTTPAuthorizationCredentials, HTTPBearer

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
bearer_scheme = HTTPBearer(auto_error=False)


def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """Require a valid API key for protected endpoints."""
    if not api_key or api_key != settings.agent_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Include header: X-API-Key: <your-key>",
            headers={"WWW-Authenticate": "API-Key"},
        )
    return api_key


def create_access_token(subject: str, role: str = "admin") -> str:
    """Create a short-lived JWT token for optional admin endpoints."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
) -> dict[str, str]:
    """Validate a JWT bearer token and return the decoded identity."""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Include: Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret,
            algorithms=[settings.jwt_algorithm],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Request a new token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return {
        "username": str(payload["sub"]),
        "role": str(payload.get("role", "admin")),
    }


def authenticate_demo_user(username: str, password: str) -> dict[str, str]:
    """Issue admin tokens for the optional demo login flow."""
    if not settings.enable_demo_jwt_login:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="JWT demo login is disabled in this environment.",
        )

    if username != settings.demo_admin_username or password != settings.demo_admin_password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    return {"username": username, "role": "admin"}
