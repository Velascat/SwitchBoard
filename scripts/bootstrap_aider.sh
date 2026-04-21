#!/usr/bin/env bash
# =============================================================================
# SwitchBoard — bootstrap_aider.sh
# Create .venv-aider and install aider-chat into it.
#
# Safe to re-run: skips install if aider binary already exists.
#
# Usage:
#   bash scripts/bootstrap_aider.sh
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV="${REPO_ROOT}/.venv-aider"
AIDER_BIN="${VENV}/bin/aider"

if [[ -x "${AIDER_BIN}" ]]; then
  echo "[bootstrap_aider] .venv-aider already exists with aider binary — nothing to do."
  echo "  ${AIDER_BIN}"
  exit 0
fi

echo "[bootstrap_aider] Creating ${VENV} ..."
python3 -m venv "${VENV}"

echo "[bootstrap_aider] Installing aider-chat ..."
"${VENV}/bin/pip" install --quiet --upgrade pip
"${VENV}/bin/pip" install --quiet aider-chat

echo ""
echo "[bootstrap_aider] Done."
echo "  Aider: ${AIDER_BIN}"
echo "  Run:   bash scripts/aider.sh"
