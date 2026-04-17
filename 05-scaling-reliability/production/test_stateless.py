"""
Test script: chứng minh stateless agent vẫn hoạt động khi một instance bị kill.

Kịch bản:
1. Tạo session mới qua Nginx
2. Gửi vài request để tạo conversation history
3. Kill ngẫu nhiên một agent container
4. Gửi tiếp request qua load balancer
5. Verify history vẫn còn trong Redis

Chạy sau khi:
    docker compose up --scale agent=3
"""

from __future__ import annotations

import json
import os
import random
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE_URL = os.getenv("STATELESS_BASE_URL", "http://localhost")
SCRIPT_DIR = Path(__file__).resolve().parent


def post(path: str, data: dict) -> dict:
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return json.loads(resp.read())


def get(path: str) -> dict:
    with urllib.request.urlopen(f"{BASE_URL}{path}", timeout=10) as resp:
        return json.loads(resp.read())


def compose_agent_container_ids() -> list[str]:
    result = subprocess.run(
        ["docker", "compose", "ps", "-q", "agent"],
        cwd=SCRIPT_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def kill_random_agent() -> str:
    container_ids = compose_agent_container_ids()
    if len(container_ids) < 2:
        raise RuntimeError("Need at least 2 running agent containers to test failover")

    victim = random.choice(container_ids)
    subprocess.run(["docker", "stop", victim], cwd=SCRIPT_DIR, check=True)
    return victim


print("=" * 60)
print("Stateless Failover Demo")
print("=" * 60)

questions_before_kill = [
    "What is Docker?",
    "Why do we need containers?",
    "What is Kubernetes?",
]

questions_after_kill = [
    "How does load balancing work?",
    "What is Redis used for?",
]

session_id = None
instances_seen = set()

for i, question in enumerate(questions_before_kill, 1):
    result = post("/chat", {"question": question, "session_id": session_id})
    session_id = result["session_id"]
    instances_seen.add(result.get("served_by", "unknown"))
    print(f"Before kill {i}: [{result['served_by']}] {question}")

victim = kill_random_agent()
print(f"\nKilled agent container: {victim}\n")
time.sleep(3)

for i, question in enumerate(questions_after_kill, 1):
    result = post("/chat", {"question": question, "session_id": session_id})
    instances_seen.add(result.get("served_by", "unknown"))
    print(f"After kill {i}: [{result['served_by']}] {question}")

history = get(f"/chat/{session_id}/history")
user_messages = [msg for msg in history["messages"] if msg["role"] == "user"]

print("\n" + "-" * 60)
print(f"Session ID: {session_id}")
print(f"Instances seen: {instances_seen}")
print(f"History messages: {history['count']}")
print(f"User turns persisted: {len(user_messages)}")

expected_turns = len(questions_before_kill) + len(questions_after_kill)
if len(user_messages) != expected_turns:
    raise RuntimeError(
        f"Expected {expected_turns} user turns after failover, got {len(user_messages)}"
    )

print("Session history survived instance failure via Redis.")
