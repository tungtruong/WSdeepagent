#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/wsdeepagent}"

if [[ ! -d "${INSTALL_DIR}/.venv" ]]; then
  echo "[ERROR] Không tìm thấy virtualenv tại ${INSTALL_DIR}/.venv"
  echo "Hãy chạy scripts/install_arch_service.sh trước."
  exit 1
fi

echo "Cài đặt Playwright browsers (chromium)..."
"${INSTALL_DIR}/.venv/bin/playwright" install chromium

echo "Cài đặt system dependencies cho Playwright..."
"${INSTALL_DIR}/.venv/bin/playwright" install-deps chromium

echo "✅ Hoàn tất setup Playwright"
