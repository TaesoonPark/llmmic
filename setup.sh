#!/usr/bin/env bash
set -euo pipefail

PYTHON_VERSION="3.11"
VENV_PATH=".venv"
DOCKER_IMAGE="llmmic-melotts"
DOCKER_CONTAINER="llmmic-melotts"
DOCKER_PORT="8899"
SKIP_DOCKER=0
SKIP_DOCKER_BUILD=0
SKIP_DOCKER_RUN=0
SKIP_PIP_INSTALL=0
RUN_SMOKE_TESTS=0

usage() {
  cat <<'EOF'
Usage: ./setup.sh [options]

Options:
  --python-version VERSION     Python version to prefer, default: 3.11
  --venv PATH                  Virtualenv path, default: .venv
  --docker-image NAME          MeloTTS Docker image name, default: llmmic-melotts
  --docker-container NAME      MeloTTS Docker container name, default: llmmic-melotts
  --docker-port PORT           Host port for MeloTTS, default: 8899
  --skip-docker                Skip all Docker steps
  --skip-docker-build          Skip Docker image build
  --skip-docker-run            Skip Docker container start
  --skip-pip-install           Skip Python dependency install
  --run-smoke-tests            Run reusable smoke tests and pytest
  -h, --help                   Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --python-version)
      PYTHON_VERSION="${2:?Missing value for --python-version}"
      shift 2
      ;;
    --venv)
      VENV_PATH="${2:?Missing value for --venv}"
      shift 2
      ;;
    --docker-image)
      DOCKER_IMAGE="${2:?Missing value for --docker-image}"
      shift 2
      ;;
    --docker-container)
      DOCKER_CONTAINER="${2:?Missing value for --docker-container}"
      shift 2
      ;;
    --docker-port)
      DOCKER_PORT="${2:?Missing value for --docker-port}"
      shift 2
      ;;
    --skip-docker)
      SKIP_DOCKER=1
      shift
      ;;
    --skip-docker-build)
      SKIP_DOCKER_BUILD=1
      shift
      ;;
    --skip-docker-run)
      SKIP_DOCKER_RUN=1
      shift
      ;;
    --skip-pip-install)
      SKIP_PIP_INSTALL=1
      shift
      ;;
    --run-smoke-tests)
      RUN_SMOKE_TESTS=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

SCRIPT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_ROOT"

OS_NAME="$(uname -s)"
if [[ "$OS_NAME" != "Darwin" ]]; then
  echo "setup.sh is for macOS. On Windows, run setup.ps1 from PowerShell." >&2
  exit 1
fi

step() {
  printf '\n==> %s\n' "$1"
}

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "$1 was not found." >&2
    exit 1
  fi
}

find_python() {
  if command -v "python${PYTHON_VERSION}" >/dev/null 2>&1; then
    command -v "python${PYTHON_VERSION}"
    return
  fi
  if command -v python3 >/dev/null 2>&1; then
    command -v python3
    return
  fi
  echo "Python ${PYTHON_VERSION} or python3 was not found. Install Python and try again." >&2
  exit 1
}

http_ready() {
  curl -fsS --max-time 3 "$1" >/dev/null 2>&1
}

wait_http_ready() {
  local url="$1"
  local timeout_seconds="${2:-30}"
  local deadline=$((SECONDS + timeout_seconds))

  while [[ "$SECONDS" -lt "$deadline" ]]; do
    if http_ready "$url"; then
      return 0
    fi
    sleep 1
  done
  return 1
}

PYTHON_BIN="$(find_python)"
VENV_FULL_PATH="$VENV_PATH"
if [[ "$VENV_FULL_PATH" != /* ]]; then
  VENV_FULL_PATH="$SCRIPT_ROOT/$VENV_FULL_PATH"
fi
VENV_PYTHON="$VENV_FULL_PATH/bin/python"

step "Preparing Python virtual environment"
if [[ ! -x "$VENV_PYTHON" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_FULL_PATH"
else
  echo "Using existing venv: $VENV_FULL_PATH"
fi

if [[ "$SKIP_PIP_INSTALL" -eq 0 ]]; then
  step "Installing Python dependencies"
  "$VENV_PYTHON" -m pip install --upgrade pip
  "$VENV_PYTHON" -m pip install -r "$SCRIPT_ROOT/requirements.txt"
else
  echo "Skipping pip install."
fi

if [[ ! -f "$SCRIPT_ROOT/.env" && -f "$SCRIPT_ROOT/.env.example" ]]; then
  step "Creating .env from .env.example"
  cp "$SCRIPT_ROOT/.env.example" "$SCRIPT_ROOT/.env"
fi

if [[ "$SKIP_DOCKER" -eq 0 ]]; then
  require_command docker
  require_command curl

  step "Checking Docker"
  docker info >/dev/null

  if [[ "$SKIP_DOCKER_BUILD" -eq 0 ]]; then
    step "Building MeloTTS Docker image"
    docker build -t "$DOCKER_IMAGE" "$SCRIPT_ROOT/docker/melotts_service"
  else
    echo "Skipping Docker image build."
  fi

  TTS_HEALTH_URL="http://127.0.0.1:${DOCKER_PORT}/health"
  if [[ "$SKIP_DOCKER_RUN" -eq 0 ]]; then
    step "Starting MeloTTS Docker service"
    if http_ready "$TTS_HEALTH_URL"; then
      echo "MeloTTS service is already responding at $TTS_HEALTH_URL"
    else
      EXISTING_CONTAINER="$(docker ps -a --filter "name=^/${DOCKER_CONTAINER}$" --format "{{.ID}}")"
      if [[ -n "$EXISTING_CONTAINER" ]]; then
        docker rm -f "$DOCKER_CONTAINER"
      fi

      docker run -d --name "$DOCKER_CONTAINER" -p "${DOCKER_PORT}:8899" "$DOCKER_IMAGE"

      if ! wait_http_ready "$TTS_HEALTH_URL" 30; then
        echo "MeloTTS service did not become ready at $TTS_HEALTH_URL" >&2
        exit 1
      fi
    fi
  else
    echo "Skipping Docker container start."
  fi
else
  echo "Skipping Docker setup."
fi

if [[ "$RUN_SMOKE_TESTS" -eq 1 ]]; then
  step "Running smoke tests"
  "$VENV_PYTHON" "$SCRIPT_ROOT/scripts/check_llm_stream.py"
  "$VENV_PYTHON" "$SCRIPT_ROOT/scripts/smoke_tts_ko.py"
  "$VENV_PYTHON" "$SCRIPT_ROOT/scripts/simulate_ws_session.py"
  "$VENV_PYTHON" -m pytest
fi

step "Ready"
echo "Start the app with:"
echo "./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
