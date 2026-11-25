import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4
import httpx
from .seed import seed


def main():
    eid, panel = seed("load", 500, 50)
    base = "http://127.0.0.1:8000"
    barrier = Barrier(len(panel))

    def worker(email):
        with httpx.Client(base_url=base, timeout=60) as client:
            r = client.post("/login", json={"email": email, "password": "Contest123"})
            r.raise_for_status()
            client.headers.update(Authorization="Bearer " + r.json()["token"])
            path = f"/events/{eid}"
            op = dict(technique=8, artistry=9, operation=str(uuid4()), version=0)
            barrier.wait(timeout=120)
            start = time.monotonic()
            client.post(path + "/scores/1", json=op).raise_for_status()
            elapsed = time.monotonic() - start
            client.post(path + "/scores/1", json=op).raise_for_status()
            client.get(path).raise_for_status()
            return elapsed, client.headers["Authorization"]

    with ThreadPoolExecutor(50) as pool:
        observations = list(pool.map(worker, panel))
    times = [v for v, _ in observations]
    data = httpx.get(
        base + "/events/" + eid, headers={"Authorization": observations[0][1]}
    ).json()
    assert len(data["participants"]) == 500 and set(data["scores"]["1"]) == set(panel)
    assert all(
        s == {"version": 1, "t": 80, "a": 90} for s in data["scores"]["1"].values()
    )
    metrics = dict(
        users=50,
        participants=500,
        max_seconds=max(times),
        median_seconds=statistics.median(times),
        p95_seconds=sorted(times)[47],
    )
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/load.json").write_text(json.dumps(metrics, indent=2))
    print(metrics)
    assert max(times) <= 1, "Превышено время сохранения оценки"


if __name__ == "__main__":
    main()
