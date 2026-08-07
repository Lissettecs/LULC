"""Calibración de umbrales tipológicos por ecorregión."""

from __future__ import annotations

import logging

import pandas as pd

from config import params_seleccion as P


def calibrar_tipologia(
    eco_id: int,
    candidatos: pd.DataFrame,
    logger: logging.Logger | None = None,
) -> dict:
    """Umbrales efectivos para una ecorregión."""
    base = dict(P.TIPOLOGIA_DEFAULT)
    if eco_id in P.TIPOLOGIA_OVERRIDES:
        base.update(P.TIPOLOGIA_OVERRIDES[eco_id])

    if not P.CALIBRAR_TIPOLOGIA_POR_ECO or candidatos.empty:
        return base

    mode = pd.to_numeric(candidatos.get("lulc_mode_pct", 0), errors="coerce").fillna(0)
    lo, hi = P.RANGO_MODE_PCT_HOMOGENEA
    if len(mode):
        p75 = float(mode.quantile(0.75))
        p25 = float(mode.quantile(0.25))
        base["E_H_MIN_MODE_PCT"] = max(lo, min(hi, p75))
        base["E_S_MIN_MODE_PCT"] = p25
        base["E_S_MAX_MODE_PCT"] = base["E_H_MIN_MODE_PCT"]

    if logger:
        logger.info(
            "  Eco %d tipología: E_H mode>=%.1f  E_S mode %.1f–%.1f",
            eco_id,
            base["E_H_MIN_MODE_PCT"],
            base["E_S_MIN_MODE_PCT"],
            base["E_S_MAX_MODE_PCT"],
        )
    return base
