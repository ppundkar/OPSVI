#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

PYTHON=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'; then
      PYTHON="$candidate"
      break
    fi
  fi
done
if [[ -z "$PYTHON" ]]; then
  echo "Python 3.11 or newer is required." >&2
  exit 1
fi

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  "$PYTHON" -m venv "$ROOT/.venv"
fi
"$ROOT/.venv/bin/python" -m pip install --upgrade pip
"$ROOT/.venv/bin/python" -m pip install -r "$ROOT/requirements.txt"
mkdir -p "$ROOT/data" "$ROOT/out"
if [[ ! -f "$ROOT/.env" ]]; then
  cp "$ROOT/.env.example" "$ROOT/.env"
fi
chmod 600 "$ROOT/.env" || true
chmod +x "$ROOT/enable-https.sh" "$ROOT/start.sh" "$ROOT/uninstall.sh" || true

configured="$(grep '^VCO_SSL_CERTFILE=' "$ROOT/.env" | head -n 1 | cut -d= -f2- || true)"
refresh=0
if [[ -f "$ROOT/data/tls/cert.pem" ]]; then
  if "$ROOT/.venv/bin/python" -c "from agent.__main__ import default_cert_is_stale; raise SystemExit(2 if default_cert_is_stale() else 0)"; then
    refresh=0
  else
    status=$?
    if [[ "$status" -eq 2 ]]; then
      refresh=1
    else
      exit "$status"
    fi
  fi
fi
if [[ "$refresh" -eq 1 ]]; then
  echo "The HTTPS certificate does not include this server's name or IP. Creating a new one."
  "$ROOT/enable-https.sh"
elif [[ -n "$configured" && ( -f "$ROOT/$configured" || -f "$configured" ) ]]; then
  echo "Keeping the HTTPS certificate already on this server."
elif [[ -f "$ROOT/data/tls/cert.pem" && -f "$ROOT/data/tls/key.pem" ]]; then
  echo "Keeping the HTTPS certificate already on this server."
else
  "$ROOT/enable-https.sh"
fi

echo
echo "Installed in $ROOT"
echo "Start:  ./start.sh"
"$ROOT/.venv/bin/python" -c "from agent.__main__ import print_browse_urls; print_browse_urls()"
echo "Guide:  INSTALL.md"
echo

if [[ "${1:-}" == "--systemd" ]]; then
  UNIT=/etc/systemd/system/vmware-cost-agent.service
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Re-run with sudo to install the systemd service." >&2
    exit 1
  fi
  sed "s|@ROOT@|$ROOT|g" "$ROOT/deploy/vmware-cost-agent.service" > "$UNIT"
  systemctl daemon-reload
  echo "Service file written to $UNIT"
  echo "Enable it with: systemctl enable --now vmware-cost-agent"
fi

if [[ "${1:-}" == "--start" ]]; then
  exec "$ROOT/start.sh"
fi
