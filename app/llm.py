from __future__ import annotations

import asyncio
import json
from typing import Any, AsyncIterator, Iterable

import httpx

from .config import Settings


def parse_sse_content_lines(lines: Iterable[str]) -> list[str]:
    chunks: list[str] = []
    for line in lines:
        chunks.extend(parse_sse_content_line(line))
    return chunks


def parse_sse_content_line(line: str) -> list[str]:
    line = line.strip()
    if not line or line.startswith(":"):
        return []
    if line.startswith("data:"):
        line = line[5:].strip()
    if not line or line == "[DONE]":
        return []

    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return []

    chunks: list[str] = []
    for choice in payload.get("choices", []):
        delta = choice.get("delta") or {}
        content = delta.get("content")
        if content:
            chunks.append(content)
    return chunks


class OpenAICompatibleLLM:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def health(self) -> dict[str, Any]:
        url = f"{self.settings.llm_base_url}/models"
        headers = {"Authorization": f"Bearer {self.settings.llm_api_key}"}
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, headers=headers)
                response.raise_for_status()
                body = response.json()
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        models = [item.get("id") for item in body.get("data", [])]
        return {
            "ok": self.settings.llm_model in models,
            "model": self.settings.llm_model,
            "models": models,
        }

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[str]:
        url = f"{self.settings.llm_base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.llm_api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.settings.llm_model,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
            "chat_template_kwargs": {"enable_thinking": False},
        }

        timeout = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if cancel_event.is_set():
                        break
                    for chunk in parse_sse_content_line(line):
                        yield chunk
