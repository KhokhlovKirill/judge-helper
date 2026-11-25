#!/usr/bin/env bash
set -euo pipefail
adb reverse tcp:8000 tcp:8000
adb shell getprop ro.build.version.release > artifacts/android-version.txt
adb shell settings put system accelerometer_rotation 0
adb shell settings put system user_rotation 1
cd mobile
flutter test integration_test/competition_test.dart -d emulator-5554 --file-reporter json:../artifacts/mobile.json
