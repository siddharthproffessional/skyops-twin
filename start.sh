#!/usr/bin/env bash
# One-command local start: builds the UI (first run) and serves everything on http://localhost:8000
set -euo pipefail
cd "$(dirname "$0")"
[ -f .env ] && set -a && . ./.env && set +a
python3 -m pip install -q -r backend/requirements.txt
if [ ! -d frontend/dist ]; then
  (cd frontend && npm install && npm run build)
fi
cd backend
echo "SkyOps Twin -> http://localhost:8000"
exec python3 -m uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
