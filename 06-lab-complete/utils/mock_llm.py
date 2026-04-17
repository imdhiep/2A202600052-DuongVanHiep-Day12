"""
LLM helper for the lab.

If OPENAI_API_KEY is available, call the real OpenAI Responses API.
Otherwise fall back to canned mock responses so the exercises still run.
"""

from __future__ import annotations

import os
import random
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

MOCK_RESPONSES = {
    "default": [
        "Day la cau tra loi tu AI agent (mock). Trong production, day se la response tu OpenAI.",
        "Agent dang hoat dong tot! (mock response) Hoi them cau hoi di nhe.",
        "Toi la AI agent duoc deploy len cloud. Cau hoi cua ban da duoc nhan.",
    ],
    "docker": ["Container la cach dong goi app de chay o moi noi. Build once, run anywhere!"],
    "deploy": ["Deployment la qua trinh dua code tu may ban len server de nguoi khac dung duoc."],
    "health": ["Agent dang hoat dong binh thuong. All systems operational."],
}

OPENAI_API_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = "gpt-4o-mini"
_ENV_LOADED = False


def _load_lab_env() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    for parent in Path(__file__).resolve().parents:
        env_path = parent / "06-lab-complete" / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            local_override = env_path.with_name(".env.local")
            if local_override.exists():
                load_dotenv(local_override, override=True)
            break

    _ENV_LOADED = True


def _openai_settings() -> tuple[str, str]:
    _load_lab_env()
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    return api_key, model


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    parts: list[str] = []
    for item in payload.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                parts.append(content["text"])

    return "\n".join(part.strip() for part in parts if part.strip()).strip()


def _ask_openai(question: str, api_key: str, model: str) -> str:
    payload = {
        "model": model,
        "input": question,
        "max_output_tokens": 300,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=30.0) as client:
        response = client.post(OPENAI_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    answer = _extract_output_text(data)
    if not answer:
        raise RuntimeError("OpenAI response did not contain text output.")
    return answer


def _ask_mock(question: str, delay: float) -> str:
    time.sleep(delay + random.uniform(0, 0.05))
    question_lower = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in question_lower:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])


def ask(question: str, delay: float = 0.1) -> str:
    api_key, model = _openai_settings()
    if api_key:
        try:
            return _ask_openai(question, api_key, model)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OpenAI API call failed: {exc}") from exc

    return _ask_mock(question, delay)


def ask_stream(question: str):
    response = ask(question)
    for word in response.split():
        time.sleep(0.05)
        yield word + " "
