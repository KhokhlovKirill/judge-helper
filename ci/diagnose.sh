#!/usr/bin/env bash
# Surface compiler and device test diagnostics alongside the failed Actions check.
set -uo pipefail
out=$(mktemp)
"$@" 2>&1 | tee "$out"
status=${PIPESTATUS[0]}
if [ "$status" -ne 0 ]; then
  python3 - "$out" <<'PY'
import re,sys
from pathlib import Path
lines=Path(sys.argv[1]).read_text(errors="replace").replace("\r","\n").splitlines()
hits=[s for s in lines if re.search(r"error:|exception|expected:|actual:|could not|failed|not found|unable|error \(",s,re.I)]
message=" / ".join([*hits[:8],*lines[-8:]])[-3200:]
print("::error::"+message.replace("%","%25"))
PY
fi
exit "$status"
