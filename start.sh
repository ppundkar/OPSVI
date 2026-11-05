#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run ./install.sh first." >&2
  exit 1
fi
exec "$ROOT/.venv/bin/python" -m agent
