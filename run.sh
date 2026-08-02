#!/usr/bin/env bash
# Starts the HTTPS server with TLS cert paths pointing outside the repo.
set -euo pipefail

CERT_DIR="${CERT_DIR:-$HOME/learning/local-test-certs}"

export TLS_CERT_FILE="$CERT_DIR/cert.pem"
export TLS_KEY_FILE="$CERT_DIR/key.pem"

for f in "$TLS_CERT_FILE" "$TLS_KEY_FILE"; do
    if [[ ! -f "$f" ]]; then
        echo "error: missing TLS file: $f" >&2
        echo "Set CERT_DIR to the directory holding cert.pem and key.pem, e.g." >&2
        echo "  CERT_DIR=/path/to/certs $0" >&2
        echo "To create them: mkcert -cert-file cert.pem -key-file key.pem localhost 127.0.0.1 ::1" >&2
        exit 1
    fi
done

cd "$(dirname "${BASH_SOURCE[0]}")"
exec python3 server.py
