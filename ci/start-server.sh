#!/usr/bin/env bash
set -eu
mkdir -p artifacts
python -m uvicorn "${1:-server.api:app}" --host 127.0.0.1 --port 8000 >artifacts/api.log 2>&1 &
for _ in {1..60}; do
  if curl -fsS http://127.0.0.1:8000/health >/dev/null; then exit 0; fi
  sleep 1
done
cat artifacts/api.log
exit 1
