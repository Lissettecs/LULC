"""Caracterización de una carta CIM y consolidación nacional.

La unidad de paralelización es la carta: se lee su ventana una sola vez y se
recorren sus celdas en memoria. Cada carta escribe
por_carta/{CARTA}_{escala}.parquet, con la escala nombrada 2x2 o 3x3, y la
consolidación junta todas en un GeoPackage con la geometría de la grilla.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

import geodesia
from caracterizacion.composicion import (
    composicion_por_celda,
    pctp_por_periodo,
    validar_suma_composicion,
)
from caracterizacion.espacial import indice_heterogeneidad, metricas_espaciales
from caracterizacion.leer import LectorCarta
from caracterizacion.temporal import agregar_a_bloques, metricas_temporales
from config import params_caracterizacion as P
from config import params_grilla as PG
from grilla.construir import cargar_grilla

COLS_GRILLA = [
    "grid_id", "cim_name", "cim_zona", "celda_px", "n_chips",
    "px_col_off", "px_row_off", "col_idx", "row_idx",
    "lon_min", "lat_min", "lon_max", "lat_max", "lon_centro", "lat_centro",
    "ancho_km", "alto_km", "razon_ancho_alto", "area_km2", "area_ha",
]


def caracterizar_celda(celda: dict, lector: LectorCarta) -> dict:
    """Fila de caracterización de una celda."""
    stack, eco = lector.celda(celda["px_col_off"], celda["px_row_off"])
    n = lector.celda_px
    lat_n = lector.lat_norte(celda["px_row_off"])
    res = lector.ref["res"]

    area_ha = geodesia.areas_pixel_ha(lat_n, res, n)
    lats = geodesia.latitudes_centro(lat_n, res, n)

    fila: dict = {k: celda[k] for k in COLS_GRILLA if k in celda}
    fila["area_ha_pixel_min"] = round(float(area_ha.min()), 6)
    fila["area_ha_pixel_max"] = round(float(area_ha.max()), 6)

    fila.update(composicion_por_celda(stack, area_ha))
    fila.update(pctp_por_periodo(stack, area_ha, P.PERIODOS, P.START_YEAR))
    fila.update(metricas_espaciales(eco, stack, area_ha, lats))

    bloques = agregar_a_bloques(stack, P.STATS_BLOQUE_PX)
    fila["stats_bloque_px"] = P.STATS_BLOQUE_PX
    fila["stats_bloques"] = int(bloques.shape[1] * bloques.shape[2])
    fila.update(
        metricas_temporales(bloques, P.START_YEAR, P.UMBRAL_ANIO_ESTABLE, P.PERIODOS)
    )

    fila["heterogeneidad_idx"] = indice_heterogeneidad(
        float(fila.get("shannon_idx", 0.0)), int(fila.get("n_mode_classes", 0))
    )
    return fila


def procesar_carta(
    cim_name: str,
    celda_px: int,
    run_dir: Path,
    logger: logging.Logger,
    resume: bool = True,
) -> Path | None:
    """Caracteriza todas las celdas de una carta para un tamaño de celda."""
    escala = PG.etiqueta(celda_px)
    destino = run_dir / "por_carta" / f"{cim_name}_{escala}.parquet"
    destino.parent.mkdir(parents=True, exist_ok=True)
    if resume and destino.is_file():
        logger.info("[%s %s] ya existe, se omite", cim_name, escala)
        return destino

    celdas = cargar_grilla(celda_px, cim_name)
    if celdas.empty:
        logger.warning("[%s %s] sin celdas en la grilla", cim_name, escala)
        return None

    t0 = time.time()
    lector = LectorCarta(celdas, celda_px)
    logger.info(
        "[%s %s] ventana %dx%d px, %d años, %.0f MB leídos en %.1f s",
        cim_name, escala, lector.width, lector.height, len(lector.anios),
        lector.memoria_mb, time.time() - t0,
    )

    filas, malas = [], 0
    for celda in celdas.drop(columns=["geometry"]).to_dict("records"):
        fila = caracterizar_celda(celda, lector)
        if not validar_suma_composicion(fila, logger):
            malas += 1
        filas.append(fila)

    df = pd.DataFrame(filas)
    # Las columnas pct_/ha_/pctp_ dependen de las clases presentes; las celdas que
    # no tienen una clase deben quedar en 0, no en NaN.
    dinamicas = [c for c in df.columns if c.split("_")[0] in ("pct", "ha", "pctp")]
    df[dinamicas] = df[dinamicas].fillna(0.0)
    df.to_parquet(destino, index=False)

    logger.info(
        "[%s %s] %d celdas en %.1f s (%d con suma fuera de rango) -> %s",
        cim_name, escala, len(df), time.time() - t0, malas, destino.name,
    )
    return destino


def consolidar(
    celda_px: int, run_dir: Path, logger: logging.Logger
) -> tuple[Path, Path]:
    """Junta todos los parquet por carta y les pega la geometría de la grilla."""
    escala = PG.etiqueta(celda_px)
    partes = sorted((run_dir / "por_carta").glob(f"*_{escala}.parquet"))
    if not partes:
        raise FileNotFoundError(f"Sin parquet de {escala} en {run_dir / 'por_carta'}")

    df = pd.concat([pd.read_parquet(p) for p in partes], ignore_index=True)
    dinamicas = [c for c in df.columns if c.split("_")[0] in ("pct", "ha", "pctp")]
    df[dinamicas] = df[dinamicas].fillna(0.0)

    grilla = cargar_grilla(celda_px)[["grid_id", "geometry"]]
    gdf = grilla.merge(df, on="grid_id", how="inner")
    if len(gdf) != len(df):
        logger.warning(
            "%d filas caracterizadas no encontraron geometría", len(df) - len(gdf)
        )
    gdf = gpd.GeoDataFrame(gdf, geometry="geometry", crs="EPSG:4326")
    gdf = gdf.sort_values(["cim_name", "row_idx", "col_idx"]).reset_index(drop=True)

    salida_gpkg = run_dir / f"caracterizacion_cim_{escala}.gpkg"
    salida_csv = run_dir / f"caracterizacion_cim_{escala}.csv"
    gdf.to_file(salida_gpkg, layer=f"caract_{escala}", driver="GPKG")
    gdf.drop(columns=["geometry"]).to_csv(salida_csv, index=False)

    logger.info(
        "Consolidado %s: %d celdas de %d cartas, %d columnas -> %s",
        escala, len(gdf), gdf["cim_name"].nunique(), len(gdf.columns), salida_gpkg.name,
    )
    return salida_gpkg, salida_csv


def resumen_consolidado(celda_px: int, run_dir: Path) -> dict:
    """Cifras de control del consolidado, para el summary de la corrida."""
    csv = run_dir / f"caracterizacion_cim_{PG.etiqueta(celda_px)}.csv"
    df = pd.read_csv(csv, low_memory=False)
    pct = [
        c for c in df.columns
        if c.startswith("pct_") and c.split("_")[1].isdigit()
    ]
    suma = df[pct].sum(axis=1)
    # Las celdas enteramente oceánicas o fuera del mosaico no tienen área válida y
    # su composición es legítimamente 0: no se les exige sumar 100.
    con_dato = df["area_valida_ha"] > 0
    suma_con_dato = suma[con_dato]
    return {
        "escala": PG.etiqueta(celda_px),
        "celda_px": celda_px,
        "n_celdas": int(len(df)),
        "n_cartas": int(df["cim_name"].nunique()),
        "n_columnas": int(len(df.columns)),
        "clases_presentes": sorted(int(c.split("_")[1]) for c in pct),
        "n_celdas_con_area_valida": int(con_dato.sum()),
        "n_celdas_sin_area_valida": int((~con_dato).sum()),
        "suma_pct_min": round(float(suma_con_dato.min()), 4) if con_dato.any() else None,
        "suma_pct_max": round(float(suma_con_dato.max()), 4) if con_dato.any() else None,
        "celdas_suma_fuera_de_rango": int(
            ((suma_con_dato < 99.9) | (suma_con_dato > 100.1)).sum()
        ),
        "valid_area_pct_min": round(float(df["valid_area_pct"].min()), 4),
        "valid_area_pct_media": round(float(df["valid_area_pct"].mean()), 4),
        "celdas_valid_area_bajo_1pct": int((df["valid_area_pct"] < 1.0).sum()),
        "area_ha_total": round(float(df["area_celda_ha"].sum()), 1),
        "area_valida_ha_total": round(float(df["area_valida_ha"].sum()), 1),
        "ha_por_pixel_min": round(float(df["area_ha_pixel_min"].min()), 6),
        "ha_por_pixel_max": round(float(df["area_ha_pixel_max"].max()), 6),
        "transition_pct_media": round(float(df["transition_pct"].mean()), 4),
        "stable_mode_pct_media": round(float(df["stable_mode_pct"].mean()), 4),
        "ecorregiones": sorted(int(v) for v in np.unique(df["eco_dom_id"].dropna())),
    }
