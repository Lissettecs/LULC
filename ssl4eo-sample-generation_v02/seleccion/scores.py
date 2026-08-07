"""Scores tipológicos y metadatos anuales."""

from __future__ import annotations

import numpy as np
import pandas as pd

from config import params_seleccion as P

LN_MAX_CLASSES = np.log(19)
N_YEARS_PERIOD = 26
SENSOR_MAP = {"P1": "Landsat_5_7", "P2": "Landsat_5_7", "P3": "Landsat_8", "P4": "Landsat_8_9"}
PERIOD_YEARS = {"P1": (1999, 2005), "P2": (2006, 2012), "P3": (2013, 2018), "P4": (2019, 2024)}
ANUAL_PERIOD_PREF = ["P4", "P3", "P2", "P1"]


def agregar_scores(cands: pd.DataFrame) -> pd.DataFrame:
    """Calcula columnas sc_* para pools generales."""
    if cands.empty:
        return cands
    out = cands.copy()
    out["shannon_norm"] = (pd.to_numeric(out.get("shannon_idx", 0), errors="coerce").fillna(0) / LN_MAX_CLASSES).clip(0, 1)
    base = (out["valid_area_pct"] / 100) * 2 + (out["eco_dom_pct"] / 100) * 1

    out["sc_e_h"] = (
        (out["max_stab_run"] / N_YEARS_PERIOD) * 5
        + (out["stable_yr_pct"] / 100) * 4
        + (out["lulc_mode_pct"] / 100) * 3
        + (1 - out["shannon_norm"]) * 2
        + base
    )
    out["sc_e_s"] = (
        (out["max_stab_run"] / N_YEARS_PERIOD) * 4
        + (out["stable_yr_pct"] / 100) * 3
        + (out["lulc_mode_pct"] / 100) * 3
        + (out["n_mode_classes"].clip(2, 4) / 4) * 2
        + base
    )
    out["sc_a_h"] = out.apply(lambda r: _score_anual(r), axis=1)
    out["sc_a_s"] = out["sc_a_h"]

    best_purity = out[["lulc_mode_pct", "lulc_last_pct"]].max(axis=1)
    out["sc_t_h"] = (
        (out["transition_pct"] / 100) * 5 + (best_purity / 100) * 4 + base
    )
    out["sc_t_s"] = (
        (out["transition_pct"] / 100) * 5
        + (out["n_mode_classes"].clip(2, 4) / 4) * 3
        + (out["conf_risk_pct"] / 100) * 3
        + base
    )
    return out


def _score_anual(row: pd.Series) -> float:
    best = 0.0
    for pn in ANUAL_PERIOD_PREF:
        n_stb = float(row.get(f"n_stb_{pn}", 0) or 0)
        if n_stb < 1:
            continue
        n_yrs = PERIOD_YEARS[pn][1] - PERIOD_YEARS[pn][0] + 1
        md_pct = float(row.get(f"md_pct_{pn}", 0) or 0)
        val_pct = float(row.get("valid_area_pct", 0) or 0)
        eco_pct = float(row.get("eco_dom_pct", 0) or 0)
        score = (n_stb / n_yrs) * 5 + (md_pct / 100) * 3 + (val_pct / 100) * 2 + (eco_pct / 100)
        best = max(best, score)
    return best


def mejor_periodo(row: pd.Series, min_stb: int) -> str | None:
    for pn in ANUAL_PERIOD_PREF:
        if float(row.get(f"n_stb_{pn}", 0) or 0) >= min_stb:
            return pn
    return None


def periodo_para_anio(year: int) -> str | None:
    for pn, (start, end) in PERIOD_YEARS.items():
        if start <= year <= end:
            return pn
    return None


def max_mode_en_periodos(row: pd.Series, min_stb: int) -> float:
    best = 0.0
    for pn in ANUAL_PERIOD_PREF:
        if float(row.get(f"n_stb_{pn}", 0) or 0) >= min_stb:
            best = max(best, float(row.get(f"md_pct_{pn}", 0) or 0))
    return best


def elegir_ref_anual(
    row: pd.Series,
    min_stb: int,
    conteos: dict[int, int] | None = None,
) -> tuple[str | None, int]:
    periodos = [pn for pn in ANUAL_PERIOD_PREF if float(row.get(f"n_stb_{pn}", 0) or 0) >= min_stb]
    if not periodos:
        return None, -9999
    candidatos: list[tuple[int, str]] = []
    for pn in periodos:
        start, end = PERIOD_YEARS[pn]
        mid = (start + end) // 2
        candidatos.append((mid, pn))
    years = [y for y, _ in candidatos]
    if not conteos:
        yr = max(years)
        return periodo_para_anio(yr), yr
    min_use = min(conteos.get(y, 0) for y in years)
    year_cands = sorted(y for y in years if conteos.get(y, 0) == min_use)
    gid = str(row.get("grid_id", ""))
    yr = year_cands[sum(ord(c) for c in gid) % len(year_cands)]
    return periodo_para_anio(yr), yr


def asignar_metadatos_anuales(
    df: pd.DataFrame,
    min_stb: int,
    conteos: dict[int, int] | None = None,
) -> pd.DataFrame:
    if conteos is None:
        conteos = {}
    if df.empty:
        return df
    out = df.copy()
    ref_periods, ref_years, ref_sensors = [], [], []
    for _, row in out.iterrows():
        pn, yr = elegir_ref_anual(row, min_stb, conteos)
        if pn and yr > 0:
            ref_periods.append(pn)
            ref_years.append(yr)
            ref_sensors.append(SENSOR_MAP.get(pn, ""))
            conteos[yr] = conteos.get(yr, 0) + 1
        else:
            ref_periods.append(None)
            ref_years.append(-9999)
            ref_sensors.append("")
    out["ref_period"] = ref_periods
    out["ref_year"] = ref_years
    out["ref_sensor"] = ref_sensors
    return out[out["ref_period"].notna() & (out["ref_year"] > 0)].copy()


def cuota_segmentos_a_rectangulos(
    cuota_seg: float,
    *,
    area_km2: float = 240.0,
    rendimiento: float = 0.26,
) -> int:
    """Convierte cuota de segmentos en número objetivo de rectángulos."""
    if cuota_seg <= 0:
        return 0
    area_ha = area_km2 * 100.0
    seg_por_rect = area_ha * P.SEGMENTOS_POR_1000HA / 1000.0 * rendimiento
    if seg_por_rect <= 0:
        return 0
    return max(1, int(round(cuota_seg / seg_por_rect)))


def estimar_segmentos_rect(row: pd.Series, rendimiento: float = 0.26) -> float:
    area_ha = float(row.get("area_km2", 240.0) or 240.0) * 100.0
    mode_pct = float(row.get("lulc_mode_pct", 100) or 100) / 100.0
    return area_ha * P.SEGMENTOS_POR_1000HA / 1000.0 * mode_pct * rendimiento
