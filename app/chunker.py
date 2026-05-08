from __future__ import annotations

import re


HARD_PUNCT_RE = re.compile(r"[.!?\u3002\uff01\uff1f\n]")
SOFT_PUNCT_RE = re.compile(r"[,;:\uff0c\u3001]")
CONNECTOR_RE = re.compile(
    r"(\uadf8\ub9ac\uace0|\ud558\uc9c0\ub9cc|\uadf8\ub798\uc11c|"
    r"\ub2e4\ub9cc|\uc989|\uc608\ub97c \ub4e4\uc5b4)\s+"
)


class KoreanTextChunker:
    def __init__(self, min_chars: int = 18, max_chars: int = 45) -> None:
        self.min_chars = min_chars
        self.max_chars = max_chars
        self._buffer = ""

    def push(self, text: str) -> list[str]:
        self._buffer += text
        chunks: list[str] = []

        while True:
            chunk = self._next_chunk()
            if chunk is None:
                break
            chunks.append(chunk)

        return chunks

    def flush(self) -> str | None:
        text = self._buffer.strip()
        self._buffer = ""
        return text or None

    def _next_chunk(self) -> str | None:
        buffer = self._buffer
        stripped = buffer.strip()
        if len(stripped) < self.min_chars:
            return None

        if len(stripped) >= self.max_chars:
            window = buffer[: self.max_chars]
            hard_match = HARD_PUNCT_RE.search(window)
            if hard_match:
                return self._take(hard_match.end())
            return self._take(self._soft_split_index(buffer))

        hard_match = HARD_PUNCT_RE.search(buffer)
        if hard_match:
            return self._take(hard_match.end())

        soft_match = SOFT_PUNCT_RE.search(buffer)
        if soft_match and soft_match.end() >= self.min_chars:
            return self._take(soft_match.end())

        connector_match = CONNECTOR_RE.search(buffer)
        if connector_match and connector_match.end() >= self.min_chars:
            return self._take(connector_match.end())

        return None

    def _soft_split_index(self, text: str) -> int:
        window = text[: self.max_chars]
        candidates = [
            window.rfind(mark) + 1 for mark in (" ", ",", ";", ":", "\uff0c", "\u3001")
        ]
        split_at = max(candidates)
        if split_at >= self.min_chars:
            return split_at
        return self.max_chars

    def _take(self, end: int) -> str:
        chunk = self._buffer[:end].strip()
        self._buffer = self._buffer[end:].lstrip()
        return chunk
