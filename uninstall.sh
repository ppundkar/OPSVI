#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

KEEP_CONFIG=0
DELETE_FOLDER=0
for arg in "$@"; do
  case "$arg" in
    --keep-config) KEEP_CONFIG=1 ;;
    --delete-folder) DELETE_FOLDER=1 ;;
    *)
      echo "Unknown option: $arg" >&2
      echo "Usage: ./uninstall.sh [--keep-config] [--delete-folder]" >&2
      exit 1
      ;;
  esac
done

echo "Uninstalling VOCE in $ROOT"

if [[ -x "$ROOT/.venv/bin/python" ]]; then
  pkill -f "$ROOT/.venv/bin/python -m agent" 2>/dev/null || true
  echo "Stopped a VOCE process when one was running."
fi

UNIT=/etc/systemd/system/vmware-cost-agent.service
if [[ -f "$UNIT" ]] && grep -q "$ROOT" "$UNIT"; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "The systemd service points at this folder. Re-run with sudo to remove it:" >&2
    echo "  sudo ./uninstall.sh${KEEP_CONFIG:+ --keep-config}${DELETE_FOLDER:+ --delete-folder}" >&2
    exit 1
  fi
  systemctl disable --now vmware-cost-agent || true
  rm -f "$UNIT"
  systemctl daemon-reload
  echo "Removed systemd service vmware-cost-agent."
fi

if [[ "$KEEP_CONFIG" -eq 1 ]]; then
  rm -rf "$ROOT/.venv"
  echo "Removed .venv. Kept .env, data, and out."
else
  rm -rf "$ROOT/.venv" "$ROOT/.env" "$ROOT/data" "$ROOT/out"
  echo "Removed .venv, .env, data, and out."
fi

echo
echo "VOCE is uninstalled from this folder."
echo "Python and Git were left installed."
echo "vCenter, NSX, Aria, and VCF were not changed."
echo "Remove the Monday cron line yourself if you added one."
echo "If a browser trusted data/tls/voce.cer, remove that certificate there."
echo "Saved endpoints and the HTTPS key are deleted unless you passed --keep-config."

if [[ "$DELETE_FOLDER" -eq 1 ]]; then
  cd /
  rm -rf "$ROOT"
  echo "Removed $ROOT"
fi
