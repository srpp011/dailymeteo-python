from __future__ import annotations

from functools import lru_cache

import requests

from . import __version__

USER_AGENT = f"dailymeteo-python/{__version__}"


class DailyMeteoError(RuntimeError):
    """A web service returned an error."""


@lru_cache(maxsize=1)
def session() -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = USER_AGENT
    return s
