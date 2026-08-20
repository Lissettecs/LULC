"""Carga y normalización de la caracterización CIM para la selección.

El algoritmo de v02 espera columnas que en CIM se llaman distinto o no existen
(`rect_side`, `mgrs_dom`, `en_bbox_3`). En vez de reescribir pools/balanceo/
selector, se sintetizan aquí a partir de lo que sí hay: `n_chips`, `cim_name` y
la geometría en EPSG:4326.
"""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import pandas as pd
from shapely.geometry import box

from config import params_seleccion as P
from config.diccionarios import BBOX_CLASE


def ruta_caracterizacion(grid_run: Path, escala: str) -> Path:
    return grid_run / f"caracterizacion_cim_{escala}.gpkg"


def cargar_escala(grid_run: Path, escala: str) -> gpd.GeoDataFrame:
    """Lee una caracterización nacional y la deja lista para el selector."""
    path = ruta_caracterizacion(grid_run, escala)
    if not path.is_file():
        raise FileNotFoundError(f"Caracterización faltante: {path}")
    gdf = gpd.read_file(path)
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        gdf = gdf.to_crs(4326)
    return normalizar_grilla(gdf, escala)


def normalizar_grilla(gdf: gpd.GeoDataFrame, escala: str) -> gpd.GeoDataFrame:
    out = gdf.copy()
    if escala == "2x2":
        out["rect_side"] = 2
        out["grid_mode"] = "homogeneo"
        out["n_chips"] = out.get("n_chips", 2)
    elif escala == "3x3":
        out["rect_side"] = 3
        out["grid_mode"] = "mixto"
        out["n_chips"] = out.get("n_chips", 3)
    else:
        raise ValueError(f"Escala no reconocida: {escala!r}")

    # balanceo.py / split agrupan por mgrs_dom; en CIM la unidad espacial es la carta
    if "mgrs_dom" not in out.columns:
        if "cim_name" not in out.columns:
            raise ValueError("La grilla necesita cim_name o mgrs_dom")
        out["mgrs_dom"] = out["cim_name"].astype(str)

    if "utm_zone" not in out.columns and "cim_zona" in out.columns:
        out["utm_zone"] = out["cim_zona"]

    # Celdas oceánicas/sin LULC: espacial.py antiguo omitía eco_dom_id → NaN al consolidar
    if "eco_dom_id" in out.columns:
        out["eco_dom_id"] = pd.to_numeric(out["eco_dom_id"], errors="coerce").fillna(0).astype(int)

    out = _anotar_bbox(out)
    return out


def _anotar_bbox(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Marca en_bbox_{cid} proyectando centroides a la CRS del BBOX_CLASE."""
    if gdf.empty or "geometry" not in gdf.columns:
        return gdf
    out = gdf.copy()
    # Centroid en CRS métrico para evitar el warning y sesgos en 4326
    metric = out.to_crs(P.CRS_PROCESO)
    centros_metric = metric.geometry.centroid
    for cid, bb in BBOX_CLASE.items():
        epsg = int(bb["epsg"])
        pts = gpd.GeoSeries(centros_metric, crs=P.CRS_PROCESO)
        if epsg != int(P.CRS_PROCESO.split(":")[-1]):
            pts = pts.to_crs(epsg)
        dentro = (
            (pts.x >= bb["xmin"]) & (pts.x <= bb["xmax"])
            & (pts.y >= bb["ymin"]) & (pts.y <= bb["ymax"])
        )
        out[f"en_bbox_{cid}"] = dentro.fillna(False).to_numpy()
        pct = pd.to_numeric(out.get(f"pct_{cid}", 0), errors="coerce").fillna(0)
        out[f"pct_{cid}_fuera_bbox"] = pct.where(~dentro, 0.0)
    return out


def cargar_parejas(grid_run: Path) -> tuple[gpd.GeoDataFrame, gpd.GeoDataFrame]:
    """(hom 2x2, mix 3x3) en EPSG:4326, listos para `ejecutar_seleccion`."""
    return cargar_escala(grid_run, "2x2"), cargar_escala(grid_run, "3x3")
