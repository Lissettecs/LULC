#!/usr/bin/env python3
"""
Caracterización zonal de segmentos SLIC+RAG: segments.gpkg único + Parquet opcional.

Se ejecuta después de la segmentación (o sobre etiquetas ya existentes).
Columnas de salida en inglés. Geometría en EPSG:4326; métricas de área en UTM.

Fase 2 (no implementada): percentiles, IQR, contexto vecinal, consolidación nacional.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import shapes
from shapely.geometry import MultiPolygon, shape

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.bands_184b import SIGNATURE_BANDS  # noqa: E402
from config.catalogo_bandas import nombres_bandas_mosaico  # noqa: E402
from config.params_slic import (  # noqa: E402
    BUFFER_PX,
    RAG_PERCENTILE,
    SLIC_COMPACTNESS,
    SLIC_SCALE,
    SLIC_SIGMA,
)
from config.paths import output_dir  # noqa: E402
from config.run_refs import GPKG_SELECCION, GPKG_UTM18, GPKG_UTM19  # noqa: E402
from rectangles import cargar_gpkg_seleccion, utm_epsg_desde_fila  # noqa: E402
from mosaic_io import leer_bandas_recorte, leer_ventana_ampliada, recortar_centro

# === PARÁMETROS DE CARACTERIZACIÓN ===
BANDAS_FIRMA = ["blue", "green", "red", "nir", "swir1", "swir2"]
ESTADISTICOS_FIRMA = ["mean", "std"]

BANDAS_FEATURES = "todas"
ESTADISTICOS_FEAT = ["median", "std"]
EXCLUIR_DE_FEATURES: list[str] = []

MANEJAR_ASPECT_CIRCULAR = True
BANDAS_CIRCULARES = ["aspect"]

PLANTILLA_UID = "{grid_id}_{rev_year}_{label:06d}"
SEG_VERSION = "slic_v1"
GENERAR_FEATURES_PARQUET = True

# Bandas mínimas esperadas para emitir Parquet (stack 184 completo).
BANDAS_PARQUET_MINIMAS = 100


def dir_salida_caracterizacion(rev_year: int | None = None) -> Path:
    import os

    y = rev_year or int(os.environ.get("REV_YEAR", "2015"))
    return output_dir(y)


DIR_SALIDA_BASE = dir_salida_caracterizacion()
RUTA_MANIFIESTO = "manifiesto_caracterizacion.json"

METADATOS_RECTANGULO = (
    "rect_id",
    "grid_id",
    "eco_dom_id",
    "eco_dom_name",
    "utm_epsg",
    "utm_zone",
    "mgrs_dom",
    "rev_year",
    "rev_slot",
    "rev_role",
)

MAPA_FIRMA_RASTERIO = {nombre: idx for nombre, idx in SIGNATURE_BANDS}


def _dir_salida_rectangulo(fila: pd.Series, base: Path | None = None) -> Path:
    base = base or DIR_SALIDA_BASE
    tile = str(fila.get("_tile") or str(fila.get("grid_id", "")).split("_")[0]).upper()
    grid_id = str(fila.get("grid_id") or fila.get("rect_id"))
    destino = base / tile / grid_id
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _ruta_manifiesto(base: Path | None = None) -> Path:
    return (base or DIR_SALIDA_BASE) / RUTA_MANIFIESTO


def construir_segment_uid(grid_id: str, rev_year: int, etiqueta: int) -> str:
    return PLANTILLA_UID.format(grid_id=grid_id, rev_year=int(rev_year), label=int(etiqueta))


def resolver_bandas_features(
    nombres_stack: list[str],
    bandas_features: str | list[str] = BANDAS_FEATURES,
    excluir: list[str] | None = None,
) -> list[str]:
    excluir = set(excluir or EXCLUIR_DE_FEATURES)
    if bandas_features == "todas":
        return [n for n in nombres_stack if n not in excluir]
    pedidas = set(bandas_features)
    return [n for n in nombres_stack if n in pedidas and n not in excluir]


def leer_stack_rectangulo(
    ruta_mosaico: Path,
    geometria,
    buffer_px: int = BUFFER_PX,
    buffer_efectivo: dict[str, int] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    with rasterio.open(ruta_mosaico) as src:
        n_bandas = src.count
        indices = list(range(1, n_bandas + 1))
        descripciones = src.descriptions
        nombres = nombres_bandas_mosaico(n_bandas, descripciones)

        if buffer_px > 0:
            stack_buf, valido_buf, _, be, _ = leer_ventana_ampliada(
                src, geometria, indices, buffer_px
            )
            beff = buffer_efectivo or be
            stack = recortar_centro(stack_buf, beff)
            valido_stack = recortar_centro(valido_buf.astype(np.int8), beff).astype(bool)
        else:
            stack, valido_stack, _ = leer_bandas_recorte(src, geometria, indices)

    return stack, valido_stack, nombres


def _preparar_columnas_estadisticos(
    stack: np.ndarray,
    nombres_bandas: list[str],
    bandas_features: list[str],
) -> tuple[np.ndarray, list[str]]:
    cols_usar = [j for j, n in enumerate(nombres_bandas) if n in bandas_features]
    if not cols_usar:
        raise ValueError("No quedan bandas para caracterización tras filtros.")

    nombres_out: list[str] = []
    bloques: list[np.ndarray] = []

    for j in cols_usar:
        nombre = nombres_bandas[j]
        if MANEJAR_ASPECT_CIRCULAR and nombre in BANDAS_CIRCULARES:
            rad = np.deg2rad(stack[..., j].astype(np.float64))
            bloques.append(np.sin(rad).astype(np.float32))
            bloques.append(np.cos(rad).astype(np.float32))
            nombres_out.extend([f"{nombre}_sin", f"{nombre}_cos"])
        else:
            bloques.append(stack[..., j].astype(np.float32))
            nombres_out.append(nombre)

    matriz = np.stack(bloques, axis=-1)
    return matriz.reshape(-1, matriz.shape[-1]), nombres_out


def calcular_estadisticos_una_pasada(
    etiquetas: np.ndarray,
    valido: np.ndarray,
    stack: np.ndarray,
    nombres_bandas: list[str],
) -> pd.DataFrame:
    """Estadísticos zonales: mean / median / std (sufijos en inglés)."""
    union_estadisticos = sorted(set(ESTADISTICOS_FIRMA) | set(ESTADISTICOS_FEAT))
    bandas_features = resolver_bandas_features(nombres_bandas)
    mat_flat, nombres_cols = _preparar_columnas_estadisticos(stack, nombres_bandas, bandas_features)

    mascara_pix = (etiquetas > 0) & valido
    if not mascara_pix.any():
        return pd.DataFrame()

    etiquetas_pix = etiquetas[mascara_pix].astype(np.int64)
    valores_pix = mat_flat[mascara_pix.reshape(-1)]

    df_pix = pd.DataFrame(valores_pix, columns=nombres_cols)
    df_pix["__etiqueta__"] = etiquetas_pix
    agrupado = df_pix.groupby("__etiqueta__", sort=True)

    filas: list[dict[str, Any]] = []
    for etiqueta, grupo in agrupado:
        fila: dict[str, Any] = {"segment_id": int(etiqueta)}
        arr = grupo.drop(columns="__etiqueta__").to_numpy(dtype=np.float64)
        n_validos = arr.shape[0]
        n_total = int((etiquetas == etiqueta).sum())
        fila["n_valid_pixels"] = n_validos
        fila["n_pixels"] = n_total
        fila["nodata_frac"] = round(1.0 - n_validos / max(n_total, 1), 6)

        for j, nombre_col in enumerate(nombres_cols):
            col = arr[:, j]
            if "mean" in union_estadisticos:
                fila[f"{nombre_col}_mean"] = float(np.mean(col))
            if "median" in union_estadisticos:
                fila[f"{nombre_col}_median"] = float(np.median(col))
            if "std" in union_estadisticos:
                fila[f"{nombre_col}_std"] = float(np.std(col, ddof=0))

        # variación espectral (media de std de las 6 bandas de firma si disponibles)
        stds_firma = []
        for b in BANDAS_FIRMA:
            # columna en stack: blue_median_std etc. según catálogo
            pass
        filas.append(fila)

    return pd.DataFrame(filas).sort_values("segment_id").reset_index(drop=True)


def _nombre_stack_firma(nombre_corto: str, nombres_bandas: list[str]) -> str:
    """Resuelve el nombre de banda en el stack (184 o 11B) para una firma corta."""
    prefer = [
        n
        for n in nombres_bandas
        if n == f"{nombre_corto}_median" or n == nombre_corto
    ]
    if prefer:
        return prefer[0]
    prefijo = [
        n
        for n in nombres_bandas
        if n.startswith(f"{nombre_corto}_") or n.startswith(f"{nombre_corto}_median")
    ]
    if prefijo:
        return prefijo[0]
    idx_rasterio = MAPA_FIRMA_RASTERIO.get(nombre_corto)
    if idx_rasterio is not None and 1 <= idx_rasterio <= len(nombres_bandas):
        return nombres_bandas[idx_rasterio - 1]
    raise KeyError(
        f"No se encontró banda de firma '{nombre_corto}' en {nombres_bandas[:12]}…"
    )


def _columna_firma(
    nombre_corto: str,
    estadistico: str,
    stats: pd.DataFrame,
    nombres_bandas: list[str],
) -> pd.Series:
    nombre_stack = _nombre_stack_firma(nombre_corto, nombres_bandas)
    col = f"{nombre_stack}_{estadistico}"
    if col not in stats.columns:
        raise KeyError(f"Columna de firma esperada ausente: {col}")
    return stats[col]


def vectorizar_segmentos_monoparte(
    etiquetas: np.ndarray,
    transform,
    crs: str,
) -> gpd.GeoDataFrame:
    """Una geometría Polygon por segment_id; aborta si hay MultiPolygon o ids duplicados."""
    vistos: set[int] = set()
    geoms = []
    vals = []
    for geom, val in shapes(
        etiquetas.astype(np.int32),
        mask=etiquetas > 0,
        transform=transform,
        connectivity=8,
    ):
        etiqueta = int(val)
        if etiqueta == 0:
            continue
        if etiqueta in vistos:
            raise ValueError(
                f"segment_id={etiqueta} produce más de un polígono (¿falló "
                f"_reetiquetar_componentes_conexas?). Se espera monoparte."
            )
        vistos.add(etiqueta)
        g = shape(geom)
        if isinstance(g, MultiPolygon):
            raise ValueError(f"segment_id={etiqueta} es MultiPolygon; abortando.")
        geoms.append(g)
        vals.append(etiqueta)

    if not geoms:
        return gpd.GeoDataFrame(columns=["segment_id", "geometry"], crs=crs)

    return gpd.GeoDataFrame({"segment_id": vals, "geometry": geoms}, crs=crs)


def _elongacion(geom) -> float:
    mrr = geom.minimum_rotated_rectangle
    coords = np.asarray(mrr.exterior.coords[:4])
    lados = sorted(
        float(np.linalg.norm(coords[i] - coords[(i + 1) % 4])) for i in range(4)
    )
    unicos = sorted(set(round(x, 4) for x in lados if x > 0))
    if len(unicos) < 2:
        return float("nan")
    return unicos[-1] / unicos[0]


def calcular_metricas_geometricas(
    gdf: gpd.GeoDataFrame,
    utm_epsg: int | str,
    etiquetas: np.ndarray,
) -> pd.DataFrame:
    """Área / perímetro / forma midiendo en UTM; no usa n_pixels × constante."""
    epsg = int(str(utm_epsg).replace("EPSG:", ""))
    gdf_utm = gdf.to_crs(epsg=epsg)

    registros = []
    for _, fila in gdf_utm.iterrows():
        geom = fila.geometry
        etiqueta = int(fila["segment_id"])
        area_m2 = float(geom.area)
        perimetro = float(geom.length)
        compacidad = (
            (4.0 * math.pi * area_m2 / (perimetro**2)) if perimetro > 0 else float("nan")
        )
        registros.append(
            {
                "segment_id": etiqueta,
                "area_px": int((etiquetas == etiqueta).sum()),
                "area_ha": round(area_m2 / 10_000.0, 6),
                "perimeter_m": round(perimetro, 4),
                "compactness": round(compacidad, 6),
                "elongation": round(_elongacion(geom), 6),
            }
        )
    return pd.DataFrame(registros)


def _metadatos_rectangulo(fila: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    rect_id = str(fila.get("rect_id") or fila.get("grid_id", ""))
    out["rect_id"] = rect_id
    out["grid_id"] = str(fila.get("grid_id") or rect_id)
    for campo in METADATOS_RECTANGULO:
        if campo in fila.index and pd.notna(fila[campo]):
            out[campo] = fila[campo]
    if "rev_year" not in out and "rev_year1" in fila.index and pd.notna(fila["rev_year1"]):
        out["rev_year"] = int(fila["rev_year1"])
    if "rev_role" not in out and "rev_role1" in fila.index and pd.notna(fila["rev_role1"]):
        out["rev_role"] = str(fila["rev_role1"])
    if "rev_slot" not in out:
        out["rev_slot"] = int(fila.get("rev_slot", 1) or 1)
    if "utm_epsg" not in out:
        out["utm_epsg"] = utm_epsg_desde_fila(fila)
    return out


def armar_segments_gpkg(
    gdf_geom: gpd.GeoDataFrame,
    stats: pd.DataFrame,
    metricas: pd.DataFrame,
    fila: pd.Series,
    nombres_bandas: list[str],
) -> gpd.GeoDataFrame:
    meta = _metadatos_rectangulo(fila)
    grid_id = str(meta["grid_id"])
    rev_year = int(meta["rev_year"])

    gdf = gdf_geom.merge(stats, on="segment_id", how="inner")
    gdf = gdf.merge(metricas[["segment_id", "area_ha"]], on="segment_id", how="left")
    gdf["segment_uid"] = gdf["segment_id"].map(
        lambda e: construir_segment_uid(grid_id, rev_year, int(e))
    )
    gdf["reviewed_class"] = np.nan

    # Firma 6 bandas con nombres cortos
    for nombre in BANDAS_FIRMA:
        gdf[f"{nombre}_mean"] = _columna_firma(nombre, "mean", gdf, nombres_bandas)
        gdf[f"{nombre}_std"] = _columna_firma(nombre, "std", gdf, nombres_bandas)

    # Variación espectral = media de std de las 6 bandas
    gdf["spectral_variation"] = gdf[[f"{b}_std" for b in BANDAS_FIRMA]].mean(axis=1).round(6)

    for c, v in meta.items():
        if c not in gdf.columns:
            gdf[c] = v

    if (gdf["n_valid_pixels"] == 0).any():
        raise ValueError("Hay segmentos con n_valid_pixels == 0.")
    if gdf["segment_uid"].duplicated().any():
        raise ValueError("segment_uid duplicado en segments.gpkg.")
    if gdf.crs is None or gdf.crs.to_epsg() != 4326:
        raise ValueError(f"Geometría debe quedar en EPSG:4326, obtenido {gdf.crs}")

    columnas = [
        "segment_id",
        "segment_uid",
        "grid_id",
        "rect_id",
        "rev_year",
        "rev_slot",
        "rev_role",
        "reviewed_class",
        "n_valid_pixels",
        "nodata_frac",
        "n_pixels",
        "spectral_variation",
        *[f"{b}_mean" for b in BANDAS_FIRMA],
        *[f"{b}_std" for b in BANDAS_FIRMA],
        "eco_dom_id",
        "eco_dom_name",
        "utm_epsg",
        "utm_zone",
        "mgrs_dom",
        "area_ha",
        "geometry",
    ]
    cols_finales = [c for c in columnas if c in gdf.columns]
    return gdf[cols_finales]


def armar_parquet_features(
    stats: pd.DataFrame,
    metricas: pd.DataFrame,
    fila: pd.Series,
    nombres_bandas: list[str],
) -> pd.DataFrame:
    meta = _metadatos_rectangulo(fila)
    grid_id = str(meta["grid_id"])
    rev_year = int(meta["rev_year"])

    bandas = resolver_bandas_features(nombres_bandas)
    cols_feat: list[str] = ["segment_id", "n_valid_pixels", "nodata_frac"]
    for nombre in bandas:
        if MANEJAR_ASPECT_CIRCULAR and nombre in BANDAS_CIRCULARES:
            bases = [f"{nombre}_sin", f"{nombre}_cos"]
        else:
            bases = [nombre]
        for base in bases:
            for est in ESTADISTICOS_FEAT:
                col = f"{base}_{est}"
                if col in stats.columns:
                    cols_feat.append(col)

    feat = stats[[c for c in cols_feat if c in stats.columns]].copy()
    feat = feat.merge(metricas, on="segment_id", how="inner")
    feat["segment_uid"] = feat["segment_id"].map(
        lambda e: construir_segment_uid(grid_id, rev_year, int(e))
    )
    feat["grid_id"] = grid_id
    feat["rev_year"] = rev_year
    feat["rev_slot"] = int(meta.get("rev_slot", 1))

    # Renombrar aspect_sin_median / aspect_cos_median si aplica
    rename = {}
    for c in list(feat.columns):
        if c.endswith("_median") or c.endswith("_std") or c.endswith("_mean"):
            continue
    # Asegurar que no queden sufijos en español
    malas = [c for c in feat.columns if "_mediana" in c or c.endswith("_media")]
    if malas:
        raise ValueError(f"Columnas no estandarizadas al inglés: {malas}")

    orden = [
        "segment_uid",
        "segment_id",
        "grid_id",
        "rev_year",
        "rev_slot",
        "n_valid_pixels",
        "nodata_frac",
        "area_px",
        "area_ha",
        "perimeter_m",
        "compactness",
        "elongation",
    ]
    resto = [c for c in feat.columns if c not in orden]
    return feat[[c for c in orden if c in feat.columns] + resto]


def verificar_consistencia(
    gdf: gpd.GeoDataFrame,
    df_parquet: pd.DataFrame | None,
) -> None:
    if gdf["segment_uid"].duplicated().any():
        raise ValueError("segment_uid duplicado en GPKG")
    if (gdf["n_valid_pixels"] == 0).any():
        raise ValueError("n_valid_pixels == 0 en GPKG")
    if df_parquet is None:
        return
    if set(gdf["segment_uid"].astype(str)) != set(df_parquet["segment_uid"].astype(str)):
        raise ValueError("segment_uid difiere entre segments.gpkg y features.parquet")
    malas = [c for c in df_parquet.columns if "_mediana" in c]
    if malas:
        raise ValueError(f"Columnas _mediana residuales: {malas}")


def actualizar_manifiesto(
    base_salida: Path,
    rect_id: str,
    params_segmentacion: dict[str, Any],
    nombres_bandas: list[str],
    rutas: dict[str, str],
) -> None:
    ruta = _ruta_manifiesto(base_salida)
    if ruta.is_file():
        manifiesto = json.loads(ruta.read_text(encoding="utf-8"))
    else:
        manifiesto = {
            "timestamp": datetime.now().strftime("%Y%m%d_%H%M"),
            "SEG_VERSION": SEG_VERSION,
            "PLANTILLA_UID": PLANTILLA_UID,
            "algoritmo": "SLIC+RAG",
            "parametros_segmentacion": params_segmentacion,
            "BANDAS_FIRMA": BANDAS_FIRMA,
            "rectangulos": [],
        }

    entrada = {"rect_id": rect_id, **rutas}
    existentes = {r["rect_id"] for r in manifiesto["rectangulos"]}
    if rect_id not in existentes:
        manifiesto["rectangulos"].append(entrada)
    else:
        manifiesto["rectangulos"] = [
            entrada if r["rect_id"] == rect_id else r for r in manifiesto["rectangulos"]
        ]
    manifiesto["actualizado_en"] = datetime.now(timezone.utc).isoformat()
    ruta.write_text(json.dumps(manifiesto, indent=2, ensure_ascii=False), encoding="utf-8")


def caracterizar_rectangulo(
    *,
    etiquetas: np.ndarray,
    valido: np.ndarray,
    stack: np.ndarray,
    nombres_bandas: list[str],
    transform,
    crs: str,
    fila: pd.Series,
    params_segmentacion: dict[str, Any],
    dir_corrida: Path | None = None,
    dir_salida_base: Path | None = None,
    buffer_efectivo: dict[str, int] | None = None,
    generar_features_parquet: bool = GENERAR_FEATURES_PARQUET,
) -> dict[str, Any]:
    """Escribe ``{grid_id}_{year}_segments.gpkg`` (+ Parquet opcional)."""
    del buffer_efectivo  # API estable; no se usa aquí
    base = dir_salida_base or DIR_SALIDA_BASE
    dir_out = dir_corrida or _dir_salida_rectangulo(fila, base)
    meta = _metadatos_rectangulo(fila)
    rect_id = str(meta["rect_id"])
    grid_id = str(meta["grid_id"])
    rev_year = int(meta["rev_year"])

    # NO reetiquetar: segment_id debe coincidir con labels.tif
    etiquetas = etiquetas.astype(np.int32)
    stats = calcular_estadisticos_una_pasada(etiquetas, valido, stack, nombres_bandas)
    if stats.empty:
        raise ValueError(f"{rect_id}: sin segmentos válidos para caracterizar.")

    gdf_geom = vectorizar_segmentos_monoparte(etiquetas, transform, crs)
    if gdf_geom.crs is None or str(gdf_geom.crs) == "None":
        gdf_geom = gdf_geom.set_crs(crs)
    if gdf_geom.crs.to_epsg() != 4326:
        gdf_geom = gdf_geom.to_crs(epsg=4326)

    utm_epsg = meta.get("utm_epsg") or utm_epsg_desde_fila(fila)
    metricas = calcular_metricas_geometricas(gdf_geom, utm_epsg, etiquetas)

    gdf_seg = armar_segments_gpkg(gdf_geom, stats, metricas, fila, nombres_bandas)

    ruta_gpkg = dir_out / f"{grid_id}_{rev_year}_segments.gpkg"
    # Compatibilidad 04_labeling: también un alias slic_ragp si se pide
    gdf_seg.to_file(ruta_gpkg, driver="GPKG")

    ruta_parquet = None
    df_feat = None
    skip_parquet_motivo = None
    if generar_features_parquet:
        if len(nombres_bandas) < BANDAS_PARQUET_MINIMAS:
            skip_parquet_motivo = f"stack_acotado_{len(nombres_bandas)}_bandas"
            print(f"  [AVISO] Sin features.parquet ({skip_parquet_motivo})")
        else:
            df_feat = armar_parquet_features(stats, metricas, fila, nombres_bandas)
            ruta_parquet = dir_out / f"{grid_id}_{rev_year}_features.parquet"
            df_feat.to_parquet(ruta_parquet, index=False)
    else:
        skip_parquet_motivo = "pendiente_desactivado_por_parametro"
        print("  [AVISO] features.parquet pendiente (FEATURES_PARQUET/flag off)")

    verificar_consistencia(gdf_seg, df_feat)

    rutas = {
        "segments_gpkg": str(ruta_gpkg),
        "features_parquet": str(ruta_parquet) if ruta_parquet else None,
        "n_segmentos": len(gdf_seg),
    }
    actualizar_manifiesto(base, rect_id, params_segmentacion, nombres_bandas, rutas)

    print(
        f"  Caracterización OK: {len(gdf_seg)} segmentos → {dir_out} "
        f"({ruta_gpkg.name}"
        + (f", {Path(ruta_parquet).name}" if ruta_parquet else "")
        + ")"
    )
    return {
        "rect_id": rect_id,
        "dir_salida": str(dir_out),
        "segments_gpkg": str(ruta_gpkg),
        "features_parquet": str(ruta_parquet) if ruta_parquet else None,
        "features_parquet_skip": skip_parquet_motivo,
        "n_segmentos": len(gdf_seg),
        "utm_epsg": int(str(utm_epsg).replace("EPSG:", "")),
        "manifiesto": str(_ruta_manifiesto(base)),
    }


def caracterizar_desde_segmentacion_existente(
    rect_dir: Path,
    fila: pd.Series,
    *,
    dir_corrida: Path | None = None,
    buffer_px: int = BUFFER_PX,
) -> dict[str, Any]:
    summary_candidates = sorted(rect_dir.glob("*_summary.json"))
    if not summary_candidates:
        raise FileNotFoundError(f"Sin summary.json en {rect_dir}")
    summary_path = summary_candidates[-1]
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels_path = Path(summary["label_raster"])
    mosaic_path = Path(summary["mosaic_path"])

    with rasterio.open(labels_path) as src:
        etiquetas = src.read(1).astype(np.int32)
        transform = src.transform
        crs = src.crs.to_string()

    beff = summary.get("buffer_effective_px") or summary.get("buffer_efectivo_px")
    if isinstance(beff, dict):
        alias = {"izq": "left", "der": "right", "arriba": "top", "abajo": "bottom"}
        beff = {alias.get(k, k): v for k, v in beff.items()}

    stack, valido_stack, nombres = leer_stack_rectangulo(
        mosaic_path,
        fila.geometry,
        buffer_px=buffer_px,
        buffer_efectivo=beff,
    )
    if stack.shape[:2] != etiquetas.shape:
        raise ValueError(
            f"Forma stack {stack.shape[:2]} != etiquetas {etiquetas.shape} "
            f"para {fila['grid_id']}"
        )

    params = {
        "slic_scale": summary.get("slic_scale", SLIC_SCALE),
        "slic_sigma": summary.get("slic_sigma", SLIC_SIGMA),
        "slic_compactness": SLIC_COMPACTNESS,
        "rag_percentil": summary.get("rag_percentil", RAG_PERCENTILE),
        "buffer_px": summary.get("buffer_px", buffer_px),
        "SEG_VERSION": SEG_VERSION,
    }

    return caracterizar_rectangulo(
        etiquetas=etiquetas,
        valido=valido_stack,
        stack=stack,
        nombres_bandas=nombres,
        transform=transform,
        crs=crs,
        fila=fila,
        params_segmentacion=params,
        dir_corrida=dir_corrida,
    )


def _buscar_fila_seleccion(
    grid_id: str,
    rev_year: int,
    gpkg_seleccion: Path | None = None,
) -> pd.Series:
    for gdf in cargar_gpkg_seleccion(
        GPKG_UTM18,
        GPKG_UTM19,
        rev_year,
        grid_id=grid_id,
        gpkg_seleccion=gpkg_seleccion or GPKG_SELECCION,
    ):
        if not gdf.empty:
            return gdf.iloc[0]
    raise ValueError(f"Rectángulo {grid_id} no encontrado en selección rev_year={rev_year}")


def parsear_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Caracterización zonal post-segmentación (segments.gpkg + Parquet)."
    )
    p.add_argument("--grid-id", type=str, required=True, help="Identificador del rectángulo")
    p.add_argument(
        "--segmentacion-dir",
        type=Path,
        default=None,
        help="Raíz de salidas de segmentación (default: prod/03_segmentation_cim/{rev_year})",
    )
    p.add_argument("--rev-year", type=int, default=2015, help="Año de revisión")
    p.add_argument(
        "--gpkg-seleccion",
        type=Path,
        default=GPKG_SELECCION,
        help="GPKG nacional de selección",
    )
    p.add_argument(
        "--dir-salida",
        type=Path,
        default=DIR_SALIDA_BASE,
        help="Directorio base de salida de caracterización",
    )
    p.add_argument("--buffer-px", type=int, default=BUFFER_PX, help="Buffer en píxeles")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parsear_args(argv)
    seg_root = args.segmentacion_dir or output_dir(args.rev_year)
    fila = _buscar_fila_seleccion(args.grid_id, args.rev_year, args.gpkg_seleccion)

    tile = str(fila.get("_tile") or args.grid_id.split("_")[0])
    rect_dir = seg_root / tile / args.grid_id
    if not rect_dir.is_dir():
        raise SystemExit(f"Directorio de segmentación no encontrado: {rect_dir}")

    dir_out = _dir_salida_rectangulo(fila, args.dir_salida)
    print(f"Caracterizando {args.grid_id} → {dir_out}…")
    try:
        resultado = caracterizar_desde_segmentacion_existente(
            rect_dir,
            fila,
            dir_corrida=dir_out,
            buffer_px=args.buffer_px,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(f"Manifiesto: {resultado['manifiesto']}")
    print(f"Verificación: OK ({resultado['n_segmentos']} segmentos)")
    return 0


parse_args = parsear_args


if __name__ == "__main__":
    raise SystemExit(main())
