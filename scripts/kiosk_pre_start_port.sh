#!/usr/bin/env bash
# Release FLASK_PORT so the bridge can bind after unclean shutdown / duplicate units.
set -uo pipefail
PORT="${FLASK_PORT:-5000}"

free_port() {
  if command -v fuser >/dev/null 2>&1; then
    fuser -k -TERM "${PORT}/tcp" >/dev/null 2>&1 || true
    sleep 0.4
    fuser -k -KILL "${PORT}/tcp" >/dev/null 2>&1 || true
  fi
  # Orphan bridge.py (e.g. legacy bridge.service or manual start) can keep port 5000
  # while systemd restarts fail with "Address already in use".
  pkill -TERM -f '/opt/kiosk/bridge\.py' 2>/dev/null || true
  pkill -TERM -f '/opt/kiosk/venv/bin/python.*bridge\.py' 2>/dev/null || true
  sleep 0.4
  pkill -KILL -f '/opt/kiosk/bridge\.py' 2>/dev/null || true
  pkill -KILL -f '/opt/kiosk/venv/bin/python.*bridge\.py' 2>/dev/null || true
}

port_in_use() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltn "( sport = :${PORT} )" 2>/dev/null | grep -q ":${PORT}"
    return $?
  fi
  if command -v fuser >/dev/null 2>&1; then
    fuser "${PORT}/tcp" >/dev/null 2>&1
    return $?
  fi
  return 1
}

free_port
# Wait until the port is actually free before ExecStart binds (avoids first-boot race).
for _ in $(seq 1 20); do
  if ! port_in_use; then
    exit 0
  fi
  free_port
  sleep 0.5
done

echo "kiosk_pre_start_port: port ${PORT} still busy after cleanup" >&2
# Do not block boot forever; let systemd restart handle a remaining conflict.
exit 0
