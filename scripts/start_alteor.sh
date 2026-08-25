#!/bin/zsh
set -eu

cd /Users/tachibanashunta/wip/local_llm_lp

if [[ ! -x .venv/bin/uvicorn ]]; then
  echo "Backend environment is missing. Run: /opt/homebrew/bin/python3.13 -m venv .venv && .venv/bin/python -m pip install -e './backend[dev]'"
  exit 1
fi

export ALTEOR_OFFLINE_MODE=true
export ALTEOR_SEED_DEMO_DATA=true
export VITE_API_TARGET=http://127.0.0.1:8081

.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8081 &
ALTEOR_BACKEND_PID=$!

cleanup() {
  kill "$ALTEOR_BACKEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

npm run dev -- --host 127.0.0.1 --port 5174
