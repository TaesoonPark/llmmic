from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from typing import Protocol

from .audio import frame_duration_ms
from .chunker import KoreanTextChunker
from .config import Settings
from .llm import OpenAICompatibleLLM
from .stt import Transcriber
from .text_sanitize import sanitize_for_tts
from .tts import TtsProvider
from .vad import VadDetector


BARGE_IN_PREROLL_MAX_MS = 1200


class Sender(Protocol):
    async def send_json(self, data: dict) -> None:
        ...

    async def send_bytes(self, data: bytes) -> None:
        ...


class VoiceSession:
    def __init__(
        self,
        settings: Settings,
        sender: Sender,
        transcriber: Transcriber,
        vad: VadDetector,
        llm: OpenAICompatibleLLM,
        tts: TtsProvider,
    ) -> None:
        self.settings = settings
        self.sender = sender
        self.transcriber = transcriber
        self.vad = vad
        self.llm = llm
        self.tts = tts

        self.running = False
        self.state = "IDLE"
        self.history: list[dict[str, str]] = []
        self.system_prompt = ""
        self.tts_speaker = settings.tts_speaker
        self.tts_speed = settings.tts_speed
        self.tts_chunk_chars = settings.tts_chunk_chars
        self.audio_buffer = bytearray()
        self.utterance_started = False
        self.speech_ms = 0.0
        self.silence_ms = 0.0
        self.barge_speech_ms = 0.0
        self.barge_audio_buffer = bytearray()
        self.barge_buffer_ms = 0.0
        self.client_playback_active = False
        self.processing_task: asyncio.Task | None = None
        self.cancel_event: asyncio.Event | None = None

    async def handle_control(self, data: dict) -> None:
        message_type = data.get("type")
        if message_type == "session.start":
            await self.start()
        elif message_type == "session.stop":
            await self.stop()
        elif message_type == "session.reset":
            await self.reset_conversation()
        elif message_type == "interrupt":
            reason = data.get("reason")
            await self.interrupt(reason if isinstance(reason, str) else "client")
        elif message_type == "playback.started":
            await self.mark_playback_started()
        elif message_type == "playback.ended":
            await self.mark_playback_ended()
        elif message_type == "config.update":
            await self.update_config(data)

    async def start(self) -> None:
        self.running = True
        self.client_playback_active = False
        self.reset_capture()
        self.reset_barge_candidate()
        self.vad.reset()
        await self._set_state("LISTENING")

    async def stop(self) -> None:
        self.running = False
        await self.interrupt("stop")
        await self._set_state("IDLE")

    async def reset_conversation(self) -> None:
        self.history.clear()
        await self.interrupt("reset")
        await self.sender.send_json({"type": "session.reset"})

    async def handle_audio_frame(self, pcm: bytes) -> None:
        if not self.running or not pcm:
            return

        speech = self.vad.is_speech(pcm)
        duration_ms = frame_duration_ms(pcm, self.settings.audio_sample_rate)

        if self.state in {"GENERATING", "SPEAKING"}:
            await self._handle_barge_in_candidate(pcm, speech, duration_ms)
            return

        if self.state != "LISTENING":
            return

        await self._capture_listening_frame(pcm, speech, duration_ms)

    async def interrupt(self, reason: str) -> None:
        preserve_barge_audio = reason in {"barge_in", "local_barge_in"}
        pre_roll = bytes(self.barge_audio_buffer) if preserve_barge_audio else b""
        pre_roll_ms = self.barge_buffer_ms if preserve_barge_audio else 0.0

        if self.cancel_event is not None:
            self.cancel_event.set()

        if self.processing_task is not None and not self.processing_task.done():
            self.processing_task.cancel()

        self.client_playback_active = False
        self.reset_capture()
        self.reset_barge_candidate()
        if pre_roll:
            self.seed_capture(pre_roll, pre_roll_ms)

        await self.sender.send_json({"type": "playback.stop", "reason": reason})

        if self.running:
            await self._set_state("LISTENING")

    async def mark_playback_started(self) -> None:
        self.client_playback_active = True
        if self.running and self.state in {"GENERATING", "LISTENING"}:
            await self._set_state("SPEAKING")

    async def mark_playback_ended(self) -> None:
        self.client_playback_active = False
        if not self.running or self.state != "SPEAKING":
            return

        if self._is_processing_active():
            await self._set_state("GENERATING")
        else:
            await self._set_state("LISTENING")

    async def update_config(self, data: dict) -> None:
        if "system_prompt" in data:
            prompt = data.get("system_prompt")
            if not isinstance(prompt, str):
                await self.sender.send_json(
                    {
                        "type": "error",
                        "message": "system_prompt must be a string.",
                    }
                )
                return
            self.system_prompt = prompt.strip()

        if "tts_speaker" in data:
            speaker = data.get("tts_speaker")
            if not isinstance(speaker, str) or not speaker.strip():
                await self.sender.send_json(
                    {
                        "type": "error",
                        "message": "tts_speaker must be a non-empty string.",
                    }
                )
                return
            self.tts_speaker = speaker.strip()

        if "tts_speed" in data:
            try:
                speed = float(data.get("tts_speed"))
            except (TypeError, ValueError):
                await self.sender.send_json(
                    {"type": "error", "message": "tts_speed must be a number."}
                )
                return

            if (
                not math.isfinite(speed)
                or speed < self.settings.tts_speed_min
                or speed > self.settings.tts_speed_max
            ):
                await self.sender.send_json(
                    {
                        "type": "error",
                        "message": (
                            "tts_speed must be between "
                            f"{self.settings.tts_speed_min} and "
                            f"{self.settings.tts_speed_max}."
                        ),
                    }
                )
                return
            self.tts_speed = speed

        if "tts_chunk_chars" in data:
            try:
                chunk_chars = int(data.get("tts_chunk_chars"))
            except (TypeError, ValueError):
                await self.sender.send_json(
                    {"type": "error", "message": "tts_chunk_chars must be an integer."}
                )
                return

            if (
                chunk_chars < self.settings.tts_chunk_chars_min
                or chunk_chars > self.settings.tts_chunk_chars_max
            ):
                await self.sender.send_json(
                    {
                        "type": "error",
                        "message": (
                            "tts_chunk_chars must be between "
                            f"{self.settings.tts_chunk_chars_min} and "
                            f"{self.settings.tts_chunk_chars_max}."
                        ),
                    }
                )
                return
            self.tts_chunk_chars = chunk_chars

        await self.sender.send_json(
            {
                "type": "config.updated",
                "system_prompt_enabled": bool(self.system_prompt),
                "tts_speaker": self.tts_speaker,
                "tts_speed": self.tts_speed,
                "tts_chunk_chars": self.tts_chunk_chars,
            }
        )

    async def _handle_barge_in_candidate(
        self, pcm: bytes, speech: bool, duration_ms: float
    ) -> None:
        if speech:
            self.append_barge_frame(pcm)
            self.barge_speech_ms += duration_ms
        else:
            self.reset_barge_candidate()

        if self.barge_speech_ms < self.settings.vad_barge_in_ms:
            return

        await self.interrupt("barge_in")

    async def _capture_listening_frame(
        self, pcm: bytes, speech: bool, duration_ms: float
    ) -> None:
        if speech:
            if not self.utterance_started:
                self.utterance_started = True
                self.audio_buffer.clear()
                self.speech_ms = 0.0
                self.silence_ms = 0.0
            self.audio_buffer.extend(pcm)
            self.speech_ms += duration_ms
            self.silence_ms = 0.0
            if self.speech_ms >= self.settings.max_utterance_ms:
                await self._finish_utterance()
            return

        if not self.utterance_started:
            return

        self.audio_buffer.extend(pcm)
        self.silence_ms += duration_ms
        if self.silence_ms >= self.settings.vad_end_silence_ms:
            if self.speech_ms >= self.settings.vad_min_speech_ms:
                await self._finish_utterance()
            else:
                self.reset_capture()

    async def _finish_utterance(self) -> None:
        pcm = bytes(self.audio_buffer)
        self.reset_capture()
        if self.processing_task is not None and not self.processing_task.done():
            return
        self.processing_task = asyncio.create_task(self._process_utterance(pcm))

    async def _process_utterance(self, pcm: bytes) -> None:
        cancel_event = asyncio.Event()
        self.cancel_event = cancel_event
        try:
            await self._set_state("TRANSCRIBING")
            user_text = await self.transcriber.transcribe_pcm(
                pcm, self.settings.audio_sample_rate
            )
            if cancel_event.is_set():
                return
            if not user_text:
                await self._set_state("LISTENING")
                return

            await self.sender.send_json({"type": "transcript.final", "text": user_text})
            await self._set_state("GENERATING")

            messages = self._build_messages(user_text)
            assistant_text = await self._stream_answer(messages, cancel_event)
            if cancel_event.is_set():
                return

            if assistant_text.strip():
                self.history.extend(
                    [
                        {"role": "user", "content": user_text},
                        {"role": "assistant", "content": assistant_text.strip()},
                    ]
                )
                self.history = self.history[-10:]

            await self.sender.send_json(
                {"type": "assistant.done", "text": assistant_text.strip()}
            )
            await self._set_state("SPEAKING" if self.client_playback_active else "LISTENING")
        except asyncio.CancelledError:
            cancel_event.set()
            raise
        except Exception as exc:
            await self.sender.send_json({"type": "error", "message": str(exc)})
            await self._set_state("LISTENING")
        finally:
            if self.cancel_event is cancel_event:
                self.cancel_event = None

    async def _stream_answer(
        self,
        messages: list[dict[str, str]],
        cancel_event: asyncio.Event,
    ) -> str:
        min_chars = max(8, min(18, self.tts_chunk_chars // 2))
        chunker = KoreanTextChunker(min_chars=min_chars, max_chars=self.tts_chunk_chars)
        tts_queue: asyncio.Queue[str | None] = asyncio.Queue()
        tts_worker = asyncio.create_task(self._tts_worker(tts_queue, cancel_event))
        assistant_parts: list[str] = []

        try:
            async for token in self._iter_llm(messages, cancel_event):
                if cancel_event.is_set():
                    break
                assistant_parts.append(token)
                await self.sender.send_json({"type": "assistant.delta", "text": token})
                for text in chunker.push(token):
                    await self._queue_tts_text(tts_queue, text)

            final_chunk = chunker.flush()
            if final_chunk:
                await self._queue_tts_text(tts_queue, final_chunk)
            await tts_queue.put(None)
            await tts_worker
            return "".join(assistant_parts)
        finally:
            if not tts_worker.done():
                tts_worker.cancel()
                try:
                    await tts_worker
                except asyncio.CancelledError:
                    pass

    async def _iter_llm(
        self,
        messages: list[dict[str, str]],
        cancel_event: asyncio.Event,
    ) -> AsyncIterator[str]:
        async for token in self.llm.stream_chat(messages, cancel_event):
            yield token

    async def _queue_tts_text(
        self,
        queue: asyncio.Queue[str | None],
        text: str,
    ) -> None:
        sanitized = sanitize_for_tts(text)
        if sanitized:
            await queue.put(sanitized)

    async def _tts_worker(
        self,
        queue: asyncio.Queue[str | None],
        cancel_event: asyncio.Event,
    ) -> None:
        while not cancel_event.is_set():
            text = await queue.get()
            if text is None:
                return
            try:
                wav_bytes = await self.tts.synthesize_wav(
                    text,
                    speaker=self.tts_speaker,
                    speed=self.tts_speed,
                )
            except Exception as exc:
                await self.sender.send_json(
                    {
                        "type": "tts.warning",
                        "message": f"TTS skipped one chunk: {exc}",
                    }
                )
                continue
            if cancel_event.is_set():
                return
            await self._set_state("SPEAKING")
            await self.sender.send_bytes(wav_bytes)

    def _is_processing_active(self) -> bool:
        return self.processing_task is not None and not self.processing_task.done()

    def _build_messages(self, user_text: str) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        messages.extend(self.history)
        messages.append({"role": "user", "content": user_text})
        return messages

    def reset_capture(self) -> None:
        self.audio_buffer.clear()
        self.utterance_started = False
        self.speech_ms = 0.0
        self.silence_ms = 0.0

    def seed_capture(self, pcm: bytes, duration_ms: float) -> None:
        self.audio_buffer.clear()
        self.audio_buffer.extend(pcm)
        self.utterance_started = True
        self.speech_ms = duration_ms
        self.silence_ms = 0.0

    def append_barge_frame(self, pcm: bytes) -> None:
        self.barge_audio_buffer.extend(pcm)
        max_bytes = int(
            self.settings.audio_sample_rate * 2 * (BARGE_IN_PREROLL_MAX_MS / 1000)
        )
        if len(self.barge_audio_buffer) > max_bytes:
            overflow = len(self.barge_audio_buffer) - max_bytes
            if overflow % 2:
                overflow += 1
            del self.barge_audio_buffer[:overflow]
        self.barge_buffer_ms = frame_duration_ms(
            bytes(self.barge_audio_buffer),
            self.settings.audio_sample_rate,
        )

    def reset_barge_candidate(self) -> None:
        self.barge_speech_ms = 0.0
        self.barge_audio_buffer.clear()
        self.barge_buffer_ms = 0.0

    async def _set_state(self, state: str) -> None:
        self.state = state
        await self.sender.send_json({"type": "state", "state": state})
