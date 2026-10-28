"""Python client for DailyMeteo: point data from the DailyMeteo API and the MeteoEurope1km dataset on Zenodo."""

__version__ = "0.1.0"

from . import meteoeurope1km  # noqa: E402
from ._http import DailyMeteoError  # noqa: E402
from .api import get_coordinates, get_meteo  # noqa: E402

__all__ = ["DailyMeteoError", "get_coordinates", "get_meteo", "meteoeurope1km", "__version__"]
