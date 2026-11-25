"""Fifty independent sessions use the same competition and participant."""

import asyncio
import json
import os
import statistics
import time
from contextlib import AsyncExitStack
from pathlib import Path
from uuid import uuid4

import httpx
from .seed import seed


async def exercise(base, eid, panel):
    path = f"/events/{eid}"
    async with AsyncExitStack() as stack:
        clients = [
            await stack.enter_async_context(
                httpx.AsyncClient(base_url=base, timeout=60)
            )
            for _ in panel
        ]

        async def login(client, who):
            response = await client.post(
                "/login", json={"email": who, "password": "Contest123"}
            )
            response.raise_for_status()
            client.headers["Authorization"] = "Bearer " + response.json()["token"]

        await asyncio.gather(
            *(login(c, j) for c, j in zip(clients, panel, strict=True))
        )
        payloads = [
            dict(technique=8, artistry=9, operation=str(uuid4()), version=0)
            for _ in panel
        ]

        async def submit(client, payload):
            start = time.perf_counter()
            response = await client.post(path + "/scores/1", json=payload)
            response.raise_for_status()
            return time.perf_counter() - start

        times = await asyncio.gather(
            *(submit(c, p) for c, p in zip(clients, payloads, strict=True))
        )

        async def check(client, payload):
            (await client.post(path + "/scores/1", json=payload)).raise_for_status()
            response = await client.get(path)
            response.raise_for_status()
            data = response.json()
            assert len(data["participants"]) == 500 and set(data["scores"]["1"]) == set(
                panel
            )
            assert all(
                s == {"version": 1, "t": 80, "a": 90}
                for s in data["scores"]["1"].values()
            )

        await asyncio.gather(
            *(check(c, p) for c, p in zip(clients, payloads, strict=True))
        )
        return times


def main():
    eid, panel = seed("load-" + uuid4().hex[:8], 500, 50)
    times = asyncio.run(
        exercise(os.getenv("ACCEPTANCE_URL", "http://127.0.0.1:8000"), eid, panel)
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
