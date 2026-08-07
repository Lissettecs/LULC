"""Métricas de dinámica temporal a STATS_SCALE."""

from __future__ import annotations

from collections import Counter

import numpy as np

from config import params_caracterizacion as P


def _moda_sin_nodata(valores: np.ndarray) -> int:
    """Moda ignorando clase 0 (nodata) y 27 (no observado)."""
    v = valores.astype(np.int64, copy=False).ravel()
    valid = v[(v != P.CLASE_NODATA_RASTER) & (v != P.CLASE_NO_OBSERVADO)]
    if valid.size == 0:
        return int(P.CLASE_NODATA_RASTER)
    return int(np.bincount(valid, minlength=P.MAX_CLASS_ID).argmax())


def agregar_moda_bloques(arr_30m: np.ndarray, factor: int) -> np.ndarray:
    """Moda por bloques factor×factor, enmascarando clase 0 y 27."""
    h, w = arr_30m.shape
    h2 = (h // factor) * factor
    w2 = (w // factor) * factor
    a = arr_30m[:h2, :w2].reshape(h2 // factor, factor, w2 // factor, factor)
    out = np.zeros((h2 // factor, w2 // factor), dtype=np.int32)
    for i in range(out.shape[0]):
        for j in range(out.shape[1]):
            out[i, j] = _moda_sin_nodata(a[i, :, j, :])
    return out


def factor_stats_scale(transform) -> int:
    """Cuántos píxeles nativos equivalen a STATS_SCALE m (aprox.)."""
    res_m = abs(transform.a) * 111_320 if str(transform).find("4326") >= 0 else abs(transform.a)
    if res_m <= 0:
        return 10
    return max(1, int(round(P.STATS_SCALE / (P.PIXEL_M if res_m < 1 else res_m))))


def agregar_mascara_bloques(mascara_30m: np.ndarray, factor: int) -> np.ndarray:
    """True si la mayoría de píxeles del bloque factor×factor es válida."""
    h, w = mascara_30m.shape
    h2 = (h // factor) * factor
    w2 = (w // factor) * factor
    a = mascara_30m[:h2, :w2].reshape(h2 // factor, factor, w2 // factor, factor)
    out = np.zeros((h2 // factor, w2 // factor), dtype=bool)
    for i in range(out.shape[0]):
        for j in range(out.shape[1]):
            bloque = a[i, :, j, :].ravel()
            out[i, j] = bool(bloque.mean() >= 0.5)
    return out


def metricas_temporales(
    stack_stats: np.ndarray,
    mascara: np.ndarray,
    start_year: int,
    end_year: int,
    umbral_estable: float,
    periodos: dict[str, tuple[int, int]],
) -> dict:
    """
    stack_stats: (n_años, h, w) a escala reducida.
    mascara: píxeles del rectángulo a considerar.
    Las métricas enmascaran clase 0 año a año para no inflar estabilidad.
    """
    del end_year  # serie completa viene en stack_stats
    pix = stack_stats[:, mascara]
    if pix.size == 0:
        return {}

    n_years = pix.shape[0]
    # Moda global ignorando nodata/noobs por píxel
    moda = np.apply_along_axis(_moda_sin_nodata, 0, pix)
    valid_moda = (moda != P.CLASE_NODATA_RASTER) & (moda != P.CLASE_NO_OBSERVADO)
    if not valid_moda.any():
        return {}

    # Máscara año×píxel: solo años con clase real
    valid_yr = (pix != P.CLASE_NODATA_RASTER) & (pix != P.CLASE_NO_OBSERVADO)

    # Transiciones: solo entre pares de años ambos válidos
    ambos = valid_yr[1:] & valid_yr[:-1]
    cambio = (pix[1:] != pix[:-1]) & ambos
    n_pares = ambos[:, valid_moda].sum(axis=0).astype(float)
    n_cambios = cambio[:, valid_moda].sum(axis=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        trans_px = np.where(n_pares > 0, n_cambios / n_pares, 0.0)
    transition_pct = float(np.mean(trans_px) * 100.0) if trans_px.size else 0.0

    # Estabilidad respecto de la moda: solo años válidos
    stab_flags = (pix == moda) & valid_yr
    n_valid_yrs = valid_yr[:, valid_moda].sum(axis=0).astype(float)
    n_stab = stab_flags[:, valid_moda].sum(axis=0).astype(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        stab_px = np.where(n_valid_yrs > 0, n_stab / n_valid_yrs, 0.0)
    stable_mode_pct = float(np.mean(stab_px) * 100.0) if stab_px.size else 0.0

    n_valid = int(valid_moda.sum())
    # Fracción de píxeles válidos estables por año (sobre los que tienen dato ese año)
    year_stability = np.zeros(n_years, dtype=float)
    for yi in range(n_years):
        yr_ok = valid_yr[yi, valid_moda]
        if yr_ok.any():
            year_stability[yi] = float(np.mean(stab_flags[yi, valid_moda][yr_ok]))
    stable_years = [start_year + i for i, f in enumerate(year_stability) if f >= umbral_estable]
    stable_yr_pct = len(stable_years) / n_years * 100.0

    best_len = best_start = 0
    cur_len = cur_start = 0
    flags = [float(year_stability[i]) >= umbral_estable for i in range(n_years)]
    for i, flag in enumerate(flags):
        if flag:
            if cur_len == 0:
                cur_start = i
            cur_len += 1
            if cur_len > best_len:
                best_len = cur_len
                best_start = cur_start
        else:
            cur_len = 0
    max_stab_run = best_len
    stab_run_start = start_year + best_start if best_len else None
    stab_run_end = start_year + best_start + best_len - 1 if best_len else None

    out = {
        "transition_pct": round(transition_pct, 4),
        "stable_mode_pct": round(stable_mode_pct, 4),
        "stable_yr_pct": round(stable_yr_pct, 4),
        "max_stab_run": max_stab_run,
        "stab_run_start": stab_run_start,
        "stab_run_end": stab_run_end,
    }

    for pname, (y0, y1) in periodos.items():
        idxs = [y - start_year for y in range(y0, y1 + 1)]
        sub = pix[idxs]
        moda_p = np.apply_along_axis(_moda_sin_nodata, 0, sub)
        moda_p = moda_p[valid_moda]
        cnt = Counter(int(v) for v in moda_p if v not in (P.CLASE_NODATA_RASTER, P.CLASE_NO_OBSERVADO))
        md_id, md_cnt = cnt.most_common(1)[0] if cnt else (0, 0)
        md_pct = md_cnt / n_valid * 100.0 if n_valid else 0.0
        sub_v = sub[:, valid_moda]
        moda_v = moda[valid_moda]
        valid_sub = (sub_v != P.CLASE_NODATA_RASTER) & (sub_v != P.CLASE_NO_OBSERVADO)
        n_stb = 0
        for yi, _y in enumerate(range(y0, y1 + 1)):
            ok = valid_sub[yi]
            if not ok.any():
                continue
            if float(np.mean((sub_v[yi] == moda_v) & ok)) >= umbral_estable:
                n_stb += 1
        out[f"md_id_{pname}"] = md_id
        out[f"md_pct_{pname}"] = round(md_pct, 4)
        out[f"n_stb_{pname}"] = n_stb
    return out
