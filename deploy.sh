#!/usr/bin/env bash
# Deploy HKJC Quinella Prediction System
# Usage: ./deploy.sh [--rebuild]

set -euo pipefail

cd "$(dirname "$0")"

echo "=== HKJC Quinella Prediction — Deploy ==="

# Ensure .env exists
if [ ! -f .env ]; then
  echo "Creating .env from .env.example..."
  cp .env.example .env
  echo "  → Edit .env if you need to change WEB_PORT (default 8321)"
fi

source .env 2>/dev/null || true
WEB_PORT="${WEB_PORT:-8321}"

# Check data directory has models
if [ ! -f data/models/top2_lightgbm.pkl ]; then
  echo "⚠️  Warning: data/models/top2_lightgbm.pkl not found."
  echo "   Models must be present in data/models/ for predictions to work."
fi

if [ "${1:-}" = "--rebuild" ]; then
  echo "Building images (--no-cache)..."
  docker compose build --no-cache
else
  echo "Building images (cached)..."
  docker compose build
fi

echo "Starting containers..."
docker compose up -d

echo ""
echo "=== Deployment complete ==="
echo "Access: http://$(hostname -I 2>/dev/null | awk '{print $1}'):${WEB_PORT}"
echo ""
echo "Useful commands:"
echo "  docker compose ps          # check status"
echo "  docker compose logs -f     # follow logs"
echo "  docker compose down        # stop"
echo "  docker compose restart web # restart frontend only"
