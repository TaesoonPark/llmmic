from __future__ import annotations

import asyncio
import wave
from io import BytesIO
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import load_settings
from app.tts import MeloTtsProvider


async def main() -> int:
    settings = load_settings()
    provider = MeloTtsProvider(settings)
    wav_bytes = await provider.synthesize_wav(
        "\uc548\ub155\ud558\uc138\uc694. \ub85c\uceec \uc74c\uc131 \ub300\ud654 \ud14c\uc2a4\ud2b8\uc785\ub2c8\ub2e4."
    )
    with wave.open(BytesIO(wav_bytes), "rb") as wav_file:
        frames = wav_file.getnframes()
        rate = wav_file.getframerate()
        duration = frames / float(rate)

    out = ROOT / "tmp" / "tts_ko_smoke.wav"
    out.parent.mkdir(exist_ok=True)
    out.write_bytes(wav_bytes)
    print(f"wrote {out} ({duration:.2f}s, {len(wav_bytes)} bytes)")
    return 0 if duration > 0.2 and len(wav_bytes) > 1000 else 1


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except RuntimeError as exc:
        print(exc)
        raise SystemExit(2)
