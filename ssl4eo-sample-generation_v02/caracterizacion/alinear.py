"""Alineación del raster de ecorregiones a la grilla del landcover."""

from __future__ import annotations

import logging
from pathlib import Path

import rasterio
from rasterio.windows import Window

from config import params_caracterizacion as P


def alinear_ecorregiones_a_landcover(
    eco_origen: Path,
    lulc_referencia: Path,
    salida: Path,
    logger: logging.Logger,
    *,
    col_offset: int = P.ECO_CROP_COL_OFFSET,
    row_offset: int = P.ECO_CROP_ROW_OFFSET,
) -> Path:
    """
    Recorta el raster de ecorregiones al extent del landcover.

    Las ecorregiones incluyen islas (Rapa Nui, Juan Fernández) ausentes en landcover;
    además hay un desfase de 1 píxel en origen. El recorte preserva vecino más cercano
    sin reproyectar: solo ventana de lectura/escritura.
    """
    if salida.is_file():
        logger.info("Raster alineado ya existe: %s", salida)
        return salida

    with rasterio.open(lulc_referencia) as lulc, rasterio.open(eco_origen) as eco:
        ventana = Window(col_offset, row_offset, lulc.width, lulc.height)
        if ventana.col_off + ventana.width > eco.width or ventana.row_off + ventana.height > eco.height:
            raise ValueError(
                f"Ventana de recorte fuera de límites del eco: {ventana} vs {eco.width}x{eco.height}"
            )
        datos = eco.read(1, window=ventana)
        perfil = eco.profile.copy()
        perfil.update(
            height=lulc.height,
            width=lulc.width,
            transform=lulc.transform,
            crs=lulc.crs,
            compress="deflate",
        )
        salida.parent.mkdir(parents=True, exist_ok=True)
        with rasterio.open(salida, "w", **perfil) as dst:
            dst.write(datos, 1)

    logger.info("Ecorregiones alineadas escritas en %s", salida)
    logger.info("  Origen recorte: col=%d fila=%d → %dx%d", col_offset, row_offset, lulc.width, lulc.height)
    return salida
