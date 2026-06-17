"""
Taxonomia de muestreo MapBiomas Chile — Niveles 1, 2 y 3.

Alineada con la leyenda Collection 3 (MapBiomas Chile, 2025).
Mapea IDs de pixel de la clasificacion nativa (sin remapeo general) a la
jerarquia de muestreo. Usar con class_level=n3 en caracterizacion_grillas_gee.py.

Nota: en C3, 11 = Humedal (L2) y 73 = Turberas (L3). No confundir.
IDs marcados con ? en la leyenda publicada (p. ej. 1.1.4 Otra formacion boscosa)
quedan pendientes hasta confirmar el pixel value en el asset.
"""

from __future__ import annotations

# id -> (n1_id, n1_cd, n1_nm, n2_cd, n2_nm, n3_cd, n3_nm, es_transversal, es_critica)
_TAXONOMY: dict[int, tuple] = {
    # 1. Formacion boscosa
    1:  (1, "1", "Formacion_boscosa", "1.0", "Formacion_boscosa", "1.0.0", "Formacion_boscosa", False, False),
    3:  (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.0", "Bosque", False, False),
    59: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.1", "Bosque_primario", False, False),
    60: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.2", "Bosque_secundario", False, False),
    67: (1, "1", "Formacion_boscosa", "1.1", "Bosque", "1.1.3", "Bosque_achaparrado", False, True),
    # 1.1.4 Otra_Formacion_boscosa: ID pendiente en leyenda C3
    # 2. Formacion natural no boscosa
    10: (2, "2", "Form_natural_no_boscosa", "2.0", "Form_natural_no_boscosa", "2.0.0", "Form_natural_no_boscosa", False, False),
    11: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.0", "Humedal", True, False),
    73: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.1", "Turberas", True, False),
    74: (2, "2", "Form_natural_no_boscosa", "2.1", "Humedal", "2.1.2", "Otros_humedales", True, False),
    12: (2, "2", "Form_natural_no_boscosa", "2.2", "Pastizal", "2.2.0", "Pastizal", False, False),
    63: (2, "2", "Form_natural_no_boscosa", "2.3", "Estepa", "2.3.0", "Estepa", False, False),
    66: (2, "2", "Form_natural_no_boscosa", "2.4", "Matorral", "2.4.0", "Matorral", False, False),
    # 3. Agropecuaria y silvicultura
    14: (3, "3", "Agropecuaria_silvicultura", "3.0", "Agropecuaria_silvicultura", "3.0.0", "Agropecuaria_silvicultura", False, False),
    15: (3, "3", "Agropecuaria_silvicultura", "3.1", "Pastura", "3.1.0", "Pastura", False, False),
    18: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.0", "Agricultura", True, False),
    19: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.1", "Cultivos_temporales", True, False),
    36: (3, "3", "Agropecuaria_silvicultura", "3.2", "Agricultura", "3.2.2", "Cultivos_perennes", True, False),
    9:  (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.0", "Silvicultura", True, False),
    79: (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.1", "Coniferas", True, False),
    80: (3, "3", "Agropecuaria_silvicultura", "3.3", "Silvicultura", "3.3.2", "Latifoliadas", True, False),
    # 4. Area sin vegetacion
    22: (4, "4", "Area_sin_vegetacion", "4.0", "Area_sin_vegetacion", "4.0.0", "Area_sin_vegetacion", False, False),
    23: (4, "4", "Area_sin_vegetacion", "4.1", "Arena_playa_duna", "4.1.0", "Arena_playa_duna", False, True),
    61: (4, "4", "Area_sin_vegetacion", "4.2", "Salar", "4.2.0", "Salar", False, True),
    29: (4, "4", "Area_sin_vegetacion", "4.3", "Afloramiento_rocoso", "4.3.0", "Afloramiento_rocoso", False, False),
    24: (4, "4", "Area_sin_vegetacion", "4.4", "Zonas_urbanas", "4.4.0", "Zonas_urbanas", True, False),
    30: (4, "4", "Area_sin_vegetacion", "4.5", "Mineria", "4.5.0", "Mineria", True, False),
    75: (4, "4", "Area_sin_vegetacion", "4.6", "Areas_fotovoltaicas", "4.6.0", "Areas_fotovoltaicas", True, False),
    25: (4, "4", "Area_sin_vegetacion", "4.7", "Otra_sin_vegetacion", "4.7.0", "Otra_sin_vegetacion", False, False),
    # 5. Cuerpo de agua
    26: (5, "5", "Cuerpo_de_agua", "5.0", "Cuerpo_de_agua", "5.0.0", "Cuerpo_de_agua", False, False),
    33: (5, "5", "Cuerpo_de_agua", "5.1", "Rio_lago_oceano", "5.1.0", "Rio_lago_oceano", False, True),
    34: (5, "5", "Cuerpo_de_agua", "5.2", "Glaciar", "5.2.0", "Glaciar", True, False),
    # 6. No observado
    27: (6, "6", "No_observado", "6.0", "No_observado", "6.0.0", "No_observado", False, False),
}

NIVEL3_CLASS_IDS = list(_TAXONOMY.keys())

NIVEL3_NAMES_DICT: dict[str, str] = {str(k): v[6] for k, v in _TAXONOMY.items()}
NIVEL1_CODE_DICT: dict[str, str] = {str(k): v[1] for k, v in _TAXONOMY.items()}
NIVEL2_CODE_DICT: dict[str, str] = {str(k): v[3] for k, v in _TAXONOMY.items()}
NIVEL3_CODE_DICT: dict[str, str] = {str(k): v[5] for k, v in _TAXONOMY.items()}
NIVEL1_NAMES_DICT: dict[str, str] = {str(k): v[2] for k, v in _TAXONOMY.items()}
NIVEL2_NAMES_DICT: dict[str, str] = {str(k): v[4] for k, v in _TAXONOMY.items()}
TRANSVERSAL_N3_IDS = [k for k, v in _TAXONOMY.items() if v[7]]
CRITICAL_N3_IDS = [k for k, v in _TAXONOMY.items() if v[8]]

# Modal excluida del pool del modelo general SSL4EO (modelos especializados aparte).
GENERAL_MODEL_EXCLUDED_MODAL_IDS = sorted(set(TRANSVERSAL_N3_IDS) | {14})

# Tras remapeo general GEE, humedal/urbano transversal puede quedar como modal 10 u 22.
GENERAL_MODAL_TRANSVERSAL_PROXY = (10, 22)
GENERAL_MODAL_TRANSVERSAL_MIN_PCT = 25.0


def lookup_taxonomy(class_id: int | str) -> dict[str, str | int | bool]:
    """Devuelve metadatos de taxonomia para un ID nativo."""
    try:
        row = _TAXONOMY[int(class_id)]
    except (TypeError, ValueError, KeyError):
        return {
            "class_id": -9999,
            "n1_cd": "", "n1_nm": "sin_nombre",
            "n2_cd": "", "n2_nm": "sin_nombre",
            "n3_cd": "", "n3_nm": "sin_nombre",
            "es_transversal": False,
            "es_critica_n3": False,
        }
    return {
        "class_id": int(class_id),
        "n1_cd": row[1], "n1_nm": row[2],
        "n2_cd": row[3], "n2_nm": row[4],
        "n3_cd": row[5], "n3_nm": row[6],
        "es_transversal": row[7],
        "es_critica_n3": row[8],
    }


def transversal_modal_mask(
    df: "pd.DataFrame",
    *,
    id_col: str = "lulc_mode_id",
    transversal_pct_col: str = "transversal_pct",
    min_proxy_pct: float = GENERAL_MODAL_TRANSVERSAL_MIN_PCT,
) -> "pd.Series":
    """
    True si la clase modal del rectangulo es transversal → excluir del modelo general.

    - IDs nativos nivel 2/3 transversales (11 Humedal, 73 Turberas, 18 Agricultura, …)
    - ID 14 Agropecuaria_silvicultura (modelo agro especializado)
    - Proxy en grillas general-remapped: modal 10 u 22 con transversal_pct alto
    """
    import pandas as pd

    mode_id = pd.to_numeric(df.get(id_col, -9999), errors="coerce").fillna(-9999).astype(int)
    mask = mode_id.isin(GENERAL_MODEL_EXCLUDED_MODAL_IDS)

    if transversal_pct_col in df.columns:
        tran = pd.to_numeric(df[transversal_pct_col], errors="coerce").fillna(0)
        mask |= mode_id.isin(GENERAL_MODAL_TRANSVERSAL_PROXY) & (tran >= min_proxy_pct)

    return mask


def annotate_transversal_modal(df: "pd.DataFrame", **kwargs) -> "pd.DataFrame":
    """Anade modal_transversal y general_model_ok."""
    out = df.copy()
    out["modal_transversal"] = transversal_modal_mask(out, **kwargs)
    out["general_model_ok"] = ~out["modal_transversal"]
    return out


def annotate_dataframe(df, id_col: str = "lulc_mode_id", prefix: str = "") -> "pd.DataFrame":
    """Anade columnas n1/n2/n3 a un DataFrame con columna de ID de clase."""
    import pandas as pd

    out = df.copy()
    p = f"{prefix}_" if prefix else ""

    def row_tax(cid):
        t = lookup_taxonomy(cid)
        return pd.Series({
            f"{p}n1_cd": t["n1_cd"], f"{p}n1_nm": t["n1_nm"],
            f"{p}n2_cd": t["n2_cd"], f"{p}n2_nm": t["n2_nm"],
            f"{p}n3_cd": t["n3_cd"], f"{p}n3_nm": t["n3_nm"],
            f"{p}es_transversal": t["es_transversal"],
            f"{p}es_critica_n3": t["es_critica_n3"],
        })

    if id_col not in out.columns:
        return out
    tax_cols = out[id_col].apply(row_tax)
    for col in tax_cols.columns:
        out[col] = tax_cols[col]
    return out
