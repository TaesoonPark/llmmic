from __future__ import annotations

import os
import tempfile
from functools import lru_cache

from fastapi import FastAPI
from fastapi.responses import Response
from pydantic import BaseModel

from melo.api import TTS


class TtsRequest(BaseModel):
    text: str
    language: str = "KR"
    speaker: str = "KR"
    speed: float = 1.0


app = FastAPI(title="MeloTTS Korean service")


@lru_cache(maxsize=8)
def load_model(language: str):
    model = TTS(language=language, device=os.environ.get("TTS_DEVICE", "cpu"))
    return model


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/speakers")
def speakers(language: str = "KR"):
    model = load_model(language)
    return {"language": language, "speakers": sorted(model.hps.data.spk2id)}


@app.post("/tts")
def tts(request: TtsRequest):
    model = load_model(request.language)
    speaker_ids = model.hps.data.spk2id
    if request.speaker not in speaker_ids:
        available = ", ".join(sorted(speaker_ids))
        return Response(
            content=f"Unknown speaker '{request.speaker}'. Available: {available}",
            status_code=400,
            media_type="text/plain",
        )

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    try:
        model.tts_to_file(
            request.text,
            int(speaker_ids[request.speaker]),
            path,
            speed=request.speed,
        )
        with open(path, "rb") as wav_file:
            return Response(content=wav_file.read(), media_type="audio/wav")
    finally:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8899)
