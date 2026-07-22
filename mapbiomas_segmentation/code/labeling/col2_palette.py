"""MapBiomas Collection 2 palette for label overlay visualization."""

from __future__ import annotations

# Canonical Col2 class ids (MapBiomas Chile Collection 2).
CLASES_VALIDAS: list[int] = [
    3, 59, 60, 67, 11, 12, 63, 66, 15, 18, 9, 23, 61, 29, 24, 25, 33, 34, 27,
    79, 80, 62,
]

# Official MapBiomas palette keyed by class id (not list position).
COL2_RGB: dict[int, tuple[int, int, int]] = {
    3: (31, 141, 73),
    59: (31, 141, 73),
    60: (92, 184, 93),
    67: (200, 255, 180),
    11: (81, 151, 153),
    12: (214, 188, 116),
    63: (235, 248, 181),
    66: (168, 147, 88),
    15: (237, 222, 142),
    18: (233, 116, 237),
    9: (122, 89, 0),
    23: (255, 160, 122),
    61: (245, 213, 213),
    29: (255, 170, 95),
    24: (212, 39, 30),
    25: (219, 77, 79),
    33: (37, 50, 228),
    34: (147, 223, 230),
    27: (255, 255, 255),
    79: (122, 89, 0),
    80: (122, 89, 0),
    62: (208, 181, 181),
}

# Sentinel labels from assignment (not in landcover raster).
SENTINEL_RGB: dict[int, tuple[int, int, int]] = {
    254: (80, 80, 80),
    255: (160, 160, 160),
}

COL2_RGB.update(SENTINEL_RGB)

COL2_NAMES: dict[int, str] = {
    3: "Otra formación boscosa",
    9: "Plantación",
    11: "Humedal",
    12: "Pastizal",
    15: "Pastura",
    18: "Cultivo / labranza",
    23: "Arena, playa y duna",
    24: "Mosaico agro-forestal",
    25: "Otra área sin vegetación",
    27: "No observado",
    29: "Afloramiento rocoso",
    33: "Río, lago u océano",
    34: "Nieve y hielo",
    59: "Bosque primario",
    60: "Bosque secundario",
    61: "Salar",
    62: "Otra área sin vegetación II",
    63: "Estepa",
    66: "Matorral",
    67: "Bosque achaparrado",
    79: "Cultivo II",
    80: "Cultivo III",
    254: "Sin datos (segmento)",
    255: "Mixto (pureza < τ)",
}


def rgb_for_class(class_id: int) -> tuple[int, int, int]:
    """Return RGB for a Col2 class id."""
    if class_id in COL2_RGB:
        return COL2_RGB[class_id]
    return (200, 200, 200)


def build_lut(max_class: int = 255) -> tuple[list[tuple[float, float, float]], list[str]]:
    """Build float RGB LUT (0-1) and names for classes 0..max_class."""
    colors: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * (max_class + 1)
    names: list[str] = [""] * (max_class + 1)
    for cls_id in range(max_class + 1):
        r, g, b = rgb_for_class(cls_id)
        colors[cls_id] = (r / 255.0, g / 255.0, b / 255.0)
        names[cls_id] = COL2_NAMES.get(cls_id, f"Clase {cls_id}")
    return colors, names
