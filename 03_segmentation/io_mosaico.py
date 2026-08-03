"""Lectura de ventanas del mosaico multibanda recortadas a rectángulos."""

from __future__ import annotations

import numpy as np
import rasterio
from rasterio.features import geometry_window
from rasterio.mask import mask
from rasterio.windows import Window

from config.params_slic import MOSAIC_NODATA


def ventana_rectangulo(src: rasterio.io.DatasetReader, geom) -> Window:
    win = geometry_window(src, [geom], pad_x=0, pad_y=0)
    return win.round_offsets().round_lengths()


def ventana_con_buffer(
    win: Window,
    buffer_px: int,
    raster_w: int,
    raster_h: int,
) -> tuple[Window, dict[str, int]]:
    col_off = int(win.col_off)
    row_off = int(win.row_off)
    width = int(win.width)
    height = int(win.height)
    col0 = max(0, col_off - buffer_px)
    row0 = max(0, row_off - buffer_px)
    col1 = min(raster_w, col_off + width + buffer_px)
    row1 = min(raster_h, row_off + height + buffer_px)
    effective = {
        "left": col_off - col0,
        "right": col1 - (col_off + width),
        "top": row_off - row0,
        "bottom": row1 - (row_off + height),
    }
    return Window(col0, row0, col1 - col0, row1 - row0), effective


def recortar_centro(arr: np.ndarray, buffer_efectivo: dict[str, int]) -> np.ndarray:
    t = buffer_efectivo
    row0 = t["top"]
    row1 = arr.shape[0] - t["bottom"] if t["bottom"] else arr.shape[0]
    col0 = t["left"]
    col1 = arr.shape[1] - t["right"] if t["right"] else arr.shape[1]
    return arr[row0:row1, col0:col1].copy()


def leer_bandas_ventana(
    src: rasterio.io.DatasetReader,
    window: Window,
    indices_bandas: list[int],
) -> np.ndarray:
    return np.stack(
        [src.read(i, window=window).astype(np.float32) for i in indices_bandas],
        axis=-1,
    )


def leer_ventana_ampliada(
    src: rasterio.io.DatasetReader,
    geom,
    indices_bandas: list[int],
    buffer_px: int,
) -> tuple[np.ndarray, np.ndarray, Window, dict[str, int], rasterio.Affine]:
    """Lee mosaico con buffer perimetral antes del recorte al rectángulo."""
    win_rect = ventana_rectangulo(src, geom)
    win_buf, buffer_efectivo = ventana_con_buffer(
        win_rect, buffer_px, src.width, src.height
    )
    stack_buf = leer_bandas_ventana(src, win_buf, indices_bandas)
    valido_buf = np.all(np.isfinite(stack_buf), axis=-1) & (
        stack_buf != MOSAIC_NODATA
    ).all(axis=-1)
    transform_rect = src.window_transform(win_rect)
    return stack_buf, valido_buf, win_rect, buffer_efectivo, transform_rect


def leer_bandas_recorte(
    src: rasterio.io.DatasetReader,
    geom,
    indices_bandas: list[int],
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Devuelve array (H,W,C), máscara válida y metadatos de ventana."""
    out_image, out_transform = mask(src, [geom], crop=True, filled=True, nodata=MOSAIC_NODATA)
    stack = np.stack([out_image[i - 1].astype(np.float32) for i in indices_bandas], axis=-1)
    valido = np.all(np.isfinite(stack), axis=-1) & (stack != MOSAIC_NODATA).all(axis=-1)
    meta = {
        "transform": out_transform,
        "width": stack.shape[1],
        "height": stack.shape[0],
        "crs": src.crs.to_string(),
    }
    return stack, valido, meta
