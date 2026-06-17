"""
Clases criticas segun caracterizacion_grillas_gee.py (CRITICAL_CLASS_IDS).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

CRITICAL_CLASS_IDS = [23, 61, 33, 67, 3]

CRITICAL_CLASS_NAMES: dict[int, str] = {
    23: "Arena_playa_duna",
    61: "Salar",
    33: "Rio_lago_oceano",
    67: "Bosque_achaparrado",
    # ID 3 en clasificacion-final-4 = bosque del norte (lat >= -33.2); proxima C2: Otra_Formacion_boscosa
    3: "Otra_Formacion_boscosa",
}

NORTH_FOREST_MODE_ID = 3
NORTH_FOREST_PRESENCE_COL = "north_forest_pct"
NORTH_FOREST_LEGACY_NAMES = ("Bosque_norte", "Bosque")

PRESENCE_THRESHOLD_PCT = 5.0
MIN_PERIOD_PCT = 25.0
MIN_RELAXED_PERIOD_PCT = 10.0
PERIOD_LABELS = ("P1", "P2", "P3", "P4")


def _safe_int(value) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -9999


def _safe_pct(row: pd.Series, col: str) -> float:
    if col not in row.index:
        return 0.0
    try:
        return float(row[col])
    except (TypeError, ValueError):
        return 0.0


def class_present(
    row: pd.Series,
    class_id: int,
    *,
    min_pct: float = PRESENCE_THRESHOLD_PCT,
    min_period_pct: float = MIN_PERIOD_PCT,
) -> bool:
    """True si el rectangulo tiene presencia de la clase critica indicada."""
    if class_id == NORTH_FOREST_MODE_ID:
        return _safe_pct(row, NORTH_FOREST_PRESENCE_COL) >= min_pct
    if class_id == 67 and _safe_pct(row, "achaparrado_pct") >= min_pct:
        return True

    mode_id = _safe_int(row.get("lulc_mode_id"))
    last_id = _safe_int(row.get("lulc_last_id"))
    if mode_id == class_id or last_id == class_id:
        return True

    if class_id == 67:
        target = str(row.get("target_rare_class", "") or "").strip()
        if target == CRITICAL_CLASS_NAMES[class_id]:
            return True
        if _safe_pct(row, "achap_presence_pct") >= min_pct:
            return True

    for period in PERIOD_LABELS:
        if _safe_int(row.get(f"md_id_{period}")) != class_id:
            continue
        if _safe_pct(row, f"md_pct_{period}") >= min_period_pct:
            return True
    return False


def _num_series(df: pd.DataFrame, col: str, default=0) -> pd.Series:
    if col in df.columns:
        return pd.to_numeric(df[col], errors="coerce").fillna(default)
    return pd.Series(default, index=df.index, dtype=float)


def class_present_mask(
    df: pd.DataFrame,
    class_id: int,
    *,
    min_pct: float = PRESENCE_THRESHOLD_PCT,
    min_period_pct: float = MIN_PERIOD_PCT,
) -> pd.Series:
    """Mascara vectorizada de presencia de clase critica."""
    mask = pd.Series(False, index=df.index)

    if class_id == NORTH_FOREST_MODE_ID:
        nfor = _num_series(df, NORTH_FOREST_PRESENCE_COL, 0)
        return nfor >= min_pct

    mode_id = _num_series(df, "lulc_mode_id", -9999).astype(int)
    if "lulc_last_id" in df.columns:
        last_id = pd.to_numeric(df["lulc_last_id"], errors="coerce").fillna(-9999).astype(int)
    elif "last_id" in df.columns:
        last_id = pd.to_numeric(df["last_id"], errors="coerce").fillna(-9999).astype(int)
    else:
        last_id = pd.Series(-9999, index=df.index, dtype=int)

    mask |= (mode_id == class_id) | (last_id == class_id)

    if class_id == 67:
        achap = _num_series(df, "achaparrado_pct", 0)
        mask |= achap >= min_pct
        if "target_rare_class" in df.columns:
            mask |= df["target_rare_class"].astype(str).str.strip() == CRITICAL_CLASS_NAMES[class_id]
        if "achap_presence_pct" in df.columns:
            ap = pd.to_numeric(df["achap_presence_pct"], errors="coerce").fillna(0)
            mask |= ap >= min_pct

    for period in PERIOD_LABELS:
        id_col = f"md_id_{period}"
        pct_col = f"md_pct_{period}"
        if id_col not in df.columns or pct_col not in df.columns:
            continue
        period_ok = (
            pd.to_numeric(df[id_col], errors="coerce").fillna(-9999).astype(int) == class_id
        ) & (pd.to_numeric(df[pct_col], errors="coerce").fillna(0) >= min_period_pct)
        mask |= period_ok

    return mask


def class_presence_strength_series(df: pd.DataFrame, class_id: int) -> pd.Series:
    """Serie vectorizada de fuerza de presencia para priorizar."""
    strength = pd.Series(0.0, index=df.index, dtype=float)

    if class_id == NORTH_FOREST_MODE_ID and NORTH_FOREST_PRESENCE_COL in df.columns:
        nfor = pd.to_numeric(df[NORTH_FOREST_PRESENCE_COL], errors="coerce").fillna(0)
        strength = nfor.copy()
        return pd.Series(strength, index=df.index)

    if class_id == 67 and "achaparrado_pct" in df.columns:
        achap = pd.to_numeric(df["achaparrado_pct"], errors="coerce").fillna(0)
        strength = strength.where(achap <= 0, achap)

    mode_id = _num_series(df, "lulc_mode_id", -9999).astype(int)
    if "lulc_last_id" in df.columns:
        last_id = pd.to_numeric(df["lulc_last_id"], errors="coerce").fillna(-9999).astype(int)
    elif "last_id" in df.columns:
        last_id = pd.to_numeric(df["last_id"], errors="coerce").fillna(-9999).astype(int)
    else:
        last_id = pd.Series(-9999, index=df.index, dtype=int)

    if "lulc_mode_pct" in df.columns:
        mode_pct = pd.to_numeric(df["lulc_mode_pct"], errors="coerce").fillna(0)
        strength = np.maximum(strength, np.where(mode_id == class_id, mode_pct, 0))

    if "lulc_last_pct" in df.columns:
        last_pct = pd.to_numeric(df["lulc_last_pct"], errors="coerce").fillna(0)
        strength = np.maximum(strength, np.where(last_id == class_id, last_pct, 0))

    for period in PERIOD_LABELS:
        id_col = f"md_id_{period}"
        pct_col = f"md_pct_{period}"
        if id_col not in df.columns or pct_col not in df.columns:
            continue
        match = pd.to_numeric(df[id_col], errors="coerce").fillna(-9999).astype(int) == class_id
        pct = pd.to_numeric(df[pct_col], errors="coerce").fillna(0)
        strength = np.maximum(strength, np.where(match, pct, 0))

    if class_id == 67 and "achap_presence_pct" in df.columns:
        ap = pd.to_numeric(df["achap_presence_pct"], errors="coerce").fillna(0)
        strength = np.maximum(strength, ap)

    return pd.Series(strength, index=df.index)


def class_presence_strength(row: pd.Series, class_id: int) -> float:
    """Porcentaje de presencia usado para priorizar una clase critica."""
    if class_id == NORTH_FOREST_MODE_ID:
        pct = _safe_pct(row, NORTH_FOREST_PRESENCE_COL)
        if pct > 0:
            return pct
    if class_id == 67:
        pct = _safe_pct(row, "achaparrado_pct")
        if pct > 0:
            return pct

    mode_id = _safe_int(row.get("lulc_mode_id"))
    last_id = _safe_int(row.get("lulc_last_id"))
    if mode_id == class_id:
        return _safe_pct(row, "lulc_mode_pct")
    if last_id == class_id:
        return _safe_pct(row, "lulc_last_pct")

    period_pcts = [
        _safe_pct(row, f"md_pct_{period}")
        for period in PERIOD_LABELS
        if _safe_int(row.get(f"md_id_{period}")) == class_id
    ]
    if period_pcts:
        return max(period_pcts)
    if class_id == 67:
        return _safe_pct(row, "achap_presence_pct")
    return 0.0


def critical_classes_for_row(row: pd.Series) -> list[str]:
    """Devuelve nombres de clases criticas presentes en una muestra."""
    return [
        CRITICAL_CLASS_NAMES[class_id]
        for class_id in CRITICAL_CLASS_IDS
        if class_present(row, class_id)
    ]


def _append_class_names(names: pd.Series, mask: pd.Series, label: str) -> pd.Series:
    add_first = mask & names.eq("")
    add_more = mask & names.ne("")
    names = names.mask(add_first, label)
    names = names.mask(add_more, names + "; " + label)
    return names


def annotate_critical_classes(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    names = pd.Series("", index=out.index, dtype="string")
    n_classes = pd.Series(0, index=out.index, dtype=int)
    for class_id in CRITICAL_CLASS_IDS:
        mask = class_present_mask(out, class_id)
        names = _append_class_names(names, mask, CRITICAL_CLASS_NAMES[class_id])
        n_classes += mask.astype(int)
    out["clases_criticas"] = names.fillna("")
    out["n_clases_criticas"] = n_classes
    out["tiene_clase_critica"] = n_classes > 0
    return out


def critical_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Conteo de muestras por clase critica."""
    rows = []
    for class_id in CRITICAL_CLASS_IDS:
        name = CRITICAL_CLASS_NAMES[class_id]
        mask = df["clases_criticas"].str.contains(name, regex=False, na=False)
        rows.append({"clase_id": class_id, "clase": name, "n_muestras": int(mask.sum())})
    rows.append(
        {
            "clase_id": "",
            "clase": "TOTAL (cualquier critica)",
            "n_muestras": int(df["tiene_clase_critica"].sum()),
        }
    )
    return pd.DataFrame(rows)


def presence_pct_column(class_name: str) -> str | None:
    if class_name == CRITICAL_CLASS_NAMES[NORTH_FOREST_MODE_ID]:
        return "north_forest_presence_pct"
    if class_name == CRITICAL_CLASS_NAMES[67]:
        return "achap_presence_pct"
    return "critical_pct"
