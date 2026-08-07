"""Tracker espacial y utilidades de selección exclusiva."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd


class TrackerEspacial:
    """
    Excluye candidatos que se solapan con rectángulos ya elegidos.

    Es un tracker GLOBAL de la corrida: una sola instancia vive durante
    `ejecutar_seleccion` y se comparte entre ecorregiones, fases y relleno.
    Así se evita solape 2x2↔3x3 y entre ecorregiones vecinas.
    """

    def __init__(self, crs, max_overlap_pct: float = 0.0, tol_m2: float = 1.0):
        self.crs = crs
        self.max_overlap_pct = max_overlap_pct
        self.tol_m2 = tol_m2
        self._selected: gpd.GeoDataFrame | None = None

    def _vacio(self) -> bool:
        return self._selected is None or self._selected.empty

    def _como_gdf(self, df: pd.DataFrame) -> gpd.GeoDataFrame:
        if isinstance(df, gpd.GeoDataFrame):
            return df
        return gpd.GeoDataFrame(
            df.drop(columns="geometry", errors="ignore"),
            geometry=df["geometry"].values,
            crs=self.crs,
        )

    def _metric_gdf(self, df: pd.DataFrame) -> gpd.GeoDataFrame:
        gdf = self._como_gdf(df)
        if gdf.crs is None:
            return gdf
        if not gdf.crs.is_geographic:
            return gdf
        if "utm_epsg" in gdf.columns:
            epsg = int(pd.to_numeric(gdf["utm_epsg"], errors="coerce").dropna().iloc[0])
            return gdf.to_crs(epsg)
        if "utm_zone" in gdf.columns:
            zone = int(pd.to_numeric(gdf["utm_zone"], errors="coerce").dropna().iloc[0])
            return gdf.to_crs(32700 + zone)
        return gdf.to_crs(32719)

    def filtrar(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._vacio() or "geometry" not in df.columns:
            return df
        gdf = self._metric_gdf(df)
        if not self._vacio() and self._selected.crs != gdf.crs:
            gdf = gdf.to_crs(self._selected.crs)
        geoms = gdf.geometry.values
        areas = gdf.geometry.area.to_numpy()
        sidx = self._selected.sindex
        sel_geoms = self._selected.geometry.values
        keep = np.ones(len(df), dtype=bool)
        for i, geom in enumerate(geoms):
            area = areas[i]
            if area <= 0:
                keep[i] = False
                continue
            ovlp = 0.0
            for j in sidx.intersection(geom.bounds):
                inter = geom.intersection(sel_geoms[j])
                if inter.is_empty:
                    continue
                ovlp += inter.area
                if ovlp > self.tol_m2 and ovlp / area > self.max_overlap_pct:
                    keep[i] = False
                    break
        return df.loc[keep].copy()

    def registrar(self, df: pd.DataFrame) -> None:
        if df.empty or "geometry" not in df.columns:
            return
        chunk = self._metric_gdf(df)[["grid_id", "geometry"]].copy()
        chunk["grid_id"] = chunk["grid_id"].astype(str)
        if self._vacio():
            self._selected = chunk
            return
        if self._selected.crs != chunk.crs:
            chunk = chunk.to_crs(self._selected.crs)
        existentes = set(self._selected["grid_id"])
        chunk = chunk[~chunk["grid_id"].isin(existentes)]
        if chunk.empty:
            return
        self._selected = pd.concat([self._selected, chunk], ignore_index=True)


def sin_ids_usados(
    df: pd.DataFrame,
    usados: set[str],
    tracker: TrackerEspacial | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    if usados:
        df = df[~df["grid_id"].astype(str).isin(usados)].copy()
    if tracker is not None:
        df = tracker.filtrar(df)
    return df


def deduplicar_espacial(
    df: pd.DataFrame,
    tracker: TrackerEspacial | None,
    max_n: int | None = None,
) -> pd.DataFrame:
    if df.empty or tracker is None:
        return df.head(max_n) if max_n else df
    kept: list[pd.Series] = []
    for _, row in df.iterrows():
        uno = pd.DataFrame([row])
        if tracker.filtrar(uno).empty:
            continue
        kept.append(row)
        tracker.registrar(uno)
        if max_n and len(kept) >= max_n:
            break
    if not kept:
        return df.iloc[0:0]
    return pd.DataFrame(kept)


def convertir_numericos(gdf: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    out = gdf.copy()
    for c in cols:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce").fillna(0)
    return out


def mascara_ecorregion_valida(gdf: pd.DataFrame) -> pd.Series:
    name = gdf.get("eco_dom_name", pd.Series("", index=gdf.index)).astype(str).str.strip()
    eid = pd.to_numeric(gdf.get("eco_dom_id", -9999), errors="coerce").fillna(-9999)
    return name.ne("sin_nombre") & name.ne("") & name.ne("nan") & (eid > 0)
