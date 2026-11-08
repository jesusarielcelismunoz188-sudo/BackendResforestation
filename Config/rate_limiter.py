"""Rate limiter en memoria por dirección IP."""
import asyncio
import math
import time
from collections import defaultdict, deque
from typing import Deque

from starlette.responses import JSONResponse


class RateLimitMiddleware:
    def __init__(
        self,
        app,
        *,
        limit: int = 10,
        window_seconds: float = 1.0,
    ):
        self.app = app
        self.limit = limit
        self.window_seconds = window_seconds
        self.requests: dict[str, Deque[float]] = defaultdict(deque)
        self.lock = asyncio.Lock()
        self.last_cleanup = time.monotonic()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        client = scope.get("client")
        client_ip = client[0] if client else "unknown"
        now = time.monotonic()

        async with self.lock:
            cutoff = now - self.window_seconds
            if now - self.last_cleanup >= self.window_seconds * 60:
                for ip, requests in list(self.requests.items()):
                    while requests and requests[0] <= cutoff:
                        requests.popleft()
                    if not requests:
                        self.requests.pop(ip, None)
                self.last_cleanup = now

            timestamps = self.requests[client_ip]
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()

            if len(timestamps) >= self.limit:
                retry_after = max(
                    1,
                    math.ceil(self.window_seconds - (now - timestamps[0])),
                )
                response = JSONResponse(
                    status_code=429,
                    content={"detail": "Límite de 10 peticiones por segundo excedido."},
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(self.limit),
                        "X-RateLimit-Remaining": "0",
                    },
                )
                await response(scope, receive, send)
                return

            timestamps.append(now)
            remaining = self.limit - len(timestamps)

        async def send_with_rate_limit_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"x-ratelimit-limit", str(self.limit).encode()),
                        (b"x-ratelimit-remaining", str(remaining).encode()),
                    ]
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_rate_limit_headers)
