from __future__ import annotations

import io
import wave

import numpy as np


def pcm16_bytes_to_float32(pcm: bytes) -> np.ndarray:
    if not pcm:
        return np.array([], dtype=np.float32)
    samples = np.frombuffer(pcm, dtype=np.int16)
    return samples.astype(np.float32) / 32768.0


def frame_duration_ms(pcm: bytes, sample_rate: int) -> float:
    if sample_rate <= 0:
        return 0.0
    sample_count = len(pcm) // 2
    return (sample_count / sample_rate) * 1000.0


def wav_bytes_from_pcm16(pcm: bytes, sample_rate: int = 16000, channels: int = 1) -> bytes:
    output = io.BytesIO()
    with wave.open(output, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm)
    return output.getvalue()


def wav_bytes_from_float32(samples: np.ndarray, sample_rate: int = 24000) -> bytes:
    clipped = np.clip(samples, -1.0, 1.0)
    pcm = (clipped * 32767.0).astype(np.int16).tobytes()
    return wav_bytes_from_pcm16(pcm, sample_rate=sample_rate)
