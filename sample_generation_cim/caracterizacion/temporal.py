"""Métricas de dinámica temporal sobre bloques agregados por moda.

Se agregan bloques de STATS_BLOQUE_PX píxeles antes de medir cambio, para que las
métricas reflejen dinámica de paisaje y no ruido de clasificación píxel a píxel.

Los años sin dato (clase 0) y los no observados (clase 27) se enmascaran año a
año: si se contaran como una clase más, un bloque con vacíos parecería inestable
cuando en realidad solo faltaba información.

A diferencia de la composición, estas métricas no se ponderan por área: son tasas
adimensionales por bloque y la variación de área dentro de una misma celda es
inferior al 0,4%.
"""

from __future__ import annotations

import numpy as np

from caracterizacion.moda import moda, moda_bloques
from config import params_caracterizacion as P

EXCLUIR = (P.CLASE_NODATA_RASTER, P.CLASE_NO_OBSERVADO)


def agregar_a_bloques(stack_anual: np.ndarray, factor: int) -> np.ndarray:
    """(n_años, h, w) -> (n_años, h/factor, w/factor) por moda, ignorando 0 y 27."""
    return moda_bloques(stack_anual, factor, excluir=EXCLUIR, sin_dato=P.CLASE_NODATA_RASTER)


def metricas_temporales(
    stack_bloques: np.ndarray,
    start_year: int,
    umbral_estable: float,
    periodos: dict[str, tuple[int, int]],
) -> dict:
    """stack_bloques: (n_años, h, w) ya agregado a la escala de análisis."""
    if stack_bloques.size == 0:
        return {}

    n_years = stack_bloques.shape[0]
    pix = stack_bloques.reshape(n_years, -1)

    moda_glob = moda(pix, eje=0, excluir=EXCLUIR, sin_dato=P.CLASE_NODATA_RASTER)
    valid_moda = (moda_glob != P.CLASE_NODATA_RASTER) & (moda_glob != P.CLASE_NO_OBSERVADO)
    if not valid_moda.any():
        return {}

    valid_yr = (pix != P.CLASE_NODATA_RASTER) & (pix != P.CLASE_NO_OBSERVADO)

    # Transiciones: solo entre pares de años consecutivos con dato en ambos
    ambos = valid_yr[1:] & valid_yr[:-1]
    cambio = (pix[1:] != pix[:-1]) & ambos
    n_pares = ambos[:, valid_moda].sum(axis=0).astype(float)
    n_cambios = cambio[:, valid_moda].sum(axis=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        trans_px = np.where(n_pares > 0, n_cambios / n_pares, 0.0)
    transition_pct = float(np.mean(trans_px) * 100.0) if trans_px.size else 0.0

    # Estabilidad respecto de la moda, solo sobre años con dato
    stab_flags = (pix == moda_glob) & valid_yr
    n_valid_yrs = valid_yr[:, valid_moda].sum(axis=0).astype(float)
    n_stab = stab_flags[:, valid_moda].sum(axis=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        stab_px = np.where(n_valid_yrs > 0, n_stab / n_valid_yrs, 0.0)
    stable_mode_pct = float(np.mean(stab_px) * 100.0) if stab_px.size else 0.0

    n_valid = int(valid_moda.sum())

    # Fracción de bloques estables en cada año, sobre los que tienen dato ese año
    year_stability = np.zeros(n_years, dtype=float)
    for yi in range(n_years):
        yr_ok = valid_yr[yi, valid_moda]
        if yr_ok.any():
            year_stability[yi] = float(np.mean(stab_flags[yi, valid_moda][yr_ok]))
    flags = year_stability >= umbral_estable
    stable_yr_pct = float(flags.sum()) / n_years * 100.0

    # Racha más larga de años estables consecutivos
    best_len = best_start = cur_len = cur_start = 0
    for i, flag in enumerate(flags):
        if not flag:
            cur_len = 0
            continue
        if cur_len == 0:
            cur_start = i
        cur_len += 1
        if cur_len > best_len:
            best_len, best_start = cur_len, cur_start

    out = {
        "transition_pct": round(transition_pct, 4),
        "stable_mode_pct": round(stable_mode_pct, 4),
        "stable_yr_pct": round(stable_yr_pct, 4),
        "max_stab_run": int(best_len),
        "stab_run_start": start_year + best_start if best_len else None,
        "stab_run_end": start_year + best_start + best_len - 1 if best_len else None,
        "n_bloques_validos": n_valid,
    }

    moda_v = moda_glob[valid_moda]
    for pname, (y0, y1) in periodos.items():
        idxs = [y - start_year for y in range(y0, y1 + 1)]
        sub = pix[idxs]
        moda_p = moda(sub, eje=0, excluir=EXCLUIR, sin_dato=P.CLASE_NODATA_RASTER)[valid_moda]
        cnt = np.bincount(
            moda_p[(moda_p != P.CLASE_NODATA_RASTER) & (moda_p != P.CLASE_NO_OBSERVADO)]
            .astype(np.int64),
            minlength=P.MAX_CLASS_ID,
        )
        md_id = int(cnt.argmax()) if cnt.sum() else 0
        md_pct = float(cnt[md_id] / n_valid * 100.0) if n_valid and cnt.sum() else 0.0

        sub_v = sub[:, valid_moda]
        valid_sub = (sub_v != P.CLASE_NODATA_RASTER) & (sub_v != P.CLASE_NO_OBSERVADO)
        n_stb = 0
        for yi in range(sub_v.shape[0]):
            ok = valid_sub[yi]
            if ok.any() and float(np.mean((sub_v[yi] == moda_v)[ok])) >= umbral_estable:
                n_stb += 1

        out[f"md_id_{pname}"] = md_id
        out[f"md_pct_{pname}"] = round(md_pct, 4)
        out[f"n_stb_{pname}"] = n_stb
    return out
