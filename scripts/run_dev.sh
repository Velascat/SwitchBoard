#!/usr/bin/env bash
# Run SwitchBoard in development mode with auto-reload.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

cd "${REPO_ROOT}"

# Load .env if present
if [ -f .env ]; then
  echo "[run_dev] Loading .env"
  set -o allexport
  # shellcheck disable=SC1091
  source .env
  set +o allexport
fi

PORT="${SWITCHBOARD_PORT:-20401}"
LOG_LEVEL="${LOG_LEVEL:-info}"

echo "[run_dev] Starting SwitchBoard on port ${PORT} (reload enabled)"
exec uvicorn switchboard.app:app \
  --reload \
  --host 0.0.0.0 \
  --port "${PORT}" \
  --log-level "${LOG_LEVEL}"
