"""Mock LLM used by the final lab project so it can run without a real API key."""

from __future__ import annotations

import random
import time


MOCK_RESPONSES = {
    "default": [
        "This is a mock response from the AI agent. In production, this would come from a real LLM provider.",
        "The agent is working correctly in mock mode. Ask another question to continue the demo.",
        "Your request was received successfully by the deployed AI agent.",
    ],
    "docker": [
        "Docker packages the application and its dependencies so it can run consistently across environments."
    ],
    "deploy": [
        "Deployment is the process of moving code from your machine to a server where other users can access it."
    ],
    "health": [
        "The service is healthy and responding normally."
    ],
}


def ask(question: str, delay: float = 0.1) -> str:
    time.sleep(delay + random.uniform(0, 0.05))
    lowered = question.lower()
    for keyword, responses in MOCK_RESPONSES.items():
        if keyword in lowered:
            return random.choice(responses)
    return random.choice(MOCK_RESPONSES["default"])


def ask_stream(question: str):
    response = ask(question)
    for word in response.split():
        time.sleep(0.05)
        yield word + " "
