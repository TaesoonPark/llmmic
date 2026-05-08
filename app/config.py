from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, str(default)))
    except ValueError:
        return default


def _env_csv(name: str, default: tuple[str, ...]) -> tuple[str, ...]:
    raw = os.environ.get(name)
    if raw is None:
        return default
    values = tuple(value.strip() for value in raw.split(",") if value.strip())
    return values or default


@dataclass(frozen=True)
class Settings:
    llm_base_url: str = "http://172.30.1.93:8000/v1"
    llm_model: str = "qwen36-35b-a3b"
    llm_api_key: str = "local"

    stt_model: str = "medium"
    stt_device: str = "cpu"
    stt_compute_type: str = "int8"

    vad_provider: str = "silero"
    vad_threshold: float = 0.55
    vad_barge_in_ms: int = 400
    vad_end_silence_ms: int = 700
    vad_min_speech_ms: int = 250

    tts_provider: str = "melotts"
    tts_language: str = "KR"
    tts_speaker: str = "KR"
    tts_voices: tuple[str, ...] = ("KR",)
    tts_device: str = "cpu"
    tts_speed: float = 1.0
    tts_speed_min: float = 0.5
    tts_speed_max: float = 2.0
    tts_chunk_chars: int = 45
    tts_chunk_chars_min: int = 20
    tts_chunk_chars_max: int = 120
    tts_docker_url: str = "http://127.0.0.1:8899"

    audio_sample_rate: int = 16000
    max_utterance_ms: int = 30000


def load_settings() -> Settings:
    _load_dotenv(Path.cwd() / ".env")
    return Settings(
        llm_base_url=_env("LLM_BASE_URL", Settings.llm_base_url).rstrip("/"),
        llm_model=_env("LLM_MODEL", Settings.llm_model),
        llm_api_key=_env("LLM_API_KEY", Settings.llm_api_key),
        stt_model=_env("STT_MODEL", Settings.stt_model),
        stt_device=_env("STT_DEVICE", Settings.stt_device),
        stt_compute_type=_env("STT_COMPUTE_TYPE", Settings.stt_compute_type),
        vad_provider=_env("VAD_PROVIDER", Settings.vad_provider),
        vad_threshold=_env_float("VAD_THRESHOLD", Settings.vad_threshold),
        vad_barge_in_ms=_env_int("VAD_BARGE_IN_MS", Settings.vad_barge_in_ms),
        vad_end_silence_ms=_env_int("VAD_END_SILENCE_MS", Settings.vad_end_silence_ms),
        vad_min_speech_ms=_env_int("VAD_MIN_SPEECH_MS", Settings.vad_min_speech_ms),
        tts_provider=_env("TTS_PROVIDER", Settings.tts_provider),
        tts_language=_env("TTS_LANGUAGE", Settings.tts_language),
        tts_speaker=_env("TTS_SPEAKER", Settings.tts_speaker),
        tts_voices=_env_csv("TTS_VOICES", Settings.tts_voices),
        tts_device=_env("TTS_DEVICE", Settings.tts_device),
        tts_speed=_env_float("TTS_SPEED", Settings.tts_speed),
        tts_speed_min=_env_float("TTS_SPEED_MIN", Settings.tts_speed_min),
        tts_speed_max=_env_float("TTS_SPEED_MAX", Settings.tts_speed_max),
        tts_chunk_chars=_env_int("TTS_CHUNK_CHARS", Settings.tts_chunk_chars),
        tts_chunk_chars_min=_env_int(
            "TTS_CHUNK_CHARS_MIN", Settings.tts_chunk_chars_min
        ),
        tts_chunk_chars_max=_env_int(
            "TTS_CHUNK_CHARS_MAX", Settings.tts_chunk_chars_max
        ),
        tts_docker_url=_env("TTS_DOCKER_URL", Settings.tts_docker_url).rstrip("/"),
    )
