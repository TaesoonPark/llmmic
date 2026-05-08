from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.llm import OpenAICompatibleLLM


async def main() -> int:
    settings = load_settings()
    llm = OpenAICompatibleLLM(settings)
    health = await llm.health()
    print("health:", health)
    if not health.get("ok"):
        return 1

    cancel_event = asyncio.Event()
    messages = [{"role": "user", "content": "\ud55c\uad6d\uc5b4\ub85c \ud55c \ubb38\uc7a5\ub9cc \uc9e7\uac8c \uc778\uc0ac\ud574\uc918."}]
    print("stream:", end=" ", flush=True)
    count = 0
    async for token in llm.stream_chat(messages, cancel_event):
        print(token, end="", flush=True)
        count += len(token)
        if count >= 80:
            cancel_event.set()
            break
    print()
    return 0 if count else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
