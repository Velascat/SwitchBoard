#!/usr/bin/env bash
# =============================================================================
# SwitchBoard — aider_smoke.sh
# One-shot connectivity smoke test using Aider as a reference client.
#
# Sends a single deterministic request through SwitchBoard via Aider's
# --message flag, verifies a response is returned, and prints the routing
# decision from the admin API.
#
# This is a non-interactive test. Use scripts/aider.sh for interactive sessions.
#
# Usage:
#   bash scripts/aider_smoke.sh
#   bash scripts/aider_smoke.sh --profile capable
#
# Prerequisites:
#   - SwitchBoard running on http://localhost:20401
#   - .venv-aider bootstrapped: bash scripts/bootstrap_aider.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

PROFILE="${PROFILE:-fast}"
SWITCHBOARD_PORT="${SWITCHBOARD_PORT:-20401}"
SWITCHBOARD_URL="http://localhost:${SWITCHBOARD_PORT}"
AIDER_BIN="${REPO_ROOT}/.venv-aider/bin/aider"
MODEL_SETTINGS_FILE="${REPO_ROOT}/config/aider/model-settings.yml"
SMOKE_MESSAGE="Reply with the single word: pong"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="$2"; shift 2 ;;
    *) shift ;;
  esac
done

echo "=== SwitchBoard Aider smoke test ==="
echo ""

# Guard: venv must exist
if [[ ! -x "${AIDER_BIN}" ]]; then
  echo "✗ .venv-aider not found. Bootstrap it:"
  echo "    bash scripts/bootstrap_aider.sh"
  exit 1
fi

# Guard: SwitchBoard must be reachable
echo "  Checking SwitchBoard health..."
if ! curl --silent --fail --max-time 3 "${SWITCHBOARD_URL}/health" > /dev/null 2>&1; then
  echo "✗ SwitchBoard unreachable at ${SWITCHBOARD_URL}"
  echo "    Start it: bash scripts/run_dev.sh"
  exit 1
fi
echo "  ✓ SwitchBoard healthy"
echo ""

export OPENAI_API_KEY="${OPENAI_API_KEY:-sk-switchboard}"
export OPENAI_API_BASE="${SWITCHBOARD_URL}/v1"

TMPDIR_SMOKE="$(mktemp -d)"
trap 'rm -rf "${TMPDIR_SMOKE}"' EXIT

echo "  Sending smoke request via Aider..."
echo "    profile : openai/${PROFILE}"
echo "    message : ${SMOKE_MESSAGE}"
echo "    endpoint: ${OPENAI_API_BASE}"
echo ""

set +e
OUTPUT=$("${AIDER_BIN}" \
  --model "openai/${PROFILE}" \
  --openai-api-base "${OPENAI_API_BASE}" \
  --openai-api-key "${OPENAI_API_KEY}" \
  --model-settings-file "${MODEL_SETTINGS_FILE}" \
  --message "${SMOKE_MESSAGE}" \
  --yes \
  --no-git \
  2>&1)
AIDER_EXIT=$?
set -e

if [[ ${AIDER_EXIT} -ne 0 ]]; then
  echo "✗ Aider exited with code ${AIDER_EXIT}"
  echo ""
  echo "${OUTPUT}"
  exit 1
fi

echo "  ✓ Aider returned successfully"
echo ""

# Show last routing decision from admin API
echo "  Last routing decision:"
DECISION=$(curl --silent --fail --max-time 5 \
  "${SWITCHBOARD_URL}/admin/decisions/recent?n=1" 2>/dev/null || echo "[]")
if command -v python3 &>/dev/null; then
  echo "${DECISION}" | python3 -c "
import json, sys
data = json.load(sys.stdin)
if data:
    d = data[0]
    print(f'    profile  : {d.get(\"profile_name\",\"?\")}')
    print(f'    model    : {d.get(\"downstream_model\",\"?\")}')
    print(f'    rule     : {d.get(\"rule_name\",\"?\")}')
    print(f'    latency  : {d.get(\"latency_ms\",\"?\")} ms')
    print(f'    status   : {d.get(\"status\",\"?\")}')
else:
    print('    (no decisions recorded yet)')
" 2>/dev/null || echo "    (could not parse decision)"
fi

echo ""
echo "=== Smoke test PASSED ==="
