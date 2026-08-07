"""Cómputo del vector de composición pct_{id} y ha_{id} a 30 m."""

from __future__ import annotations

import numpy as np

from config import params_caracterizacion as P
from config.diccionarios import CLASES_MASCARA, CLASES_TRANSVERSALES, CLASS_NAMES

CLASES_EXCLUIDAS_COMP = {P.CLASE_NODATA_RASTER, P.CLASE_NO_OBSERVADO}


def composicion_por_rectangulo(
    stack_anual_30m: np.ndarray,
    mascara_rect: np.ndarray,
) -> dict[str, float]:
    """
    stack_anual_30m: (n_años, h, w) int
    mascara_rect: (h, w) bool — píxeles del rectángulo

    pct_{id} = 100 * count(id) / píxeles_válidos, id ∉ {0, 27}
    ha_{id}  = pct_{id}/100 * area_valida_ha
    píxeles_válidos = totales - nodata(0) - noobs(27)
    """
    pixeles = stack_anual_30m[:, mascara_rect]  # (años, n_pix)
    if pixeles.size == 0:
        return {}

    moda_temporal = np.apply_along_axis(
        lambda row: np.bincount(row.astype(np.int64), minlength=P.MAX_CLASS_ID).argmax(),
        0,
        pixeles,
    )
    n_total = moda_temporal.size
    es_nodata = moda_temporal == P.CLASE_NODATA_RASTER
    es_noobs = moda_temporal == P.CLASE_NO_OBSERVADO
    validos = (~es_nodata) & (~es_noobs)
    n_valid = int(validos.sum())
    out: dict[str, float] = {
        "nodata_raster_pct": round(float(es_nodata.sum() / n_total * 100.0), 4),
        "noobs_pct": round(float(es_noobs.sum() / n_total * 100.0), 4),
        "valid_area_pct": round(float(n_valid / n_total * 100.0), 4),
        "n_valid": float(n_valid),
        "area_valida_ha": round(n_valid * P.PIXEL_HA, 4),
    }
    if n_valid == 0:
        out["transversal_pct"] = 0.0
        out["mascara_pct"] = 0.0
        out["general_pct"] = 0.0
        return out

    moda_v = moda_temporal[validos]
    conteo = np.bincount(moda_v.astype(np.int64), minlength=P.MAX_CLASS_ID)
    pct = {
        cid: float(conteo[cid] / n_valid * 100.0)
        for cid in range(P.MAX_CLASS_ID)
        if conteo[cid] > 0 and cid not in CLASES_EXCLUIDAS_COMP
    }

    area_valida_ha = float(out["area_valida_ha"])
    # Emitir TODAS las clases reales (no solo CLASS_NAMES) para que sum(pct)=100.
    for cid, val in pct.items():
        out[f"pct_{cid}"] = round(val, 4)
        out[f"ha_{cid}"] = round(val / 100.0 * area_valida_ha, 4)

    transversal = sum(pct.get(c, 0.0) for c in CLASES_TRANSVERSALES)
    mascara = sum(pct.get(c, 0.0) for c in CLASES_MASCARA)
    out["transversal_pct"] = round(transversal, 4)
    out["mascara_pct"] = round(mascara, 4)
    out["general_pct"] = round(100.0 - transversal - mascara, 4)
    return out


def pctp_por_periodo(
    stack_anual_30m: np.ndarray,
    mascara_rect: np.ndarray,
    periodos: dict[str, tuple[int, int]],
    start_year: int,
) -> dict[str, float]:
    """Máximo % de cada clase como moda de periodo P1–P4 (sobre píxeles válidos)."""
    pix_all = stack_anual_30m[:, mascara_rect]
    if pix_all.size == 0:
        return {}
    moda_global = np.apply_along_axis(
        lambda row: np.bincount(row.astype(np.int64), minlength=P.MAX_CLASS_ID).argmax(),
        0,
        pix_all,
    )
    validos = (moda_global != P.CLASE_NODATA_RASTER) & (moda_global != P.CLASE_NO_OBSERVADO)
    if not validos.any():
        return {}

    max_por_clase: dict[int, float] = {}
    for _pname, (y0, y1) in periodos.items():
        idxs = [y - start_year for y in range(y0, y1 + 1)]
        sub = stack_anual_30m[idxs][:, mascara_rect][:, validos]
        if sub.size == 0:
            continue
        moda_p = np.apply_along_axis(
            lambda row: np.bincount(row.astype(np.int64), minlength=P.MAX_CLASS_ID).argmax(),
            0,
            sub,
        )
        n = moda_p.size
        conteo = np.bincount(moda_p.astype(np.int64), minlength=P.MAX_CLASS_ID)
        for cid in range(P.MAX_CLASS_ID):
            if conteo[cid] == 0 or cid in CLASES_EXCLUIDAS_COMP:
                continue
            val = float(conteo[cid] / n * 100.0)
            max_por_clase[cid] = max(max_por_clase.get(cid, 0.0), val)
    # Solo clases con nombre conocido (nunca 0 ni 27).
    return {
        f"pctp_{cid}": round(v, 4)
        for cid, v in max_por_clase.items()
        if cid in CLASS_NAMES and cid not in CLASES_EXCLUIDAS_COMP
    }


def validar_suma_composicion(fila: dict, claves_pct: list[str], logger) -> bool:
    claves = [k for k in claves_pct if k not in ("pct_0", "pct_27")]
    total = sum(fila.get(k, 0.0) for k in claves)
    if not (99.9 <= total <= 100.1):
        logger.warning("Suma composición fuera de rango: %.2f (grid_id=%s)", total, fila.get("grid_id"))
        return False
    if "pct_0" in fila or "pctp_0" in fila:
        logger.warning("Columna pct_0/pctp_0 presente (grid_id=%s)", fila.get("grid_id"))
        return False
    return True
