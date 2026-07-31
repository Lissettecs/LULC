"""MapBiomas Collection 2 — clases nodata, tier protegido y nombres."""

from __future__ import annotations

# Píxeles excluidos del cómputo de pureza / moda
C2_NODATA: frozenset[int] = frozenset({0, 27})

# Tier protegido: si aparece ≥1 píxel en el segmento → tiene_protegida=True
# (aunque no sea la moda). Referencia: seg-labeling exp_buffer + ssl4eo CLASES_PROTEGIDAS
CLASES_TIER_PROTEGIDO: frozenset[int] = frozenset({
    3,   # Bosque / tamarugo
    11,  # Humedal
    23,  # Arena, playa y duna
    24,  # Zona urbana / mosaico agro-forestal
    33,  # Río, lago u océano
    34,  # Glaciar / nieve y hielo
    61,  # Salar
    67,  # Bosque achaparrado
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


def nombre_clase(clase_id: int) -> str:
    if clase_id == 0:
        return ""
    return CLASS_NAMES.get(int(clase_id), f"clase_{int(clase_id)}")
