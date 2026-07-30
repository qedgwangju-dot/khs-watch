from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.parse import urlencode
from urllib.request import Request, urlopen


@dataclass
class Fetcher:
    timeout: int = 25
    retries: int = 3
    backoff: float = 1.0
    rate_limit: float = 1.0

    async def get(self, session: object, url: str, params: dict | None = None) -> str:
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                target = f"{url}?{urlencode(params)}" if params else url
                def fetch() -> str:
                    request = Request(target, headers={"User-Agent": "Samsung-SVIC-Tracker/1.0"})
                    with urlopen(request, timeout=self.timeout) as response:
                        return response.read().decode(response.headers.get_content_charset() or "utf-8", errors="replace")
                text = await asyncio.to_thread(fetch)
                await asyncio.sleep(1 / max(self.rate_limit, 0.1))
                return text
            except (OSError, TimeoutError) as exc:
                last_error = exc
                if attempt + 1 < self.retries:
                    await asyncio.sleep(self.backoff * (2 ** attempt))
        raise RuntimeError(f"GET failed after {self.retries} attempts: {url}: {last_error}")
