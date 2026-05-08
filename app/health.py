from __future__ import annotations

import importlib.util

import httpx

from .config import Settings
from .llm import OpenAICompatibleLLM


def _installed(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


async def collect_health(settings: Settings, llm: OpenAICompatibleLLM) -> dict:
    llm_health = await llm.health()
    native_melotts = _installed("melo")
    docker_ready = False
    docker_error = None
    docker_voices: list[str] | None = None
    if not native_melotts:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{settings.tts_docker_url}/health")
                docker_ready = response.status_code == 200
                speakers_response = await client.get(f"{settings.tts_docker_url}/speakers")
                if speakers_response.status_code == 200:
                    body = speakers_response.json()
                    speakers = body.get("speakers")
                    if isinstance(speakers, list):
                        docker_voices = [
                            speaker for speaker in speakers if isinstance(speaker, str)
                        ]
        except Exception as exc:
            docker_error = str(exc)

    voices = docker_voices or list(settings.tts_voices)
    if settings.tts_speaker not in voices:
        voices.insert(0, settings.tts_speaker)

    return {
        "llm": llm_health,
        "stt": {
            "provider": "faster-whisper",
            "installed": _installed("faster_whisper"),
            "model": settings.stt_model,
            "device": settings.stt_device,
        },
        "vad": {
            "provider": settings.vad_provider,
            "installed": _installed("silero_vad"),
        },
        "tts": {
            "provider": settings.tts_provider,
            "native_installed": native_melotts,
            "mode": "native" if native_melotts else "docker-http",
            "ready": native_melotts or docker_ready,
            "docker_url": settings.tts_docker_url,
            "docker_error": docker_error,
            "language": settings.tts_language,
            "speaker": settings.tts_speaker,
            "voices": voices,
            "speed": settings.tts_speed,
            "speed_min": settings.tts_speed_min,
            "speed_max": settings.tts_speed_max,
            "chunk_chars": settings.tts_chunk_chars,
            "chunk_chars_min": settings.tts_chunk_chars_min,
            "chunk_chars_max": settings.tts_chunk_chars_max,
        },
    }
