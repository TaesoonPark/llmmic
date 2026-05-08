from __future__ import annotations

import json
import mimetypes
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import Settings, load_settings
from .health import collect_health
from .llm import OpenAICompatibleLLM
from .session import VoiceSession
from .stt import FasterWhisperTranscriber
from .tts import MeloTtsProvider
from .vad import EnergyVadDetector, SileroVadDetector


ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = ROOT / "static"


class LockedWebSocketSender:
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket
        self._send_lock = None

    @property
    def send_lock(self):
        import asyncio

        if self._send_lock is None:
            self._send_lock = asyncio.Lock()
        return self._send_lock

    async def send_json(self, data: dict) -> None:
        async with self.send_lock:
            await self.websocket.send_json(data)

    async def send_bytes(self, data: bytes) -> None:
        async with self.send_lock:
            await self.websocket.send_bytes(data)


def _make_vad(settings: Settings):
    if settings.vad_provider.lower() == "energy":
        return EnergyVadDetector()
    return SileroVadDetector(settings)


def create_app() -> FastAPI:
    mimetypes.add_type("text/javascript", ".js")
    mimetypes.add_type("text/css", ".css")

    settings = load_settings()
    app = FastAPI(title="llmmic", version="0.1.0")

    llm = OpenAICompatibleLLM(settings)
    transcriber = FasterWhisperTranscriber(settings)
    tts = MeloTtsProvider(settings)

    app.state.settings = settings
    app.state.llm = llm
    app.state.transcriber = transcriber
    app.state.tts = tts

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/")
    async def index():
        return FileResponse(STATIC_DIR / "index.html")

    @app.get("/api/health")
    async def health():
        return await collect_health(settings, llm)

    @app.websocket("/ws/voice")
    async def voice_socket(websocket: WebSocket):
        await websocket.accept()
        sender = LockedWebSocketSender(websocket)
        session = VoiceSession(
            settings=settings,
            sender=sender,
            transcriber=transcriber,
            vad=_make_vad(settings),
            llm=llm,
            tts=tts,
        )
        await sender.send_json({"type": "state", "state": "IDLE"})

        try:
            while True:
                message = await websocket.receive()
                if "bytes" in message and message["bytes"] is not None:
                    await session.handle_audio_frame(message["bytes"])
                elif "text" in message and message["text"] is not None:
                    await session.handle_control(json.loads(message["text"]))
                elif message.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        finally:
            await session.stop()

    return app


app = create_app()
