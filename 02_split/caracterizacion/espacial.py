"""Métricas espaciales: ecorregión dominante, cobertura modal, diversidad y conf_risk.

Igual que la composición, todo se pondera por el área real del píxel. Las
métricas de ecorregión exigen además que el píxel tenga ecorregión asignada, así
que su denominador es más chico que el del área válida de landcover.
"""

from __future__ import annotations

import math

import numpy as np

from caracterizacion.composicion import area_por_clase
from caracterizacion.moda import moda
from config import params_caracterizacion as P
from config.diccionarios import CLASS_NAMES, CONFUSION_PAIRS, ECO_NAMES

# Al norte de este paralelo el bosque de tamarugo (clase 3) no coexiste con
# bosque secundario (60) ni achaparrado (67), así que no son confusiones posibles.
LAT_TAMARUGO = -23.2


def shannon(ha_por_clase: np.ndarray) -> float:
    total = float(ha_por_clase.sum())
    if total <= 0:
        return 0.0
    p = ha_por_clase[ha_por_clase > 0] / total
    return float(-(p * np.log(p)).sum())


def metricas_espaciales(
    eco: np.ndarray,
    stack_anual: np.ndarray,
    area_ha: np.ndarray,
    latitudes: np.ndarray,
) -> dict:
    """
    eco: (h, w) IDs de ecorregión, alineado píxel a píxel con el landcover.
    stack_anual: (n_años, h, w) IDs de clase.
    area_ha: (h, 1) área de un píxel de cada fila.
    latitudes: (h, 1) latitud del centro de cada fila.
    """
    if stack_anual.size == 0:
        return {}

    moda_temporal = moda(stack_anual, eje=0)
    pesos = np.broadcast_to(area_ha, moda_temporal.shape)
    ha_total = float(pesos.sum())

    es_nodata = moda_temporal == P.CLASE_NODATA_RASTER
    es_noobs = moda_temporal == P.CLASE_NO_OBSERVADO
    valid_lulc = ~(es_nodata | es_noobs)

    ha_nodata = float(pesos[es_nodata].sum())
    ha_noobs = float(pesos[es_noobs].sum())
    ha_lulc = float(pesos[valid_lulc].sum())

    base = {
        "nodata_raster_pct": round(ha_nodata / ha_total * 100.0, 4),
        "noobs_pct": round(ha_noobs / ha_total * 100.0, 4),
        "valid_area_pct": round(ha_lulc / ha_total * 100.0, 4),
    }
    if ha_lulc <= 0:
        return {
            **base,
            "cim_dom_pct": 100.0,
            "eco_dom_id": 0,
            "eco_dom_name": "SIN_ECO",
            "eco_dom_pct": 0.0,
            "lulc_mode_id": 0,
            "lulc_mode_name": "SIN_DATO",
            "lulc_mode_pct": 0.0,
            "lulc_last_id": 0,
            "lulc_last_pct": 0.0,
            "n_mode_classes": 0,
            "shannon_idx": 0.0,
            "conf_risk_pct": 0.0,
        }

    ha_clase = area_por_clase(np.where(valid_lulc, moda_temporal, 0), area_ha)
    ha_clase[P.CLASE_NODATA_RASTER] = 0.0
    mode_id = int(ha_clase.argmax())
    mode_ha = float(ha_clase[mode_id])

    ultimo = np.where(valid_lulc, stack_anual[-1], 0)
    ha_ultimo = area_por_clase(ultimo, area_ha)
    ha_ultimo[P.CLASE_NODATA_RASTER] = 0.0
    last_id = int(ha_ultimo.argmax())

    base.update({
        "cim_dom_pct": 100.0,  # la celda nunca cruza a otra carta, por construcción
        "lulc_mode_id": mode_id,
        "lulc_mode_name": CLASS_NAMES.get(mode_id, f"DESCONOCIDO_{mode_id}"),
        "lulc_mode_pct": round(mode_ha / ha_lulc * 100.0, 4),
        "lulc_last_id": last_id,
        "lulc_last_pct": round(float(ha_ultimo[last_id]) / ha_lulc * 100.0, 4),
        "n_mode_classes": int((ha_clase > 0).sum()),
        "shannon_idx": round(shannon(ha_clase), 4),
    })

    con_eco = valid_lulc & (eco != P.ECO_NODATA)
    ha_con_eco = float(pesos[con_eco].sum())
    if ha_con_eco <= 0:
        base.update({
            "eco_dom_id": 0,
            "eco_dom_name": "SIN_ECO",
            "eco_dom_pct": 0.0,
            "conf_risk_pct": 0.0,
        })
        return base

    ha_eco = np.bincount(
        eco[con_eco].astype(np.int64), weights=pesos[con_eco], minlength=len(ECO_NAMES) + 1
    )
    eco_id = int(ha_eco.argmax())

    conf_ids = list(CONFUSION_PAIRS.get(mode_id, []))
    if mode_id == 3:
        lat_v = np.broadcast_to(latitudes, moda_temporal.shape)[con_eco]
        if np.any(lat_v >= LAT_TAMARUGO):
            conf_ids = [c for c in conf_ids if c not in (60, 67)]

    ha_clase_eco = area_por_clase(np.where(con_eco, moda_temporal, 0), area_ha)
    ha_conf = sum(float(ha_clase_eco[c]) for c in conf_ids if c < P.MAX_CLASS_ID)

    base.update({
        "eco_dom_id": eco_id,
        "eco_dom_name": ECO_NAMES.get(eco_id, f"ECO_{eco_id}"),
        "eco_dom_pct": round(float(ha_eco[eco_id]) / ha_con_eco * 100.0, 4),
        "conf_risk_pct": round(ha_conf / ha_con_eco * 100.0, 4),
    })
    return base


def indice_heterogeneidad(shannon_idx: float, n_clases: int) -> float:
    """Shannon normalizado por su máximo posible: 0 = monoclase, 1 = equireparto."""
    if n_clases <= 1:
        return 0.0
    return round(shannon_idx / math.log(n_clases), 4)
