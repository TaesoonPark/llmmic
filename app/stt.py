from __future__ import annotations

import asyncio
from typing import Protocol

from .audio import pcm16_bytes_to_float32
from .config import Settings


class Transcriber(Protocol):
    async def transcribe_pcm(self, pcm: bytes, sample_rate: int) -> str:
        ...


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None

    def _load_model(self):
        if self._model is None:
            from faster_whisper import WhisperModel

            self._model = WhisperModel(
                self.settings.stt_model,
                device=self.settings.stt_device,
                compute_type=self.settings.stt_compute_type,
            )
        return self._model

    async def transcribe_pcm(self, pcm: bytes, sample_rate: int) -> str:
        return await asyncio.to_thread(self._transcribe_sync, pcm, sample_rate)

    def _transcribe_sync(self, pcm: bytes, sample_rate: int) -> str:
        samples = pcm16_bytes_to_float32(pcm)
        if samples.size == 0:
            return ""

        model = self._load_model()
        segments, _ = model.transcribe(
            samples,
            language="ko",
            beam_size=5,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500},
            condition_on_previous_text=False,
        )
        return " ".join(segment.text.strip() for segment in segments).strip()
