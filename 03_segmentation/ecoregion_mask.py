"""Máscara espacial de ecorregiones alineada a la ventana del mosaico."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.warp import reproject

# En ecorregiones_col3: nodata=0 y 0 = océano / fuera de cobertura.
ECORREGION_NODATA = 0


def mascara_ecorregion_en_ventana(
    ruta_ecorregiones: Path,
    *,
    transform,
    crs,
    height: int,
    width: int,
) -> tuple[np.ndarray, float]:
    """
    Devuelve máscara bool (True = tierra / ecorregión válida) alineada a la grilla dada.

    Remuestrea por vecino más cercano (nunca bilineal). También reporta
    ``ocean_masked_frac`` = fracción de píxeles inválidos en la ventana.
    """
    if not ruta_ecorregiones.is_file():
        raise FileNotFoundError(ruta_ecorregiones)

    destino = np.zeros((height, width), dtype=np.uint8)
    with rasterio.open(ruta_ecorregiones) as src:
        reproject(
            source=rasterio.band(src, 1),
            destination=destino,
            src_transform=src.transform,
            src_crs=src.crs,
            dst_transform=transform,
            dst_crs=crs,
            src_nodata=src.nodata if src.nodata is not None else ECORREGION_NODATA,
            dst_nodata=ECORREGION_NODATA,
            resampling=Resampling.nearest,
        )

    valida = destino > 0
    ocean_frac = float((~valida).sum()) / float(destino.size)
    return valida, ocean_frac
