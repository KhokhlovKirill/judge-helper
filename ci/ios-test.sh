#!/usr/bin/env bash
set -euo pipefail
xcrun simctl list devices available --json > artifacts/simulators.json
udid=$(python3 - "$1" <<'PY'
import json,sys
devices=json.load(open("artifacts/simulators.json"))["devices"]
eligible=[(tuple(map(int,key.split("iOS-")[-1].split("-"))), d["udid"]) for key,group in devices.items() if "iOS-" in key for d in group if d["name"].startswith(sys.argv[1])]
print(max(eligible)[1])
PY
)
xcrun simctl boot "$udid"
xcrun simctl bootstatus "$udid" -b
cd mobile
flutter build ios --debug --simulator --no-pub
ditto -c -k --keepParent build/ios/iphonesimulator/Runner.app ../artifacts/Runner-simulator.zip
flutter test integration_test/competition_test.dart -d "$udid" --file-reporter json:../artifacts/mobile.json
