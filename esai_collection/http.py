from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

USER_AGENT = "esai-benchmark-collection/0.2"


class JsonHttpClient:
    def __init__(self, *, timeout: int = 30, delay_seconds: float = 0.0) -> None:
        self.timeout = timeout
        self.delay_seconds = delay_seconds

    def get_json(
        self, url: str, *, headers: dict[str, str] | None = None
    ) -> tuple[dict[str, Any] | list[Any] | None, str]:
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        request_headers = {"User-Agent": USER_AGENT, **(headers or {})}
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8")
            return json.loads(text), ""
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            return None, f"{type(exc).__name__}: {exc}"
