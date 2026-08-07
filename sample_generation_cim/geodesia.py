"""Áreas exactas de cuadrángulos y píxeles en EPSG:4326.

En la grilla nativa del landcover el píxel mide 0.00026949° de lado, que son
~30 m en latitud pero ~30·cos(lat) m en longitud. Su área en el suelo cae de
0.0854 ha en Arica a 0.0506 ha en Magallanes, así que contar píxeles no es medir
superficie: hay que ponderar cada fila del ráster por su área.

El área de un cuadrángulo del elipsoide entre dos paralelos es exactamente

    A = R_q² · Δλ · (sin β₂ − sin β₁)

con β la latitud autálica y R_q el radio autálico. No es una aproximación
esférica: la latitud autálica es justamente el cambio de variable que hace exacta
esa fórmula.

Se usa en lugar de pyproj.Geod porque Geod une los vértices del polígono con
geodésicas, y una geodésica entre dos puntos del mismo paralelo no sigue el
paralelo. Para una celda de 528 px la diferencia es de 0.1 m² —irrelevante— pero
obliga a densificar los bordes para comparar. scripts/02_verificar_insumos.py
contrasta esta fórmula contra Geod con los bordes densificados y coinciden a
1e-13. Este módulo es la única fuente de áreas del pipeline, así que la grilla y
la caracterización informan siempre la misma cifra.
"""

from __future__ import annotations

import numpy as np
from pyproj import Geod

GEOD = Geod(ellps="WGS84")

# WGS84
A_WGS84 = 6_378_137.0
F_WGS84 = 1 / 298.257223563
E2 = F_WGS84 * (2 - F_WGS84)
E = np.sqrt(E2)


def _q(lat_rad: np.ndarray) -> np.ndarray:
    """Función auxiliar de la latitud autálica (Snyder, 3-12)."""
    s = np.sin(lat_rad)
    return (1 - E2) * (
        s / (1 - E2 * s**2) - np.log((1 - E * s) / (1 + E * s)) / (2 * E)
    )


_Q_POLO = float(_q(np.array(np.pi / 2)))
RADIO_AUTALICO_M = A_WGS84 * np.sqrt(_Q_POLO / 2)


def _sin_autalica(lat_deg: np.ndarray) -> np.ndarray:
    return _q(np.deg2rad(lat_deg)) / _Q_POLO


def areas_filas_m2(lat_norte_deg: float, res_deg: float, n_filas: int) -> np.ndarray:
    """Área en m² de un píxel en cada una de las n_filas, de norte a sur.

    Todos los píxeles de una misma fila tienen la misma área, así que basta un
    vector de largo n_filas.
    """
    bordes = lat_norte_deg - res_deg * np.arange(n_filas + 1, dtype=np.float64)
    sin_b = _sin_autalica(bordes)
    dlambda = np.deg2rad(res_deg)
    return RADIO_AUTALICO_M**2 * dlambda * (sin_b[:-1] - sin_b[1:])


def areas_pixel_ha(lat_norte_deg: float, res_deg: float, n_filas: int) -> np.ndarray:
    """Área en ha por fila, con forma (n_filas, 1) para difundir sobre las columnas."""
    return (areas_filas_m2(lat_norte_deg, res_deg, n_filas) / 10_000.0).reshape(-1, 1)


def latitudes_centro(lat_norte_deg: float, res_deg: float, n_filas: int) -> np.ndarray:
    """Latitud del centro de cada fila, con forma (n_filas, 1)."""
    return (
        lat_norte_deg - res_deg * (np.arange(n_filas, dtype=np.float64) + 0.5)
    ).reshape(-1, 1)


def area_celda_m2(lat_norte_deg: float, res_deg: float, n_lado: int) -> float:
    """Área total de una celda cuadrada de n_lado x n_lado píxeles."""
    return float(areas_filas_m2(lat_norte_deg, res_deg, n_lado).sum()) * n_lado


def ancho_alto_m(lat_norte_deg: float, res_deg: float, n_lado: int) -> tuple[float, float]:
    """Ancho (medido por el centro de la celda) y alto, en metros.

    Sirve para dimensionar la celda: en EPSG:4326 es siempre más angosta que alta.
    """
    lado = res_deg * n_lado
    lat_c = lat_norte_deg - lado / 2
    _, _, ancho = GEOD.inv(0.0, lat_c, lado, lat_c)
    _, _, alto = GEOD.inv(0.0, lat_norte_deg - lado, 0.0, lat_norte_deg)
    return float(ancho), float(alto)
