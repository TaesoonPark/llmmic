from __future__ import annotations

from typing import Protocol

import numpy as np

from .audio import pcm16_bytes_to_float32
from .config import Settings


class VadDetector(Protocol):
    def is_speech(self, pcm: bytes) -> bool:
        ...

    def reset(self) -> None:
        ...


class SileroVadDetector:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._model = None
        self._torch = None

    def _load_model(self) -> None:
        if self._model is not None:
            return

        import torch
        from silero_vad import load_silero_vad

        torch.set_num_threads(1)
        self._torch = torch
        self._model = load_silero_vad()

    def is_speech(self, pcm: bytes) -> bool:
        self._load_model()
        assert self._model is not None
        assert self._torch is not None

        samples = pcm16_bytes_to_float32(pcm)
        if samples.size == 0:
            return False

        tensor = self._torch.from_numpy(samples.astype(np.float32))
        with self._torch.no_grad():
            probability = float(self._model(tensor, self.settings.audio_sample_rate).item())
        return probability >= self.settings.vad_threshold

    def reset(self) -> None:
        if self._model is not None and hasattr(self._model, "reset_states"):
            self._model.reset_states()


class EnergyVadDetector:
    def __init__(self, threshold: float = 0.015) -> None:
        self.threshold = threshold

    def is_speech(self, pcm: bytes) -> bool:
        samples = pcm16_bytes_to_float32(pcm)
        if samples.size == 0:
            return False
        return float(np.sqrt(np.mean(samples * samples))) >= self.threshold

    def reset(self) -> None:
        return None
