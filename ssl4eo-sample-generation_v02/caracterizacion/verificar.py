"""Verificación de insumos y compatibilidad de grillas."""

from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from pathlib import Path

import rasterio


@dataclass
class ResultadoVerificacion:
    ok: bool
    diferencias: list[str]
    eco_path: str
    lulc_path: str
    crs: str
    ancho: int
    alto: int
    res: tuple[float, float]
    crs_metrico_nacional: bool


def _es_crs_metrico(crs_str: str) -> bool:
    if not crs_str:
        return False
    return not crs_str.endswith("4326")


def verificar_grillas_raster(
    eco_path: Path,
    lulc_path: Path,
    logger: logging.Logger,
) -> ResultadoVerificacion:
    diferencias: list[str] = []
    with rasterio.open(eco_path) as eco, rasterio.open(lulc_path) as lulc:
        eco_crs = eco.crs.to_string() if eco.crs else ""
        lulc_crs = lulc.crs.to_string() if lulc.crs else ""
        if eco_crs != lulc_crs:
            diferencias.append(f"CRS: eco={eco_crs!r} vs lulc={lulc_crs!r}")
        if eco.width != lulc.width:
            diferencias.append(f"Ancho: eco={eco.width} vs lulc={lulc.width}")
        if eco.height != lulc.height:
            diferencias.append(f"Alto: eco={eco.height} vs lulc={lulc.height}")
        if eco.res != lulc.res:
            diferencias.append(f"Resolución: eco={eco.res} vs lulc={lulc.res}")
        if eco.transform != lulc.transform:
            diffs = []
            for i, (a, b) in enumerate(zip(eco.transform, lulc.transform)):
                if abs(a - b) > 1e-12:
                    diffs.append(f"  [{i}] Δ={a - b:.12f}")
            detalle = "\n".join(diffs) if diffs else ""
            diferencias.append(f"Transform distinto:\n{detalle}")

        resultado = ResultadoVerificacion(
            ok=len(diferencias) == 0,
            diferencias=diferencias,
            eco_path=str(eco_path),
            lulc_path=str(lulc_path),
            crs=eco_crs,
            ancho=eco.width,
            alto=eco.height,
            res=(float(eco.res[0]), float(eco.res[1])),
            crs_metrico_nacional=_es_crs_metrico(eco_crs),
        )

    if resultado.ok:
        logger.info("Grillas compatibles: %dx%d | CRS=%s", resultado.ancho, resultado.alto, resultado.crs)
        if resultado.crs_metrico_nacional:
            logger.info("CRS métrico detectado: huso UTM será atributo derivado del tile MGRS.")
        else:
            logger.info("CRS geográfico: grilla anclada a píxeles nativos del raster.")
    else:
        logger.error("Grillas INCOMPATIBLES — ejecute scripts/02_alinear_ecorregiones.py")
        for d in diferencias:
            logger.error("  • %s", d)
    return resultado


def verificar_anios(lulc_dir: Path, patron: str, inicio: int, fin: int) -> list[int]:
    faltantes = []
    for anio in range(inicio, fin + 1):
        if not (lulc_dir / patron.format(year=anio)).is_file():
            faltantes.append(anio)
    return faltantes


def verificar_mgrs(ruta: Path, campo: str) -> None:
    import geopandas as gpd

    if not ruta.is_file():
        raise FileNotFoundError(f"Vector MGRS no encontrado: {ruta}")
    gdf = gpd.read_file(ruta)
    if campo not in gdf.columns:
        raise ValueError(f"Campo {campo!r} ausente en {ruta}. Columnas: {list(gdf.columns)}")


def metadatos_dict(r: ResultadoVerificacion) -> dict:
    return asdict(r)
