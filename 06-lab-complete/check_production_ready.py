"""Lightweight production-readiness checks for the final lab deliverable."""

from __future__ import annotations

import sys
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
APP_DIR = BASE_DIR / "app"
REPO_ROOT = BASE_DIR.parent


def check(name: str, condition: bool, detail: str = "") -> bool:
    icon = "[PASS]" if condition else "[FAIL]"
    suffix = f" - {detail}" if detail else ""
    print(f"{icon} {name}{suffix}")
    return condition


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    results: list[bool] = []

    print("=" * 60)
    print("Day 12 Final Project - Production Readiness Check")
    print("=" * 60)

    required_files = [
        BASE_DIR / "Dockerfile",
        BASE_DIR / "docker-compose.yml",
        BASE_DIR / ".dockerignore",
        BASE_DIR / ".env.example",
        BASE_DIR / "requirements.txt",
        BASE_DIR / "railway.toml",
        BASE_DIR / "render.yaml",
        APP_DIR / "main.py",
        APP_DIR / "config.py",
        APP_DIR / "auth.py",
        APP_DIR / "rate_limiter.py",
        APP_DIR / "cost_guard.py",
        APP_DIR / "conversation_store.py",
        BASE_DIR / "utils" / "mock_llm.py",
        REPO_ROOT / "MISSION_ANSWERS.md",
        REPO_ROOT / "DEPLOYMENT.md",
    ]

    print("\nFiles")
    for file_path in required_files:
        results.append(check(f"{file_path.relative_to(REPO_ROOT)} exists", file_path.exists()))

    print("\nSecurity")
    gitignore_text = read_text(REPO_ROOT / ".gitignore")
    results.append(check(".env is ignored", ".env" in gitignore_text))

    main_text = read_text(APP_DIR / "main.py")
    config_text = read_text(APP_DIR / "config.py")
    auth_text = read_text(APP_DIR / "auth.py")
    limiter_text = read_text(APP_DIR / "rate_limiter.py")
    cost_text = read_text(APP_DIR / "cost_guard.py")
    store_text = read_text(APP_DIR / "conversation_store.py")
    docker_text = read_text(BASE_DIR / "Dockerfile")
    compose_text = read_text(BASE_DIR / "docker-compose.yml")

    results.append(check("No hardcoded secret keys", "sk-" not in main_text and "sk-" not in config_text))
    results.append(check("API key auth implemented", "verify_api_key" in auth_text))
    results.append(check("Rate limiting implemented", "HTTP_429_TOO_MANY_REQUESTS" in limiter_text))
    results.append(check("Cost guard implemented", "Monthly budget exceeded" in cost_text))

    print("\nArchitecture")
    results.append(check("Conversation history support", "user_id" in main_text and "history" in store_text))
    results.append(check("Redis-backed stateless storage", "redis" in store_text.lower()))
    results.append(check("Health endpoint defined", '"/health"' in main_text))
    results.append(check("Readiness endpoint defined", '"/ready"' in main_text))
    results.append(check("Graceful shutdown handled", "SIGTERM" in main_text))
    results.append(check("Structured logging present", "json.dumps" in main_text))

    print("\nDocker")
    results.append(check("Dockerfile is multi-stage", "AS builder" in docker_text and "AS runtime" in docker_text))
    results.append(check("Dockerfile uses slim image", "python:3.11-slim" in docker_text))
    results.append(check("Dockerfile runs as non-root user", "USER agent" in docker_text))
    results.append(check("Docker healthcheck configured", "HEALTHCHECK" in docker_text))
    results.append(check("Compose includes redis", "redis:" in compose_text))
    results.append(check("Compose includes nginx", "nginx:" in compose_text))

    passed = sum(results)
    total = len(results)
    print("\n" + "=" * 60)
    print(f"Passed {passed}/{total} checks")
    print("=" * 60)
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
