#!/usr/bin/env python3
"""
Caracterización zonal de segmentos SLIC+RAG: GPKG de revisión + Parquet de features.

Se ejecuta después de la segmentación (o sobre etiquetas ya existentes).
Una sola pasada de estadísticos por segmento; la firma espectral del GPKG
se proyecta desde ese mismo cálculo (no se recorre el stack dos veces).

Fase 2 (no implementada): percentiles p10/p90, IQR, contexto vecinal,
poda de bandas *_min/_max/_amp/_stdDev, consolidación nacional, selección de features.
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
from shapely.geometry import shape

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.bands_184b import SIGNATURE_BANDS  # noqa: E402
from config.catalogo_bandas import nombres_bandas_mosaico  # noqa: E402
from config.params_slic import (  # noqa: E402
    BUFFER_PX,
    MOSAIC_NODATA,
    RAG_PERCENTILE,
    SLIC_COMPACTNESS,
    SLIC_SCALE,
    SLIC_SIGMA,
)
from config.paths import output_dir  # noqa: E402
from config.run_refs import GPKG_UTM18, GPKG_UTM19  # noqa: E402
from rectangles import load_selection_gpkg  # noqa: E402
from io_mosaico import leer_bandas_recorte, leer_ventana_ampliada, recortar_centro

# === PARÁMETROS DE CARACTERIZACIÓN ===
# --- Firma espectral (GPKG de revisión) ---
BANDAS_FIRMA = ["blue", "green", "red", "nir", "swir1", "swir2"]
ESTADISTICOS_FIRMA = ["media", "std"]

# --- Features (Parquet) ---
BANDAS_FEATURES = "todas"
ESTADISTICOS_FEAT = ["mediana", "std"]
EXCLUIR_DE_FEATURES: list[str] = []

# --- Manejo especial de bandas ---
MANEJAR_ASPECT_CIRCULAR = True
BANDAS_CIRCULARES = ["aspect"]

# --- Geometría e identificación ---
PIXEL_SIZE_M = 30
CAMPO_ID = "segment_id"
PLANTILLA_ID = "{rect_id}_{label:06d}"
SEG_VERSION = "slic_v1"
CAMPO_CLASE = "clase_revisada"

# --- Nodata / validez ---
VALOR_NODATA = 0

# --- Salidas (junto a labels/summary de cada rectángulo; año vía REV_YEAR en jobs) ---
def dir_salida_caracterizacion(rev_year: int | None = None) -> Path:
    import os

    y = rev_year or int(os.environ.get("REV_YEAR", "2015"))
    return output_dir(y)


DIR_SALIDA_BASE = dir_salida_caracterizacion()
RUTA_MANIFIESTO = "manifiesto_caracterizacion.json"

# Metadatos de rectángulo que se copian al GPKG si están presentes en la fila de selección.
METADATOS_RECTANGULO = (
    "rect_id",
    "grid_id",
    "eco_dom_id",
    "eco_dom_name",
    "utm_epsg",
    "utm_zone",
    "mgrs_dom",
    "rev_year1",
    "rev_role1",
)

MAPA_FIRMA_RASTERIO = {nombre: idx for nombre, idx in SIGNATURE_BANDS}


def _dir_salida_rectangulo(fila: pd.Series, base: Path | None = None) -> Path:
    """Directorio del rectángulo: {base}/{tile}/{grid_id}/."""
    base = base or DIR_SALIDA_BASE
    tile = str(fila.get("_tile") or str(fila.get("grid_id", "")).split("_")[0]).upper()
    grid_id = str(fila.get("grid_id") or fila.get("rect_id"))
    destino = base / tile / grid_id
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def _ruta_manifiesto(base: Path | None = None) -> Path:
    return (base or DIR_SALIDA_BASE) / RUTA_MANIFIESTO


def reetiquetar_deterministico(etiquetas: np.ndarray, valido: np.ndarray) -> np.ndarray:
    """Reordena etiquetas por posición raster (fila, col) del primer píxel."""
    salida = np.zeros_like(etiquetas, dtype=np.int32)
    candidatos = np.unique(etiquetas[(etiquetas > 0) & valido])
    if candidatos.size == 0:
        return salida

    anclas: list[tuple[int, int, int]] = []
    for etiqueta in candidatos:
        filas, cols = np.where((etiquetas == etiqueta) & valido)
        anclas.append((int(filas.min()), int(cols.min()), int(etiqueta)))
    anclas.sort()

    for nueva, (_, _, vieja) in enumerate(anclas, start=1):
        salida[(etiquetas == vieja) & valido] = nueva
    return salida


def construir_segment_id(rect_id: str, etiqueta: int) -> str:
    return PLANTILLA_ID.format(rect_id=rect_id, label=int(etiqueta))


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
    """Lee el stack multibanda recortado al rectángulo (H, W, C)."""
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
    """
    Devuelve matriz (N_pix, N_cols) y nombres de columnas para el groupby.

    Si aspect está presente y MANEJAR_ASPECT_CIRCULAR, reemplaza aspect por sin/cos.
    """
    cols_usar = [j for j, n in enumerate(nombres_bandas) if n in bandas_features]
    if not cols_usar:
        raise ValueError("No quedan bandas para caracterización tras filtros.")

    nombres_out: list[str] = []
    bloques: list[np.ndarray] = []

    for j in cols_usar:
        nombre = nombres_bandas[j]
        if (
            MANEJAR_ASPECT_CIRCULAR
            and nombre in BANDAS_CIRCULARES
        ):
            # Grados → radianes; sin/cos evitan promediar ángulos directamente.
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
    """
    Estadísticos zonales en una pasada (media, mediana, std).

    Solo píxeles con etiqueta > 0 y máscara ``valido`` entran al cálculo.
    """
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
        fila: dict[str, Any] = {"etiqueta": int(etiqueta)}
        arr = grupo.drop(columns="__etiqueta__").to_numpy(dtype=np.float64)
        n_validos = arr.shape[0]
        n_total = int((etiquetas == etiqueta).sum())
        fila["n_pixeles_validos"] = n_validos
        fila["frac_nodata"] = round(1.0 - n_validos / max(n_total, 1), 6)

        for j, nombre_col in enumerate(nombres_cols):
            col = arr[:, j]
            if "media" in union_estadisticos:
                fila[f"{nombre_col}_media"] = float(np.mean(col))
            if "mediana" in union_estadisticos:
                fila[f"{nombre_col}_mediana"] = float(np.median(col))
            if "std" in union_estadisticos:
                fila[f"{nombre_col}_std"] = float(np.std(col, ddof=0))

        filas.append(fila)

    return pd.DataFrame(filas).sort_values("etiqueta").reset_index(drop=True)


def _columna_firma(
    nombre_corto: str,
    estadistico: str,
    stats: pd.DataFrame,
    nombres_bandas: list[str],
) -> pd.Series:
    """Proyecta firma espectral desde stats ya calculados (sin recomputar)."""
    idx_rasterio = MAPA_FIRMA_RASTERIO[nombre_corto]
    nombre_stack = nombres_bandas[idx_rasterio - 1]
    col = f"{nombre_stack}_{estadistico}"
    if col not in stats.columns:
        raise KeyError(f"Columna de firma esperada ausente: {col}")
    return stats[col]


def _columnas_parquet(stats: pd.DataFrame, nombres_bandas: list[str]) -> pd.DataFrame:
    bandas = resolver_bandas_features(nombres_bandas)
    cols_id = ["etiqueta", "n_pixeles_validos", "frac_nodata"]
    cols_feat: list[str] = []
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
    existentes = [c for c in cols_id + cols_feat if c in stats.columns]
    return stats[existentes].copy()


def vectorizar_segmentos(
    etiquetas: np.ndarray,
    transform,
    crs: str,
) -> gpd.GeoDataFrame:
    geoms = []
    vals = []
    for geom, val in shapes(etiquetas.astype(np.int32), mask=etiquetas > 0, transform=transform):
        etiqueta = int(val)
        if etiqueta == 0:
            continue
        geoms.append(shape(geom))
        vals.append(etiqueta)

    if not geoms:
        return gpd.GeoDataFrame(columns=["etiqueta", "geometry"], crs=crs)

    gdf = gpd.GeoDataFrame({"etiqueta": vals, "geometry": geoms}, crs=crs)
    # Un segmento puede tener varios polígonos disjuntos → una fila por etiqueta.
    return gdf.dissolve(by="etiqueta", as_index=False)


def _elongacion(geom) -> float:
    mrr = geom.minimum_rotated_rectangle
    coords = np.array(mrr.exterior.coords[:4])
    lados = sorted(
        float(np.linalg.norm(coords[i] - coords[(i + 1) % 4])) for i in range(4)
    )
    unicos = sorted(set(round(x, 4) for x in lados if x > 0))
    if len(unicos) < 2:
        return float("nan")
    return unicos[-1] / unicos[0]


def calcular_metricas_geometricas(
    gdf: gpd.GeoDataFrame,
    utm_epsg: str | int,
    etiquetas: np.ndarray,
) -> pd.DataFrame:
    """Métricas en UTM (reproyección solo de geometrías)."""
    epsg = str(utm_epsg).replace("EPSG:", "")
    gdf_utm = gdf.to_crs(epsg=int(epsg))

    registros = []
    for _, fila in gdf_utm.iterrows():
        geom = fila.geometry
        etiqueta = int(fila["etiqueta"])
        area_m2 = float(geom.area)
        perimetro = float(geom.length)
        compacidad = (
            (4.0 * math.pi * area_m2 / (perimetro**2)) if perimetro > 0 else float("nan")
        )
        registros.append(
            {
                "etiqueta": etiqueta,
                "area_px": int((etiquetas == etiqueta).sum()),
                "area_ha": round(area_m2 / 10_000.0, 6),
                "perimetro_m": round(perimetro, 4),
                "compacidad": round(compacidad, 6),
                "elongacion": round(_elongacion(geom), 6),
            }
        )
    return pd.DataFrame(registros)


def _metadatos_rectangulo(fila: pd.Series) -> dict[str, Any]:
    out: dict[str, Any] = {}
    rect_id = str(fila.get("rect_id") or fila.get("grid_id", ""))
    out["rect_id"] = rect_id
    for campo in METADATOS_RECTANGULO:
        if campo in fila.index and pd.notna(fila[campo]):
            out[campo] = fila[campo]
    if "grid_id" not in out and "grid_id" in fila.index:
        out["grid_id"] = fila["grid_id"]
    return out


def armar_gpkg_revision(
    gdf_geom: gpd.GeoDataFrame,
    stats: pd.DataFrame,
    fila: pd.Series,
    nombres_bandas: list[str],
) -> gpd.GeoDataFrame:
    meta = _metadatos_rectangulo(fila)
    rect_id = meta["rect_id"]

    gdf = gdf_geom.merge(stats, on="etiqueta", how="inner")
    gdf[CAMPO_ID] = gdf["etiqueta"].map(lambda e: construir_segment_id(rect_id, int(e)))
    gdf[CAMPO_CLASE] = np.nan

    for nombre in BANDAS_FIRMA:
        for est in ESTADISTICOS_FIRMA:
            gdf[f"{nombre}_{est}"] = _columna_firma(nombre, est, gdf, nombres_bandas)

    columnas = [CAMPO_ID, CAMPO_CLASE, "n_pixeles_validos", "frac_nodata"]
    columnas += [f"{b}_{e}" for b in BANDAS_FIRMA for e in ESTADISTICOS_FIRMA]
    columnas += [c for c in METADATOS_RECTANGULO if c in meta]
    for c, v in meta.items():
        if c not in gdf.columns:
            gdf[c] = v

    cols_finales = ["geometry"] + [c for c in columnas if c in gdf.columns]
    # Evitar duplicar geometry
    cols_finales = list(dict.fromkeys(cols_finales))
    return gdf[cols_finales]


def armar_parquet_features(
    stats: pd.DataFrame,
    metricas: pd.DataFrame,
    fila: pd.Series,
    nombres_bandas: list[str],
) -> pd.DataFrame:
    rect_id = str(fila.get("rect_id") or fila.get("grid_id", ""))
    feat = _columnas_parquet(stats, nombres_bandas)
    feat = feat.merge(metricas, on="etiqueta", how="inner")
    feat[CAMPO_ID] = feat["etiqueta"].map(lambda e: construir_segment_id(rect_id, int(e)))
    cols = [CAMPO_ID] + [c for c in feat.columns if c not in ("etiqueta", CAMPO_ID)]
    return feat[cols]


def verificar_consistencia_gpkg_parquet(gdf: gpd.GeoDataFrame, df_parquet: pd.DataFrame) -> None:
    ids_gpkg = gdf[CAMPO_ID].astype(str)
    ids_parquet = df_parquet[CAMPO_ID].astype(str)

    if ids_gpkg.duplicated().any():
        dup = ids_gpkg[ids_gpkg.duplicated()].iloc[0]
        raise ValueError(f"segment_id duplicado en GPKG: {dup}")
    if ids_parquet.duplicated().any():
        dup = ids_parquet[ids_parquet.duplicated()].iloc[0]
        raise ValueError(f"segment_id duplicado en Parquet: {dup}")

    set_g = set(ids_gpkg)
    set_p = set(ids_parquet)
    if set_g != set_p:
        solo_g = sorted(set_g - set_p)[:5]
        solo_p = sorted(set_p - set_g)[:5]
        raise ValueError(
            "Conjuntos de segment_id difieren entre GPKG y Parquet. "
            f"Solo GPKG (muestra): {solo_g}; solo Parquet (muestra): {solo_p}"
        )

    if (gdf["n_pixeles_validos"] == 0).any():
        raise ValueError("Hay segmentos con n_pixeles_validos == 0 en el GPKG.")
    if (df_parquet["n_pixeles_validos"] == 0).any():
        raise ValueError("Hay segmentos con n_pixeles_validos == 0 en el Parquet.")


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
            "PLANTILLA_ID": PLANTILLA_ID,
            "PIXEL_SIZE_M": PIXEL_SIZE_M,
            "algoritmo": "SLIC+RAG",
            "parametros_segmentacion": params_segmentacion,
            "BANDAS_FIRMA": BANDAS_FIRMA,
            "ESTADISTICOS_FIRMA": ESTADISTICOS_FIRMA,
            "BANDAS_FEATURES": BANDAS_FEATURES,
            "ESTADISTICOS_FEAT": ESTADISTICOS_FEAT,
            "bandas_escritas_features": resolver_bandas_features(nombres_bandas),
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
) -> dict[str, Any]:
    """Genera GPKG de revisión, Parquet de features y actualiza manifiesto."""
    base = dir_salida_base or DIR_SALIDA_BASE
    dir_out = dir_corrida or _dir_salida_rectangulo(fila, base)
    rect_id = str(fila.get("rect_id") or fila.get("grid_id", ""))

    etiquetas = reetiquetar_deterministico(etiquetas.astype(np.int32), valido)
    stats = calcular_estadisticos_una_pasada(etiquetas, valido, stack, nombres_bandas)
    if stats.empty:
        raise ValueError(f"{rect_id}: sin segmentos válidos para caracterizar.")

    gdf_geom = vectorizar_segmentos(etiquetas, transform, crs)
    utm_epsg = fila.get("utm_epsg", "EPSG:32718")
    metricas = calcular_metricas_geometricas(gdf_geom, utm_epsg, etiquetas)

    gdf_rev = armar_gpkg_revision(gdf_geom, stats, fila, nombres_bandas)
    df_feat = armar_parquet_features(stats, metricas, fila, nombres_bandas)

    verificar_consistencia_gpkg_parquet(gdf_rev, df_feat)

    ruta_gpkg = dir_out / f"{rect_id}_revision.gpkg"
    ruta_parquet = dir_out / f"{rect_id}_features.parquet"
    gdf_rev.to_file(ruta_gpkg, driver="GPKG")
    df_feat.to_parquet(ruta_parquet, index=False)

    rutas = {
        "gpkg_revision": str(ruta_gpkg),
        "parquet_features": str(ruta_parquet),
        "n_segmentos": len(gdf_rev),
    }
    actualizar_manifiesto(base, rect_id, params_segmentacion, nombres_bandas, rutas)

    print(
        f"  Caracterización OK: {len(gdf_rev)} segmentos → {dir_out} "
        f"({ruta_gpkg.name}, {ruta_parquet.name})"
    )
    return {
        "rect_id": rect_id,
        "dir_salida": str(dir_out),
        "gpkg_revision": str(ruta_gpkg),
        "parquet_features": str(ruta_parquet),
        "n_segmentos": len(gdf_rev),
        "manifiesto": str(_ruta_manifiesto(base)),
    }


def caracterizar_desde_segmentacion_existente(
    rect_dir: Path,
    fila: pd.Series,
    *,
    dir_corrida: Path | None = None,
    buffer_px: int = BUFFER_PX,
) -> dict[str, Any]:
    """Caracteriza un rectángulo ya segmentado (labels.tif + summary.json)."""
    summary_path = rect_dir / f"{fila['grid_id']}_summary.json"
    if not summary_path.is_file():
        summaries = sorted(rect_dir.glob("*_summary.json"))
        if not summaries:
            raise FileNotFoundError(f"Sin summary.json en {rect_dir}")
        summary_path = summaries[0]

    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    labels_path = Path(summary["label_raster"])
    mosaic_path = Path(summary["mosaic_path"])
    if not labels_path.is_file():
        raise FileNotFoundError(f"Raster de etiquetas no encontrado: {labels_path}")

    with rasterio.open(labels_path) as src:
        etiquetas = src.read(1).astype(np.int32)
        transform = src.transform
        crs = src.crs.to_string()

    beff = summary.get("buffer_effective_px") or summary.get("buffer_efectivo_px")
    if isinstance(beff, dict):
        # Compatibilidad con summaries en español (izq/der/arriba/abajo).
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

    valido = valido_stack.copy()

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
        valido=valido,
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
    gpkg_utm18: Path,
    gpkg_utm19: Path,
    rev_year: int,
) -> pd.Series:
    for gdf in load_selection_gpkg(gpkg_utm18, gpkg_utm19, rev_year, grid_id=grid_id):
        if not gdf.empty:
            return gdf.iloc[0]
    raise ValueError(f"Rectángulo {grid_id} no encontrado en selección rev_year={rev_year}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Caracterización zonal post-segmentación (GPKG revisión + Parquet features)."
    )
    p.add_argument("--grid-id", type=str, required=True, help="Identificador del rectángulo")
    p.add_argument(
        "--segmentacion-dir",
        type=Path,
        default=None,
        help="Raíz de segmentacion_slic_rev{year} (default: prod/…)",
    )
    p.add_argument("--rev-year", type=int, default=2015)
    p.add_argument("--gpkg-utm18", type=Path, default=GPKG_UTM18)
    p.add_argument("--gpkg-utm19", type=Path, default=GPKG_UTM19)
    p.add_argument(
        "--dir-salida",
        type=Path,
        default=DIR_SALIDA_BASE,
        help="Raíz prod segmentacion_slic_rev{year} (default: DIR_SALIDA_BASE)",
    )
    p.add_argument("--buffer-px", type=int, default=BUFFER_PX)
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    seg_root = args.segmentacion_dir or output_dir(args.rev_year)
    fila = _buscar_fila_seleccion(args.grid_id, args.gpkg_utm18, args.gpkg_utm19, args.rev_year)

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
    print(f"Verificación GPKG↔Parquet: OK ({resultado['n_segmentos']} segmentos)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
