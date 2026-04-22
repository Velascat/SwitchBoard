#!/usr/bin/env bash
# Smoke test: hit each SwitchBoard endpoint and verify basic responses.
set -euo pipefail

BASE_URL="${SWITCHBOARD_URL:-http://localhost:20401}"
PASS=0
FAIL=0

_green() { printf '\033[0;32m%s\033[0m\n' "$1"; }
_red()   { printf '\033[0;31m%s\033[0m\n' "$1"; }

check() {
  local description="$1"
  local actual_status="$2"
  local expected_status="$3"
  if [ "${actual_status}" = "${expected_status}" ]; then
    _green "  PASS  ${description} [HTTP ${actual_status}]"
    PASS=$((PASS + 1))
  else
    _red   "  FAIL  ${description} [expected HTTP ${expected_status}, got HTTP ${actual_status}]"
    FAIL=$((FAIL + 1))
  fi
}

echo "SwitchBoard smoke tests → ${BASE_URL}"
echo "-------------------------------------------"

# 1. Health check
echo ""
echo "1. GET /health"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/health")
check "GET /health returns 200" "${STATUS}" "200"
echo "   Response body:"
curl -s "${BASE_URL}/health" | python3 -m json.tool 2>/dev/null || true

# 2. Route a canonical proposal
echo ""
echo "2. POST /route"
PAYLOAD='{"task_id":"smoke-1","project_id":"switchboard-smoke","task_type":"documentation","execution_mode":"goal","goal_text":"Refresh architecture wording","target":{"repo_key":"docs","clone_url":"https://example.invalid/docs.git","base_branch":"main","allowed_paths":[]},"priority":"normal","risk_level":"low","constraints":{"allowed_paths":[],"require_clean_validation":true},"validation_profile":{"profile_name":"default","commands":[]},"branch_policy":{"push_on_success":true,"open_pr":false},"labels":[]}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/route" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")
check "POST /route returns 200" "${STATUS}" "200"
echo "   Response body:"
curl -s -X POST "${BASE_URL}/route" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool 2>/dev/null || true

# 3. Route plan
echo ""
echo "3. POST /route-plan"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/route-plan" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")
check "POST /route-plan returns 200" "${STATUS}" "200"
echo "   Response body:"
curl -s -X POST "${BASE_URL}/route-plan" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool 2>/dev/null || true

# Summary
echo ""
echo "-------------------------------------------"
echo "Results: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ] && exit 0 || exit 1
