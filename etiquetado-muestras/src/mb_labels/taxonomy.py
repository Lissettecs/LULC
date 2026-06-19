#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Taxonomía de muestreo MapBiomas Chile — Niveles 1, 2 y 3.

Nota clave:
  11 = Humedal
  73 = Turberas
  74 = Otros_humedales
"""

from __future__ import annotations

_TAXONOMY: dict[int, tuple] = {
    1:  (1, "1", "Formacion_boscosa", "1.0", "Formacion_boscosa", "1.0.0", "Formacion_boscosa", False, False),
    3:  (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.0", "Bosque", False, False),
    59: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.1", "Bosque_primario", False, False),
    60: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.2", "Bosque_secundario", False, False),
    67: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.3", "Bosque_achaparrado", False, True),
    10: (2, "2", "Form_natural_no_boscosa", "2.0", "Form_natural_no_boscosa", "2.0.0", "Form_natural_no_boscosa", False, False),
    11: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.0", "Humedal", True, False),
    73: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.1", "Turberas", True, False),
    74: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.2", "Otros_humedales", True, False),
    12: (2, "2", "Form_natural_no_boscosa", "2.2", "Pastizal", "2.2.0", "Pastizal", False, False),
    63: (2, "2", "Form_natural_no_boscosa", "2.3", "Estepa", "2.3.0", "Estepa", False, False),
    66: (2, "2", "Form_natural_no_boscosa", "2.4", "Matorral", "2.4.0", "Matorral", False, False),
    14: (3, "3", "Agropecuaria_silvicultura", "3.0", "Agropecuaria_silvicultura", "3.0.0", "Agropecuaria_silvicultura", False, False),
    15: (3, "3", "Agropecuaria_silvicultura", "3.1", "Pastura", "3.1.0", "Pastura", False, False),
    18: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.0", "Agricultura", True, False),
    19: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.1", "Cultivos_temporales", True, False),
    36: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.2", "Cultivos_perennes", True, False),
    9:  (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.0", "Silvicultura", True, False),
    79: (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.1", "Coniferas", True, False),
    80: (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.2", "Latifoliadas", True, False),
    22: (4, "4", "Area_sin_vegetacion", "4.0", "Area_sin_vegetacion", "4.0.0", "Area_sin_vegetacion", False, False),
    23: (4, "4", "Area_sin_vegetacion", "4.1", "Arena_playa_duna", "4.1.0", "Arena_playa_duna", False, True),
    61: (4, "4", "Area_sin_vegetacion", "4.2", "Salar", "4.2.0", "Salar", False, True),
    29: (4, "4", "Area_sin_vegetacion", "4.3", "Afloramiento_rocoso", "4.3.0", "Afloramiento_rocoso", False, False),
    24: (4, "4", "Area_sin_vegetacion", "4.4", "Zonas_urbanas", "4.4.0", "Zonas_urbanas", True, False),
    30: (4, "4", "Area_sin_vegetacion", "4.5", "Mineria", "4.5.0", "Mineria", True, False),
    75: (4, "4", "Area_sin_vegetacion", "4.6", "Areas_fotovoltaicas", "4.6.0", "Areas_fotovoltaicas", True, False),
    25: (4, "4", "Area_sin_vegetacion", "4.7", "Otra_sin_vegetacion", "4.7.0", "Otra_sin_vegetacion", False, False),
    26: (5, "5", "Cuerpo_de_agua", "5.0", "Cuerpo_de_agua", "5.0.0", "Cuerpo_de_agua", False, False),
    33: (5, "5", "Cuerpo_de_agua", "5.1", "Rio_lago_oceano", "5.1.0", "Rio_lago_oceano", False, True),
    34: (5, "5", "Cuerpo_de_agua", "5.2", "Glaciar", "5.2.0", "Glaciar", True, False),
    35: (5, "5", "Cuerpo_de_agua", "5.2", "Glaciar", "5.2.0", "Glaciar", True, False),
    27: (6, "6", "No_observado", "6.0", "No_observado", "6.0.0", "No_observado", False, False),
}

NIVEL3_CLASS_IDS = list(_TAXONOMY.keys())
TRANSVERSAL_N3_IDS = [k for k, v in _TAXONOMY.items() if v[7]]
CRITICAL_N3_IDS = [k for k, v in _TAXONOMY.items() if v[8]]


def lookup_taxonomy(class_id: int | str) -> dict[str, str | int | bool]:
    try:
        cid = int(class_id)
        row = _TAXONOMY[cid]
    except (TypeError, ValueError, KeyError):
        return {
            "class_id": -9999,
            "class_name": "sin_nombre",
            "n1_cd": "", "n1_nm": "sin_nombre",
            "n2_cd": "", "n2_nm": "sin_nombre",
            "n3_cd": "", "n3_nm": "sin_nombre",
            "es_transversal": False,
            "es_critica_n3": False,
        }
    return {
        "class_id": cid,
        "class_name": row[6],
        "n1_cd": row[1], "n1_nm": row[2],
        "n2_cd": row[3], "n2_nm": row[4],
        "n3_cd": row[5], "n3_nm": row[6],
        "es_transversal": bool(row[7]),
        "es_critica_n3": bool(row[8]),
    }
