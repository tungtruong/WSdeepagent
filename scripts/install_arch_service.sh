#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/tungtruong/WSdeepagent.git}"
INSTALL_DIR="${INSTALL_DIR:-/opt/wsdeepagent}"
SERVICE_NAME="${SERVICE_NAME:-wsdeepagent}"
BOT_USER="${BOT_USER:-${SUDO_USER:-$USER}}"

sync_env_missing() {
  local env_file="$1"
  local example_file="$2"

  if [[ ! -f "${env_file}" ]]; then
    cp "${example_file}" "${env_file}"
    echo "[WARN] Khong tim thay .env, da tao moi tu .env.example"
    return
  fi

  local added_count=0
  while IFS= read -r line || [[ -n "${line}" ]]; do
    [[ -z "${line}" ]] && continue
    [[ "${line}" =~ ^[[:space:]]*# ]] && continue
    [[ "${line}" != *=* ]] && continue

    local key="${line%%=*}"
    if ! grep -qE "^${key}=" "${env_file}"; then
      echo "${line}" >> "${env_file}"
      added_count=$((added_count + 1))
    fi
  done < "${example_file}"

  if (( added_count > 0 )); then
    echo "[INFO] Da bo sung ${added_count} bien moi vao .env (giu nguyen gia tri cu)."
  fi
}

if [[ "${EUID}" -eq 0 ]]; then
  echo "[ERROR] Khong chay script bang root. Hay chay bang user thuong (script se tu dung sudo)."
  exit 1
fi

if ! command -v sudo >/dev/null 2>&1; then
  echo "[ERROR] Khong tim thay sudo."
  exit 1
fi

echo "[1/8] Cai package he thong can thiet..."
sudo pacman -Syu --noconfirm --needed git python

echo "[2/8] Tao thu muc cai dat: ${INSTALL_DIR}"
sudo install -d -m 755 "${INSTALL_DIR}"
sudo chown -R "${BOT_USER}:${BOT_USER}" "${INSTALL_DIR}"

echo "[3/8] Clone/Update project..."
if [[ -d "${INSTALL_DIR}/.git" ]]; then
  git -C "${INSTALL_DIR}" fetch origin
  git -C "${INSTALL_DIR}" checkout main
  git -C "${INSTALL_DIR}" pull --ff-only origin main
else
  rm -rf "${INSTALL_DIR}"
  git clone "${REPO_URL}" "${INSTALL_DIR}"
fi

echo "[4/8] Tao Python virtualenv va cai dependencies..."
python -m venv "${INSTALL_DIR}/.venv"
"${INSTALL_DIR}/.venv/bin/python" -m pip install -U pip
"${INSTALL_DIR}/.venv/bin/pip" install -r "${INSTALL_DIR}/requirements.txt"

echo "[5/8] Tao file .env neu chua co..."
if [[ ! -f "${INSTALL_DIR}/.env" ]]; then
  cp "${INSTALL_DIR}/.env.example" "${INSTALL_DIR}/.env"
  echo "[WARN] Da tao ${INSTALL_DIR}/.env tu mau. Ban can dien OPENAI_API_KEY, TAVILY_API_KEY, TELEGRAM_BOT_TOKEN."
fi
sync_env_missing "${INSTALL_DIR}/.env" "${INSTALL_DIR}/.env.example"

echo "[6/8] Tao file systemd service..."
SERVICE_PATH="/etc/systemd/system/${SERVICE_NAME}.service"
sudo tee "${SERVICE_PATH}" >/dev/null <<EOF
[Unit]
Description=WSDeepAgent Telegram Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=${BOT_USER}
WorkingDirectory=${INSTALL_DIR}
EnvironmentFile=${INSTALL_DIR}/.env
ExecStart=${INSTALL_DIR}/.venv/bin/python ${INSTALL_DIR}/src/telegram_bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

echo "[7/8] Reload + enable service..."
sudo systemctl daemon-reload
sudo systemctl enable --now "${SERVICE_NAME}.service"

echo "[8/8] Hoan tat."
echo "- Kiem tra trang thai: sudo systemctl status ${SERVICE_NAME}.service"
echo "- Xem log realtime : journalctl -u ${SERVICE_NAME}.service -f"
