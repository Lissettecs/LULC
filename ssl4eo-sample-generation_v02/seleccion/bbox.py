"""Restricciones geográficas por clase (bbox tamarugo)."""

from __future__ import annotations

import geopandas as gpd
import pandas as pd

from config.diccionarios import BBOX_CLASE


def filtrar_pool_bbox(df: pd.DataFrame, class_id: int) -> pd.DataFrame:
    """Excluye candidatos con presencia fuera de la bbox definida."""
    if class_id not in BBOX_CLASE or df.empty:
        return df
    col = f"en_bbox_{class_id}"
    if col not in df.columns:
        return df.iloc[0:0]
    en = df[col].astype(bool)
    pct = pd.to_numeric(df.get(f"pct_{class_id}", 0), errors="coerce").fillna(0)
    return df[en & (pct > 0)].copy()


def candidatos_fuera_bbox(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Rectángulos con presencia de clase bbox fuera del rango geográfico."""
    partes = []
    for cid in BBOX_CLASE:
        fuera_col = f"pct_{cid}_fuera_bbox"
        if fuera_col not in gdf.columns:
            continue
        fuera = pd.to_numeric(gdf[fuera_col], errors="coerce").fillna(0)
        hit = gdf[fuera > 0].copy()
        if not hit.empty:
            hit["clase_bbox"] = cid
            partes.append(hit)
    if not partes:
        return gpd.GeoDataFrame(columns=gdf.columns, crs=gdf.crs)
    return gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), geometry="geometry", crs=gdf.crs)
