#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run ./install.sh first." >&2
  exit 1
fi

UNIT=/etc/systemd/system/vmware-cost-agent.service
if [[ -f "$UNIT" ]] && grep -q "$ROOT" "$UNIT" && command -v systemctl >/dev/null 2>&1; then
  systemctl enable --now vmware-cost-agent
  echo "VOCE is running as a service. Disconnecting does not stop it."
  exit 0
fi

mkdir -p "$ROOT/out" "$ROOT/data"
if [[ -f "$ROOT/data/voce.pid" ]] && kill -0 "$(cat "$ROOT/data/voce.pid")" 2>/dev/null; then
  echo "VOCE is already running. Disconnecting does not stop it."
  exit 0
fi

nohup "$ROOT/.venv/bin/python" -m agent >> "$ROOT/out/voce.log" 2>&1 &
echo $! > "$ROOT/data/voce.pid"
echo "VOCE is running in the background. Disconnecting does not stop it."
echo "Log: $ROOT/out/voce.log"
