# llmmic

로컬 OpenAI-compatible LLM 서버와 브라우저 마이크를 연결하는 한국어 음성 대화 MVP입니다.

## 구성

- Browser: 마이크 캡처, WebRTC echo cancellation 요청, 오디오 재생 큐
- FastAPI: 정적 UI, health endpoint, voice WebSocket
- STT: faster-whisper
- VAD: silero-vad
- LLM: `http://172.30.1.93:8000/v1` 기본값
- TTS: MeloTTS Korean voice

## 설치

Python 3.11을 사용하세요. MeloTTS는 Windows PyPI 패키지 빌드가 깨지는 경우가 있어, 기본 앱은 native `melo` 모듈이 없으면 Docker HTTP 서비스로 자동 fallback합니다.

```powershell
cd C:\llmmic
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

## MeloTTS Docker 서비스

Windows venv에 `MeloTTS`가 설치되어 있지 않으면 앱은 `TTS_DOCKER_URL`로 합성 요청을 보냅니다.
Docker Desktop의 Linux engine이 실행 중이어야 합니다.

```powershell
docker build -t llmmic-melotts .\docker\melotts_service
docker run --rm -p 8899:8899 llmmic-melotts
```

## 실행

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 열고 마이크 권한을 허용합니다.

오른쪽 `Settings` 패널에서 barge-in threshold, TTS chunk 글자 수, RP system prompt, TTS voice, speech speed를 조정할 수 있습니다. `Voice` 목록은 기본적으로 `TTS_VOICES` 환경변수의 쉼표 구분 값을 사용합니다. Docker MeloTTS 서비스를 새 이미지로 다시 빌드하면 `/speakers` endpoint가 있을 때 해당 목록을 우선 사용합니다.

## 재사용 검증 스크립트

```powershell
python scripts/check_llm_stream.py
python scripts/smoke_tts_ko.py
python scripts/simulate_ws_session.py
pytest
```

## 동작 메모

- LLM 요청에는 `chat_template_kwargs.enable_thinking=false`를 넣습니다.
- 스트리밍 응답에서 `delta.reasoning`은 무시하고 `delta.content`만 화면과 TTS로 보냅니다.
- barge-in은 브라우저 AEC와 서버 VAD를 조합합니다. 오픈 스피커 환경의 품질은 장치와 브라우저에 따라 달라집니다.
