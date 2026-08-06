#!/bin/bash
# Синхронизирует локальный backend/ с staging-сервером и перезапускает его.
# Запускать ПЕРЕД деплоем в прод — проверить изменения на staging сначала.
#
# Использование: ./scripts/deploy_staging.sh
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SSH_HOST="root@80.78.246.188"
SSH_KEY="$HOME/.ssh/moy_put"
STAGING_DIR="/opt/voice-diary-staging"

echo "Синхронизирую backend/ → staging..."
rsync -av --delete \
  --exclude=venv --exclude=.venv --exclude=__pycache__ --exclude='*.pyc' \
  --exclude=.pytest_cache \
  --exclude=.env --exclude=uploads --exclude=backups \
  -e "ssh -i $SSH_KEY" \
  "$REPO_ROOT/backend/" "$SSH_HOST:$STAGING_DIR/"

echo "Перезапускаю voice-diary-staging.service..."
ssh -i "$SSH_KEY" "$SSH_HOST" "systemctl restart voice-diary-staging.service && sleep 2 && systemctl is-active voice-diary-staging.service"

echo "Проверяю здоровье..."
curl -s https://moy-way.ru:8443/health && echo ""
echo "Готово. Staging: https://moy-way.ru:8443"
