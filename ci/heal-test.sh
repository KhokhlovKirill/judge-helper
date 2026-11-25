#!/usr/bin/env bash
set -euo pipefail
adb reverse tcp:8000 tcp:8000
appium --address 127.0.0.1 --log artifacts/appium.log &
for _ in {1..40}; do
  if curl -fsS http://127.0.0.1:4723/status >/dev/null; then break; fi
  sleep 1
done
python -m ci.healing_ui
