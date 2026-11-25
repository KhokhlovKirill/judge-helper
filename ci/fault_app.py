"""Acceptance-only app variant. Inject an incorrect stored value for fixture 3."""

import json
from server.api import app as production


async def app(scope, receive, send):
    if (
        scope["type"] == "http"
        and scope["method"] == "POST"
        and scope["path"].endswith("/scores/3")
    ):
        raw = bytearray()
        while True:
            chunk = await receive()
            raw.extend(chunk["body"])
            if not chunk.get("more_body"):
                break
        data = json.loads(raw)
        data["technique"] = "0"

        async def replacement():
            return {
                "type": "http.request",
                "body": json.dumps(data).encode(),
                "more_body": False,
            }

        await production(scope, replacement, send)
    else:
        await production(scope, receive, send)
