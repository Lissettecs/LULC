"""Exclusión de modal transversal del modelo general."""

from __future__ import annotations

import pandas as pd

from config.diccionarios import CLASES_MASCARA, CLASES_TRANSVERSALES

MODAL_EXCLUIDOS = sorted(set(CLASES_TRANSVERSALES) | set(CLASES_MASCARA) | {14, 27})


def modal_transversal_mask(df: pd.DataFrame, id_col: str = "lulc_mode_id") -> pd.Series:
    mode = pd.to_numeric(df.get(id_col, -9999), errors="coerce").fillna(-9999).astype(int)
    mask = mode.isin(MODAL_EXCLUIDOS)
    if "transversal_pct" in df.columns:
        tran = pd.to_numeric(df["transversal_pct"], errors="coerce").fillna(0)
        mask |= (tran >= 25.0) & mode.isin(CLASES_TRANSVERSALES)
    return mask


def anotar_modal_transversal(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["modal_transversal"] = modal_transversal_mask(out)
    out["general_model_ok"] = ~out["modal_transversal"]
    return out
