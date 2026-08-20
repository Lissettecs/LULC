"""Diagnóstico de geometrías almacenadas vs extensión nominal (D)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

logger = logging.getLogger("reauditoria")

# km² nominales a 30 m · chip 264 px
AREA_NOMINAL_KM2 = {2: 250.9056, 3: 564.5376}
LADO_NOMINAL_M = {2: 15840.0, 3: 23760.0}
PIXEL_M = 30.0


def _pares_con_area(g: gpd.GeoDataFrame, tol_m2: float = 1.0) -> int:
    if g.empty:
        return 0
    work = g[["grid_id", "geometry"]].dropna(subset=["geometry"]).copy()
    work = work[~work.geometry.is_empty]
    if work.empty:
        return 0
    pares = gpd.sjoin(work, work, predicate="intersects", how="inner")
    pares = pares[pares["grid_id_left"].astype(str) != pares["grid_id_right"].astype(str)]
    idx = work.set_index(work["grid_id"].astype(str), drop=False)
    vistos: set[tuple[str, str]] = set()
    n = 0
    for _, row in pares.iterrows():
        a, b = str(row["grid_id_left"]), str(row["grid_id_right"])
        key = (a, b) if a < b else (b, a)
        if key in vistos:
            continue
        vistos.add(key)
        inter = idx.loc[a].geometry.intersection(idx.loc[b].geometry)
        if inter.area > tol_m2:
            n += 1
    return n


def _reconstruir_desde_indices(g: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """
    Extensión nominal en un marco local por tile: x=col_off·30 m, y=−row_off·30 m.
    No requiere leer el ráster. Los solapes son comparables dentro del mismo mgrs_dom;
    entre tiles el marco es independiente (solo se usan para conteo intra-tile + nacional
    vía reconstrucción por centroide).
    """
    geoms = []
    for _, row in g.iterrows():
        if pd.isna(row.get("col_off")) or pd.isna(row.get("row_off")):
            geoms.append(None)
            continue
        w = float(row.get("width_px") or 0) * PIXEL_M
        h = float(row.get("height_px") or 0) * PIXEL_M
        if w <= 0 or h <= 0:
            side = int(row.get("rect_side", 0) or 0)
            lado = float(row.get("rect_m") or LADO_NOMINAL_M.get(side, 0.0))
            w = h = lado
        x0 = float(row["col_off"]) * PIXEL_M
        y0 = -float(row["row_off"]) * PIXEL_M
        geoms.append(box(x0, y0 - h, x0 + w, y0))
    return gpd.GeoSeries(geoms, index=g.index)


def _reconstruir_centroide(g: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """Caja axis-aligned de lado nominal centrada en el centroide (CRS de g)."""
    geoms = []
    for _, row in g.iterrows():
        side = int(row.get("rect_side", 0) or 0)
        if side not in LADO_NOMINAL_M and "rect_m" in row and pd.notna(row["rect_m"]):
            lado = float(row["rect_m"])
        else:
            lado = float(LADO_NOMINAL_M.get(side, 0.0))
        if lado <= 0 or row.geometry is None or row.geometry.is_empty:
            geoms.append(None)
            continue
        c = row.geometry.centroid
        half = lado / 2.0
        geoms.append(box(c.x - half, c.y - half, c.x + half, c.y + half))
    return gpd.GeoSeries(geoms, index=g.index, crs=g.crs)


def diagnostico_geometrias(sel_dir: Path) -> tuple[pd.DataFrame, dict]:
    """
    Contrasta geometría almacenada vs área nominal (en CRS nativo de cada huso)
    y compara solapes almacenados vs extensiones nominales reconstruidas.
    """
    partes: list[gpd.GeoDataFrame] = []
    for huso, epsg in ((18, 32718), (19, 32719)):
        path = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
        if not path.is_file():
            continue
        g = gpd.read_file(path)
        # Área en CRS nativo del GPKG (no reproyectar antes de medir)
        if g.crs is None:
            g = g.set_crs(epsg)
        g = g.copy()
        g["area_geom_km2"] = g.geometry.area / 1e6
        g["_huso"] = huso
        partes.append(g)

    if not partes:
        raise FileNotFoundError(f"Sin GPKG de selección en {sel_dir}")

    g = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs=None)
    # CRS mixto: para sjoin nacional unificar a 32719 solo en copia de solape
    side = pd.to_numeric(g.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    g["rect_side"] = side
    if "rect_m" in g.columns:
        rm = pd.to_numeric(g["rect_m"], errors="coerce")
        g["area_nominal_km2"] = (rm / 1000.0) ** 2
    else:
        g["area_nominal_km2"] = side.map(AREA_NOMINAL_KM2)
    g["ratio_geom_nominal"] = g["area_geom_km2"] / g["area_nominal_km2"].replace(0, np.nan)

    if "area_km2" in g.columns:
        g["ratio_area_km2_nominal"] = (
            pd.to_numeric(g["area_km2"], errors="coerce") / g["area_nominal_km2"].replace(0, np.nan)
        )

    # Solape sobre geometrías almacenadas (unificadas a 32719)
    g_nat = []
    for huso, epsg in ((18, 32718), (19, 32719)):
        sub = g[g["_huso"] == huso].copy()
        if sub.empty:
            continue
        sub = gpd.GeoDataFrame(sub, geometry="geometry", crs=epsg).to_crs(32719)
        g_nat.append(sub)
    g32719 = gpd.GeoDataFrame(pd.concat(g_nat, ignore_index=True), crs="EPSG:32719")
    n_pares_almacenadas = _pares_con_area(g32719)

    # Reconstrucción A: centroide + lado nominal en 32719
    g_c = g32719.copy()
    g_c["geometry"] = _reconstruir_centroide(g32719)
    g_c = g_c.dropna(subset=["geometry"])
    n_pares_centroide = _pares_con_area(gpd.GeoDataFrame(g_c, geometry="geometry", crs="EPSG:32719"))

    # Reconstrucción B: col_off/row_off en marco local por tile (intra + concat)
    # Desplazar cada tile para evitar colisiones artificiales entre mgrs
    g_idx = g.copy()
    locales = _reconstruir_desde_indices(g_idx)
    # Offset por tile para poder concatenar
    tiles = sorted(g_idx["mgrs_dom"].astype(str).unique())
    tile_off = {t: i * 1_000_000.0 for i, t in enumerate(tiles)}
    geoms_shift = []
    for i, row in g_idx.iterrows():
        geom = locales.loc[i]
        if geom is None or geom.is_empty:
            geoms_shift.append(None)
            continue
        dx = tile_off[str(row["mgrs_dom"])]
        geoms_shift.append(box(geom.bounds[0] + dx, geom.bounds[1], geom.bounds[2] + dx, geom.bounds[3]))
    g_idx = gpd.GeoDataFrame(g_idx, geometry=geoms_shift, crs=None)
    g_idx = g_idx.dropna(subset=["geometry"])
    n_pares_indices = _pares_con_area(g_idx)

    ratio = g["ratio_geom_nominal"].dropna()
    resumen = {
        "n_rects": int(len(g)),
        "suma_geom_km2": round(float(g["area_geom_km2"].sum()), 4),
        "suma_nominal_km2": round(float(g["area_nominal_km2"].sum()), 4),
        "suma_area_km2_campo": round(float(pd.to_numeric(g["area_km2"], errors="coerce").sum()), 4)
        if "area_km2" in g.columns
        else None,
        "ratio_geom_nominal_mediana": round(float(ratio.median()), 4) if len(ratio) else None,
        "ratio_geom_nominal_p10": round(float(ratio.quantile(0.10)), 4) if len(ratio) else None,
        "ratio_geom_nominal_p90": round(float(ratio.quantile(0.90)), 4) if len(ratio) else None,
        "ratio_geom_nominal_min": round(float(ratio.min()), 4) if len(ratio) else None,
        "n_ratio_lt_099": int((ratio < 0.99).sum()) if len(ratio) else 0,
        "n_pares_area_almacenadas": int(n_pares_almacenadas),
        "n_pares_area_nominales": int(n_pares_indices),
        "n_pares_area_nominales_centroide": int(n_pares_centroide),
        "solape_difiere_reconstruccion": bool(n_pares_almacenadas != n_pares_indices),
    }

    por_side = (
        g.groupby("rect_side")["ratio_geom_nominal"]
        .agg(n="count", mediana="median", p10=lambda s: s.quantile(0.10), p90=lambda s: s.quantile(0.90), minimo="min")
        .reset_index()
    )

    cols = [
        "grid_id",
        "eco_dom_id",
        "mgrs_dom",
        "rect_side",
        "area_geom_km2",
        "area_nominal_km2",
        "ratio_geom_nominal",
    ]
    if "area_km2" in g.columns:
        cols.append("area_km2")
    peores = (
        g.sort_values("ratio_geom_nominal", ascending=True)[cols]
        .head(10)
        .reset_index(drop=True)
    )

    detalle = g[[c for c in cols if c in g.columns]].copy()
    if "ratio_area_km2_nominal" in g.columns:
        detalle["ratio_area_km2_nominal"] = g["ratio_area_km2_nominal"]

    meta = {
        "resumen": resumen,
        "por_rect_side": por_side.to_dict(orient="records"),
        "peores_10": peores.to_dict(orient="records"),
    }
    return detalle, meta
