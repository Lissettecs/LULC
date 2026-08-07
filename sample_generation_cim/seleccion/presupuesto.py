"""Reparto de presupuesto de segmentos por ecorregión."""

from __future__ import annotations

import logging
import math

import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASES_MODELO_GENERAL, ECO_NAMES
from seleccion.presencia import universo_local


def validar_presupuesto_global(n_ecos: int, logger: logging.Logger) -> None:
    minimo = P.MIN_SEGMENTOS_ECO * n_ecos
    if P.PRESUPUESTO_SEGMENTOS_TOTAL < minimo:
        raise ValueError(
            f"PRESUPUESTO_SEGMENTOS_TOTAL ({P.PRESUPUESTO_SEGMENTOS_TOTAL}) < "
            f"MIN_SEGMENTOS_ECO × n_ecos ({minimo}). Inconsistencia de diseño."
        )
    logger.info("Presupuesto global válido: %d segmentos / %d ecorregiones", P.PRESUPUESTO_SEGMENTOS_TOTAL, n_ecos)


def score_ecorregion(universo: dict[int, dict]) -> float:
    area_gen = sum(v["area_ha"] for k, v in universo.items() if k in CLASES_MODELO_GENERAL)
    n_clases = sum(1 for v in universo.values() if v["presencia"] in ("presente", "marginal"))
    n_raras = sum(1 for v in universo.values() if v["modo"] in ("censo", "refuerzo"))
    return (
        P.PESO_AREA_GENERAL * math.sqrt(area_gen)
        + P.PESO_N_CLASES * n_clases
        + P.PESO_N_RARAS * n_raras
    )


def repartir_presupuesto(matriz: pd.DataFrame, logger: logging.Logger) -> pd.DataFrame:
    """Cuotas por ecorregión y clase."""
    validar_presupuesto_global(len(P.ECORREGIONES), logger)
    filas = []
    scores = {}
    universos = {}
    for eco_id in P.ECORREGIONES:
        u = universo_local(eco_id, matriz, logger)
        universos[eco_id] = u
        scores[eco_id] = score_ecorregion(u)

    total_score = sum(scores.values()) or 1.0
    presupuestos_eco = {}
    for eco_id in P.ECORREGIONES:
        raw = P.PRESUPUESTO_SEGMENTOS_TOTAL * scores[eco_id] / total_score
        presupuestos_eco[eco_id] = max(P.MIN_SEGMENTOS_ECO, int(raw))

    # Renormalizar al total
    suma = sum(presupuestos_eco.values())
    factor = P.PRESUPUESTO_SEGMENTOS_TOTAL / suma
    for eco_id in presupuestos_eco:
        presupuestos_eco[eco_id] = max(P.MIN_SEGMENTOS_ECO, int(presupuestos_eco[eco_id] * factor))

    for eco_id in P.ECORREGIONES:
        u = universos[eco_id]
        pres_eco = presupuestos_eco[eco_id]
        refuerzo_clases = [c for c, v in u.items() if v["modo"] == "refuerzo"]
        censo_clases = [c for c, v in u.items() if v["modo"] == "censo"]
        # Cuota censo: techo de segmentos (la cobertura ha se aplica en el selector)
        cuota_censo = sum(P.segmentos_desde_area_ha(u[c]["area_ha"]) for c in censo_clases)
        # Refuerzo: piso mínimo de segmentos; cobertura objetivo se cierra en selector
        cuota_ref_min = len(refuerzo_clases) * 50 if refuerzo_clases else 0
        remanente = max(0, pres_eco - cuota_censo - cuota_ref_min)

        # Peso del remanente: √píxeles en ruta "pixeles", √ha en ruta "superficie"
        # (a PIXEL_M=30 son proporcionales → mismo reparto relativo).
        def _peso(area_ha: float) -> float:
            if P.BASE_CUOTA == "pixeles":
                return P.pixeles_nominales_desde_ha(area_ha)
            return float(area_ha)

        estandar_peso = sum(
            _peso(u[c]["area_ha"]) for c, v in u.items() if v["modo"] in ("estandar", "techo")
        )
        for cid, info in u.items():
            if info["modo"] == "censo":
                cuota = P.segmentos_desde_area_ha(u[cid]["area_ha"])
            elif info["modo"] == "refuerzo":
                cuota = 50
            elif info["modo"] == "techo":
                cuota = remanente * 0.15 if estandar_peso > 0 else 0
            else:
                cuota = remanente * math.sqrt(_peso(info["area_ha"])) / math.sqrt(
                    estandar_peso or 1
                )
            filas.append(
                {
                    "ecorregion_id": eco_id,
                    "ecorregion": ECO_NAMES.get(eco_id, f"E{eco_id}"),
                    "clase_id": cid,
                    "clase": info["clase"],
                    "modo": info["modo"],
                    "area_ha": info["area_ha"],
                    "pct_eco": info["pct_eco"],
                    "cuota_segmentos": round(cuota, 1),
                    "presupuesto_eco": pres_eco,
                }
            )
    return pd.DataFrame(filas)
