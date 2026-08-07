"""Universo local de clases por ecorregión."""

from __future__ import annotations

import logging

import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, CLASES_MODELO_GENERAL, ECO_NAMES


def cargar_matriz_presencia(ruta) -> pd.DataFrame:
    df = pd.read_csv(ruta)
    return df


def universo_local(
    eco_id: int,
    matriz: pd.DataFrame,
    logger: logging.Logger | None = None,
) -> dict[int, dict]:
    """
    Retorna {class_id: {area_ha, pct_eco, modo, presencia}} para una ecorregión.

    El universo local SOLO contiene clases del modelo general.
    """
    sub = matriz[matriz["ecorregion_id"] == eco_id].copy()
    presentes = sub[sub["area_ha"] > 0]
    dominante = int(presentes.loc[presentes["area_ha"].idxmax(), "clase_id"]) if not presentes.empty else None
    if dominante is not None and dominante not in CLASES_MODELO_GENERAL:
        gen = presentes[presentes["clase_id"].isin(CLASES_MODELO_GENERAL)]
        dominante = int(gen.loc[gen["area_ha"].idxmax(), "clase_id"]) if not gen.empty else None

    clases_validas = set(CLASES_MODELO_GENERAL)
    excluidas: list[tuple[int, float, str]] = []
    resultado: dict[int, dict] = {}

    for _, row in sub.iterrows():
        cid = int(row["clase_id"])
        area = float(row["area_ha"])
        if cid not in clases_validas:
            if area > 0:
                excluidas.append((cid, area, str(row.get("clase", CLASS_NAMES.get(cid, f"DESCONOCIDO_{cid}")))))
            continue
        pct = float(row["pct_de_ecorregion"])
        presencia = str(row.get("presencia", "ausente"))
        modo = _asignar_modo(eco_id, cid, area, pct, dominante)
        resultado[cid] = {
            "area_ha": area,
            "pct_eco": pct,
            "modo": modo,
            "presencia": presencia,
            "clase": row.get("clase", CLASS_NAMES.get(cid, f"DESCONOCIDO_{cid}")),
        }

    if logger is not None and excluidas:
        nombre = ECO_NAMES.get(eco_id, f"E{eco_id}")
        logger.info(
            "  E%d (%s): excluidas %d clases fuera del modelo general:",
            eco_id,
            nombre,
            len(excluidas),
        )
        for cid, area, clase in sorted(excluidas, key=lambda x: -x[1]):
            logger.info("    [%3d] %-30s %10.0f ha", cid, clase, area)

    return resultado


def _asignar_modo(
    eco_id: int,
    cid: int,
    area_ha: float,
    pct_eco: float,
    dominante: int | None,
) -> str:
    if (eco_id, cid) in P.EXCEPCIONES_MODO:
        return P.EXCEPCIONES_MODO[(eco_id, cid)]
    seg_est = area_ha * P.SEGMENTOS_POR_1000HA / 1000.0
    if seg_est <= P.UMBRAL_CENSO_SEGMENTOS:
        return "censo"
    if pct_eco < P.UMBRAL_RAREZA_PCT_ECO:
        return "refuerzo"
    if dominante is not None and cid == dominante:
        return "techo"
    return "estandar"


def refinar_modo_por_concentracion(
    modo_inicial: str,
    candidatos_ordenados_por_ha,
    area_clase_eco_ha: float,
    logger: logging.Logger | None = None,
    *,
    eco_id: int | None = None,
    class_id: int | None = None,
) -> tuple[str, int]:
    """
    Redefine censo→refuerzo si la cobertura objetivo de censo no se alcanza
    con ≤ UMBRAL_CENSO_RECTS rectángulos (acumulando ha descendente).

    Retorna (modo_final, n_rects_requeridos_para_censo).
    Las EXCEPCIONES_MODO se respetan fuera de esta función (no llamar si hay excepción).
    """
    from seleccion.presencia_rect import ha_clase_series, presencia_clase_por_ha

    if modo_inicial != "censo":
        return modo_inicial, 0

    if candidatos_ordenados_por_ha is None or getattr(candidatos_ordenados_por_ha, "empty", True):
        if logger is not None:
            logger.info(
                "  Refinar modo E%s clase %s: sin candidatos con piso ha → refuerzo",
                eco_id,
                class_id,
            )
        return "refuerzo", 0

    df = candidatos_ordenados_por_ha
    cid = class_id
    if cid is None:
        # Intentar inferir de columnas ha_*
        ha_cols = [c for c in df.columns if c.startswith("ha_") and c[3:].isdigit()]
        if len(ha_cols) == 1:
            cid = int(ha_cols[0][3:])
        else:
            return modo_inicial, 0

    mask = presencia_clase_por_ha(df, cid)
    pool = df.loc[mask].copy()
    if pool.empty:
        if logger is not None:
            logger.info(
                "  Refinar modo E%s clase %s: 0 rects sobre piso → refuerzo",
                eco_id,
                class_id,
            )
        return "refuerzo", 0

    ha = ha_clase_series(pool, cid)
    pool = pool.assign(_ha_clase=ha).sort_values("_ha_clase", ascending=False)
    objetivo = float(P.COBERTURA_OBJETIVO_CENSO) * float(area_clase_eco_ha or 0.0)
    if objetivo <= 0:
        return modo_inicial, 0

    acum = 0.0
    n_req = 0
    for v in pool["_ha_clase"].tolist():
        acum += float(v)
        n_req += 1
        if acum >= objetivo:
            break
    alcanzado = acum >= objetivo

    if alcanzado and n_req <= P.UMBRAL_CENSO_RECTS:
        if logger is not None:
            logger.info(
                "  Modo censo confirmado E%s clase %s: cobertura %.0f%% con %d rects (umbral %d)",
                eco_id,
                class_id,
                100 * P.COBERTURA_OBJETIVO_CENSO,
                n_req,
                P.UMBRAL_CENSO_RECTS,
            )
        return "censo", n_req

    if logger is not None:
        logger.info(
            "  Cambio de modo E%s clase %s: censo→refuerzo "
            "(habría requerido %d rects para cobertura censo; umbral=%d; alcanzado=%s)",
            eco_id,
            class_id,
            n_req if alcanzado else n_req,
            P.UMBRAL_CENSO_RECTS,
            alcanzado,
        )
    return "refuerzo", n_req


def imprimir_universo(eco_id: int, universo: dict[int, dict], logger: logging.Logger) -> None:
    nombre = ECO_NAMES.get(eco_id, f"E{eco_id}")
    logger.info("── Ecorregión %s (%s) ──", eco_id, nombre)
    for cid, info in sorted(universo.items(), key=lambda x: x[1]["area_ha"], reverse=True):
        if info["presencia"] == "ausente" and info["area_ha"] <= 0:
            continue
        logger.info(
            "  [%3d] %-30s %10.0f ha %6.2f%% eco | modo=%s | %s",
            cid,
            info["clase"],
            info["area_ha"],
            info["pct_eco"],
            info["modo"],
            info["presencia"],
        )
