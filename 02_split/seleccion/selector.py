"""Selección exclusiva de rectángulos por ecorregión."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, ECO_NAMES
from seleccion.auditoria import (
    auditoria_cobertura_celdas,
    auditoria_ecorregion,
    auditoria_nacional,
    consolidar_deficits,
)
from seleccion.balanceo import alternar_mgrs, corregir_fugas_split, ids_cluster_espacial, seleccionar_top
from seleccion.bbox import candidatos_fuera_bbox
from seleccion.pools import construir_pools_ecorregion
from seleccion.presencia_rect import ha_clase_series
from seleccion.scores import agregar_scores, asignar_metadatos_anuales, cuota_segmentos_a_rectangulos
from seleccion.split import aplicar_split_ecorregion
from seleccion.tipologia import calibrar_tipologia
from seleccion.tracker import (
    TrackerEspacial,
    convertir_numericos,
    deduplicar_espacial,
    mascara_ecorregion_valida,
    sin_ids_usados,
)

CRS_PROCESO = P.CRS_PROCESO
CRS_SALIDA = P.CRS_SALIDA


def _epsg(crs) -> int | None:
    """EPSG de un CRS, tolerando representaciones distintas de la misma proyección."""
    if crs is None:
        return None
    try:
        return crs.to_epsg()
    except Exception:
        return None


def _asegurar_crs(gdf: gpd.GeoDataFrame, crs_destino: str) -> gpd.GeoDataFrame:
    destino = int(str(crs_destino).split(":")[-1])
    if _epsg(gdf.crs) == destino:
        return gdf
    return gdf.to_crs(crs_destino)


def _preparar_grilla(grilla_hom: gpd.GeoDataFrame, grilla_mix: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    hom = grilla_hom.copy()
    mix = grilla_mix.copy()
    hom["grid_mode"] = "homogeneo"
    mix["grid_mode"] = "mixto"
    if "rect_side" not in hom.columns:
        hom["rect_side"] = 2
    if "rect_side" not in mix.columns:
        mix["rect_side"] = 3
    if hom.crs != mix.crs:
        mix = mix.to_crs(hom.crs)
    gdf = gpd.GeoDataFrame(
        pd.concat([hom, mix], ignore_index=True),
        geometry=pd.concat([hom.geometry, mix.geometry], ignore_index=True),
        crs=hom.crs,
    )
    num_cols = [
        "valid_area_pct", "eco_dom_pct", "noobs_pct", "lulc_mode_pct", "n_mode_classes",
        "transition_pct", "stable_mode_pct", "shannon_idx", "conf_risk_pct", "stable_yr_pct",
        "max_stab_run", "lulc_last_pct", "lulc_mode_id", "lulc_last_id", "eco_dom_id",
        "area_km2", "rect_side", "area_valida_ha",
    ] + [f"md_pct_{p}" for p in ("P1", "P2", "P3", "P4")] + [f"n_stb_{p}" for p in ("P1", "P2", "P3", "P4")]
    gdf = convertir_numericos(gdf, num_cols)
    if "area_valida_ha" not in gdf.columns or gdf["area_valida_ha"].fillna(0).eq(0).all():
        if "area_km2" in gdf.columns and "valid_area_pct" in gdf.columns:
            gdf["area_valida_ha"] = (
                pd.to_numeric(gdf["area_km2"], errors="coerce").fillna(0)
                * pd.to_numeric(gdf["valid_area_pct"], errors="coerce").fillna(0)
            )
    gdf = gdf[mascara_ecorregion_valida(gdf)].copy()
    gdf = agregar_scores(gdf)
    return gdf


def _motivo_cierre(n_sel: int, max_n: int, n_disponibles: int, n_tipologia: int) -> str:
    if n_tipologia == 0:
        return "pool_vacio"
    if n_disponibles == 0:
        return "sin_disponibles"
    if n_sel >= max_n:
        return "cuota_cumplida"
    if n_sel < max_n:
        return "pool_agotado"
    return "pool_agotado"


def _actualizar_registro(pools_log: pd.DataFrame, nombre: str, **kwargs) -> pd.DataFrame:
    if pools_log.empty or "pool" not in pools_log.columns:
        return pools_log
    idx = pools_log.index[pools_log["pool"] == nombre]
    if len(idx) == 0:
        return pools_log
    for k, v in kwargs.items():
        pools_log.loc[idx[0], k] = v
    return pools_log


def _elegir_de_pool(
    spec,
    usados: set[str],
    tracker: TrackerEspacial,
    conteos_anual: dict[int, int],
) -> tuple[pd.DataFrame, set[str], int, str]:
    """
    Elige rectángulos de un pool.

    Si el pool tiene cobertura_objetivo, acumula ha_{clase} hasta el objetivo
    o hasta max_n. Motivo: cobertura_alcanzada | presupuesto_agotado | …
    """
    disponibles = sin_ids_usados(spec.df, usados, tracker)
    n_disponibles = len(disponibles)
    if disponibles.empty or spec.max_n <= 0:
        motivo = "sin_disponibles" if n_disponibles == 0 and len(spec.df) > 0 else _motivo_cierre(
            0, spec.max_n, n_disponibles, len(spec.df)
        )
        return pd.DataFrame(), usados, n_disponibles, motivo

    usa_cobertura = (
        getattr(spec, "cobertura_objetivo", None) is not None
        and spec.clase_objetivo is not None
        and float(getattr(spec, "area_clase_eco_ha", 0) or 0) > 0
    )

    if usa_cobertura:
        cid = int(spec.clase_objetivo)
        work = disponibles.copy()
        work["_ha_clase"] = ha_clase_series(work, cid)
        if "rect_side" in work.columns:
            # Preferir 2×2: alinea con métrica de cobertura alcanzable (grilla 2×2)
            work = work.sort_values(["rect_side", "_ha_clase"], ascending=[True, False])
        else:
            work = work.sort_values("_ha_clase", ascending=False)
        objetivo_ha = float(spec.cobertura_objetivo) * float(spec.area_clase_eco_ha)
        acum = 0.0
        elegidos_idx: list = []
        cuota_obj = getattr(P, "CUOTA_CLASE_ES_OBJETIVO", False)
        for idx, row in work.iterrows():
            if len(elegidos_idx) >= spec.max_n:
                break
            uno = work.loc[[idx]]
            if deduplicar_espacial(uno, tracker, 1).empty:
                continue
            elegidos_idx.append(idx)
            acum += float(row["_ha_clase"])
            if acum >= objetivo_ha:
                break
        if not elegidos_idx:
            return pd.DataFrame(), usados, n_disponibles, "sin_disponibles"
        sel = work.loc[elegidos_idx].copy()
        if acum >= objetivo_ha:
            motivo = "cobertura_alcanzada"
        elif len(sel) >= spec.max_n:
            motivo = "presupuesto_eco_agotado" if cuota_obj else "presupuesto_agotado"
        else:
            motivo = "pool_agotado"
        sel["sample_type"] = spec.sample_type
        sel["dim_temporal"] = spec.dim_temporal
        sel["dim_espacial"] = spec.dim_espacial
        sel["review_tier"] = spec.tier
        # Ya registrados en tracker vía deduplicar_espacial uno a uno
    elif spec.group_cols:
        sel = seleccionar_top(
            disponibles,
            spec.group_cols,
            spec.n_per_group,
            spec.sample_type,
            spec.dim_temporal,
            spec.dim_espacial,
            score_col=spec.score_col if spec.score_col in disponibles.columns else "score",
            tier=spec.tier,
        )
        sel = alternar_mgrs(sel, spec.score_col if spec.score_col in sel.columns else "score")
        sel = sel.head(spec.max_n)
        sel = deduplicar_espacial(sel, tracker, spec.max_n)
        motivo = _motivo_cierre(len(sel), spec.max_n, n_disponibles, len(spec.df))
    else:
        sc = spec.score_col if spec.score_col in disponibles.columns else "score"
        sel = disponibles.sort_values(sc, ascending=False).head(spec.max_n * 3).copy()
        sel["sample_type"] = spec.sample_type
        sel["dim_temporal"] = spec.dim_temporal
        sel["dim_espacial"] = spec.dim_espacial
        sel["review_tier"] = spec.tier
        sel = alternar_mgrs(sel, sc)
        sel = deduplicar_espacial(sel, tracker, spec.max_n)
        motivo = _motivo_cierre(len(sel), spec.max_n, n_disponibles, len(spec.df))

    if sel.empty:
        return sel, usados, n_disponibles, motivo

    if spec.anual_min_stb is not None:
        sel = asignar_metadatos_anuales(sel, spec.anual_min_stb, conteos_anual)
    else:
        sel["ref_period"] = ""
        sel["ref_year"] = -9999
        sel["ref_sensor"] = ""

    if spec.modo_tratamiento:
        sel["modo_tratamiento"] = spec.modo_tratamiento
    else:
        sel["modo_tratamiento"] = "estandar"

    if spec.clase_objetivo is not None:
        sel["clase_objetivo"] = spec.clase_objetivo
        sel["clase_objetivo_nombre"] = CLASS_NAMES.get(spec.clase_objetivo, str(spec.clase_objetivo))
    else:
        sel["clase_objetivo"] = sel["lulc_mode_id"]
        sel["clase_objetivo_nombre"] = sel.get("lulc_mode_name", "")

    sel["pool_origen"] = spec.nombre
    sel["review_status"] = "pendiente"
    usados |= set(sel["grid_id"].astype(str).tolist())
    return sel, usados, n_disponibles, motivo


def _pasada_relleno(
    eco_id: int,
    eco_gdf: gpd.GeoDataFrame,
    eco_sel: pd.DataFrame,
    pres_eco: pd.DataFrame,
    usados: set[str],
    tracker: TrackerEspacial,
    celdas_vacias: set[tuple[int, int]],
    celdas_parciales: set[tuple[int, int]],
    split_inviable_previo: bool,
    logger: logging.Logger,
    *,
    cupo_relleno_restante: int,
    presupuesto_no_asignado: list[dict],
) -> tuple[pd.DataFrame, set[str], int]:
    """
    Relleno con tope nacional, orden 3x3→2x2 y siempre vía tracker.
    Retorna (eco_sel, usados, n_relleno_agregado).
    """
    pres_eco_val = float(pres_eco["presupuesto_eco"].iloc[0])
    max_rects = cuota_segmentos_a_rectangulos(pres_eco_val, rendimiento=0.26)
    deficit = max(0, max_rects - len(eco_sel))
    if deficit <= 0 or cupo_relleno_restante <= 0:
        if deficit > 0 and cupo_relleno_restante <= 0:
            presupuesto_no_asignado.append(
                {
                    "ecorregion_id": eco_id,
                    "deficit_rects": deficit,
                    "motivo": "tope_relleno_nacional",
                }
            )
            logger.info(
                "  Relleno: tope nacional alcanzado — déficit %d no asignado",
                deficit,
            )
        return eco_sel, usados, 0

    tomar_n = min(deficit, cupo_relleno_restante)
    f = dict(P.FILTRO_BASE)
    if eco_id in P.FILTRO_BASE_OVERRIDES:
        f.update(P.FILTRO_BASE_OVERRIDES[eco_id])
    libres = eco_gdf[
        (eco_gdf["valid_area_pct"] >= f["valid_area_pct"])
        & (eco_gdf["eco_dom_pct"] >= f["eco_dom_pct"])
        & (eco_gdf["noobs_pct"] <= f["noobs_pct"])
    ].copy()
    libres = sin_ids_usados(libres, usados, tracker)
    if libres.empty:
        logger.info("  Relleno: sin candidatos libres (déficit %d rects)", deficit)
        presupuesto_no_asignado.append(
            {"ecorregion_id": eco_id, "deficit_rects": deficit, "motivo": "sin_candidatos"}
        )
        return eco_sel, usados, 0

    def _prioridad(row) -> tuple:
        cid = int(row.get("lulc_mode_id", -1))
        celda_vacia = (eco_id, cid) in celdas_vacias
        celda_parcial = (eco_id, cid) in celdas_parciales
        score = float(row.get("score", 0))
        return (
            0 if celda_vacia else (1 if celda_parcial else 2),
            0 if split_inviable_previo else 1,
            -score,
        )

    partes_relleno: list[pd.DataFrame] = []
    n_tomados = 0
    orden = list(getattr(P, "RELLENO_ORDEN_TAMANOS", P.ORDEN_TAMANOS))
    for side in orden:
        if n_tomados >= tomar_n:
            break
        if "rect_side" in libres.columns:
            sub = libres[pd.to_numeric(libres["rect_side"], errors="coerce").fillna(0).astype(int) == side]
        else:
            modo = "mixto" if side == 3 else "homogeneo"
            sub = libres[libres.get("grid_mode", "") == modo] if "grid_mode" in libres.columns else libres
        if sub.empty:
            continue
        sub = sub.copy()
        sub["_prio"] = sub.apply(_prioridad, axis=1)
        sub = sub.sort_values("_prio").drop(columns="_prio")
        falta = tomar_n - n_tomados
        chunk = deduplicar_espacial(sub.head(falta * 3), tracker, falta)
        if chunk.empty:
            continue
        partes_relleno.append(chunk)
        n_tomados += len(chunk)
        # Quitar del pool libre los ya usados
        usados_chunk = set(chunk["grid_id"].astype(str))
        libres = libres[~libres["grid_id"].astype(str).isin(usados_chunk)]

    if not partes_relleno:
        presupuesto_no_asignado.append(
            {"ecorregion_id": eco_id, "deficit_rects": deficit, "motivo": "tracker_bloqueo"}
        )
        return eco_sel, usados, 0

    tomar = pd.concat(partes_relleno, ignore_index=True)
    tomar = tomar.copy()
    tomar["pool_origen"] = "relleno"
    tomar["sample_type"] = "relleno_presupuesto"
    tomar["modo_tratamiento"] = "estandar"
    tomar["clase_objetivo"] = tomar["lulc_mode_id"]
    tomar["clase_objetivo_nombre"] = tomar.get("lulc_mode_name", "")
    tomar["review_status"] = "pendiente"
    usados |= set(tomar["grid_id"].astype(str).tolist())
    remanente_deficit = deficit - len(tomar)
    if remanente_deficit > 0:
        presupuesto_no_asignado.append(
            {
                "ecorregion_id": eco_id,
                "deficit_rects": remanente_deficit,
                "motivo": "parcial_o_tope",
            }
        )
    logger.info(
        "  Relleno: +%d rectángulos (déficit era %d, cupo nacional restante tras toma %d)",
        len(tomar),
        deficit,
        cupo_relleno_restante - len(tomar),
    )
    if eco_sel.empty:
        return tomar, usados, len(tomar)
    return pd.concat([eco_sel, tomar], ignore_index=True), usados, len(tomar)


def _verificar_solape_global(
    selected: gpd.GeoDataFrame,
    logger: logging.Logger,
    *,
    tol_m2: float = 1.0,
) -> dict:
    """
    Verifica solape geométrico global (2x2↔3x3, entre ecos).

    `intersects` cuenta también contactos de borde (área 0). Solo se consideran
    pares con área de intersección > tol_m2 como solape real.
    """
    if selected.empty:
        return {"suma_km2": 0.0, "union_km2": 0.0, "n_pares_intersectan": 0, "ok": True}

    g = selected
    if _epsg(g.crs) != int(CRS_PROCESO.split(":")[-1]):
        g = g.to_crs(CRS_PROCESO)
    suma = float(g.geometry.area.sum() / 1e6)
    try:
        union_area = float(g.geometry.union_all().area / 1e6)
    except AttributeError:
        from shapely.ops import unary_union

        union_area = float(unary_union(g.geometry.values).area / 1e6)

    candidatos = gpd.sjoin(
        g[["grid_id", "geometry"]],
        g[["grid_id", "geometry"]],
        predicate="intersects",
        how="inner",
    )
    candidatos = candidatos[
        candidatos["grid_id_left"].astype(str) != candidatos["grid_id_right"].astype(str)
    ]

    g_idx = g.set_index(g["grid_id"].astype(str), drop=False)
    vistos: set[tuple[str, str]] = set()
    n_pares = 0
    for _, row in candidatos.iterrows():
        a = str(row["grid_id_left"])
        b = str(row["grid_id_right"])
        key = (a, b) if a < b else (b, a)
        if key in vistos:
            continue
        vistos.add(key)
        inter = g_idx.loc[a].geometry.intersection(g_idx.loc[b].geometry)
        if inter.area > tol_m2:
            n_pares += 1

    rel_diff = abs(suma - union_area) / max(suma, 1e-9)
    ok = n_pares == 0 and rel_diff <= 0.001
    info = {
        "suma_km2": round(suma, 4),
        "union_km2": round(union_area, 4),
        "n_pares_intersectan": int(n_pares),
        "n_pares_tocan_borde": int(len(vistos) - n_pares),
        "diff_rel": round(rel_diff, 6),
        "ok": ok,
    }
    if not ok:
        raise RuntimeError(
            f"Solape geométrico detectado al cierre: n_pares={n_pares}, "
            f"suma_km2={suma:.4f}, union_km2={union_area:.4f}, diff_rel={rel_diff:.4%}"
        )
    logger.info(
        "Verificación solape OK: suma=%.2f km² unión=%.2f km² "
        "pares_con_area=%d (contactos_borde=%d ignorados)",
        suma,
        union_area,
        n_pares,
        info["n_pares_tocan_borde"],
    )
    return info


def _exportar_gpkg(gdf: gpd.GeoDataFrame, path: Path) -> None:
    """Exporta un único GeoPackage en CRS_SALIDA (EPSG:4326)."""
    if gdf.empty:
        vacio = gpd.GeoDataFrame(columns=["grid_id", "geometry"], crs=CRS_SALIDA)
        vacio.to_file(path, driver="GPKG")
        return
    out = gdf.copy()
    out = _asegurar_crs(out, CRS_SALIDA)
    out.to_file(path, driver="GPKG")


def ejecutar_seleccion(
    grilla_hom: gpd.GeoDataFrame,
    grilla_mix: gpd.GeoDataFrame,
    presupuesto: pd.DataFrame,
    run_dir: Path,
    logger: logging.Logger,
    matriz: pd.DataFrame | None = None,
) -> gpd.GeoDataFrame:
    run_dir.mkdir(parents=True, exist_ok=True)
    gdf = _asegurar_crs(_preparar_grilla(grilla_hom, grilla_mix), CRS_PROCESO)
    candidatos_2x2 = _asegurar_crs(grilla_hom.copy(), CRS_PROCESO)
    logger.info("Universo nacional: %d rectángulos (%d 2x2 + %d 3x3)", len(gdf), len(grilla_hom), len(grilla_mix))

    err = candidatos_fuera_bbox(gdf)
    if not err.empty:
        err_path = run_dir / "candidatos_error_probable_c2.gpkg"
        _exportar_gpkg(err, err_path)
        logger.info("Exportados %d candidatos fuera bbox tamarugo → %s", len(err), err_path.name)

    tracker = TrackerEspacial(CRS_PROCESO, max_overlap_pct=0.0, tol_m2=1.0)
    usados: set[str] = set()
    partes: list[pd.DataFrame] = []
    deficits: list[dict] = []
    advertencias: list[str] = []
    conteos_anual: dict[int, int] = {}
    presupuesto_no_asignado: list[dict] = []

    # Cupo nacional de relleno: fracción del total final ≤ TOPE_RELLENO_PCT.
    # Equivale a relleno ≤ TOPE/(1-TOPE) × seleccionados_sin_relleno.
    # Se actualiza dinámicamente tras cada ecorregión.
    n_relleno_global = 0
    n_sin_relleno_global = 0
    logger.info(
        "Tope relleno nacional: ≤ %.0f%% del total "
        "(cupo dinámico = %.3f × seleccionados_sin_relleno)",
        100 * P.TOPE_RELLENO_PCT,
        P.TOPE_RELLENO_PCT / max(1e-9, 1.0 - P.TOPE_RELLENO_PCT),
    )

    eco_counts = gdf.groupby("eco_dom_id").size().sort_values()
    eco_order = [int(e) for e in eco_counts.index if int(e) in P.ECORREGIONES]

    por_eco_dir = run_dir / "por_ecorregion"
    por_eco_dir.mkdir(exist_ok=True)

    for eco_id in eco_order:
        nombre = ECO_NAMES.get(eco_id, f"E{eco_id}")
        logger.info("── Ecorregión %d (%s) ──", eco_id, nombre)
        eco_gdf = gdf[gdf["eco_dom_id"].astype(int) == eco_id].copy()
        hom = eco_gdf[eco_gdf["grid_mode"] == "homogeneo"]
        mix = eco_gdf[eco_gdf["grid_mode"] == "mixto"]
        pres_eco = presupuesto[presupuesto["ecorregion_id"] == eco_id].copy()
        if pres_eco.empty:
            logger.warning("  Sin filas de presupuesto")
            continue

        tipologia = calibrar_tipologia(eco_id, eco_gdf, logger)
        pools, adv, pools_log = construir_pools_ecorregion(eco_id, hom, mix, pres_eco, tipologia, logger)
        advertencias.extend(adv)

        # Log por fase: candidatos y bloqueados por fases anteriores
        usados_antes_eco = set(usados)
        fase_actual = -1
        eco_sel_parts: list[pd.DataFrame] = []
        for spec in pools:
            if getattr(spec, "fase", 0) != fase_actual:
                fase_actual = getattr(spec, "fase", 0)
                n_cand = len(spec.df)
                n_bloq = len(usados) - len(usados_antes_eco)
                logger.info(
                    "  · FASE %d — pool %s: %d candidatos en pool, %d ids ya bloqueados en eco",
                    fase_actual,
                    spec.nombre,
                    n_cand,
                    n_bloq,
                )
            sel, usados, n_disponibles, motivo = _elegir_de_pool(spec, usados, tracker, conteos_anual)
            n = len(sel)
            n_tip = len(spec.df)
            pools_log = _actualizar_registro(
                pools_log,
                spec.nombre,
                n_disponibles=n_disponibles,
                n_seleccionados=n,
                motivo_cierre=motivo,
            )
            logger.info("  %-28s: %4d / max %d (%s)", spec.nombre, n, spec.max_n, motivo)
            if (
                n < spec.max_n
                and spec.modo_tratamiento in ("refuerzo", "censo")
                and spec.clase_objetivo
                and motivo != "cobertura_alcanzada"
            ):
                if getattr(P, "CUOTA_CLASE_ES_OBJETIVO", False):
                    if motivo in ("pool_agotado", "sin_disponibles", "presupuesto_eco_agotado"):
                        deficits.append(
                            {
                                "ecorregion_id": eco_id,
                                "ecorregion": nombre,
                                "clase_id": spec.clase_objetivo,
                                "clase": CLASS_NAMES.get(spec.clase_objetivo, ""),
                                "modo": spec.modo_tratamiento,
                                "cuota_rectangulos": spec.max_n,
                                "n_seleccionados": n,
                                "deficit": spec.max_n - n,
                                "motivo_cierre": motivo,
                            }
                        )
                else:
                    deficits.append(
                        {
                            "ecorregion_id": eco_id,
                            "ecorregion": nombre,
                            "clase_id": spec.clase_objetivo,
                            "clase": CLASS_NAMES.get(spec.clase_objetivo, ""),
                            "modo": spec.modo_tratamiento,
                            "cuota_rectangulos": spec.max_n,
                            "n_seleccionados": n,
                            "deficit": spec.max_n - n,
                            "motivo_cierre": motivo,
                        }
                    )
            if spec.clase_objetivo == 3 and n == 0 and n_tip == 0:
                    advertencias.append(
                        f"E{eco_id}: clase 3 (tamarugo) sin candidatos en bbox — "
                        "déficit permanente con grilla actual"
                    )
            if not sel.empty:
                eco_sel_parts.append(sel)

        eco_sel = pd.concat(eco_sel_parts, ignore_index=True) if eco_sel_parts else pd.DataFrame()
        celdas_vacias: set[tuple[int, int]] = set()
        celdas_parciales: set[tuple[int, int]] = set()
        if matriz is not None:
            eco_sel_gdf = None
            if not eco_sel.empty and "geometry" in eco_sel.columns:
                eco_sel_gdf = gpd.GeoDataFrame(eco_sel, geometry="geometry", crs=CRS_PROCESO)
            celdas_prev, _marg = auditoria_cobertura_celdas(
                eco_sel,
                matriz,
                presupuesto,
                candidatos_2x2=candidatos_2x2,
                seleccion_gdf=eco_sel_gdf,
            )
            vac = celdas_prev[(celdas_prev["eco_id"] == eco_id) & (celdas_prev["estado"] == "vacia")]
            par = celdas_prev[(celdas_prev["eco_id"] == eco_id) & (celdas_prev["estado"] == "parcial")]
            celdas_vacias = {(int(r["eco_id"]), int(r["class_id"])) for _, r in vac.iterrows()}
            celdas_parciales = {(int(r["eco_id"]), int(r["class_id"])) for _, r in par.iterrows()}

        # Actualizar conteo sin relleno antes de la pasada
        n_pools_eco = len(eco_sel)
        n_sin_relleno_global += n_pools_eco
        # relleno_max tal que relleno/(sin_relleno+relleno) ≤ TOPE
        factor = P.TOPE_RELLENO_PCT / max(1e-9, 1.0 - P.TOPE_RELLENO_PCT)
        cupo_total = int(factor * n_sin_relleno_global)
        cupo_restante = max(0, cupo_total - n_relleno_global)
        eco_sel, usados, n_rel = _pasada_relleno(
            eco_id,
            eco_gdf,
            eco_sel,
            pres_eco,
            usados,
            tracker,
            celdas_vacias,
            celdas_parciales,
            False,
            logger,
            cupo_relleno_restante=cupo_restante,
            presupuesto_no_asignado=presupuesto_no_asignado,
        )
        n_relleno_global += n_rel
        if eco_sel.empty:
            if not pools_log.empty:
                eco_dir = por_eco_dir / f"E{eco_id:02d}"
                eco_dir.mkdir(exist_ok=True)
                pools_log.to_csv(eco_dir / f"pools_E{eco_id:02d}.csv", index=False)
            continue

        eco_sel, inviable = aplicar_split_ecorregion(eco_sel, eco_id, logger)
        if inviable:
            advertencias.append(f"E{eco_id}: split_inviable")

        eco_gdf_out = gpd.GeoDataFrame(eco_sel, geometry="geometry", crs=gdf.crs)
        eco_dir = por_eco_dir / f"E{eco_id:02d}"
        eco_dir.mkdir(exist_ok=True)
        _exportar_gpkg(eco_gdf_out, eco_dir / f"seleccion_E{eco_id:02d}.gpkg")
        if not pools_log.empty:
            pools_log.to_csv(eco_dir / f"pools_E{eco_id:02d}.csv", index=False)
        aud = auditoria_ecorregion(eco_id, pres_eco, eco_sel, pools_log, deficits)
        aud.to_csv(eco_dir / f"auditoria_E{eco_id:02d}.csv", index=False)
        partes.append(eco_sel)

    presupuesto.to_csv(run_dir / "universo_por_ecorregion.csv", index=False)
    presupuesto.to_csv(run_dir / "presupuesto_por_ecorregion.csv", index=False)
    if presupuesto_no_asignado:
        pd.DataFrame(presupuesto_no_asignado).to_csv(run_dir / "presupuesto_no_asignado.csv", index=False)

    if not partes:
        logger.warning("Selección vacía — sin rectángulos elegidos")
        vacio = gpd.GeoDataFrame(columns=["grid_id", "geometry"], crs=CRS_SALIDA)
        vacio.to_file(run_dir / "seleccion_nacional.gpkg", driver="GPKG")
        return vacio

    selected = gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), geometry="geometry", crs=gdf.crs)
    selected = corregir_fugas_split(selected)
    # Revalidar mínimos de split tras corrección de fugas (por ecorregión)
    if "eco_dom_id" in selected.columns and "split" in selected.columns:
        for eco_id, grp in selected.groupby("eco_dom_id"):
            tmp = grp.copy()
            tmp["_cluster_id"] = ids_cluster_espacial(tmp)
            n_val = tmp.loc[tmp["split"] == "val", "_cluster_id"].nunique()
            n_test = tmp.loc[tmp["split"] == "test", "_cluster_id"].nunique()
            n_train = int((tmp["split"] == "train").sum())
            pct_train = n_train / max(len(tmp), 1)
            inviable = (
                n_val < P.SPLIT_MIN_CLUSTERS.get("val", 2)
                or n_test < P.SPLIT_MIN_CLUSTERS.get("test", 2)
                or pct_train < P.SPLIT_MIN_PCT_TRAIN
            )
            selected.loc[selected["eco_dom_id"] == eco_id, "split_inviable"] = inviable
            if inviable:
                msg = f"E{int(eco_id)}: split_inviable tras corrección de fugas"
                if msg not in advertencias:
                    advertencias.append(msg)
                    logger.warning("  %s (val_c=%d test_c=%d train=%.0f%%)", msg, n_val, n_test, 100 * pct_train)
    _exportar_gpkg(selected, run_dir / "seleccion_nacional.gpkg")
    selected.drop(columns="geometry", errors="ignore").to_csv(run_dir / "seleccion_nacional.csv", index=False)

    consolidar_deficits(deficits).to_csv(run_dir / "deficit_celdas.csv", index=False)
    if matriz is not None:
        celdas, marginales = auditoria_cobertura_celdas(
            selected,
            matriz,
            presupuesto,
            candidatos_2x2=candidatos_2x2,
            seleccion_gdf=selected,
        )
        celdas.to_csv(run_dir / "auditoria_cobertura_celdas.csv", index=False)
        if not marginales.empty:
            marginales.to_csv(run_dir / "auditoria_cobertura_celdas_marginales.csv", index=False)
        n_vacias = int((celdas["estado"] == "vacia").sum()) if "estado" in celdas.columns else 0
        logger.info("Celdas vacías (clase×eco confirmadas): %d / %d", n_vacias, len(celdas))
        if n_vacias and (celdas["class_id"] == 3).any() and (celdas[celdas["class_id"] == 3]["estado"] == "vacia").any():
            advertencias.append(
                "Clase 3 (tamarugo) con celda vacía — puede no ser alcanzable con la grilla actual"
            )
    auditoria_nacional(selected, matriz, presupuesto).to_csv(run_dir / "auditoria_nacional.csv", index=False)

    # B.10 — verificación solape al cierre (después de exportar)
    try:
        solape = _verificar_solape_global(selected, logger)
    except RuntimeError:
        # Aún así guardar cifras parciales si es posible
        raise
    pd.DataFrame([solape]).to_csv(run_dir / "auditoria_solape.csv", index=False)

    n_rel = int((selected.get("pool_origen", "") == "relleno").sum()) if "pool_origen" in selected.columns else 0
    logger.info(
        "Selección nacional: %d rectángulos, %d únicos (relleno=%d, %.1f%%)",
        len(selected),
        selected["grid_id"].nunique(),
        n_rel,
        100 * n_rel / max(len(selected), 1),
    )
    logger.info("Por tipo:\n%s", selected["sample_type"].value_counts().to_string())
    if advertencias:
        logger.warning("Advertencias (%d):\n  %s", len(advertencias), "\n  ".join(advertencias[:30]))
    return selected
