#!/usr/bin/env bash
set -euo pipefail
APP_NAME="pool-maintainer"
APP_PORT=8420
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_FILE="$ROOT_DIR/data/${APP_NAME}.pid"
LOG_FILE="$ROOT_DIR/data/${APP_NAME}.log"

mkdir -p "$ROOT_DIR/data"

cleanup() {
  if [ -f "$PID_FILE" ]; then
    old_pid=$(cat "$PID_FILE" 2>/dev/null || true)
    if [ -n "$old_pid" ] && kill -0 "$old_pid" 2>/dev/null; then
      echo "[$APP_NAME] stopping old instance (pid=$old_pid)..."
      kill "$old_pid" 2>/dev/null || true
      sleep 1
      kill -0 "$old_pid" 2>/dev/null && kill -9 "$old_pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE"
  fi
}

cleanup
cd "$ROOT_DIR"
uv sync >/dev/null 2>&1

nohup uv run uvicorn app.main:app --host 127.0.0.1 --port "$APP_PORT" \
  >> "$LOG_FILE" 2>&1 &
pid=$!
echo "$pid" > "$PID_FILE"

for i in $(seq 1 40); do
  if ss -ltnp | grep -q ":$APP_PORT "; then
    echo "[$APP_NAME] running at http://127.0.0.1:$APP_PORT (pid=$pid)"
    exit 0
  fi
  sleep 0.25
done

echo "[$APP_NAME] failed to start in 10s, check $LOG_FILE"
exit 1
