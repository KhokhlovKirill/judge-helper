import json
import sys
from pathlib import Path


def check_server():
    files = json.loads(Path("artifacts/coverage.json").read_text())["files"]
    rules = files["server/domain.py"]
    selected = {
        name: files["server/api.py"]["functions"][name]
        for name in (
            "actor",
            "token_user",
            "editable",
            "load",
            "correction",
            "score",
            "action",
            "detail",
            "insert_person",
            "setup",
            "check_password",
            "make_pdf",
        )
    }
    for name, record in {"server/domain.py": rules, **selected}.items():
        assert not record["missing_lines"] and not record["missing_branches"], (
            name,
            record["missing_lines"],
            record["missing_branches"],
        )
    print("Critical server lines and branches: 100%")


def check_flutter():
    blocks = Path("artifacts/lcov.info").read_text().split("end_of_record")
    lines = next(
        block for block in blocks if "SF:lib/score_queue.dart" in block
    ).splitlines()
    hits = [s.split(",")[-1] for s in lines if s.startswith("DA:")]
    edges = [s.split(",")[-1] for s in lines if s.startswith("BRDA:")]
    assert hits and edges, "Missing line or branch instrumentation"
    missing = [
        s
        for s in lines
        if s.startswith(("DA:", "BRDA:")) and s.split(",")[-1] in ("0", "-")
    ]
    assert not missing, missing
    print("Offline queue lines and branches: 100%")


if __name__ == "__main__":
    {"server": check_server, "flutter": check_flutter}[sys.argv[1]]()
