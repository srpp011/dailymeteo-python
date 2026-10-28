from unittest import mock

import pytest

import dailymeteo as dm
from dailymeteo import account as acc


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.ok, self.text = data, status, status < 400, str(data)

    def json(self):
        return self._data


def patched(responses):
    s = mock.Mock()
    s.post.side_effect = [r[1] for r in responses if r[0] == "login"]
    s.request.side_effect = [r[1] for r in responses if r[0] == "api"]
    return mock.patch.object(acc, "session", return_value=s), s


LOGIN = ("login", Resp({"access_token": "A1", "refresh_token": "R1"}))


def test_needs_credentials(monkeypatch):
    monkeypatch.delenv("DAILYMETEO_EMAIL", raising=False)
    monkeypatch.delenv("DAILYMETEO_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="email and password"):
        dm.Account()


def test_credits_and_bearer_header():
    sub = {"current_plan": [{"subscription_type": "basic", "credits": 900, "initial_credits": 1000, "start_date": "2026-10-01"}],
           "bulk_data": [{"credits": 2}, {"credits": 3}], "history_data": [], "bulk_history_data": []}
    p, s = patched([LOGIN, ("api", Resp(sub))])
    with p:
        out = dm.Account("a@b.c", "pw").credits()
    assert out == {"plan": "basic", "credits": 900, "initial_credits": 1000, "plan_start": "2026-10-01", "bulk_credits": 5}
    assert s.request.call_args.kwargs["headers"] == {"Authorization": "Bearer A1"}


def test_relogin_after_expired_token():
    p, s = patched([LOGIN, ("login", Resp({"access_token": "A2"})), ("api", Resp({"detail": "expired"}, 401)),
                    ("api", Resp({"success": 552}))])
    with p:
        cost = dm.Account("a@b.c", "pw").estimate_area("POLYGON((20 44,20.1 44,20.1 44.1,20 44))", ["tmax", "prcp"], "2020-01-01", "2020-01-31")
    assert cost == 552
    assert s.request.call_args.kwargs["headers"] == {"Authorization": "Bearer A2"}
    assert s.request.call_args.kwargs["json"]["vars"] == "tmax,prcp"


def test_error_reported_with_status_200():
    p, _ = patched([LOGIN, ("api", Resp({"error": "Provide area smaller than 3 000 square kilometers."}))])
    with p, pytest.raises(dm.DailyMeteoError, match="3 000"):
        dm.Account("a@b.c", "pw").area_download("POLYGON((0 0,1 0,1 1,0 0))", ["tmean"], "2020-01-01", "2020-01-02")


def test_bulk_download_params():
    p, s = patched([LOGIN, ("api", Resp({"success": "You can expect to receive the data on your email."}))])
    with p:
        msg = dm.Account("a@b.c", "pw").bulk_download(44.8, 20.46, start="2000-01-01")
    assert "email" in msg
    assert s.request.call_args.kwargs["params"] == {"lat": 44.8, "lon": 20.46, "from": "2000-01-01"}


def test_bad_login():
    p, _ = patched([("login", Resp({"non_field_errors": ["Unable to log in"]}, 400))])
    with p, pytest.raises(dm.DailyMeteoError, match="sign-in failed"):
        dm.Account("a@b.c", "bad").credits()
