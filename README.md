# dailymeteo

Python client for meteorological data from [DailyMeteo](https://app.dailymeteo.com/):

- **`get_meteo`**: daily, monthly or annual values and long-term means for a location, World, 1961 to the present, from the DailyMeteo API. Monthly, annual and long-term mean values are free; daily data need an API key and are billed per returned day.
- **`meteoeurope1km`**: download of the **MeteoEurope1km** gridded dataset from Zenodo. It covers Europe at 1 km for 1961–2020: TMAX, TMIN, TMEAN, PRCP and SLP, with aggregates and climate normals.

It is the Python counterpart of `get_meteo`, `get_coordinates` and `get_meteoeurope1km` in the R package [meteo](https://cran.r-project.org/package=meteo). Spatial interpolation (RFSI, STRK) is available only in R.

## Installation

```
pip install dailymeteo
```

## Point data from the DailyMeteo API

```python
import dailymeteo as dm

lat, lon = dm.get_coordinates("Belgrade")
df = dm.get_meteo(lat, lon, var="tmean",     # "tmax", "tmin", "prcp"
                  time_scale="mon",           # "ann"; "day" needs api_key="..." from https://app.dailymeteo.com/
                  start="2020-01", end="2020-12")
# or time=["2020-01", "2020-07"]

# climate normals 1961-1990 and 1991-2020 for July
dm.get_meteo(lat, lon, var="tmax", agg_level="ltm", time_scale="mon", time="07")
```

The result is a `pandas.DataFrame` with columns `timestamp` and `value`. Locations without data (e.g. sea) give `NaN`.

## MeteoEurope1km gridded dataset

```python
from dailymeteo import meteoeurope1km as meu

# list archives: one ZIP per year with daily Cloud-Optimized GeoTIFFs
meu.files(var="tmean", product="day", years=[2001, 2002])

# download, verify MD5, unzip; interrupted downloads are resumed
meu.download(var="tmean", product="day", years=[2001, 2002], dest_dir="meteoeurope1km", unzip=True)

# aggregates and climate normals
meu.download(var="prcp", product="ltm_diff", dest_dir="meteoeurope1km")
```

| `product` | Content | Archives |
|---|---|---|
| `day` | daily data | one per year (about 1–3.5 GB) |
| `mon` | monthly aggregates | one per decade |
| `ann` | annual aggregates, 1961–2020 | one |
| `ltm_day` | daily climate normals | one per period (`period="1961-1990"` / `"1991-2020"`) |
| `ltm_mon_ann` | monthly and annual climate normals | one per period |
| `ltm_diff` | difference of normals, 1991–2020 minus 1961–1990 | one |

Aggregates are means for temperatures and sums for precipitation. For SLP only daily data are available.

Rasters are in the Equi7 Europe projection (EPSG:27704) at 1000 m. Values are Int16 in tenths of the unit, so divide by 10 to get °C, mm or hPa. NoData is −9999.

`meu.catalog()` lists all Zenodo records of the dataset.

## Citation

Sekulić, A., & Kilibarda, M. (2026). *MeteoEurope1km (1961–2020): daily gridded meteorological dataset for Europe at a 1-km spatial resolution*. Zenodo. https://doi.org/10.5281/zenodo.23264155

## License

GPL-2.0-or-later, the same as the R package `meteo`.
