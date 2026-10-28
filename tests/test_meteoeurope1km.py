import hashlib

import pytest

from dailymeteo import meteoeurope1km as meu


def test_wanted_day_spans_decades():
    assert meu._wanted("tmax", "day", [1970, 1971], []) == [
        ("tmax_1961_1970", "tmax_1970_equi7.zip"),
        ("tmax_1971_1980", "tmax_1971_equi7.zip"),
    ]


def test_wanted_aggregates():
    agg = "prcp_agg_ltm_1961_2020"
    assert meu._wanted("prcp", "mon", [1961, 1965, 2020], []) == [
        (agg, "prcp_mon_1961_1970_equi7.zip"), (agg, "prcp_mon_2011_2020_equi7.zip")]
    assert meu._wanted("prcp", "ltm_mon_ann", None, ["1991-2020"]) == [(agg, "prcp_ltm_mon_ann_19912020_equi7.zip")]
    assert meu._wanted("prcp", "ann", None, []) == [(agg, "prcp_ann_1961_2020_equi7.zip")]


@pytest.mark.parametrize("kw,msg", [
    ({"var": "x"}, "var"),
    ({"product": "x", "years": [2000]}, "product"),
    ({"var": "slp", "product": "mon", "years": [2000]}, "slp"),
    ({"product": "day"}, "years"),
    ({"product": "day", "years": [1960]}, "between"),
    ({"product": "ltm_day", "period": "1971-2000"}, "period"),
])
def test_files_validation(kw, msg):
    with pytest.raises(ValueError, match=msg):
        meu.files(**kw)


@pytest.mark.network
def test_catalog_live():
    cat = meu.catalog()
    assert len(cat) == 34
    assert {"tmax_1961_1970", "slp_2011_2020", "prcp_agg_ltm_1961_2020"} <= set(cat.record)


@pytest.mark.network
def test_files_live():
    t = meu.files(var="tmean", product="day", years=[1970, 1971])
    assert t.file.tolist() == ["tmean_1970_equi7.zip", "tmean_1971_equi7.zip"]
    assert t.record.tolist() == ["tmean_1961_1970", "tmean_1971_1980"]
    assert (t["size"] > 1e9).all() and t.md5.str.len().eq(32).all()


@pytest.mark.network
def test_download_resume_and_skip(tmp_path):
    # smallest archive in the dataset (~52 MB); start from a truncated .part to exercise resume
    row = meu.files(var="tmax", product="ltm_diff").iloc[0]
    meu._fetch(row.url, tmp_path / (row.file + ".part"), 5_000_000, retries=3, progress=False)
    part = tmp_path / (row.file + ".part")
    part.write_bytes(part.read_bytes()[:3_000_000])
    t = meu.download(var="tmax", product="ltm_diff", dest_dir=tmp_path, unzip=True, progress=False)
    path = tmp_path / row.file
    assert path.exists() and not part.exists()
    assert hashlib.md5(path.read_bytes()).hexdigest() == row.md5
    assert any(p.suffix == ".tif" for p in tmp_path.iterdir())
    again = meu.download(var="tmax", product="ltm_diff", dest_dir=tmp_path, progress=False)
    assert again.path.tolist() == t.path.tolist()
