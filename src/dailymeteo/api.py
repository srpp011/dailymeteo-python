"""DailyMeteo API client: point values of gridded meteorological data, World, 1961 to the present."""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

import pandas as pd

from ._http import USER_AGENT, DailyMeteoError, session

if TYPE_CHECKING:
    from .account import Account

API_URL = "https://api.dailymeteo.com/meteo/v2/pq/"
NODATA = -999.9  # returned for locations without data (e.g. sea)
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

VARS = ("tmean", "tmax", "tmin", "prcp")
AGG_LEVELS = ("agg", "ltm")
TIME_SCALES = ("day", "mon", "ann")

# The API is called with GET; long lists of dates are split so the URL stays short.
_MAX_TIME_CHARS = 1500


def _check(name: str, value: str, allowed: Sequence[str]) -> None:
    if value not in allowed:
        raise ValueError(f"{name} must be one of {', '.join(allowed)}; got {value!r}")


def _batches(times: list[str]) -> Iterable[list[str]]:
    batch, length = [], 0
    for t in times:
        if batch and length + len(t) + 1 > _MAX_TIME_CHARS:
            yield batch
            batch, length = [], 0
        batch.append(t)
        length += len(t) + 1
    if batch:
        yield batch


def get_meteo(
    lat: float,
    lon: float,
    api_key: str | None = None,
    var: str = "tmean",
    agg_level: str = "agg",
    time_scale: str = "day",
    time: str | Sequence[str] | None = None,
    start: str | None = None,
    end: str | None = None,
    account: Account | None = None,
) -> pd.DataFrame:
    """Meteorological values for one location from the DailyMeteo API.

    Parameters
    ----------
    lat, lon
        Location in WGS84 (EPSG:4326).
    api_key
        API key from the DailyMeteo portal (https://app.dailymeteo.com/). Required for daily data
        (``time_scale="day"`` with ``agg_level="agg"``), which is billed per returned day; monthly,
        annual and long-term mean values are free.
    var
        ``"tmean"`` (mean temperature, °C), ``"tmax"``, ``"tmin"``, or ``"prcp"`` (total precipitation, mm).
    agg_level
        ``"agg"`` (values for the given dates) or ``"ltm"`` (long-term means, 1961-1990 and 1991-2020).
    time_scale
        ``"day"``, ``"mon"`` or ``"ann"``.
    time
        Date(s): ``"YYYY-MM-DD"`` for daily, ``"YYYY-MM"`` for monthly, ``"YYYY"`` for annual data.
        A list or a comma-separated string. If given, ``start`` and ``end`` are ignored.
    start, end
        Date range (same format as ``time``), sent to the API as ``from`` and ``to``.
    account
        Signed-in :class:`dailymeteo.Account`; an alternative to ``api_key`` for daily data.

    Returns
    -------
    pandas.DataFrame
        Columns ``timestamp`` and ``value``. Locations without data (e.g. sea) give ``NaN``.
        Long-term means (``agg_level="ltm"``) have timestamps like ``"1991-2020"``, ``"07.1991-2020"``
        or ``"25.07.1991-2020"``.
    """
    _check("var", var, VARS)
    _check("agg_level", agg_level, AGG_LEVELS)
    _check("time_scale", time_scale, TIME_SCALES)
    if not (api_key or account) and time_scale == "day" and agg_level == "agg":
        raise ValueError("daily data require api_key or account; get a key from the DailyMeteo portal (https://app.dailymeteo.com/)")
    params = {"var": var, "agg_level": agg_level, "time_scale": time_scale, "lat": lat, "lon": lon}
    if api_key:
        params["api_key"] = api_key

    if time is not None:
        times = [t.strip() for t in (time.split(",") if isinstance(time, str) else time) if str(t).strip()]
        if not times:
            raise ValueError("time is empty")
        requests_params = [params | {"time": ",".join(b)} for b in _batches(times)]
    elif start is not None and end is not None:
        requests_params = [params | {"from": start, "to": end}]
    else:
        raise ValueError("either time or both start and end must be given")

    frames = []
    s = session()
    for p in requests_params:
        r = s.get(API_URL, params=p, headers=account.headers() if account and not api_key else None, timeout=300)
        if not r.ok:
            raise DailyMeteoError(f"DailyMeteo API returned {r.status_code}: {r.text[:300]}")
        data = r.json()
        if data:
            frames.append(pd.DataFrame(data)[["timestamp", "value"]])
    if not frames:
        return pd.DataFrame(columns=["timestamp", "value"])
    df = pd.concat(frames, ignore_index=True)
    df["value"] = df["value"].mask(df["value"] <= NODATA)
    return df


def get_coordinates(location_name: str = "Belgrade") -> tuple[float, float]:
    """Latitude and longitude (WGS84) of a place name, from OpenStreetMap Nominatim.

    Nominatim allows at most one request per second; do not use this for bulk geocoding.
    """
    r = session().get(
        NOMINATIM_URL,
        params={"q": location_name, "format": "json", "limit": 1},
        headers={"User-Agent": USER_AGENT},
        timeout=60,
    )
    if not r.ok:
        raise DailyMeteoError(f"Nominatim returned {r.status_code}: {r.text[:300]}")
    data = r.json()
    if not data:
        raise LookupError(f"location not found: {location_name!r}")
    return float(data[0]["lat"]), float(data[0]["lon"])
