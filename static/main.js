const startButton = document.getElementById("startButton");
const stopButton = document.getElementById("stopButton");
const interruptButton = document.getElementById("interruptButton");
const resetButton = document.getElementById("resetButton");
const stateText = document.getElementById("stateText");
const micText = document.getElementById("micText");
const playbackText = document.getElementById("playbackText");
const healthText = document.getElementById("healthText");
const conversation = document.getElementById("conversation");
const bargeThreshold = document.getElementById("bargeThreshold");
const thresholdValue = document.getElementById("thresholdValue");
const voiceSelect = document.getElementById("voiceSelect");
const speechSpeed = document.getElementById("speechSpeed");
const speedValue = document.getElementById("speedValue");
const ttsChunkChars = document.getElementById("ttsChunkChars");
const chunkCharsValue = document.getElementById("chunkCharsValue");
const rpPrompt = document.getElementById("rpPrompt");
const applySettingsButton = document.getElementById("applySettingsButton");
const settingsStatus = document.getElementById("settingsStatus");

const AUDIO_SAMPLE_RATE = 16000;
const LOCAL_BARGE_IN_HOLD_MS = 180;
const LOCAL_BARGE_IN_COOLDOWN_MS = 1200;
const DEFAULT_BARGE_IN_RMS_THRESHOLD = 0.025;
const THRESHOLD_STORAGE_KEY = "llmmic.bargeThreshold";
const RP_PROMPT_STORAGE_KEY = "llmmic.rpPrompt";
const VOICE_STORAGE_KEY = "llmmic.voice";
const SPEED_STORAGE_KEY = "llmmic.speechSpeed";
const CHUNK_CHARS_STORAGE_KEY = "llmmic.ttsChunkChars";

let ws = null;
let mediaStream = null;
let captureContext = null;
let playbackContext = null;
let workletNode = null;
let assistantMessage = null;
let playbackCursor = 0;
let playbackSources = [];
let localBargeInMs = 0;
let localInterruptCooldownUntil = 0;
let localBargeInThreshold = DEFAULT_BARGE_IN_RMS_THRESHOLD;
let selectedVoice = "KR";
let selectedSpeed = 1.0;
let selectedChunkChars = 45;

function wsUrl() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ws/voice`;
}

function addMessage(kind, text = "") {
  const node = document.createElement("div");
  node.className = `message ${kind}`;
  node.textContent = text;
  conversation.appendChild(node);
  conversation.scrollTop = conversation.scrollHeight;
  return node;
}

function setControls(running) {
  startButton.disabled = running;
  interruptButton.disabled = !running;
  stopButton.disabled = !running;
}

function sendControl(data) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(data));
  }
}

function loadSettings() {
  const storedThresholdValue = localStorage.getItem(THRESHOLD_STORAGE_KEY);
  const storedThreshold = Number(storedThresholdValue);
  if (storedThresholdValue !== null && Number.isFinite(storedThreshold)) {
    localBargeInThreshold = clampThreshold(storedThreshold);
  }
  bargeThreshold.value = localBargeInThreshold.toFixed(3);
  thresholdValue.value = localBargeInThreshold.toFixed(3);

  const storedSpeedValue = localStorage.getItem(SPEED_STORAGE_KEY);
  const storedSpeed = Number(storedSpeedValue);
  if (storedSpeedValue !== null && Number.isFinite(storedSpeed)) {
    selectedSpeed = clampSpeed(storedSpeed);
  }
  speechSpeed.value = selectedSpeed.toFixed(2);
  speedValue.value = `${selectedSpeed.toFixed(2)}x`;

  selectedVoice = localStorage.getItem(VOICE_STORAGE_KEY) || selectedVoice;
  setVoiceOptions([selectedVoice], selectedVoice);

  const storedChunkValue = localStorage.getItem(CHUNK_CHARS_STORAGE_KEY);
  const storedChunkChars = Number(storedChunkValue);
  if (storedChunkValue !== null && Number.isFinite(storedChunkChars)) {
    selectedChunkChars = clampChunkChars(storedChunkChars);
  }
  ttsChunkChars.value = String(selectedChunkChars);
  chunkCharsValue.value = `${selectedChunkChars} chars`;

  rpPrompt.value = localStorage.getItem(RP_PROMPT_STORAGE_KEY) || "";
}

function clampThreshold(value) {
  const min = Number(bargeThreshold.min);
  const max = Number(bargeThreshold.max);
  return Math.min(max, Math.max(min, value));
}

function clampSpeed(value) {
  const min = Number(speechSpeed.min);
  const max = Number(speechSpeed.max);
  return Math.min(max, Math.max(min, value));
}

function clampChunkChars(value) {
  const min = Number(ttsChunkChars.min);
  const max = Number(ttsChunkChars.max);
  return Math.round(Math.min(max, Math.max(min, value)));
}

function setVoiceOptions(voices, selected) {
  const normalized = Array.from(new Set(voices.filter(Boolean)));
  if (!normalized.includes(selected)) {
    normalized.unshift(selected);
  }
  voiceSelect.textContent = "";
  for (const voice of normalized) {
    const option = document.createElement("option");
    option.value = voice;
    option.textContent = voice;
    voiceSelect.appendChild(option);
  }
  voiceSelect.value = selected;
  selectedVoice = selected;
}

function applySettings() {
  localBargeInThreshold = clampThreshold(Number(bargeThreshold.value));
  bargeThreshold.value = localBargeInThreshold.toFixed(3);
  thresholdValue.value = localBargeInThreshold.toFixed(3);
  selectedVoice = voiceSelect.value;
  selectedSpeed = clampSpeed(Number(speechSpeed.value));
  speechSpeed.value = selectedSpeed.toFixed(2);
  speedValue.value = `${selectedSpeed.toFixed(2)}x`;
  selectedChunkChars = clampChunkChars(Number(ttsChunkChars.value));
  ttsChunkChars.value = String(selectedChunkChars);
  chunkCharsValue.value = `${selectedChunkChars} chars`;
  localStorage.setItem(THRESHOLD_STORAGE_KEY, localBargeInThreshold.toFixed(3));
  localStorage.setItem(VOICE_STORAGE_KEY, selectedVoice);
  localStorage.setItem(SPEED_STORAGE_KEY, selectedSpeed.toFixed(2));
  localStorage.setItem(CHUNK_CHARS_STORAGE_KEY, String(selectedChunkChars));
  localStorage.setItem(RP_PROMPT_STORAGE_KEY, rpPrompt.value);

  sendControl({
    type: "config.update",
    system_prompt: rpPrompt.value,
    tts_speaker: selectedVoice,
    tts_speed: selectedSpeed,
    tts_chunk_chars: selectedChunkChars,
  });
  settingsStatus.textContent =
    ws && ws.readyState === WebSocket.OPEN ? "applying" : "saved";
}

function sendCurrentSessionConfig() {
  sendControl({
    type: "config.update",
    system_prompt: rpPrompt.value,
    tts_speaker: selectedVoice,
    tts_speed: selectedSpeed,
    tts_chunk_chars: selectedChunkChars,
  });
}

async function loadHealth() {
  try {
    const response = await fetch("/api/health");
    const health = await response.json();
    const llm = health.llm?.ok ? "LLM ready" : "LLM unavailable";
    const stt = health.stt?.installed ? "STT installed" : "STT missing";
    const vad = health.vad?.installed ? "VAD installed" : "VAD missing";
    const tts = health.tts?.native_installed
      ? "TTS native"
      : health.tts?.ready
        ? "TTS docker ready"
        : "TTS docker offline";
    speechSpeed.min = String(health.tts?.speed_min ?? 0.5);
    speechSpeed.max = String(health.tts?.speed_max ?? 2.0);
    selectedSpeed = clampSpeed(selectedSpeed);
    speechSpeed.value = selectedSpeed.toFixed(2);
    speedValue.value = `${selectedSpeed.toFixed(2)}x`;
    ttsChunkChars.min = String(health.tts?.chunk_chars_min ?? 20);
    ttsChunkChars.max = String(health.tts?.chunk_chars_max ?? 120);
    const storedChunkValue = localStorage.getItem(CHUNK_CHARS_STORAGE_KEY);
    if (storedChunkValue === null && typeof health.tts?.chunk_chars === "number") {
      selectedChunkChars = health.tts.chunk_chars;
    }
    selectedChunkChars = clampChunkChars(selectedChunkChars);
    ttsChunkChars.value = String(selectedChunkChars);
    chunkCharsValue.value = `${selectedChunkChars} chars`;
    const voices = health.tts?.voices?.length ? health.tts.voices : ["KR"];
    const defaultVoice = localStorage.getItem(VOICE_STORAGE_KEY) || health.tts?.speaker || voices[0];
    setVoiceOptions(voices, defaultVoice);
    healthText.textContent = `${llm} / ${stt} / ${vad} / ${tts}`;
  } catch (error) {
    healthText.textContent = `health check failed: ${error.message}`;
  }
}

async function startSession() {
  setControls(true);
  await ensurePlaybackContext();
  await startCapture();
  connectSocket();
}

function connectSocket() {
  ws = new WebSocket(wsUrl());
  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    ws.send(JSON.stringify({ type: "session.start" }));
    sendCurrentSessionConfig();
    micText.textContent = "open";
  };

  ws.onmessage = async (event) => {
    if (event.data instanceof ArrayBuffer) {
      await enqueueWav(event.data);
      return;
    }

    const message = JSON.parse(event.data);
    handleServerMessage(message);
  };

  ws.onclose = () => {
    stateText.textContent = "DISCONNECTED";
    micText.textContent = "closed";
    setControls(false);
  };

  ws.onerror = () => {
    addMessage("system", "WebSocket error");
  };
}

async function startCapture() {
  mediaStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
      channelCount: 1,
    },
  });

  captureContext = new AudioContext();
  await captureContext.audioWorklet.addModule("/static/pcm-worklet.js");
  const source = captureContext.createMediaStreamSource(mediaStream);
  workletNode = new AudioWorkletNode(captureContext, "pcm-downsample");
  workletNode.port.onmessage = (event) => {
    maybeInterruptFromMic(event.data);
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(event.data);
    }
  };
  source.connect(workletNode);
}

async function ensurePlaybackContext() {
  if (!playbackContext) {
    playbackContext = new AudioContext();
  }
  if (playbackContext.state !== "running") {
    await playbackContext.resume();
  }
}

async function enqueueWav(arrayBuffer) {
  await ensurePlaybackContext();
  const audioBuffer = await playbackContext.decodeAudioData(arrayBuffer.slice(0));
  const source = playbackContext.createBufferSource();
  source.buffer = audioBuffer;
  source.connect(playbackContext.destination);

  const wasIdle = playbackSources.length === 0;
  const startAt = Math.max(playbackContext.currentTime + 0.02, playbackCursor);
  source.start(startAt);
  playbackCursor = startAt + audioBuffer.duration;
  playbackSources.push(source);
  playbackText.textContent = "playing";
  if (wasIdle) {
    sendControl({ type: "playback.started" });
  }

  source.onended = () => {
    playbackSources = playbackSources.filter((item) => item !== source);
    if (playbackSources.length === 0) {
      playbackText.textContent = "idle";
      playbackCursor = playbackContext.currentTime;
      sendControl({ type: "playback.ended" });
    }
  };
}

function stopPlayback() {
  for (const source of playbackSources) {
    try {
      source.onended = null;
      source.stop();
    } catch (_error) {
      // Already stopped.
    }
  }
  playbackSources = [];
  playbackCursor = playbackContext ? playbackContext.currentTime : 0;
  playbackText.textContent = "idle";
  localBargeInMs = 0;
}

function maybeInterruptFromMic(arrayBuffer) {
  if (!isPlaybackActiveForBargeIn()) {
    localBargeInMs = 0;
    return;
  }

  const samples = new Int16Array(arrayBuffer);
  if (samples.length === 0) {
    return;
  }

  const rms = pcmRms(samples);
  const frameMs = (samples.length / AUDIO_SAMPLE_RATE) * 1000;
  if (rms >= localBargeInThreshold) {
    localBargeInMs += frameMs;
  } else {
    localBargeInMs = Math.max(0, localBargeInMs - frameMs * 2);
  }

  const now = Date.now();
  if (
    localBargeInMs >= LOCAL_BARGE_IN_HOLD_MS &&
    now >= localInterruptCooldownUntil
  ) {
    localInterruptCooldownUntil = now + LOCAL_BARGE_IN_COOLDOWN_MS;
    localBargeInMs = 0;
    sendControl({ type: "interrupt", reason: "local_barge_in" });
    stopPlayback();
  }
}

function isPlaybackActiveForBargeIn() {
  if (!ws || ws.readyState !== WebSocket.OPEN || !playbackContext) {
    return false;
  }
  if (playbackSources.length > 0) {
    return true;
  }
  return playbackCursor > playbackContext.currentTime + 0.05;
}

function pcmRms(samples) {
  let sum = 0;
  for (let i = 0; i < samples.length; i += 1) {
    const normalized = samples[i] / 32768;
    sum += normalized * normalized;
  }
  return Math.sqrt(sum / samples.length);
}

function handleServerMessage(message) {
  if (message.type === "state") {
    stateText.textContent = message.state;
    return;
  }

  if (message.type === "transcript.final") {
    addMessage("user", message.text);
    assistantMessage = addMessage("assistant", "");
    return;
  }

  if (message.type === "assistant.delta") {
    if (!assistantMessage) {
      assistantMessage = addMessage("assistant", "");
    }
    assistantMessage.textContent += message.text;
    conversation.scrollTop = conversation.scrollHeight;
    return;
  }

  if (message.type === "assistant.done") {
    assistantMessage = null;
    return;
  }

  if (message.type === "playback.stop") {
    stopPlayback();
    assistantMessage = null;
    return;
  }

  if (message.type === "session.reset") {
    conversation.textContent = "";
    assistantMessage = null;
    settingsStatus.textContent = "session reset";
    return;
  }

  if (message.type === "config.updated") {
    settingsStatus.textContent = message.system_prompt_enabled
      ? "applied"
      : "cleared";
    if (message.tts_speaker) {
      selectedVoice = message.tts_speaker;
      voiceSelect.value = selectedVoice;
    }
    if (typeof message.tts_speed === "number") {
      selectedSpeed = message.tts_speed;
      speechSpeed.value = selectedSpeed.toFixed(2);
      speedValue.value = `${selectedSpeed.toFixed(2)}x`;
    }
    if (typeof message.tts_chunk_chars === "number") {
      selectedChunkChars = message.tts_chunk_chars;
      ttsChunkChars.value = String(selectedChunkChars);
      chunkCharsValue.value = `${selectedChunkChars} chars`;
    }
    return;
  }

  if (message.type === "tts.warning") {
    addMessage("system", message.message);
    return;
  }

  if (message.type === "error") {
    addMessage("system", message.message);
  }
}

async function stopSession() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "session.stop" }));
    ws.close();
  }

  if (workletNode) {
    workletNode.disconnect();
    workletNode = null;
  }
  if (captureContext) {
    await captureContext.close();
    captureContext = null;
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
    mediaStream = null;
  }
  stopPlayback();
  micText.textContent = "closed";
  setControls(false);
}

startButton.addEventListener("click", () => {
  startSession().catch((error) => {
    addMessage("system", error.message);
    setControls(false);
  });
});

interruptButton.addEventListener("click", () => {
  sendControl({ type: "interrupt" });
  stopPlayback();
});

resetButton.addEventListener("click", () => {
  conversation.textContent = "";
  assistantMessage = null;
  stopPlayback();
  sendControl({ type: "session.reset" });
  settingsStatus.textContent =
    ws && ws.readyState === WebSocket.OPEN ? "resetting" : "reset local";
});

bargeThreshold.addEventListener("input", () => {
  localBargeInThreshold = clampThreshold(Number(bargeThreshold.value));
  thresholdValue.value = localBargeInThreshold.toFixed(3);
  localStorage.setItem(THRESHOLD_STORAGE_KEY, localBargeInThreshold.toFixed(3));
});

voiceSelect.addEventListener("change", () => {
  selectedVoice = voiceSelect.value;
  localStorage.setItem(VOICE_STORAGE_KEY, selectedVoice);
});

speechSpeed.addEventListener("input", () => {
  selectedSpeed = clampSpeed(Number(speechSpeed.value));
  speedValue.value = `${selectedSpeed.toFixed(2)}x`;
  localStorage.setItem(SPEED_STORAGE_KEY, selectedSpeed.toFixed(2));
});

ttsChunkChars.addEventListener("input", () => {
  selectedChunkChars = clampChunkChars(Number(ttsChunkChars.value));
  chunkCharsValue.value = `${selectedChunkChars} chars`;
  localStorage.setItem(CHUNK_CHARS_STORAGE_KEY, String(selectedChunkChars));
});

applySettingsButton.addEventListener("click", () => {
  applySettings();
});

stopButton.addEventListener("click", () => {
  stopSession().catch((error) => addMessage("system", error.message));
});

window.addEventListener("beforeunload", () => {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ type: "session.stop" }));
  }
});

loadSettings();
loadHealth();
