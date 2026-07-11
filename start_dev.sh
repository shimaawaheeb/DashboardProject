#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
if [[ ! -x .venv/bin/python ]]; then
  echo "Missing DashboardProject/.venv."
  echo "Run: python3 -m venv .venv && .venv/bin/python -m pip install -r requirements-dev.txt"
  exit 1
fi
exec .venv/bin/python -m watchfiles \
  --filter dev_filter.dashboard_file_filter \
  ".venv/bin/python server.py --host 0.0.0.0 --port 8000" \
  .
