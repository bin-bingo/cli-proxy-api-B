#!/usr/bin/env bash
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="pool-maintainer"
PID_FILE="$ROOT_DIR/data/${APP_NAME}.pid"

if [ ! -f "$PID_FILE" ]; then
  echo "[$APP_NAME] not running (no pid file)"
  exit 0
fi

pid=$(cat "$PID_FILE" 2>/dev/null || true)
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  echo "[$APP_NAME] not running (stale pid file, cleaning)"
  rm -f "$PID_FILE"
  exit 0
fi

echo "[$APP_NAME] stopping pid=$pid"
kill "$pid" 2>/dev/null || true
sleep 1
if kill -0 "$pid" 2>/dev/null; then
  echo "[$APP_NAME] force killing pid=$pid"
  kill -9 "$pid" 2>/dev/null || true
fi
rm -f "$PID_FILE"
echo "[$APP_NAME] stopped"
