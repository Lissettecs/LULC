"""Paleta RGB MapBiomas C2 para visualización."""

from __future__ import annotations

COL2_RGB: dict[int, tuple[int, int, int]] = {
    3: (31, 141, 73),
    9: (122, 89, 0),
    11: (81, 151, 153),
    12: (214, 188, 116),
    15: (237, 222, 142),
    18: (233, 116, 237),
    23: (255, 160, 122),
    24: (212, 39, 30),
    25: (219, 77, 79),
    29: (255, 170, 95),
    33: (37, 50, 228),
    34: (147, 223, 230),
    59: (31, 141, 73),
    60: (92, 184, 93),
    67: (200, 255, 180),
    61: (245, 213, 213),
    63: (235, 248, 181),
    66: (168, 147, 88),
    79: (122, 89, 0),
    80: (122, 89, 0),
}

DEFAULT_RGB = (180, 180, 180)


def rgb_clase(clase_id: int) -> tuple[int, int, int]:
    return COL2_RGB.get(int(clase_id), DEFAULT_RGB)


def rgba_css(clase_id: int, alpha: float = 0.75) -> str:
    r, g, b = rgb_clase(clase_id)
    return f"rgba({r},{g},{b},{alpha})"
