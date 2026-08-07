"""Construcción dinámica de pools por ecorregión."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import pandas as pd

from config import params_seleccion as P
from seleccion.balanceo import bloquear_otra_desierto, mascara_transicion_arida
from seleccion.bbox import filtrar_pool_bbox
from seleccion.presencia import refinar_modo_por_concentracion
from seleccion.presencia_rect import (
    fuerza_presencia_series,
    ha_clase_series,
    presencia_clase_por_ha,
)
from seleccion.scores import mejor_periodo, max_mode_en_periodos
from seleccion.taxonomia import anotar_modal_transversal


@dataclass
class PoolSpec:
    nombre: str
    df: pd.DataFrame
    max_n: int
    score_col: str = "score"
    sample_type: str = ""
    dim_temporal: str = ""
    dim_espacial: str = ""
    tier: int = 2
    group_cols: list[str] | None = None
    n_per_group: int = 2
    anual_min_stb: int | None = None
    clase_objetivo: int | None = None
    modo_tratamiento: str = ""
    cobertura_objetivo: float | None = None
    area_clase_eco_ha: float = 0.0
    fase: int = 0
    rect_side_filtro: int | None = None


# Orden tipológico: FASE 1 (3x3) antes que FASE 2 (2x2)
ORDEN_POOLS = [
    "censo",
    "presencia",
    "transicion_homogenea",
    "anual_simple_media",
    "transicion_simple_media",
    "estable_simple_media",
    "anual_homogenea",
    "estable_homogenea",
]

# Tipológicos 3x3 (mixto) y 2x2 (homogéneo)
POOLS_3X3 = {
    "transicion_homogenea",
    "anual_simple_media",
    "transicion_simple_media",
    "estable_simple_media",
}
POOLS_2X2 = {
    "anual_homogenea",
    "estable_homogenea",
}


def _contar_fallas_calidad(
    df: pd.DataFrame,
    relajado: bool = False,
    eco_id: int | None = None,
) -> dict[str, int]:
    """Conteos individuales de falla del filtro de calidad."""
    if df.empty:
        return {"n_falla_valid_area": 0, "n_falla_eco_dom": 0, "n_falla_noobs": 0}
    f = dict(P.FILTRO_RELAJADO if relajado else P.FILTRO_BASE)
    if eco_id is not None and eco_id in P.FILTRO_BASE_OVERRIDES:
        f.update(P.FILTRO_BASE_OVERRIDES[eco_id])
    va = pd.to_numeric(df.get("valid_area_pct", 0), errors="coerce").fillna(0)
    eco = pd.to_numeric(df.get("eco_dom_pct", 0), errors="coerce").fillna(0)
    no = pd.to_numeric(df.get("noobs_pct", 0), errors="coerce").fillna(0)
    return {
        "n_falla_valid_area": int((va < f["valid_area_pct"]).sum()),
        "n_falla_eco_dom": int((eco < f["eco_dom_pct"]).sum()),
        "n_falla_noobs": int((no > f["noobs_pct"]).sum()),
    }


def _contar_fallas_tipologia(nombre: str, base: pd.DataFrame, th: dict) -> dict[str, int]:
    """Conteos de falla por condición tipológica clave (al menos estable_simple_media)."""
    if base.empty:
        return {}
    out: dict[str, int] = {}
    if nombre == "estable_simple_media":
        out["n_falla_max_stab_run"] = int(
            (pd.to_numeric(base.get("max_stab_run", 0), errors="coerce").fillna(0) < th["E_S_MIN_STAB_RUN"]).sum()
        )
        out["n_falla_transition_pct"] = int(
            (pd.to_numeric(base.get("transition_pct", 0), errors="coerce").fillna(0) > th["E_S_MAX_TR_PCT"]).sum()
        )
        mode = pd.to_numeric(base.get("lulc_mode_pct", 0), errors="coerce").fillna(0)
        out["n_falla_lulc_mode_pct"] = int(
            ((mode < th["E_S_MIN_MODE_PCT"]) | (mode >= th["E_S_MAX_MODE_PCT"])).sum()
        )
        nmc = pd.to_numeric(base.get("n_mode_classes", 0), errors="coerce").fillna(0)
        out["n_falla_n_mode_classes"] = int(
            ((nmc < th["E_S_MIN_N_MODE"]) | (nmc > th["E_S_MAX_N_MODE"])).sum()
        )
    elif nombre == "estable_homogenea":
        out["n_falla_max_stab_run"] = int(
            (pd.to_numeric(base.get("max_stab_run", 0), errors="coerce").fillna(0) < th["E_H_MIN_STAB_RUN"]).sum()
        )
        out["n_falla_transition_pct"] = int(
            (pd.to_numeric(base.get("transition_pct", 0), errors="coerce").fillna(0) > th["E_H_MAX_TR_PCT"]).sum()
        )
        out["n_falla_lulc_mode_pct"] = int(
            (pd.to_numeric(base.get("lulc_mode_pct", 0), errors="coerce").fillna(0) < th["E_H_MIN_MODE_PCT"]).sum()
        )
    elif nombre in ("transicion_homogenea", "transicion_simple_media"):
        tr = pd.to_numeric(base.get("transition_pct", 0), errors="coerce").fillna(0)
        out["n_falla_transition_pct"] = int((tr < th["TR_MIN_TR_PCT"]).sum())
        out["n_falla_lulc_mode_pct"] = int(
            (pd.to_numeric(base.get("lulc_mode_pct", 0), errors="coerce").fillna(0) < th.get("E_S_MIN_MODE_PCT", 45)).sum()
        )
    elif nombre in ("anual_simple_media", "anual_homogenea"):
        out["n_falla_lulc_mode_pct"] = int(
            (pd.to_numeric(base.get("lulc_mode_pct", 0), errors="coerce").fillna(0) < th.get("E_S_MIN_MODE_PCT", 45)).sum()
        )
    return out


def _filtro_calidad(
    df: pd.DataFrame,
    relajado: bool = False,
    eco_id: int | None = None,
) -> tuple[pd.DataFrame, dict[str, int]]:
    fallas = _contar_fallas_calidad(df, relajado=relajado, eco_id=eco_id)
    f = dict(P.FILTRO_RELAJADO if relajado else P.FILTRO_BASE)
    if eco_id is not None and eco_id in P.FILTRO_BASE_OVERRIDES:
        f.update(P.FILTRO_BASE_OVERRIDES[eco_id])
    ok = df[
        (df["valid_area_pct"] >= f["valid_area_pct"])
        & (df["eco_dom_pct"] >= f["eco_dom_pct"])
        & (df["noobs_pct"] <= f["noobs_pct"])
    ].copy()
    return ok, fallas


def _registro_pool(
    nombre: str,
    *,
    n_universo: int,
    n_calidad: int,
    n_tipologia: int,
    n_cuota: int,
    fallas_calidad: dict[str, int] | None = None,
    fallas_tipologia: dict[str, int] | None = None,
    fase: int = 0,
) -> dict:
    reg = {
        "pool": nombre,
        "fase": fase,
        "n_candidatos_universo": n_universo,
        "n_pasa_filtro_calidad": n_calidad,
        "n_cumple_tipologia": n_tipologia,
        "n_disponibles": n_tipologia,
        "n_cuota": n_cuota,
        "n_seleccionados": 0,
        "motivo_cierre": "pool_vacio" if n_tipologia == 0 else "",
        "n_falla_valid_area": 0,
        "n_falla_eco_dom": 0,
        "n_falla_noobs": 0,
    }
    if fallas_calidad:
        reg.update(fallas_calidad)
    if fallas_tipologia:
        reg.update(fallas_tipologia)
    return reg


def _ordenar_pool_presencia(pool: pd.DataFrame, cid: int) -> pd.DataFrame:
    """Preferir 3x3 (rect_side desc), luego ha_clase desc; pctp solo como desempate."""
    out = pool.copy()
    out["_ha_clase"] = ha_clase_series(out, cid)
    out["score"] = out["_ha_clase"]
    if "rect_side" in out.columns:
        side = pd.to_numeric(out["rect_side"], errors="coerce").fillna(0)
    elif "grid_mode" in out.columns:
        # mixto = 3x3, homogeneo = 2x2
        side = out["grid_mode"].map({"mixto": 3, "homogeneo": 2}).fillna(0)
    else:
        side = pd.Series(0, index=out.index)
    out["_rect_side"] = side
    out["_pctp"] = fuerza_presencia_series(out, cid)
    return out.sort_values(
        ["_rect_side", "_ha_clase", "_pctp"],
        ascending=[False, False, False],
    ).drop(columns=["_rect_side", "_pctp"], errors="ignore")


def _filtrar_por_tamano(df: pd.DataFrame, rect_side: int) -> pd.DataFrame:
    if df.empty:
        return df
    if "rect_side" in df.columns:
        return df[pd.to_numeric(df["rect_side"], errors="coerce").fillna(0).astype(int) == rect_side].copy()
    modo = "mixto" if rect_side == 3 else "homogeneo"
    if "grid_mode" in df.columns:
        return df[df["grid_mode"] == modo].copy()
    return df.copy()


def construir_pools_ecorregion(
    eco_id: int,
    hom: pd.DataFrame,
    mix: pd.DataFrame,
    presupuesto_eco: pd.DataFrame,
    tipologia: dict,
    logger: logging.Logger,
) -> tuple[list[PoolSpec], list[str], pd.DataFrame]:
    """
    Retorna lista de pools ordenados por fase, advertencias de pctp faltante,
    y registro pool×tamaño para auditoría.
    """
    adv: list[str] = []
    registros: list[dict] = []

    if hom.empty and mix.empty:
        return [], adv, pd.DataFrame()

    comb = pd.concat([hom, mix], ignore_index=True)
    n_universo = len(comb)
    comb = anotar_modal_transversal(comb)
    cands_rel, fallas_rel = _filtro_calidad(comb, relajado=True, eco_id=eco_id)
    base_modelo = comb[comb["general_model_ok"]] if "general_model_ok" in comb.columns else comb
    cands, fallas_base = _filtro_calidad(base_modelo, relajado=False, eco_id=eco_id)
    cands = bloquear_otra_desierto(cands)
    # Censo/refuerzo: no bloquear modal OTRA — muchas clases raras viven en matrices desérticas.

    # homogeneno=2x2, mixto=3x3 (convención de caracterización)
    hom_ok = _filtrar_por_tamano(cands, 2)
    mix_ok = _filtrar_por_tamano(cands, 3)
    if hom_ok.empty and "grid_mode" in cands.columns:
        hom_ok = cands[cands["grid_mode"] == "homogeneo"].copy()
    if hom_ok.empty:
        hom_ok = cands.copy()
    if mix_ok.empty and "grid_mode" in cands.columns:
        mix_ok = cands[cands["grid_mode"] == "mixto"].copy()
    if mix_ok.empty:
        mix_ok = cands.copy()

    th = tipologia
    pools: list[PoolSpec] = []
    from seleccion.scores import cuota_segmentos_a_rectangulos

    # ── FASE 0: censo y refuerzo por clase ──
    refuerzo_rows = presupuesto_eco[presupuesto_eco["modo"] == "refuerzo"].sort_values("pct_eco")
    censo_rows = presupuesto_eco[presupuesto_eco["modo"] == "censo"]

    pres_eco_val = float(presupuesto_eco["presupuesto_eco"].iloc[0]) if not presupuesto_eco.empty else 0.0
    max_presupuesto_rects = cuota_segmentos_a_rectangulos(pres_eco_val, rendimiento=0.26)

    def _construir_pool_presencia(
        row,
        modo_inicial: str,
    ) -> None:
        nonlocal pools, registros, adv
        cid = int(row["clase_id"])
        area_eco = float(row.get("area_ha", 0) or 0)
        pctp_col = f"pctp_{cid}"
        if pctp_col not in cands_rel.columns and f"pct_{cid}" not in cands_rel.columns:
            adv.append(f"E{eco_id}: falta pct/pctp_{cid} ({modo_inicial} clase {cid})")
            return

        # EXCEPCIONES_MODO siempre se respetan
        if (eco_id, cid) in P.EXCEPCIONES_MODO:
            modo = P.EXCEPCIONES_MODO[(eco_id, cid)]
            n_req = 0
        elif modo_inicial == "censo":
            modo, n_req = refinar_modo_por_concentracion(
                "censo",
                cands_rel,
                area_eco,
                logger,
                eco_id=eco_id,
                class_id=cid,
            )
        else:
            modo = "refuerzo"
            n_req = 0

        # Propagar modo refinado al presupuesto (auditoría / cobertura objetivo)
        if modo != modo_inicial:
            presupuesto_eco.loc[presupuesto_eco["clase_id"] == cid, "modo"] = modo

        mask = presencia_clase_por_ha(cands_rel, cid)
        pool = cands_rel.loc[mask].copy()
        pool = filtrar_pool_bbox(pool, cid)
        pool = _ordenar_pool_presencia(pool, cid) if not pool.empty else pool

        if getattr(P, "CUOTA_CLASE_ES_OBJETIVO", False) and modo in ("censo", "refuerzo"):
            max_n = max_presupuesto_rects
        else:
            max_n = cuota_segmentos_a_rectangulos(float(row["cuota_segmentos"]), rendimiento=0.26)
            if modo == "refuerzo":
                max_n = max(1, max_n)
        cobertura = (
            P.COBERTURA_OBJETIVO_CENSO if modo == "censo" else P.COBERTURA_OBJETIVO_RARAS
        )
        nombre = f"censo_{cid}" if modo == "censo" else f"presencia_{cid}"
        sample = "presencia_censo" if modo == "censo" else "presencia_refuerzo"
        tier = 1 if modo == "censo" else 2

        registros.append(
            _registro_pool(
                nombre,
                n_universo=n_universo,
                n_calidad=len(cands_rel),
                n_tipologia=len(pool),
                n_cuota=max_n,
                fallas_calidad=fallas_rel,
                fase=0,
            )
        )
        if pool.empty:
            return
        pools.append(
            PoolSpec(
                nombre=nombre,
                df=pool,
                max_n=max_n,
                score_col="score",
                sample_type=sample,
                dim_temporal="estable",
                dim_espacial="homogenea",
                tier=tier,
                clase_objetivo=cid,
                modo_tratamiento=modo,
                cobertura_objetivo=cobertura,
                area_clase_eco_ha=area_eco,
                fase=0,
            )
        )
        if n_req and modo != modo_inicial:
            logger.info(
                "  Pool %s: modo refinido %s→%s (n_rects censo simulado=%d)",
                nombre,
                modo_inicial,
                modo,
                n_req,
            )

    for _, row in censo_rows.iterrows():
        _construir_pool_presencia(row, "censo")
    for _, row in refuerzo_rows.iterrows():
        _construir_pool_presencia(row, "refuerzo")

    # Presupuesto remanente para tipos generales
    seg_usado = float(
        presupuesto_eco[presupuesto_eco["modo"].isin(["censo", "refuerzo"])]["cuota_segmentos"].sum()
    )
    pres_eco = float(presupuesto_eco["presupuesto_eco"].iloc[0]) if not presupuesto_eco.empty else 0
    remanente = max(0, pres_eco - seg_usado)
    budget_general = cuota_segmentos_a_rectangulos(remanente, rendimiento=0.26)
    n_pools_3x3 = 4
    n_pools_2x2 = 2
    min_3x3 = max(n_pools_3x3, int(round(budget_general * P.CUOTA_MIN_3X3_PCT)))
    min_2x2 = max(n_pools_2x2, int(round(budget_general * P.CUOTA_MIN_2X2_PCT)))
    if min_3x3 + min_2x2 > budget_general and budget_general > 0:
        escala = budget_general / (min_3x3 + min_2x2)
        min_3x3 = max(n_pools_3x3, int(min_3x3 * escala))
        min_2x2 = max(n_pools_2x2, int(min_2x2 * escala))
    n_tipo_3x3 = max(1, min_3x3 // n_pools_3x3)
    n_tipo_2x2 = max(1, min_2x2 // n_pools_2x2)

    def _add_tipologico(
        nombre: str,
        pool_df: pd.DataFrame,
        base_para_fallas: pd.DataFrame,
        *,
        score_col: str,
        sample_type: str,
        dim_t: str,
        dim_s: str,
        fase: int,
        rect_side: int,
        max_n: int,
        group_cols: list[str] | None = None,
        anual_min_stb: int | None = None,
        tier: int = 2,
    ) -> None:
        fallas_tip = _contar_fallas_tipologia(nombre, base_para_fallas, th)
        registros.append(
            _registro_pool(
                nombre,
                n_universo=n_universo,
                n_calidad=len(cands),
                n_tipologia=len(pool_df),
                n_cuota=max_n,
                fallas_calidad=fallas_base,
                fallas_tipologia=fallas_tip,
                fase=fase,
            )
        )
        pools.append(
            PoolSpec(
                nombre=nombre,
                df=pool_df,
                max_n=max_n,
                score_col=score_col,
                sample_type=sample_type,
                dim_temporal=dim_t,
                dim_espacial=dim_s,
                group_cols=group_cols or ["lulc_mode_id"],
                n_per_group=2,
                anual_min_stb=anual_min_stb,
                tier=tier,
                fase=fase,
                rect_side_filtro=rect_side,
            )
        )

    # ── FASE 1 — tipológicos 3x3 (mixto) ──
    pool_t_h = mix_ok[mascara_transicion_arida(mix_ok, min_tr=th["TR_MIN_TR_PCT"], min_pure=65)].copy()
    _add_tipologico(
        "transicion_homogenea",
        pool_t_h,
        mix_ok,
        score_col="sc_t_h",
        sample_type="transicion_homogenea",
        dim_t="transicion",
        dim_s="homogenea",
        fase=1,
        rect_side=3,
        max_n=n_tipo_3x3,
    )

    pool_a_s = mix_ok[
        mix_ok.apply(lambda r: mejor_periodo(r, th.get("A_H_MIN_STAB_YRS", 4) - 1) is not None, axis=1)
        & (mix_ok["lulc_mode_pct"] >= th["E_S_MIN_MODE_PCT"])
        & (mix_ok["lulc_mode_pct"] < th["E_S_MAX_MODE_PCT"])
    ].copy() if not mix_ok.empty else mix_ok.copy()
    _add_tipologico(
        "anual_simple_media",
        pool_a_s,
        mix_ok,
        score_col="sc_a_s",
        sample_type="anual_simple_media",
        dim_t="anual",
        dim_s="simple_media",
        fase=1,
        rect_side=3,
        max_n=n_tipo_3x3,
        anual_min_stb=th.get("A_H_MIN_STAB_YRS", 4) - 1,
    )

    pool_t_s = mix_ok[
        mascara_transicion_arida(mix_ok, min_tr=th["TR_MIN_TR_PCT"], min_pure=65)
        & (mix_ok["n_mode_classes"] >= th["E_S_MIN_N_MODE"])
        & (mix_ok["lulc_mode_pct"] >= th["E_S_MIN_MODE_PCT"])
    ].copy() if not mix_ok.empty else mix_ok.copy()
    _add_tipologico(
        "transicion_simple_media",
        pool_t_s,
        mix_ok,
        score_col="sc_t_s",
        sample_type="transicion_simple_media",
        dim_t="transicion",
        dim_s="simple_media",
        fase=1,
        rect_side=3,
        max_n=n_tipo_3x3,
    )

    pool_e_s = mix_ok[
        (mix_ok["max_stab_run"] >= th["E_S_MIN_STAB_RUN"])
        & (mix_ok["transition_pct"] <= th["E_S_MAX_TR_PCT"])
        & (mix_ok["lulc_mode_pct"] >= th["E_S_MIN_MODE_PCT"])
        & (mix_ok["lulc_mode_pct"] < th["E_S_MAX_MODE_PCT"])
        & (mix_ok["n_mode_classes"] >= th["E_S_MIN_N_MODE"])
        & (mix_ok["n_mode_classes"] <= th["E_S_MAX_N_MODE"])
    ].copy() if not mix_ok.empty else mix_ok.copy()
    _add_tipologico(
        "estable_simple_media",
        pool_e_s,
        mix_ok,
        score_col="sc_e_s",
        sample_type="estable_simple_media",
        dim_t="estable",
        dim_s="simple_media",
        fase=1,
        rect_side=3,
        max_n=n_tipo_3x3,
    )

    # ── FASE 2 — tipológicos 2x2 (homogéneo) ──
    pool_a_h = (
        hom_ok[
            hom_ok.apply(lambda r: mejor_periodo(r, th.get("A_H_MIN_STAB_YRS", 4)) is not None, axis=1)
            & hom_ok.apply(
                lambda r: max_mode_en_periodos(r, th.get("A_H_MIN_STAB_YRS", 4)) >= th["E_H_MIN_MODE_PCT"],
                axis=1,
            )
        ].copy()
        if not hom_ok.empty
        else hom_ok.copy()
    )
    _add_tipologico(
        "anual_homogenea",
        pool_a_h,
        hom_ok,
        score_col="sc_a_h",
        sample_type="anual_homogenea",
        dim_t="anual",
        dim_s="homogenea",
        fase=2,
        rect_side=2,
        max_n=n_tipo_2x2,
        anual_min_stb=th.get("A_H_MIN_STAB_YRS", 4),
        tier=1,
    )

    pool_e_h = (
        hom_ok[
            (hom_ok["max_stab_run"] >= th["E_H_MIN_STAB_RUN"])
            & (hom_ok["transition_pct"] <= th["E_H_MAX_TR_PCT"])
            & (hom_ok["stable_yr_pct"] >= th["E_H_MIN_STAB_PCT"])
            & (hom_ok["lulc_mode_pct"] >= th["E_H_MIN_MODE_PCT"])
            & (hom_ok["shannon_idx"] <= th["E_H_MAX_SHANNON"])
        ].copy()
        if not hom_ok.empty
        else hom_ok.copy()
    )
    _add_tipologico(
        "estable_homogenea",
        pool_e_h,
        hom_ok,
        score_col="sc_e_h",
        sample_type="estable_homogenea",
        dim_t="estable",
        dim_s="homogenea",
        fase=2,
        rect_side=2,
        max_n=n_tipo_2x2,
        tier=1,
    )

    def _orden(p: PoolSpec) -> tuple:
        if p.nombre.startswith("censo_"):
            return (0, 0, p.nombre)
        if p.nombre.startswith("presencia_"):
            return (0, 1, p.nombre)
        try:
            return (p.fase if p.fase else 2, ORDEN_POOLS.index(p.nombre), p.nombre)
        except ValueError:
            return (3, 99, p.nombre)

    pools.sort(key=_orden)
    logger.info(
        "  Eco %d: %d pools (fase0=%d fase1=%d fase2=%d), budget general ~%d rects",
        eco_id,
        len(pools),
        sum(1 for p in pools if p.fase == 0),
        sum(1 for p in pools if p.fase == 1),
        sum(1 for p in pools if p.fase == 2),
        budget_general,
    )
    return pools, adv, pd.DataFrame(registros)
