from __future__ import annotations

import asyncio
import importlib.util
import os
import tempfile
from typing import Protocol

import httpx

from .config import Settings


class TtsProvider(Protocol):
    async def synthesize_wav(
        self,
        text: str,
        speaker: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        ...


class MeloTtsProvider:
    def __init__(self, settings: Settings) -> None:
        provider = settings.tts_provider.lower()
        if provider == "melotts_http":
            self._provider: TtsProvider = HttpMeloTtsProvider(settings)
        elif importlib.util.find_spec("melo") is not None:
            self._provider = NativeMeloTtsProvider(settings)
        else:
            self._provider = HttpMeloTtsProvider(settings)

    async def synthesize_wav(
        self,
        text: str,
        speaker: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        return await self._provider.synthesize_wav(text, speaker=speaker, speed=speed)


class HttpMeloTtsProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def synthesize_wav(
        self,
        text: str,
        speaker: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        payload = {
            "text": text,
            "language": self.settings.tts_language,
            "speaker": speaker or self.settings.tts_speaker,
            "speed": speed if speed is not None else self.settings.tts_speed,
        }
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    f"{self.settings.tts_docker_url}/tts",
                    json=payload,
                )
                response.raise_for_status()
                return response.content
        except httpx.RequestError as exc:
            raise RuntimeError(
                "MeloTTS Docker service is not reachable at "
                f"{self.settings.tts_docker_url}. Start it with: "
                "docker build -t llmmic-melotts .\\docker\\melotts_service; "
                "docker run --rm -p 8899:8899 llmmic-melotts"
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise RuntimeError(
                f"MeloTTS Docker service returned {exc.response.status_code}: "
                f"{exc.response.text}"
            ) from exc


class NativeMeloTtsProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._speaker_ids: dict[str, int] | None = None

    def _load_model(self) -> None:
        if self._model is not None:
            return

        from melo.api import TTS

        model = TTS(language=self.settings.tts_language, device=self.settings.tts_device)
        speaker_ids = model.hps.data.spk2id
        if self.settings.tts_speaker not in speaker_ids:
            available = ", ".join(sorted(speaker_ids))
            raise RuntimeError(
                f"MeloTTS speaker '{self.settings.tts_speaker}' is not available. "
                f"Available speakers: {available}"
            )

        self._model = model
        self._speaker_ids = {key: int(value) for key, value in speaker_ids.items()}

    async def synthesize_wav(
        self,
        text: str,
        speaker: str | None = None,
        speed: float | None = None,
    ) -> bytes:
        return await asyncio.to_thread(self._synthesize_sync, text, speaker, speed)

    def _synthesize_sync(
        self,
        text: str,
        speaker: str | None,
        speed: float | None,
    ) -> bytes:
        self._load_model()
        assert self._model is not None
        assert self._speaker_ids is not None

        selected_speaker = speaker or self.settings.tts_speaker
        if selected_speaker not in self._speaker_ids:
            available = ", ".join(sorted(self._speaker_ids))
            raise RuntimeError(
                f"MeloTTS speaker '{selected_speaker}' is not available. "
                f"Available speakers: {available}"
            )

        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            self._model.tts_to_file(
                text,
                self._speaker_ids[selected_speaker],
                path,
                speed=speed if speed is not None else self.settings.tts_speed,
            )
            with open(path, "rb") as wav_file:
                return wav_file.read()
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass
