"""MapBiomas Collection 2 — nodata values, protected tier, and class names."""

from __future__ import annotations

C2_NODATA: frozenset[int] = frozenset({0, 27})

CLASES_TIER_PROTEGIDO: frozenset[int] = frozenset({
    3, 11, 23, 24, 33, 34, 61, 67,
})

CLASS_NAMES: dict[int, str] = {
    3: "Bosque",
    9: "Silvicultura",
    11: "Humedal",
    12: "Pastizal",
    15: "Pastura",
    18: "Agricultura",
    23: "Arena_playa_duna",
    24: "Zona_urbana",
    25: "Otra_area_sin_vegetacion",
    27: "No_observado",
    29: "Afloramiento_rocoso",
    33: "Rio_lago_oceano",
    34: "Glaciar",
    59: "Bosque_primario",
    60: "Bosque_secundario",
    61: "Salar",
    63: "Estepa",
    66: "Matorral",
    67: "Bosque_achaparrado",
    79: "Silvicultura_coniferas",
    80: "Silvicultura_latifoliadas",
}


def class_name(clase_id: int) -> str:
    if clase_id == 0:
        return ""
    return CLASS_NAMES.get(int(clase_id), f"class_{int(clase_id)}")


nombre_clase = class_name
