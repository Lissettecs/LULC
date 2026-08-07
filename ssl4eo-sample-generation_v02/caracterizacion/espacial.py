"""Métricas espaciales, ecorregión, calidad y conf_risk."""

from __future__ import annotations

import math
from collections import Counter

import numpy as np

from config import params_caracterizacion as P
from config.diccionarios import CLASS_NAMES, CONFUSION_PAIRS, ECO_NAMES


def shannon_index(conteo: Counter, total: float) -> float:
    if total <= 0:
        return 0.0
    h = 0.0
    for c in conteo.values():
        p = c / total
        if p > 0:
            h -= p * math.log(p)
    return h


def metricas_espaciales(
    eco_30m: np.ndarray,
    stack_30m: np.ndarray,
    mascara: np.ndarray,
    latitudes: np.ndarray | None = None,
) -> dict:
    eco_px = eco_30m[mascara]
    pix = stack_30m[:, mascara]
    moda = np.apply_along_axis(
        lambda row: np.bincount(row.astype(np.int64), minlength=P.MAX_CLASS_ID).argmax(),
        0,
        pix,
    )
    n = moda.size
    if n == 0:
        return {}

    es_nodata = moda == P.CLASE_NODATA_RASTER
    es_noobs = moda == P.CLASE_NO_OBSERVADO
    # Área válida LULC: totales − nodata − noobs (alineado con composición).
    valid_lulc = (~es_nodata) & (~es_noobs)
    n_lulc = int(valid_lulc.sum())
    valid_area_pct = float(n_lulc / n * 100.0)
    nodata_raster_pct = float(es_nodata.sum() / n * 100.0)
    noobs_pct = float(es_noobs.sum() / n * 100.0)
    # Métricas de ecorregión: además exige eco != nodata.
    valid = valid_lulc & (eco_px != P.ECO_NODATA)
    valid_count = int(valid.sum())

    if n_lulc == 0:
        return {
            "nodata_raster_pct": round(nodata_raster_pct, 4),
            "noobs_pct": round(noobs_pct, 4),
            "valid_area_pct": round(valid_area_pct, 4),
        }

    mode_lulc = moda[valid_lulc]
    mode_cnt_lulc = Counter(int(v) for v in mode_lulc)
    mode_id, mode_n = mode_cnt_lulc.most_common(1)[0]
    if mode_id == P.CLASE_NODATA_RASTER:
        mode_id = next(
            (c for c, _ in mode_cnt_lulc.most_common() if c != P.CLASE_NODATA_RASTER),
            mode_id,
        )

    last = pix[-1][valid_lulc]
    last_cnt = Counter(int(v) for v in last)
    last_id, last_n = last_cnt.most_common(1)[0]

    if valid_count == 0:
        return {
            "valid_area_pct": round(valid_area_pct, 4),
            "nodata_raster_pct": round(nodata_raster_pct, 4),
            "noobs_pct": round(noobs_pct, 4),
            "mgrs_dom_pct": 100.0,
            "eco_dom_id": 0,
            "eco_dom_name": "SIN_ECO",
            "eco_dom_pct": 0.0,
            "lulc_mode_id": mode_id,
            "lulc_mode_name": CLASS_NAMES.get(mode_id, f"DESCONOCIDO_{mode_id}"),
            "lulc_mode_pct": round(mode_n / n_lulc * 100.0, 4),
            "lulc_last_id": last_id,
            "lulc_last_pct": round(last_n / n_lulc * 100.0, 4),
            "n_mode_classes": len(mode_cnt_lulc),
            "shannon_idx": round(shannon_index(mode_cnt_lulc, n_lulc), 4),
            "conf_risk_pct": 0.0,
        }

    eco_v = eco_px[valid]
    mode_v = moda[valid]
    eco_cnt = Counter(int(v) for v in eco_v)
    mode_cnt = Counter(int(v) for v in mode_v)
    eco_id, eco_n = eco_cnt.most_common(1)[0]

    conf_ids = CONFUSION_PAIRS.get(mode_id, [])
    if latitudes is not None and mode_id == 3:
        lat_v = latitudes[mascara][valid]
        conf_ids = [c for c in conf_ids if c not in (60, 67) or np.any(lat_v >= -23.2)]

    conf_area = sum(mode_cnt.get(c, 0) for c in conf_ids)
    conf_risk_pct = conf_area / valid_count * 100.0 if valid_count else 0.0

    return {
        "valid_area_pct": round(valid_area_pct, 4),
        "nodata_raster_pct": round(nodata_raster_pct, 4),
        "noobs_pct": round(noobs_pct, 4),
        "mgrs_dom_pct": 100.0,
        "eco_dom_id": eco_id,
        "eco_dom_name": ECO_NAMES.get(eco_id, f"ECO_{eco_id}"),
        "eco_dom_pct": round(eco_n / valid_count * 100.0, 4) if valid_count else 0.0,
        "lulc_mode_id": mode_id,
        "lulc_mode_name": CLASS_NAMES.get(mode_id, f"DESCONOCIDO_{mode_id}"),
        "lulc_mode_pct": round(mode_n / n_lulc * 100.0, 4),
        "lulc_last_id": last_id,
        "lulc_last_pct": round(last_n / n_lulc * 100.0, 4),
        "n_mode_classes": len(mode_cnt_lulc),
        "shannon_idx": round(shannon_index(mode_cnt_lulc, n_lulc), 4),
        "conf_risk_pct": round(conf_risk_pct, 4),
    }
