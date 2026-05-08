#!/usr/bin/env bash
set -euo pipefail

APP_HOST="127.0.0.1"
PORT="8000"
RELOAD=0
EXTRA_ARGS=()

usage() {
  cat <<'EOF'
Usage: ./run.sh [options] [-- extra uvicorn args]

Options:
  --host HOST    Host to bind, default: 127.0.0.1
  --port PORT    Port to bind, default: 8000
  --reload       Enable uvicorn reload
  -h, --help     Show this help

Examples:
  ./run.sh
  ./run.sh --port 8010 --reload
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      APP_HOST="${2:?Missing value for --host}"
      shift 2
      ;;
    --port)
      PORT="${2:?Missing value for --port}"
      shift 2
      ;;
    --reload)
      RELOAD=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_ARGS=("$@")
      break
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
  echo "run.sh is for macOS. On Windows, run run.ps1 from PowerShell." >&2
  exit 1
fi

VENV_PYTHON="$SCRIPT_ROOT/.venv/bin/python"
if [[ ! -x "$VENV_PYTHON" ]]; then
  echo "Virtualenv was not found. Run ./setup.sh first." >&2
  exit 1
fi

UVICORN_ARGS=(-m uvicorn app.main:app --host "$APP_HOST" --port "$PORT")
if [[ "$RELOAD" -eq 1 ]]; then
  UVICORN_ARGS+=(--reload)
fi

echo "Starting llmmic at http://${APP_HOST}:${PORT}"
exec "$VENV_PYTHON" "${UVICORN_ARGS[@]}" "${EXTRA_ARGS[@]}"
