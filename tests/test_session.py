from __future__ import annotations

import asyncio
import math
import struct

from app.audio import wav_bytes_from_pcm16
from app.config import Settings
from app.session import VoiceSession


class FakeSender:
    def __init__(self) -> None:
        self.json_events: list[dict] = []
        self.audio_chunks: list[bytes] = []

    async def send_json(self, data: dict) -> None:
        self.json_events.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.audio_chunks.append(data)


class FakeVad:
    def __init__(self) -> None:
        self.force_speech = False

    def is_speech(self, pcm: bytes) -> bool:
        if self.force_speech:
            return True
        values = struct.unpack(f"<{len(pcm)//2}h", pcm)
        return any(abs(value) > 1000 for value in values)

    def reset(self) -> None:
        return None


class FakeTranscriber:
    def __init__(self) -> None:
        self.last_pcm_len = 0

    async def transcribe_pcm(self, pcm: bytes, sample_rate: int) -> str:
        self.last_pcm_len = len(pcm)
        return "\ud14c\uc2a4\ud2b8 \uc9c8\ubb38\uc785\ub2c8\ub2e4"


class FakeLLM:
    def __init__(self) -> None:
        self.cancel_seen = False
        self.last_messages = None

    async def stream_chat(self, messages, cancel_event):
        self.last_messages = messages
        for token in [
            "\uc548\ub155\ud558\uc138\uc694. ",
            "\uc870\uae08 \uae34 \uc751\ub2f5\uc744 ",
            "\uc2a4\ud2b8\ub9ac\ubc0d\ud569\ub2c8\ub2e4.",
        ]:
            if cancel_event.is_set():
                self.cancel_seen = True
                return
            await asyncio.sleep(0.02)
            yield token
        while not cancel_event.is_set():
            await asyncio.sleep(0.02)
        self.cancel_seen = True


class FakeTTS:
    def __init__(self) -> None:
        self.last_speaker = None
        self.last_speed = None
        self.texts: list[str] = []

    async def synthesize_wav(self, text: str, speaker=None, speed=None) -> bytes:
        self.last_speaker = speaker
        self.last_speed = speed
        self.texts.append(text)
        await asyncio.sleep(0.01)
        return wav_bytes_from_pcm16(b"\x00\x10" * 1600, sample_rate=16000)


class FailingOnceTTS(FakeTTS):
    def __init__(self) -> None:
        super().__init__()
        self.failed = False

    async def synthesize_wav(self, text: str, speaker=None, speed=None) -> bytes:
        self.texts.append(text)
        if not self.failed:
            self.failed = True
            raise RuntimeError("bad tts chunk")
        return await super().synthesize_wav(text, speaker=speaker, speed=speed)


def sine_frame(samples: int = 512, rate: int = 16000) -> bytes:
    values = [
        int(12000 * math.sin(2 * math.pi * 440 * (i / rate))) for i in range(samples)
    ]
    return struct.pack(f"<{len(values)}h", *values)


def silence_frame(samples: int = 512) -> bytes:
    return b"\x00\x00" * samples


def test_session_interrupts_generation_on_barge_in() -> None:
    asyncio.run(_run_barge_in_case())


def test_playback_events_keep_server_state_aligned() -> None:
    asyncio.run(_run_playback_state_case())


def test_config_update_adds_system_prompt_to_llm_messages() -> None:
    asyncio.run(_run_system_prompt_case())


def test_config_update_applies_tts_voice_and_speed() -> None:
    asyncio.run(_run_tts_config_case())


def test_tts_text_removes_emoji_without_changing_visible_answer() -> None:
    asyncio.run(_run_tts_sanitize_case())


def test_tts_failure_skips_chunk_without_failing_answer() -> None:
    asyncio.run(_run_tts_failure_skip_case())


def test_local_barge_in_preserves_preroll_audio() -> None:
    asyncio.run(_run_local_barge_preroll_case())


def test_server_barge_in_preserves_preroll_audio() -> None:
    asyncio.run(_run_server_barge_preroll_case())


def test_session_reset_clears_history_but_keeps_config() -> None:
    asyncio.run(_run_session_reset_case())


async def _run_barge_in_case() -> None:
    settings = Settings(
        vad_end_silence_ms=96,
        vad_min_speech_ms=64,
        vad_barge_in_ms=64,
    )
    sender = FakeSender()
    vad = FakeVad()
    llm = FakeLLM()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=vad,
        llm=llm,
        tts=FakeTTS(),
    )

    await session.start()
    for _ in range(4):
        await session.handle_audio_frame(sine_frame())
    for _ in range(4):
        await session.handle_audio_frame(silence_frame())

    await asyncio.sleep(0.05)
    vad.force_speech = True
    for _ in range(3):
        await session.handle_audio_frame(sine_frame())
    await asyncio.sleep(0)

    assert any(event.get("type") == "playback.stop" for event in sender.json_events)
    assert session.cancel_event is None or session.cancel_event.is_set()


async def _run_playback_state_case() -> None:
    settings = Settings()
    sender = FakeSender()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=FakeTTS(),
    )

    await session.start()
    await session.handle_control({"type": "playback.started"})
    assert session.state == "SPEAKING"

    await session.handle_control({"type": "playback.ended"})
    assert session.state == "LISTENING"


async def _run_system_prompt_case() -> None:
    settings = Settings(
        vad_end_silence_ms=96,
        vad_min_speech_ms=64,
    )
    sender = FakeSender()
    llm = FakeLLM()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=llm,
        tts=FakeTTS(),
    )

    await session.start()
    await session.handle_control(
        {"type": "config.update", "system_prompt": "Roleplay as a concise pilot."}
    )
    for _ in range(4):
        await session.handle_audio_frame(sine_frame())
    for _ in range(4):
        await session.handle_audio_frame(silence_frame())

    for _ in range(20):
        if llm.last_messages is not None:
            break
        await asyncio.sleep(0.01)

    if session.processing_task:
        if session.cancel_event:
            session.cancel_event.set()
        session.processing_task.cancel()
        try:
            await session.processing_task
        except asyncio.CancelledError:
            pass

    assert llm.last_messages is not None
    assert llm.last_messages[0] == {
        "role": "system",
        "content": "Roleplay as a concise pilot.",
    }


async def _run_tts_config_case() -> None:
    settings = Settings(
        vad_end_silence_ms=96,
        vad_min_speech_ms=64,
    )
    sender = FakeSender()
    llm = FakeLLM()
    tts = FakeTTS()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=llm,
        tts=tts,
    )

    await session.start()
    await session.handle_control(
        {
            "type": "config.update",
            "tts_speaker": "KR",
            "tts_speed": 1.35,
            "tts_chunk_chars": 25,
        }
    )
    for _ in range(4):
        await session.handle_audio_frame(sine_frame())
    for _ in range(4):
        await session.handle_audio_frame(silence_frame())

    for _ in range(20):
        if tts.last_speaker is not None:
            break
        await asyncio.sleep(0.01)

    if session.processing_task:
        if session.cancel_event:
            session.cancel_event.set()
        session.processing_task.cancel()
        try:
            await session.processing_task
        except asyncio.CancelledError:
            pass

    assert tts.last_speaker == "KR"
    assert tts.last_speed == 1.35
    assert session.tts_chunk_chars == 25


async def _run_tts_sanitize_case() -> None:
    settings = Settings()
    sender = FakeSender()
    tts = FakeTTS()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=tts,
    )
    cancel_event = asyncio.Event()

    async def emoji_stream(_messages, _cancel_event):
        yield "\uc548\ub155\ud558\uc138\uc694 \U0001f44b \ubc18\uac11\uc2b5\ub2c8\ub2e4!"

    session.llm.stream_chat = emoji_stream

    answer = await session._stream_answer(
        [{"role": "user", "content": "hello"}],
        cancel_event,
    )

    assert "\U0001f44b" in answer
    assert tts.texts == ["\uc548\ub155\ud558\uc138\uc694 \ubc18\uac11\uc2b5\ub2c8\ub2e4!"]


async def _run_tts_failure_skip_case() -> None:
    settings = Settings(tts_chunk_chars=20)
    sender = FakeSender()
    tts = FailingOnceTTS()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=tts,
    )
    cancel_event = asyncio.Event()

    async def two_chunk_stream(_messages, _cancel_event):
        yield "\uccab \ubb38\uc7a5\uc785\ub2c8\ub2e4. "
        yield "\ub458\uc9f8 \ubb38\uc7a5\uc785\ub2c8\ub2e4."

    session.llm.stream_chat = two_chunk_stream

    answer = await session._stream_answer(
        [{"role": "user", "content": "hello"}],
        cancel_event,
    )

    assert "\uccab \ubb38\uc7a5" in answer
    assert any(event.get("type") == "tts.warning" for event in sender.json_events)
    assert sender.audio_chunks


async def _run_local_barge_preroll_case() -> None:
    settings = Settings(vad_barge_in_ms=400)
    sender = FakeSender()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=FakeTTS(),
    )
    frame = sine_frame()

    await session.start()
    await session.handle_control({"type": "playback.started"})
    await session.handle_audio_frame(frame)
    await session.handle_audio_frame(frame)
    assert not session.utterance_started

    await session.handle_control({"type": "interrupt", "reason": "local_barge_in"})

    assert session.state == "LISTENING"
    assert session.utterance_started
    assert len(session.audio_buffer) >= len(frame) * 2


async def _run_server_barge_preroll_case() -> None:
    settings = Settings(vad_barge_in_ms=64)
    sender = FakeSender()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=FakeTTS(),
    )
    frame = sine_frame()

    await session.start()
    await session.handle_control({"type": "playback.started"})
    await session.handle_audio_frame(frame)
    await session.handle_audio_frame(frame)

    assert session.state == "LISTENING"
    assert session.utterance_started
    assert len(session.audio_buffer) >= len(frame) * 2


async def _run_session_reset_case() -> None:
    settings = Settings()
    sender = FakeSender()
    session = VoiceSession(
        settings=settings,
        sender=sender,
        transcriber=FakeTranscriber(),
        vad=FakeVad(),
        llm=FakeLLM(),
        tts=FakeTTS(),
    )
    session.history = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "old answer"},
    ]

    await session.start()
    await session.handle_control(
        {
            "type": "config.update",
            "system_prompt": "Keep this RP.",
            "tts_speaker": "KR",
            "tts_speed": 1.25,
            "tts_chunk_chars": 30,
        }
    )
    await session.handle_control({"type": "session.reset"})

    assert session.history == []
    assert session.system_prompt == "Keep this RP."
    assert session.tts_speaker == "KR"
    assert session.tts_speed == 1.25
    assert session.tts_chunk_chars == 30
    assert any(event.get("type") == "session.reset" for event in sender.json_events)
