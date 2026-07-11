#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
echo "Starting Enterprise Dashboard..."
echo "The dashboard URL will be displayed below."
exec python3 server.py --host "${HOST:-0.0.0.0}" --port "${PORT:-8000}"
