"""Presencia de clase en rectángulos (pct / pctp / ha)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import params_seleccion as P

UMBRAL_PRESENCIA_PCT = 5.0


def _asegurar_area_valida_ha(df: pd.DataFrame) -> pd.DataFrame:
    """Deriva area_valida_ha si falta, a partir de area_km2 × valid_area_pct."""
    if "area_valida_ha" in df.columns:
        return df
    if "area_km2" in df.columns and "valid_area_pct" in df.columns:
        out = df.copy()
        out["area_valida_ha"] = (
            pd.to_numeric(out["area_km2"], errors="coerce").fillna(0)
            * pd.to_numeric(out["valid_area_pct"], errors="coerce").fillna(0)
        )
        return out
    return df


def ha_clase_series(df: pd.DataFrame, class_id: int) -> pd.Series:
    """
    Superficie de la clase en hectáreas por rectángulo.

    Preferencia: columna ha_{id}. Si no existe, ha = pct_{id}/100 * area_valida_ha.
    """
    work = _asegurar_area_valida_ha(df)
    ha_col = f"ha_{class_id}"
    if ha_col in work.columns:
        return pd.to_numeric(work[ha_col], errors="coerce").fillna(0.0)

    pct_col = f"pct_{class_id}"
    if pct_col in work.columns and "area_valida_ha" in work.columns:
        pct = pd.to_numeric(work[pct_col], errors="coerce").fillna(0.0)
        area = pd.to_numeric(work["area_valida_ha"], errors="coerce").fillna(0.0)
        return pct / 100.0 * area

    raise ValueError(
        f"No se puede obtener ha_{class_id}: falta la columna '{ha_col}' y tampoco "
        f"hay '{pct_col}' + 'area_valida_ha' (ni area_km2/valid_area_pct para derivarla)."
    )


def piso_presencia_ha(class_id: int, piso_ha: float | None = None) -> float:
    if piso_ha is not None:
        return float(piso_ha)
    return float(P.PISO_PRESENCIA_HA_POR_CLASE.get(class_id, P.PISO_PRESENCIA_HA))


def presencia_clase_por_ha(
    df: pd.DataFrame,
    class_id: int,
    piso_ha: float | None = None,
) -> pd.Series:
    """Máscara booleana: ha_{id} >= piso (override por clase o PISO_PRESENCIA_HA)."""
    umbral = piso_presencia_ha(class_id, piso_ha)
    return ha_clase_series(df, class_id) >= umbral


def presencia_clase_mask(
    df: pd.DataFrame,
    class_id: int,
    *,
    min_pct: float = UMBRAL_PRESENCIA_PCT,
) -> pd.Series:
    """Filtro legacy por pct/pctp/moda — solo auditoría; no usar en pools censo/refuerzo."""
    mask = pd.Series(False, index=df.index)
    if "lulc_mode_id" in df.columns:
        mode = pd.to_numeric(df["lulc_mode_id"], errors="coerce").fillna(-9999).astype(int)
        mask |= mode == class_id
    if "lulc_last_id" in df.columns:
        last = pd.to_numeric(df["lulc_last_id"], errors="coerce").fillna(-9999).astype(int)
        mask |= last == class_id
    pct_col = f"pct_{class_id}"
    if pct_col in df.columns:
        mask |= pd.to_numeric(df[pct_col], errors="coerce").fillna(0) >= min_pct
    pctp_col = f"pctp_{class_id}"
    if pctp_col in df.columns:
        mask |= pd.to_numeric(df[pctp_col], errors="coerce").fillna(0) >= min_pct
    for p in ("P1", "P2", "P3", "P4"):
        id_col = f"md_id_{p}"
        pct_p = f"md_pct_{p}"
        if id_col in df.columns and pct_p in df.columns:
            ok = (
                pd.to_numeric(df[id_col], errors="coerce").fillna(-9999).astype(int) == class_id
            ) & (pd.to_numeric(df[pct_p], errors="coerce").fillna(0) >= min_pct)
            mask |= ok
    return mask


def fuerza_presencia_series(df: pd.DataFrame, class_id: int) -> pd.Series:
    """Fuerza de presencia (pctp/pct/moda) — solo ordena, nunca excluye."""
    strength = pd.Series(0.0, index=df.index, dtype=float)
    pctp_col = f"pctp_{class_id}"
    pct_col = f"pct_{class_id}"
    if pctp_col in df.columns:
        strength = pd.to_numeric(df[pctp_col], errors="coerce").fillna(0)
    if pct_col in df.columns:
        strength = strength.combine(
            pd.to_numeric(df[pct_col], errors="coerce").fillna(0), max
        )
    if "lulc_mode_id" in df.columns and "lulc_mode_pct" in df.columns:
        mode = pd.to_numeric(df["lulc_mode_id"], errors="coerce").fillna(-9999).astype(int)
        mpct = pd.to_numeric(df["lulc_mode_pct"], errors="coerce").fillna(0)
        strength = strength.combine(
            pd.Series(np.where(mode == class_id, mpct, 0.0), index=df.index), max
        )
    return strength
