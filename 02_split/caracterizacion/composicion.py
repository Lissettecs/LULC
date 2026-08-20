"""Composición de coberturas de la celda: pct_{id} y ha_{id}.

La clase de cada píxel es su moda temporal en la serie 1999–2024. Los
porcentajes se calculan sobre el área válida (excluye nodata y no observado) y
ponderando por el área real de cada píxel, no por conteo: en EPSG:4326 el píxel
del sur cubre casi la mitad de superficie que el del norte.
"""

from __future__ import annotations

import numpy as np

from caracterizacion.moda import moda
from config import params_caracterizacion as P
from config.diccionarios import CLASES_MASCARA, CLASES_TRANSVERSALES, CLASS_NAMES

CLASES_EXCLUIDAS = (P.CLASE_NODATA_RASTER, P.CLASE_NO_OBSERVADO)


def area_por_clase(clases: np.ndarray, area_ha: np.ndarray) -> np.ndarray:
    """Hectáreas acumuladas por ID de clase."""
    pesos = np.broadcast_to(area_ha, clases.shape)
    return np.bincount(
        clases.ravel().astype(np.int64),
        weights=pesos.ravel(),
        minlength=P.MAX_CLASS_ID,
    )


def composicion_por_celda(stack_anual: np.ndarray, area_ha: np.ndarray) -> dict[str, float]:
    """
    stack_anual: (n_años, h, w) con los IDs de clase nativos.
    area_ha: (h, 1) área en hectáreas de un píxel de cada fila.

    pct_{id} = 100 · ha_{id} / area_valida_ha,  id ∉ {0, 27}
    """
    if stack_anual.size == 0:
        return {}

    moda_temporal = moda(stack_anual, eje=0)
    ha = area_por_clase(moda_temporal, area_ha)

    ha_total = float(ha.sum())
    ha_nodata = float(ha[P.CLASE_NODATA_RASTER])
    ha_noobs = float(ha[P.CLASE_NO_OBSERVADO])
    ha_valida = ha_total - ha_nodata - ha_noobs

    n_valid = int(
        ((moda_temporal != P.CLASE_NODATA_RASTER) & (moda_temporal != P.CLASE_NO_OBSERVADO)).sum()
    )
    out: dict[str, float] = {
        "area_celda_ha": round(ha_total, 4),
        "nodata_raster_pct": round(ha_nodata / ha_total * 100.0, 4),
        "noobs_pct": round(ha_noobs / ha_total * 100.0, 4),
        "valid_area_pct": round(ha_valida / ha_total * 100.0, 4),
        "n_valid": float(n_valid),
        "area_valida_ha": round(ha_valida, 4),
    }
    if ha_valida <= 0:
        out["transversal_pct"] = 0.0
        out["mascara_pct"] = 0.0
        out["general_pct"] = 0.0
        return out

    # Se emiten TODAS las clases realmente presentes, no solo las de CLASS_NAMES,
    # para que sum(pct_*) = 100.
    pct: dict[int, float] = {}
    for cid in range(P.MAX_CLASS_ID):
        if cid in CLASES_EXCLUIDAS or ha[cid] <= 0:
            continue
        pct[cid] = float(ha[cid] / ha_valida * 100.0)
        out[f"pct_{cid}"] = round(pct[cid], 4)
        out[f"ha_{cid}"] = round(float(ha[cid]), 4)

    transversal = sum(pct.get(c, 0.0) for c in CLASES_TRANSVERSALES)
    mascara = sum(pct.get(c, 0.0) for c in CLASES_MASCARA)
    out["transversal_pct"] = round(transversal, 4)
    out["mascara_pct"] = round(mascara, 4)
    out["general_pct"] = round(100.0 - transversal - mascara, 4)
    return out


def pctp_por_periodo(
    stack_anual: np.ndarray,
    area_ha: np.ndarray,
    periodos: dict[str, tuple[int, int]],
    start_year: int,
) -> dict[str, float]:
    """Máximo % de cada clase como moda de periodo P1–P4, sobre el área válida global.

    Detecta coberturas que dominaron en algún tramo de la serie pero que la moda
    de 26 años diluye.
    """
    if stack_anual.size == 0:
        return {}

    moda_global = moda(stack_anual, eje=0)
    validos = (moda_global != P.CLASE_NODATA_RASTER) & (moda_global != P.CLASE_NO_OBSERVADO)
    if not validos.any():
        return {}

    pesos = np.broadcast_to(area_ha, moda_global.shape)
    ha_valida = float(pesos[validos].sum())
    if ha_valida <= 0:
        return {}

    maximo: dict[int, float] = {}
    for _nombre, (y0, y1) in periodos.items():
        idxs = [y - start_year for y in range(y0, y1 + 1)]
        moda_p = moda(stack_anual[idxs], eje=0)
        ha_p = np.bincount(
            moda_p[validos].astype(np.int64),
            weights=pesos[validos],
            minlength=P.MAX_CLASS_ID,
        )
        for cid in range(P.MAX_CLASS_ID):
            if cid in CLASES_EXCLUIDAS or ha_p[cid] <= 0:
                continue
            maximo[cid] = max(maximo.get(cid, 0.0), float(ha_p[cid] / ha_valida * 100.0))

    return {
        f"pctp_{cid}": round(v, 4)
        for cid, v in maximo.items()
        if cid in CLASS_NAMES and cid not in CLASES_EXCLUIDAS
    }


def validar_suma_composicion(fila: dict, logger) -> bool:
    claves = [
        k for k in fila
        if k.startswith("pct_") and k.split("_")[1].isdigit()
        and int(k.split("_")[1]) not in CLASES_EXCLUIDAS
    ]
    total = sum(fila.get(k, 0.0) for k in claves)
    if claves and not (99.9 <= total <= 100.1):
        logger.warning(
            "Suma de composición fuera de rango: %.4f (grid_id=%s)", total, fila.get("grid_id")
        )
        return False
    for prohibida in ("pct_0", "pct_27", "pctp_0", "pctp_27"):
        if prohibida in fila:
            logger.warning("Columna %s presente (grid_id=%s)", prohibida, fila.get("grid_id"))
            return False
    return True
