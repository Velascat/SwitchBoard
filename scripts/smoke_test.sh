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

# 2. Model list
echo ""
echo "2. GET /v1/models"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/v1/models")
check "GET /v1/models returns 200" "${STATUS}" "200"
echo "   Response body:"
curl -s "${BASE_URL}/v1/models" | python3 -m json.tool 2>/dev/null || true

# 3. Chat completion (expect 200 or 502 if 9router not running)
echo ""
echo "3. POST /v1/chat/completions"
PAYLOAD='{"model":"fast","messages":[{"role":"user","content":"Say hello."}]}'
STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}")
# 200 = success, 502 = SwitchBoard ran correctly but 9router not available
if [ "${STATUS}" = "200" ] || [ "${STATUS}" = "502" ]; then
  _green "  PASS  POST /v1/chat/completions routing reached 9router [HTTP ${STATUS}]"
  PASS=$((PASS + 1))
else
  _red   "  FAIL  POST /v1/chat/completions [expected 200 or 502, got ${STATUS}]"
  FAIL=$((FAIL + 1))
fi
echo "   Response body:"
curl -s -X POST "${BASE_URL}/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d "${PAYLOAD}" | python3 -m json.tool 2>/dev/null || true

# 4. Admin decisions
echo ""
echo "4. GET /admin/decisions/recent"
STATUS=$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/admin/decisions/recent?n=5")
check "GET /admin/decisions/recent returns 200" "${STATUS}" "200"
echo "   Response body:"
curl -s "${BASE_URL}/admin/decisions/recent?n=5" | python3 -m json.tool 2>/dev/null || true

# Summary
echo ""
echo "-------------------------------------------"
echo "Results: ${PASS} passed, ${FAIL} failed"
[ "${FAIL}" -eq 0 ] && exit 0 || exit 1
