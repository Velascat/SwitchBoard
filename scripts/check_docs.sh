#!/usr/bin/env bash
# Verify that files referenced in docs and README exist.
# Run before publishing or after large refactors.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FAIL=0

_red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }
_green() { printf '\033[0;32m%s\033[0m\n' "$1"; }

check_file() {
  local path="$1"
  if [ -f "${REPO_ROOT}/${path}" ]; then
    _green "  OK    ${path}"
  else
    _red   "  MISS  ${path}"
    FAIL=$((FAIL + 1))
  fi
}

echo "Checking required files exist..."
echo ""

# Docs referenced from README
check_file "docs/quickstart.md"
check_file "docs/configuration.md"
check_file "docs/architecture.md"
check_file "docs/api.md"
check_file "docs/observability.md"
check_file "docs/troubleshooting.md"
check_file "docs/policies.md"
check_file "docs/profiles.md"
check_file "docs/capabilities.md"
check_file "docs/stability.md"
check_file "docs/roadmap.md"
check_file "CONTRIBUTING.md"

# Config templates
check_file ".env.example"
check_file "config/policy.yaml"
check_file "config/profiles.yaml"
check_file "config/capabilities.yaml"

# Scripts referenced in README / docs
check_file "scripts/run_dev.sh"
check_file "scripts/smoke_test.sh"
check_file "scripts/inspect.py"

# Site
check_file "docs/index.md"
check_file "mkdocs.yml"
check_file ".github/workflows/docs.yml"
check_file ".github/workflows/ci.yml"

# License
check_file "LICENSE"

echo ""
if [ "${FAIL}" -eq 0 ]; then
  _green "All ${#} referenced files present."
  exit 0
else
  _red "${FAIL} file(s) missing."
  exit 1
fi
