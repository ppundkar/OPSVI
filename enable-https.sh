#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
if [[ $# -lt 1 ]]; then
  short="$(hostname -s 2>/dev/null || hostname)"
  set -- "$short"
  fqdn="$(hostname -f 2>/dev/null || true)"
  if [[ -n "$fqdn" && "$fqdn" != "$short" ]]; then
    set -- "$@" "$fqdn"
  fi
  for ip in $(hostname -I 2>/dev/null || true); do
    [[ "$ip" == 127.* || "$ip" == 169.254.* ]] && continue
    set -- "$@" "$ip"
  done
fi
if ! command -v openssl >/dev/null 2>&1; then
  echo "openssl is required to create the VOCE certificate." >&2
  exit 1
fi

names=("localhost" "127.0.0.1" "$@")
san=""
seen=" "
for name in "${names[@]}"; do
  [[ "$seen" == *" $name "* ]] && continue
  seen+="$name "
  if [[ "$name" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ || "$name" == *:* ]]; then
    entry="IP:$name"
  else
    entry="DNS:$name"
  fi
  san+="${san:+,}$entry"
done

mkdir -p "$ROOT/data/tls"
openssl req -x509 -newkey rsa:2048 -sha256 -days 825 -nodes \
  -keyout "$ROOT/data/tls/key.pem" \
  -out "$ROOT/data/tls/cert.pem" \
  -subj "/CN=$1" \
  -addext "subjectAltName=$san" \
  -addext "extendedKeyUsage=serverAuth"
chmod 600 "$ROOT/data/tls/key.pem" || true
cp "$ROOT/data/tls/cert.pem" "$ROOT/data/tls/voce.cer"

env_file="$ROOT/.env"
if [[ ! -f "$env_file" ]]; then
  cp "$ROOT/.env.example" "$env_file"
fi
set_line() {
  local key="$1" value="$2"
  if grep -q "^${key}=" "$env_file"; then
    grep -v "^${key}=" "$env_file" > "$env_file.tmp" || true
    printf '%s=%s\n' "$key" "$value" >> "$env_file.tmp"
    mv "$env_file.tmp" "$env_file"
  else
    printf '%s=%s\n' "$key" "$value" >> "$env_file"
  fi
}
set_line VCO_HOST 0.0.0.0
set_line VCO_SSL_CERTFILE data/tls/cert.pem
set_line VCO_SSL_KEYFILE data/tls/key.pem
chmod 600 "$env_file" || true

port="$(grep '^VCO_PORT=' "$env_file" | head -n 1 | cut -d= -f2- || true)"
port="${port:-8080}"
echo "Certificate names: $san"
echo "Import data/tls/voce.cer on each browser computer that should trust VOCE."
echo "Restart with ./start.sh"
for name in "$@"; do
  [[ "$name" == localhost || "$name" == 127.* || "$name" == 169.254.* ]] && continue
  echo "Dashboard: https://${name}:${port}"
  echo "Admin:     https://${name}:${port}/admin"
done
