"""MeteoEurope1km on Zenodo: daily gridded meteorological data for Europe at 1 km, 1961-2020.

Sekulić, A., & Kilibarda, M. (2026). MeteoEurope1km (1961-2020): daily gridded meteorological
dataset for Europe at a 1-km spatial resolution. Zenodo. https://doi.org/10.5281/zenodo.23264155

The dataset is one Zenodo record per variable and decade with daily data (one ZIP per year), and one
record per variable with monthly/annual aggregates and climate normals. Records are found through
``catalog.csv`` in the umbrella record, whose concept DOI always resolves to the latest version.
"""
from __future__ import annotations

import hashlib
import io
import time
import zipfile
from collections.abc import Iterable
from pathlib import Path

import pandas as pd
import requests

from ._http import DailyMeteoError, session

ZENODO_API = "https://zenodo.org/api/records/"
CONCEPT_RECORD = "23264155"
DOI = "10.5281/zenodo.23264155"

VARS = ("tmax", "tmin", "tmean", "prcp", "slp")
PRODUCTS = ("day", "mon", "ann", "ltm_day", "ltm_mon_ann", "ltm_diff")
PERIODS = ("1961-1990", "1991-2020")
FIRST_YEAR, LAST_YEAR = 1961, 2020

CHUNK = 1 << 20


def _record(record_id: str) -> dict:
    r = session().get(ZENODO_API + record_id, timeout=120)
    if not r.ok:
        raise DailyMeteoError(f"Zenodo returned {r.status_code} for record {record_id}")
    return r.json()


def catalog() -> pd.DataFrame:
    """All records of MeteoEurope1km: ``record``, ``title``, ``doi`` and Zenodo ``id``."""
    files = {f["key"]: f for f in _record(CONCEPT_RECORD)["files"]}
    if "catalog.csv" not in files:
        raise DailyMeteoError("catalog.csv not found in the MeteoEurope1km umbrella record")
    r = session().get(files["catalog.csv"]["links"]["self"], timeout=120)
    r.raise_for_status()
    cat = pd.read_csv(io.StringIO(r.content.decode("utf-8")))
    cat["id"] = cat["doi"].str.rsplit(".", n=1).str[-1]
    return cat


def _decade(year: int) -> str:
    d = FIRST_YEAR + 10 * ((year - FIRST_YEAR) // 10)
    return f"{d}_{d + 9}"


def _wanted(var: str, product: str, years: list[int] | None, periods: list[str]) -> list[tuple[str, str]]:
    """(record, file) pairs for the request."""
    if product == "day":
        return [(f"{var}_{_decade(y)}", f"{var}_{y}_equi7.zip") for y in years]
    agg = f"{var}_agg_ltm_1961_2020"
    if product == "mon":
        return [(agg, f"{var}_mon_{d}_equi7.zip") for d in dict.fromkeys(_decade(y) for y in years)]
    if product == "ann":
        return [(agg, f"{var}_ann_1961_2020_equi7.zip")]
    if product == "ltm_diff":
        return [(agg, f"{var}_ltm_diff_equi7.zip")]
    return [(agg, f"{var}_{product}_{p.replace('-', '')}_equi7.zip") for p in periods]


def files(
    var: str = "tmean",
    product: str = "day",
    years: Iterable[int] | None = None,
    period: str | Iterable[str] | None = None,
) -> pd.DataFrame:
    """List the archives matching the request, without downloading.

    Parameters
    ----------
    var
        ``"tmax"``, ``"tmin"``, ``"tmean"``, ``"prcp"`` or ``"slp"`` (``"slp"``: daily data only).
    product
        ``"day"`` (one archive per year), ``"mon"`` (one per decade), ``"ann"`` (1961-2020),
        ``"ltm_day"``, ``"ltm_mon_ann"`` (climate normals) or ``"ltm_diff"`` (1991-2020 minus 1961-1990).
    years
        Years 1961-2020; required for ``"day"`` and ``"mon"``.
    period
        ``"1961-1990"`` and/or ``"1991-2020"`` for ``"ltm_day"`` and ``"ltm_mon_ann"``; default both.

    Returns
    -------
    pandas.DataFrame
        Columns ``record``, ``doi``, ``file``, ``size`` (bytes), ``md5`` and ``url``.
    """
    if var not in VARS:
        raise ValueError(f"var must be one of {', '.join(VARS)}; got {var!r}")
    if product not in PRODUCTS:
        raise ValueError(f"product must be one of {', '.join(PRODUCTS)}; got {product!r}")
    if var == "slp" and product != "day":
        raise ValueError('only daily data (product="day") are available for slp')
    ys = None
    if product in ("day", "mon"):
        if years is None:
            raise ValueError("years is required for product 'day' and 'mon'")
        ys = sorted({int(y) for y in ([years] if isinstance(years, int) else years)})
        if not ys or ys[0] < FIRST_YEAR or ys[-1] > LAST_YEAR:
            raise ValueError(f"years must be between {FIRST_YEAR} and {LAST_YEAR}")
    periods = list(PERIODS) if period is None else ([period] if isinstance(period, str) else list(period))
    if bad := [p for p in periods if p not in PERIODS]:
        raise ValueError(f"period must be one of {', '.join(PERIODS)}; got {bad}")

    wanted = _wanted(var, product, ys, periods)
    cat = catalog().set_index("record")
    rows = []
    for rec in dict.fromkeys(r for r, _ in wanted):
        if rec not in cat.index:
            raise DailyMeteoError(f"record {rec} not found in the MeteoEurope1km catalog")
        entries = {f["key"]: f for f in _record(cat.at[rec, "id"])["files"]}
        for r, key in wanted:
            if r != rec:
                continue
            if key not in entries:
                raise DailyMeteoError(f"file {key} not found in record {rec}")
            f = entries[key]
            rows.append({"record": rec, "doi": cat.at[rec, "doi"], "file": key, "size": f["size"],
                         "md5": f["checksum"].removeprefix("md5:"), "url": f["links"]["self"]})
    return pd.DataFrame(rows, columns=["record", "doi", "file", "size", "md5", "url"])


def _md5(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(CHUNK), b""):
            h.update(b)
    return h.hexdigest()


def _fetch(url: str, part: Path, size: int, retries: int, progress: bool) -> None:
    """Download into ``part``, resuming after dropped connections (HTTP Range)."""
    for attempt in range(retries + 1):
        have = part.stat().st_size if part.exists() else 0
        if have >= size:
            return
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with session().get(url, headers=headers, stream=True, timeout=(30, 300)) as r:
                if r.status_code == 200 and have:
                    have = 0  # server ignored Range; start over
                elif r.status_code not in (200, 206):
                    raise DailyMeteoError(f"Zenodo returned {r.status_code} for {url}")
                with part.open("ab" if have else "wb") as f:
                    done, t0 = have, time.time()
                    for b in r.iter_content(CHUNK):
                        f.write(b)
                        done += len(b)
                        if progress:
                            mbps = (done - have) / max(time.time() - t0, 1e-3) / 1e6
                            print(f"\r  {done / 1e6:,.0f} / {size / 1e6:,.0f} MB  {mbps:.1f} MB/s", end="", flush=True)
            if progress:
                print()
        except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError) as e:
            if attempt == retries:
                raise DailyMeteoError(f"download failed after {retries} retries: {e}") from e
            if progress:
                print(f"\n  connection dropped ({type(e).__name__}), resuming")
            time.sleep(min(60, 5 * (attempt + 1)))


def download(
    var: str = "tmean",
    product: str = "day",
    years: Iterable[int] | None = None,
    period: str | Iterable[str] | None = None,
    dest_dir: str | Path = ".",
    unzip: bool = False,
    overwrite: bool = False,
    retries: int = 20,
    progress: bool = True,
) -> pd.DataFrame:
    """Download MeteoEurope1km archives and verify their MD5 checksums.

    Interrupted downloads are resumed. Archives already in ``dest_dir`` with a matching checksum are
    skipped unless ``overwrite=True``. Arguments ``var``, ``product``, ``years`` and ``period`` are as in
    :func:`files`. Returns the :func:`files` table with an added ``path`` column.
    """
    table = files(var=var, product=product, years=years, period=period)
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    paths = []
    for row in table.itertuples(index=False):
        path, part = dest / row.file, dest / (row.file + ".part")
        if path.exists() and not overwrite and _md5(path) == row.md5:
            if progress:
                print(f"{row.file}: already downloaded")
        else:
            if progress:
                print(f"{row.file}: {row.size / 1e6:,.0f} MB")
            if overwrite:
                part.unlink(missing_ok=True)
            _fetch(row.url, part, row.size, retries, progress)
            if _md5(part) != row.md5:
                part.unlink()
                raise DailyMeteoError(f"MD5 checksum mismatch for {row.file}; the partial file was removed")
            part.replace(path)
        if unzip:
            with zipfile.ZipFile(path) as z:
                z.extractall(dest)
        paths.append(str(path))
    return table.assign(path=paths)
