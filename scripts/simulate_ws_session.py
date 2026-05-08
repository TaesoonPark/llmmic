from __future__ import annotations

import asyncio
import math
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.audio import wav_bytes_from_pcm16
from app.config import Settings
from app.session import VoiceSession


class FakeSender:
    def __init__(self) -> None:
        self.json_events: list[dict] = []
        self.audio_chunks: list[bytes] = []

    async def send_json(self, data: dict) -> None:
        self.json_events.append(data)
        print("json:", data)

    async def send_bytes(self, data: bytes) -> None:
        self.audio_chunks.append(data)
        print("audio:", len(data), "bytes")


class FakeVad:
    def is_speech(self, pcm: bytes) -> bool:
        return any(abs(sample) > 1000 for sample in struct.unpack(f"<{len(pcm)//2}h", pcm))

    def reset(self) -> None:
        return None


class FakeTranscriber:
    async def transcribe_pcm(self, pcm: bytes, sample_rate: int) -> str:
        return "\ud14c\uc2a4\ud2b8 \uc9c8\ubb38\uc785\ub2c8\ub2e4"


class FakeLLM:
    async def stream_chat(self, messages, cancel_event):
        for token in [
            "\uc548\ub155\ud558\uc138\uc694. ",
            "\uc2a4\ud2b8\ub9ac\ubc0d ",
            "\uc751\ub2f5\uc785\ub2c8\ub2e4.",
        ]:
            if cancel_event.is_set():
                return
            await asyncio.sleep(0.01)
            yield token


class FakeTTS:
    async def synthesize_wav(self, text: str, speaker=None, speed=None) -> bytes:
        pcm = b"\x00\x10" * 1600
        return wav_bytes_from_pcm16(pcm, sample_rate=16000)


def sine_frame(samples: int = 512, rate: int = 16000) -> bytes:
    values = [
        int(12000 * math.sin(2 * math.pi * 440 * (i / rate))) for i in range(samples)
    ]
    return struct.pack(f"<{len(values)}h", *values)


def silence_frame(samples: int = 512) -> bytes:
    return b"\x00\x00" * samples


async def main() -> int:
    settings = Settings(
        vad_end_silence_ms=96,
        vad_min_speech_ms=64,
        vad_barge_in_ms=64,
    )
    sender = FakeSender()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=FakeTTS(),
    )

    await session.start()
    for _ in range(4):
        await session.handle_audio_frame(sine_frame())
    for _ in range(4):
        await session.handle_audio_frame(silence_frame())

    if session.processing_task:
        await session.processing_task

    ok = any(event.get("type") == "transcript.final" for event in sender.json_events)
    ok = ok and any(event.get("type") == "assistant.done" for event in sender.json_events)
    ok = ok and bool(sender.audio_chunks)
    print("ok:", ok)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
