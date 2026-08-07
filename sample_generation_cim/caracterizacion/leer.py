"""Lectura de ventanas de píxeles, sin reproyección ni remuestreo.

Como las celdas se construyeron sobre la grilla nativa del ráster, cada una es
una ventana de píxeles enteros: se lee con un offset y un tamaño, y los valores
que salen son los del archivo, sin interpolar. Esto es lo que se gana respecto de
v02, donde cada rectángulo UTM había que reproyectarlo desde 4326.

Se lee una sola ventana por carta y por año (26 lecturas) y después se recortan
las celdas en memoria, en vez de hacer una lectura por celda y por año (1.820
lecturas para una carta de 70 celdas).
"""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.windows import Window

from config import params_caracterizacion as P


def anios() -> list[int]:
    return list(range(P.START_YEAR, P.END_YEAR + 1))


def ruta_lulc(anio: int):
    return P.LULC_DIR / P.LULC_PATRON.format(year=anio)


def perfil_referencia() -> dict:
    """Transform, tamaño y resolución de la grilla de píxeles."""
    with rasterio.open(ruta_lulc(P.START_YEAR)) as src:
        return {
            "transform": src.transform,
            "width": int(src.width),
            "height": int(src.height),
            "res": float(src.res[0]),
            "lon_origen": float(src.bounds.left),
            "lat_origen": float(src.bounds.top),
        }


def _leer_recortado(src, col_off: int, row_off: int, w: int, h: int, relleno) -> np.ndarray:
    """Lee la ventana rellenando con `relleno` la parte que cae fuera del ráster.

    Fuera del ráster no hay dato, que es exactamente la semántica de la clase 0,
    así que las celdas que asoman al mar o al borde del mosaico quedan marcadas
    como nodata en lugar de fallar.
    """
    salida = np.full((h, w), relleno, dtype=src.dtypes[0])
    c0, r0 = max(0, col_off), max(0, row_off)
    c1, r1 = min(src.width, col_off + w), min(src.height, row_off + h)
    if c1 <= c0 or r1 <= r0:
        return salida
    datos = src.read(1, window=Window(c0, r0, c1 - c0, r1 - r0))
    salida[r0 - row_off : r1 - row_off, c0 - col_off : c1 - col_off] = datos
    return salida


class LectorCarta:
    """Mantiene en memoria la ventana que cubre todas las celdas de una carta."""

    def __init__(self, celdas, celda_px: int, lista_anios: list[int] | None = None):
        self.celda_px = celda_px
        self.anios = lista_anios or anios()
        self.ref = perfil_referencia()

        self.col_off = int(celdas["px_col_off"].min())
        self.row_off = int(celdas["px_row_off"].min())
        self.width = int(celdas["px_col_off"].max()) + celda_px - self.col_off
        self.height = int(celdas["px_row_off"].max()) + celda_px - self.row_off

        self.lulc = np.zeros((len(self.anios), self.height, self.width), dtype=np.uint8)
        for i, anio in enumerate(self.anios):
            with rasterio.open(ruta_lulc(anio)) as src:
                if (src.width, src.height) != (self.ref["width"], self.ref["height"]):
                    raise ValueError(f"{ruta_lulc(anio)} no comparte grilla con la referencia")
                self.lulc[i] = _leer_recortado(
                    src, self.col_off, self.row_off, self.width, self.height,
                    P.CLASE_NODATA_RASTER,
                )

        with rasterio.open(P.ECO_RASTER) as src:
            if (src.width, src.height) != (self.ref["width"], self.ref["height"]):
                raise ValueError(f"{P.ECO_RASTER} no está alineado con el landcover")
            self.eco = _leer_recortado(
                src, self.col_off, self.row_off, self.width, self.height, P.ECO_NODATA
            )

    @property
    def memoria_mb(self) -> float:
        return (self.lulc.nbytes + self.eco.nbytes) / 1e6

    def celda(self, px_col_off: int, px_row_off: int) -> tuple[np.ndarray, np.ndarray]:
        """Stack anual (n_años, lado, lado) y ecorregión (lado, lado) de una celda."""
        c = int(px_col_off) - self.col_off
        r = int(px_row_off) - self.row_off
        n = self.celda_px
        if c < 0 or r < 0 or c + n > self.width or r + n > self.height:
            raise IndexError(f"Celda fuera de la ventana de la carta: ({px_col_off}, {px_row_off})")
        return self.lulc[:, r : r + n, c : c + n], self.eco[r : r + n, c : c + n]

    def lat_norte(self, px_row_off: int) -> float:
        """Latitud del borde norte de la celda, para calcular el área de sus filas."""
        return self.ref["lat_origen"] - int(px_row_off) * self.ref["res"]
