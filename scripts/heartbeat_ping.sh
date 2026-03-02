#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/wsdeepagent}"
ENV_FILE="${ENV_FILE:-${INSTALL_DIR}/.env}"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "[WARN] Missing env file: ${ENV_FILE}"
  exit 0
fi

set -a
source "${ENV_FILE}"
set +a

PING_URL="${HEALTHCHECKS_PING_URL:-}"
FAIL_URL="${HEALTHCHECKS_FAIL_URL:-}"
SERVICE_NAME="${SERVICE_NAME:-wsdeepagent}"
HOST_NAME="${HOSTNAME:-unknown-host}"

if [[ -z "${PING_URL}" ]]; then
  echo "[INFO] HEALTHCHECKS_PING_URL is empty. Skip heartbeat ping."
  exit 0
fi

payload="service=${SERVICE_NAME};host=${HOST_NAME};time=$(date -u +%Y-%m-%dT%H:%M:%SZ)"

if curl -fsS -m 10 --retry 2 --retry-delay 1 --data "${payload}" "${PING_URL}" >/dev/null; then
  echo "[INFO] Heartbeat ping sent."
  exit 0
fi

echo "[WARN] Heartbeat ping failed."
if [[ -n "${FAIL_URL}" ]]; then
  curl -fsS -m 10 --retry 1 --data "${payload}" "${FAIL_URL}" >/dev/null || true
fi

exit 1
