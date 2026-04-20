#!/usr/bin/env bash
# =============================================================================
# SwitchBoard — aider.sh
# Launch Aider pointed at the local SwitchBoard instance.
#
# Usage:
#   bash scripts/aider.sh                      # default profile: fast
#   bash scripts/aider.sh --profile capable    # use capable profile
#   bash scripts/aider.sh --no-stream          # disable streaming
#   bash scripts/aider.sh -- <extra aider args>
#
# Prerequisites:
#   - SwitchBoard running on http://localhost:20401
#   - aider-chat installed: pip install aider-chat
#   - OPENAI_API_KEY set (any non-empty value works; SwitchBoard ignores it)
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

# ── Load .env if present ──────────────────────────────────────────────────────
if [[ -f "${REPO_ROOT}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${REPO_ROOT}/.env"
  set +a
fi

# ── Defaults ──────────────────────────────────────────────────────────────────
PROFILE="${PROFILE:-fast}"
SWITCHBOARD_HOST="${SWITCHBOARD_HOST:-0.0.0.0}"
SWITCHBOARD_PORT="${SWITCHBOARD_PORT:-20401}"
SWITCHBOARD_URL="http://localhost:${SWITCHBOARD_PORT}"
MODEL_SETTINGS_FILE="${REPO_ROOT}/config/aider/model-settings.yml"

EXTRA_ARGS=()
PASS_THROUGH=false

# ── Parse arguments ───────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile)
      PROFILE="$2"
      shift 2
      ;;
    --)
      PASS_THROUGH=true
      shift
      ;;
    *)
      if $PASS_THROUGH; then
        EXTRA_ARGS+=("$1")
        shift
      else
        EXTRA_ARGS+=("$1")
        shift
      fi
      ;;
  esac
done

# ── Verify SwitchBoard is reachable ───────────────────────────────────────────
echo "[aider.sh] Checking SwitchBoard health at ${SWITCHBOARD_URL}/health ..."
if ! curl --silent --fail --max-time 3 "${SWITCHBOARD_URL}/health" > /dev/null 2>&1; then
  echo ""
  echo "[aider.sh] ERROR: SwitchBoard is not reachable at ${SWITCHBOARD_URL}"
  echo "           Start it first:  bash scripts/run_dev.sh"
  exit 1
fi
echo "[aider.sh] SwitchBoard healthy."

# ── Require API key (any value) ───────────────────────────────────────────────
if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "[aider.sh] INFO: OPENAI_API_KEY not set. Using placeholder 'sk-switchboard'."
  export OPENAI_API_KEY="sk-switchboard"
fi

# ── Set OpenAI-compatible endpoint ────────────────────────────────────────────
export OPENAI_API_BASE="${SWITCHBOARD_URL}/v1"

echo ""
echo "[aider.sh] Starting Aider"
echo "  Profile : openai/${PROFILE}"
echo "  Endpoint: ${OPENAI_API_BASE}"
echo "  Settings: ${MODEL_SETTINGS_FILE}"
echo ""

exec aider \
  --model "openai/${PROFILE}" \
  --openai-api-base "${OPENAI_API_BASE}" \
  --openai-api-key "${OPENAI_API_KEY}" \
  --model-settings-file "${MODEL_SETTINGS_FILE}" \
  "${EXTRA_ARGS[@]+"${EXTRA_ARGS[@]}"}"
