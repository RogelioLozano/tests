#!/usr/bin/env bash
# Starts the FastAPI backend for local development.
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

PYTHON="${PYTHON:-.venv/bin/python}"
if [[ ! -x "$PYTHON" ]]; then
    echo "error: no interpreter at $PYTHON" >&2
    echo "Create one with: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# Bound to loopback: the API executes generated code through Manim and must not
# be reachable from the network without a reverse proxy and auth in front.
HOST="${ANIM_HOST:-127.0.0.1}"
PORT="${ANIM_PORT:-8000}"

cd backend
exec "../$PYTHON" -m uvicorn app.main:create_app --factory --host "$HOST" --port "$PORT" "$@"
