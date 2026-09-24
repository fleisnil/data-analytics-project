from __future__ import annotations

import time
from typing import Any

import requests

USER_AGENT = (
    "ZHAW-Data-Analytics-Student-Project/0.1 "
    "(research and teaching; contact details in project presentation)"
)


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    timeout: int = 45,
    attempts: int = 3,
) -> dict:
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            response = requests.get(
                url,
                params=params,
                headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
                timeout=(10, timeout),
            )
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError) as exc:
            last_error = exc
            if attempt < attempts:
                time.sleep(2 ** (attempt - 1))
    raise RuntimeError(f"Request failed after {attempts} attempts: {url}") from last_error

