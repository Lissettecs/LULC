"""
Bandas seleccionadas por tile (RF_N, importance_gated_clusters).

Fuente: random_forest/REPORT/REPORT.md — selección per-tile Level 1 y Level 3.
Índices = catálogo RF (band_0 … band_183); al leer GeoTIFF se resuelven por nombre
en rasterio descriptions (el orden del TIF puede diferir del índice).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_RF_ROOT = Path(__file__).resolve().parents[3] / "random_forest"
if str(_RF_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_RF_ROOT.parent))

from random_forest.core.band_catalog import RF_BAND_NAMES, band_name  # noqa: E402

# Level 1 — per-tile RF_N (REPORT §2.1)
SELECTED_INDICES_LV1: dict[str, list[int]] = {
    "19KDU": [
        0, 3, 9, 10, 22, 29, 33, 43, 47, 48, 80, 86, 91, 92, 93, 95, 97, 102, 104,
        106, 107, 109, 114, 121, 123, 124, 125, 136, 143, 151, 154, 167, 176, 178, 179,
    ],
    "19JCJ": [
        0, 8, 9, 13, 14, 23, 25, 38, 42, 49, 60, 68, 80, 90, 92, 93, 94, 95, 97, 102,
        103, 104, 106, 107, 123, 142, 144, 147, 149, 154, 161, 163, 172, 174, 179,
    ],
    "19HCD": [
        0, 4, 9, 10, 12, 20, 24, 35, 38, 39, 41, 46, 49, 53, 54, 56, 61, 63, 68, 90,
        92, 96, 101, 102, 103, 122, 123, 142, 149, 153, 154, 157, 166, 170, 172, 179, 183,
    ],
    "18HYD": [
        2, 9, 10, 11, 13, 17, 18, 22, 29, 38, 42, 43, 46, 47, 48, 61, 63, 64, 81, 90,
        92, 99, 102, 103, 104, 107, 111, 119, 122, 124, 125, 136, 143, 148, 150, 153,
        154, 167, 172,
    ],
    "18GXP": [
        0, 10, 11, 13, 25, 29, 32, 34, 38, 39, 41, 42, 45, 46, 48, 60, 61, 68, 81, 90,
        92, 94, 95, 101, 102, 103, 107, 121, 122, 123, 124, 138, 142, 144, 154, 170, 171,
        178, 181, 183,
    ],
    "18FXH": [
        0, 4, 10, 12, 13, 22, 27, 30, 32, 35, 38, 39, 40, 41, 42, 43, 46, 48, 52, 55,
        59, 63, 64, 68, 80, 81, 90, 92, 93, 96, 102, 107, 112, 113, 120, 121, 123, 136,
        144, 154, 164, 169,
    ],
}

# Level 3 — per-tile RF_N (REPORT Lv3 §2.1)
SELECTED_INDICES_LV3: dict[str, list[int]] = {
    "19KDU": [
        0, 8, 10, 22, 33, 43, 48, 56, 68, 81, 92, 94, 97, 99, 101, 102, 104, 106, 107,
        115, 120, 121, 123, 129, 130, 136, 138, 143, 150, 154, 170, 176, 181,
    ],
    "19JCJ": [
        3, 22, 26, 29, 32, 38, 42, 48, 49, 81, 90, 92, 94, 95, 97, 99, 101, 104, 107,
        109, 117, 119, 121, 125, 135, 143, 148, 150, 154, 161, 165, 176, 180,
    ],
    "19HCD": [
        0, 4, 9, 10, 11, 12, 14, 22, 27, 34, 38, 39, 42, 43, 46, 80, 84, 90, 91, 92, 94,
        95, 97, 99, 101, 102, 103, 104, 110, 119, 122, 123, 125, 130, 138, 139, 150,
        151, 154, 163, 166, 171, 172, 180, 181,
    ],
    "18HYD": [
        3, 9, 12, 13, 17, 22, 24, 25, 29, 30, 38, 39, 41, 48, 59, 80, 86, 90, 92, 98,
        99, 102, 106, 107, 108, 121, 123, 124, 129, 144, 145, 148, 154, 164,
    ],
    "18GXP": [
        0, 10, 12, 13, 22, 27, 37, 38, 39, 40, 41, 46, 48, 49, 53, 61, 68, 90, 92, 94,
        95, 97, 98, 100, 101, 102, 103, 104, 107, 108, 121, 122, 123, 127, 136, 142,
        144, 154, 163, 168, 171, 172, 173, 176, 177,
    ],
    "18FXH": [
        0, 1, 3, 10, 13, 22, 32, 38, 39, 40, 47, 48, 63, 68, 80, 90, 93, 95, 98, 99,
        100, 101, 102, 103, 104, 106, 107, 110, 114, 133, 136, 142, 145, 148, 149,
        150, 154, 162, 167, 170,
    ],
}

RGB_DISPLAY_NAMES = ("nir_median", "swir1_median", "red_median")
RGB_FALLBACK_NAMES = ("nir_median", "green_median", "ndvi_max")


def indices_para_tile(tile: str, level: int = 1) -> list[int]:
    tile = tile.upper()
    tabla = SELECTED_INDICES_LV1 if level == 1 else SELECTED_INDICES_LV3
    if tile not in tabla:
        raise KeyError(f"Sin bandas RF_N para tile={tile} level={level}")
    return list(tabla[tile])


def nombres_para_indices(indices: list[int]) -> list[str]:
    return [band_name(i) for i in indices]


def cargar_indices_desde_json(ruta: Path) -> list[int]:
    with ruta.open(encoding="utf-8") as f:
        payload = json.load(f)
    if "selected_indices" in payload:
        return [int(i) for i in payload["selected_indices"]]
    if "indices" in payload:
        return [int(i) for i in payload["indices"]]
    raise ValueError(f"JSON sin selected_indices: {ruta}")


def resolver_posiciones_geotiff(descriptions: tuple[str, ...] | list[str], nombres: list[str]) -> list[int]:
    """Posiciones 0-based en el stack leído, según nombres en descriptions del GeoTIFF."""
    mapa = {d: i for i, d in enumerate(descriptions) if d}
    faltantes = [n for n in nombres if n not in mapa]
    if faltantes:
        raise KeyError(
            "Bandas no encontradas en descriptions del GeoTIFF: "
            + ", ".join(faltantes)
        )
    return [mapa[n] for n in nombres]


def resolver_rgb_desde_descriptions(descriptions: tuple[str, ...] | list[str]) -> list[int]:
    mapa = {d: i for i, d in enumerate(descriptions) if d}
    for trio in (RGB_DISPLAY_NAMES, RGB_FALLBACK_NAMES):
        if all(n in mapa for n in trio):
            return [mapa[n] for n in trio]
    disponibles = [i for i, d in enumerate(descriptions) if d]
    if len(disponibles) >= 3:
        return disponibles[:3]
    raise ValueError("No hay suficientes bandas para RGB en el mosaico 184B")


def validar_catalogo() -> None:
    """Comprueba que todos los índices embebidos existen en RF_BAND_NAMES."""
    n = len(RF_BAND_NAMES)
    for level, tabla in ((1, SELECTED_INDICES_LV1), (3, SELECTED_INDICES_LV3)):
        for tile, idxs in tabla.items():
            for i in idxs:
                if not (0 <= i < n):
                    raise ValueError(f"Índice inválido tile={tile} lv={level}: {i}")
