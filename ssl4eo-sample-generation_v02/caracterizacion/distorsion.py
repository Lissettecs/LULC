"""Distorsión de área UTM en bordes de huso."""

from __future__ import annotations

import geopandas as gpd

from config import params_caracterizacion as P

_R = 6_378_137.0


def factor_area_utm(geom, utm_zone: int) -> tuple[float, bool]:
    """
    Factor de escala de área UTM en el centroide de la celda.

    Retorna (factor_area, flag_distorsion_borde).
    """
    epsg = P.UTM_EPSG[utm_zone]
    g = gpd.GeoDataFrame([1], geometry=[geom], crs=f"EPSG:{epsg}")
    cx = g.geometry.centroid.iloc[0].x
    e = cx - 500_000.0
    k = 0.9996 * (1.0 + (e / _R) ** 2 / 2.0)
    factor = k**2
    flag = abs(factor - 1.0) > P.MAX_DISTORSION_UTM
    return factor, flag
