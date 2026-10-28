"""DailyMeteo account: credits, bulk point downloads and polygon (area) downloads.

These services need a signed-in account (email and password); an API key covers only point queries.
Results of bulk and area downloads are prepared on the server and sent to the account's email.
"""
from __future__ import annotations

import os
from collections.abc import Sequence

from ._http import DailyMeteoError, session

API_BASE = "https://api.dailymeteo.com"
AREA_LIMIT_KM2 = 3000


class Account:
    """Signed-in DailyMeteo account. Credentials default to ``DAILYMETEO_EMAIL`` and ``DAILYMETEO_PASSWORD``."""

    def __init__(self, email: str | None = None, password: str | None = None):
        self.email = email or os.environ.get("DAILYMETEO_EMAIL")
        self._password = password or os.environ.get("DAILYMETEO_PASSWORD")
        if not (self.email and self._password):
            raise ValueError("an account needs email and password (or DAILYMETEO_EMAIL and DAILYMETEO_PASSWORD)")
        self._access: str | None = None

    def __repr__(self) -> str:
        return f"Account({self.email!r})"

    def _login(self) -> None:
        r = session().post(f"{API_BASE}/auth/login/", json={"email": self.email, "password": self._password}, timeout=60)
        if not r.ok:
            raise DailyMeteoError(f"DailyMeteo sign-in failed ({r.status_code}): {r.text[:300]}")
        self._access = r.json()["access_token"]

    def headers(self) -> dict:
        """Authorization header with a valid access token (signs in when needed)."""
        if self._access is None:
            self._login()
        return {"Authorization": f"Bearer {self._access}"}

    def request(self, method: str, path: str, **kwargs) -> dict:
        """Authenticated request; signs in again once if the access token expired (it lives 30 minutes)."""
        for attempt in (1, 2):
            r = session().request(method, f"{API_BASE}{path}", headers=self.headers(), timeout=kwargs.pop("timeout", 300), **kwargs)
            if r.status_code == 401 and attempt == 1:
                self._access = None
                continue
            break
        try:
            data = r.json()
        except ValueError:
            data = {"error": r.text[:300]}
        # some endpoints report failures as {"error": ...} with status 200
        if not r.ok or (isinstance(data, dict) and data.get("error")):
            msg = data.get("error") or data.get("message") or data.get("detail") if isinstance(data, dict) else data
            raise DailyMeteoError(f"DailyMeteo returned {r.status_code}: {msg}")
        return data

    def credits(self) -> dict:
        """Plan and remaining credits: API credits (point and area queries) and bulk credits (point history)."""
        s = self.request("GET", "/subscription/")
        plan = (s.get("current_plan") or [{}])[0]
        return {
            "plan": plan.get("subscription_type"),
            "credits": plan.get("credits"),
            "initial_credits": plan.get("initial_credits"),
            "plan_start": plan.get("start_date"),
            "bulk_credits": sum(b.get("credits", 0) for b in s.get("bulk_data") or []),
        }

    def bulk_download(self, lat: float, lon: float, start: str | None = None, end: str | None = None) -> str:
        """Every variable, daily, for one location (whole record unless ``start``/``end`` YYYY-MM-DD are given).

        Costs one bulk credit; the CSV is emailed to the account.
        """
        params = {"lat": lat, "lon": lon}
        if start:
            params["from"] = start
        if end:
            params["to"] = end
        return self.request("GET", "/meteo/bulk/", params=params).get("success", "requested")

    def estimate_area(self, geom_wkt: str, variables: Sequence[str], start: str, end: str) -> int:
        """Credit cost of an area download (polygon in WGS84 WKT, at most 3,000 km², full days YYYY-MM-DD)."""
        body = {"geom": geom_wkt, "vars": ",".join(variables), "from": start, "to": end}
        return int(self.request("POST", "/meteo/calculate-area/", json=body)["success"])

    def area_download(self, geom_wkt: str, variables: Sequence[str], start: str, end: str) -> str:
        """Daily rasters clipped to a polygon (WGS84 WKT, at most 3,000 km²); emailed to the account."""
        body = {"geom": geom_wkt, "vars": ",".join(variables), "from": start, "to": end}
        return self.request("POST", "/meteo/polygon-download/", json=body).get("success", "requested")
