from unittest import mock

import pytest

import dailymeteo as dm
from dailymeteo import api


class Resp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.ok, self.text = data, status, status < 400, str(data)

    def json(self):
        return self._data


def fake_session(responses):
    s = mock.Mock()
    s.get.side_effect = responses
    return mock.patch.object(api, "session", return_value=s), s


def test_get_meteo_range():
    p, s = fake_session([Resp([{"timestamp": "2020-01-01", "value": 0.7, "extra": 1}])])
    with p:
        df = dm.get_meteo(44.8, 20.46, api_key="k", start="2020-01-01", end="2020-01-01")
    assert list(df.columns) == ["timestamp", "value"]
    assert df.value.tolist() == [0.7]
    params = s.get.call_args.kwargs["params"]
    assert params["from"] == "2020-01-01" and params["to"] == "2020-01-01" and "time" not in params


def test_get_meteo_time_list_is_comma_joined_and_batched():
    times = [f"2020-01-{d:02d}" for d in range(1, 32)] * 10  # 310 dates, ~3.4k characters
    p, s = fake_session([Resp([{"timestamp": "x", "value": 1}])] * 10)
    with p:
        df = dm.get_meteo(1, 2, api_key="k", time=times)
    sent = [c.kwargs["params"]["time"] for c in s.get.call_args_list]
    assert len(sent) > 1 and all(len(t) <= api._MAX_TIME_CHARS for t in sent)
    assert ",".join(sent).split(",") == times
    assert len(df) == len(sent)


def test_get_meteo_validation():
    with pytest.raises(ValueError, match="var"):
        dm.get_meteo(1, 2, api_key="k", var="slp", time="2020-01-01")
    with pytest.raises(ValueError, match="api_key"):
        dm.get_meteo(1, 2, api_key="", time="2020-01-01")
    with pytest.raises(ValueError, match="start and end"):
        dm.get_meteo(1, 2, api_key="k", start="2020-01-01")


def test_get_meteo_http_error():
    p, _ = fake_session([Resp({"detail": "bad key"}, status=401)])
    with p, pytest.raises(dm.DailyMeteoError, match="401"):
        dm.get_meteo(1, 2, api_key="k", time="2020-01-01")


def test_get_meteo_empty():
    p, _ = fake_session([Resp([])])
    with p:
        df = dm.get_meteo(1, 2, api_key="k", time="2020-01-01")
    assert df.empty and list(df.columns) == ["timestamp", "value"]


def test_get_coordinates():
    p, s = fake_session([Resp([{"lat": "44.8178", "lon": "20.4569"}])])
    with p:
        assert dm.get_coordinates("Belgrade") == (44.8178, 20.4569)
    assert s.get.call_args.kwargs["params"]["q"] == "Belgrade"
    p, _ = fake_session([Resp([])])
    with p, pytest.raises(LookupError):
        dm.get_coordinates("nowhere-xyz")
