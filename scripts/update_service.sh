#!/usr/bin/env bash
set -euo pipefail

INSTALL_DIR="${INSTALL_DIR:-/opt/wsdeepagent}"
SERVICE_NAME="${SERVICE_NAME:-wsdeepagent}"
BOT_USER="${BOT_USER:-${SUDO_USER:-$USER}}"

if [[ "${EUID}" -eq 0 ]]; then
  echo "[ERROR] Khong chay script bang root. Hay chay bang user thuong (script se tu dung sudo)."
  exit 1
fi

if [[ ! -d "${INSTALL_DIR}/.git" ]]; then
  echo "[ERROR] Khong tim thay git repo tai ${INSTALL_DIR}."
  echo "Hay chay scripts/install_arch_service.sh truoc."
  exit 1
fi

echo "[1/5] Pull code moi nhat..."
git -C "${INSTALL_DIR}" fetch origin
git -C "${INSTALL_DIR}" checkout main
git -C "${INSTALL_DIR}" pull --ff-only origin main

echo "[2/5] Dam bao virtualenv ton tai..."
if [[ ! -x "${INSTALL_DIR}/.venv/bin/python" ]]; then
  python -m venv "${INSTALL_DIR}/.venv"
fi

echo "[3/5] Cap nhat dependencies..."
"${INSTALL_DIR}/.venv/bin/python" -m pip install -U pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[4/5] Sua owner thu muc neu can..."
sudo chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}"

echo "[5/5] Restart service..."
sudo systemctl restart "${SERVICE_NAME}.service"
sudo systemctl status "${SERVICE_NAME}.service" --no-pager

echo "Hoan tat. Xem log realtime bang lenh:"
echo "journalctl -u ${SERVICE_NAME}.service -f"
