#!/usr/bin/env python3
"""Fase 2 — Selección de muestra no contigua + paquetes supervisora/revisores.

NO construye la clave definitiva (eso es Fase 3). Genera:
  - supervisor_review.gpkg (trabajo de la supervisora)
  - calibration_review_blind.* (base ciega)
  - per_reviewer/review_<revisor>.gpkg (ciego, orden distinto por revisor)
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# PARÁMETROS
# ═══════════════════════════════════════════════════════════════
RUTA_ENTRADA = (
    "/home/lserey/mapbiomas_land/prod/04_labeling_cim/2015/consolidado/"
    "labeled_segments_rev2015.gpkg"
)
DIR_RESULTADOS = "/home/lserey/mapbiomas_land/prod/sample_review_calibration"

# Ruta a proposed_quotas.csv (o copia aprobada). AJUSTAR tras Fase 1.
QUOTAS_CSV = (
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "20260810_161113/analysis/proposed_quotas.csv"
)

SEED = 2026
DISTANCIA_MINIMA_M = None   # None = auto = FACTOR_SEP * mediana(diámetro equivalente)
FACTOR_SEP = 3.0            # múltiplo del tamaño de segmento para la separación
NO_CONTIGUIDAD_ALCANCE = "global"  # "global" | "intra_clase"

REVISORES: list[str] = []  # vacío = solo muestra base; completar después con nombres reales
SUPERVISOR_MODE = "confirmar"   # "confirmar" | "ciego"
SUPERVISOR_ORDER = "por_clase"  # "por_clase" | "aleatorio" (ignorado si modo ciego)

PUREZA_MIN = 100.0
TOL_PUREZA = 1e-6

# Mismos filtros que Fase 1 (importados como default desde 01; se reiteran aquí
# para que queden visibles en el bloque de parámetros del script).
CLASES_EXCLUIDAS = {33, 34}  # agua, glaciar
AREA_MIN_REGLA = "p40"
AREA_MIN_PERCENTIL = 0.40
PIXEL_M = 30.0
BORDE_MIN_PX = 20
BORDE_MIN_M = BORDE_MIN_PX * PIXEL_M
ESTRATIFICACION_ECO = "par_igual"
ECO_STRATA_CSV = (
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "20260810_161113/analysis/proposed_eco_strata.csv"
)
# ═══════════════════════════════════════════════════════════════

import importlib.util
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from pyproj import Geod
from scipy.spatial import cKDTree

# Importar utilidades de Fase 1 (módulo con nombre numérico)
_SRC = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "analyze_proportion", _SRC / "01_analyze_proportion.py"
)
_AP = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_AP)

crear_dir_run = _AP.crear_dir_run
cargar_segmentos_puros = _AP.cargar_segmentos_puros
areas_km2_utm_series = _AP.areas_km2_utm_series
diametro_equivalente_km = _AP.diametro_equivalente_km
filtrar_candidatos_calibracion = _AP.filtrar_candidatos_calibracion
planificar_estratos_eco = _AP.planificar_estratos_eco

GEOD = Geod(ellps="WGS84")


def _distancia_geodesica_m(lon1, lat1, lon2, lat2) -> float:
    _, _, dist = GEOD.inv(lon1, lat1, lon2, lat2)
    return float(abs(dist))


def seleccionar_greedy(
    puros: gpd.GeoDataFrame,
    quotas: pd.DataFrame,
    seed: int,
    dist_min_m: float,
    alcance: str,
    eco_plan: pd.DataFrame | None = None,
) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    """Selección greedy clase-a-clase (rara→común) con separación mínima.

    Si eco_plan tiene filas, within-class se respeta la cuota por ecorregión
    (par_igual); el déficit de un eco se intenta completar con otros ecos de
    la misma clase al final.
    """
    import warnings

    rng = np.random.default_rng(seed)
    alcance = alcance.lower().strip()
    if alcance not in {"global", "intra_clase"}:
        raise ValueError(f"NO_CONTIGUIDAD_ALCANCE inválido: {alcance}")

    q = quotas.copy()
    q["code"] = q["code"].astype(int)
    q["proposed_quota"] = q["proposed_quota"].astype(int)
    order_codes = (
        q.sort_values(["available", "code"], ascending=[True, True])["code"]
        .tolist()
    )

    work = puros.copy()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message=".*geographic CRS.*")
        cents = work.geometry.centroid
    work["_lon"] = cents.x.values
    work["_lat"] = cents.y.values
    work["_idx"] = np.arange(len(work))
    if "eco_dom_id" not in work.columns:
        work["eco_dom_id"] = -1

    selected_mask = np.zeros(len(work), dtype=bool)
    selected_rows: list[int] = []

    ang_tol_deg = (dist_min_m / 111_320.0) * 1.25

    def _violates(i: int, pool_indices: list[int]) -> bool:
        if not pool_indices:
            return False
        lon_i, lat_i = float(work.iloc[i]["_lon"]), float(work.iloc[i]["_lat"])
        pts = np.column_stack(
            [
                work.iloc[pool_indices]["_lon"].to_numpy(),
                work.iloc[pool_indices]["_lat"].to_numpy(),
            ]
        )
        tree = cKDTree(pts)
        near = tree.query_ball_point([lon_i, lat_i], r=ang_tol_deg)
        for j_local in near:
            j = pool_indices[j_local]
            d = _distancia_geodesica_m(
                lon_i,
                lat_i,
                float(work.iloc[j]["_lon"]),
                float(work.iloc[j]["_lat"]),
            )
            if d < dist_min_m:
                return True
        return False

    def _try_pick(cand_pos: np.ndarray, need: int, code: int) -> int:
        taken = 0
        for i in cand_pos:
            if taken >= need:
                break
            if selected_mask[i]:
                continue
            if alcance == "global":
                pool = selected_rows
            else:
                pool = [
                    j
                    for j in selected_rows
                    if int(work.iloc[j]["class_code"]) == code
                ]
            if _violates(int(i), pool):
                continue
            selected_mask[i] = True
            selected_rows.append(int(i))
            taken += 1
        return taken

    logro = []
    for code in order_codes:
        quota = int(q.loc[q["code"] == code, "proposed_quota"].iloc[0])
        avail_n = int(q.loc[q["code"] == code, "available"].iloc[0])
        name = (
            q.loc[q["code"] == code, "name"].iloc[0]
            if "name" in q.columns
            else str(code)
        )

        taken = 0
        if eco_plan is not None and len(eco_plan):
            ep = eco_plan.loc[
                (eco_plan["code"].astype(int) == code)
                & (eco_plan["proposed_quota"].astype(int) > 0)
            ].copy()
            # Ecos más raros primero
            ep = ep.sort_values(["available", "eco_dom_id"], ascending=[True, True])
            for _, erow in ep.iterrows():
                eco_id = int(erow["eco_dom_id"])
                need = int(erow["proposed_quota"])
                cand_pos = np.where(
                    (~selected_mask)
                    & (work["class_code"].astype(int).to_numpy() == code)
                    & (work["eco_dom_id"].astype(int).to_numpy() == eco_id)
                )[0]
                rng.shuffle(cand_pos)
                taken += _try_pick(cand_pos, need, code)

        # Completar déficit de la clase con cualquier ecorregión
        if taken < quota:
            cand_pos = np.where(
                (~selected_mask) & (work["class_code"].astype(int).to_numpy() == code)
            )[0]
            rng.shuffle(cand_pos)
            taken += _try_pick(cand_pos, quota - taken, code)

        deficit_nc = max(0, quota - taken)
        logro.append(
            {
                "code": code,
                "name": name,
                "available": avail_n,
                "quota": quota,
                "achieved": taken,
                "deficit_noncontig": deficit_nc,
            }
        )
        print(
            f"  clase {code} ({name}): cuota={quota} logrado={taken} "
            f"déficit_no_contigüedad={deficit_nc}"
        )

    sel = work.iloc[selected_rows].copy().reset_index(drop=True)
    sel["review_id"] = np.arange(1, len(sel) + 1, dtype=int)
    return sel, pd.DataFrame(logro)


def _columnas_ubicacion(sel: gpd.GeoDataFrame) -> list[str]:
    cols = ["review_id"]
    for c in ["segment_uid", "segment_id", "grid_id", "utm_zone", "utm_epsg", "rev_year"]:
        if c in sel.columns:
            cols.append(c)
    return cols


def construir_supervisor(sel: gpd.GeoDataFrame, mode: str, order: str, seed: int) -> gpd.GeoDataFrame:
    mode = mode.lower().strip()
    order = order.lower().strip()
    base_cols = _columnas_ubicacion(sel)
    geom = sel.geometry.name

    if mode == "confirmar":
        df = sel[base_cols + ["class_code", "class_name", "proportion_pct", geom]].copy()
        df = df.rename(
            columns={
                "class_code": "proposed_class",
                "class_name": "proposed_class_name",
                "proportion_pct": "proportion",
            }
        )
        df["supervisor_class"] = df["proposed_class"].astype("Int64")
        df["supervisor_confirmed"] = False
        df["supervisor_notes"] = ""
        if order == "por_clase":
            df = df.sort_values(["proposed_class", "review_id"]).reset_index(drop=True)
        else:
            df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    elif mode == "ciego":
        df = sel[base_cols + [geom]].copy()
        df["supervisor_class"] = pd.Series([pd.NA] * len(df), dtype="Int64")
        df["supervisor_confirmed"] = False
        df["supervisor_notes"] = ""
        df = df.sample(frac=1.0, random_state=seed).reset_index(drop=True)
    else:
        raise ValueError(f"SUPERVISOR_MODE inválido: {mode}")

    return gpd.GeoDataFrame(df, geometry=geom, crs=sel.crs)


def construir_ciego(sel: gpd.GeoDataFrame, seed: int, reviewer_id: str | None = None) -> gpd.GeoDataFrame:
    base_cols = _columnas_ubicacion(sel)
    # Preferir grid_id/utm_zone para ubicación; sin clase/proportion
    keep = [c for c in base_cols if c in sel.columns]
    geom = sel.geometry.name
    df = sel[keep + [geom]].copy()
    df["reviewer_class"] = pd.Series([pd.NA] * len(df), dtype="Int64")
    df["reviewer_notes"] = ""
    if reviewer_id is not None:
        df["reviewer_id"] = reviewer_id
        # Semilla distinta por revisor
        seed_r = seed + (sum(ord(ch) for ch in reviewer_id) * 17)
    else:
        seed_r = seed
    df = df.sample(frac=1.0, random_state=seed_r).reset_index(drop=True)
    return gpd.GeoDataFrame(df, geometry=geom, crs=sel.crs)


def escribir_readme_run(
    path: Path,
    dist_min_m: float,
    logro: pd.DataFrame,
    n_sel: int,
    params: dict,
) -> None:
    lines = [
        "# Calibration sample run notes",
        "",
        "## Framework",
        "",
        "The test reference is the **class confirmed by the supervisor**, not the raw C2 label.",
        "Supervisor validation produces the answer key; reviewers classify blind and are scored",
        "against that key. This measures reviewer agreement on 100% pure segments — **not** a C2 validation.",
        "",
        "## Parameters used",
        "",
    ]
    for k, v in params.items():
        lines.append(f"- `{k}` = `{v}`")
    lines += [
        "",
        f"**Applied minimum separation:** {dist_min_m:.2f} m",
        "",
        f"**Selected segments:** {n_sel}",
        "",
        "## Quota vs achieved",
        "",
        logro.to_markdown(index=False) if _has_tabulate() else _md_table(logro),
        "",
    ]
    deficits = logro.loc[logro["deficit_noncontig"] > 0]
    if len(deficits):
        lines += [
            "## Non-contiguity deficits",
            "",
            deficits.to_markdown(index=False) if _has_tabulate() else _md_table(deficits),
            "",
        ]
    else:
        lines += ["## Non-contiguity deficits", "", "None.", ""]

    lines += [
        "## Execution order",
        "",
        "1. Phase 1 → approve quotas (`proposed_quotas.csv`)",
        "2. Phase 2 → generates `supervisor_review` + blind reviewer files",
        "3a. Supervisor fills `supervisor_review` (confirmed class)",
        "3b. Reviewers fill `reviewer_class` in their files (parallel, blind)",
        "4. Phase 3 → scores reviewers against the confirmed key",
        "",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")


def _has_tabulate() -> bool:
    try:
        import tabulate  # noqa: F401

        return True
    except ImportError:
        return False


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = [
        "| " + " | ".join(cols) + " |",
        "| " + " | ".join("---" for _ in cols) + " |",
    ]
    for _, row in df.iterrows():
        lines.append("| " + " | ".join(str(row[c]) for c in cols) + " |")
    return "\n".join(lines)


def main() -> None:
    print("═" * 60)
    print("FASE 2 — Selección de muestra + paquetes")
    print("═" * 60)

    quotas_path = Path(QUOTAS_CSV)
    if not quotas_path.is_file():
        print(f"ERROR: no existe QUOTAS_CSV: {quotas_path}")
        print("Ajuste el parámetro tras aprobar las cuotas de la Fase 1.")
        raise SystemExit(1)

    params = {
        "RUTA_ENTRADA": RUTA_ENTRADA,
        "QUOTAS_CSV": str(quotas_path),
        "SEED": SEED,
        "DISTANCIA_MINIMA_M": DISTANCIA_MINIMA_M,
        "FACTOR_SEP": FACTOR_SEP,
        "NO_CONTIGUIDAD_ALCANCE": NO_CONTIGUIDAD_ALCANCE,
        "REVISORES": REVISORES,
        "SUPERVISOR_MODE": SUPERVISOR_MODE,
        "SUPERVISOR_ORDER": SUPERVISOR_ORDER,
        "PUREZA_MIN": PUREZA_MIN,
        "CLASES_EXCLUIDAS": sorted(CLASES_EXCLUIDAS),
        "AREA_MIN_REGLA": AREA_MIN_REGLA,
        "AREA_MIN_PERCENTIL": AREA_MIN_PERCENTIL,
        "BORDE_MIN_PX": BORDE_MIN_PX,
        "BORDE_MIN_M": BORDE_MIN_M,
        "ESTRATIFICACION_ECO": ESTRATIFICACION_ECO,
        "ECO_STRATA_CSV": ECO_STRATA_CSV,
    }
    print("Parámetros:")
    for k, v in params.items():
        print(f"  {k} = {v}")

    quotas = pd.read_csv(quotas_path)
    required = {"code", "available", "proposed_quota"}
    if not required.issubset(quotas.columns):
        print(f"ERROR: proposed_quotas.csv debe tener columnas {required}")
        raise SystemExit(1)
    quotas = quotas.loc[quotas["proposed_quota"].astype(int) > 0].copy()
    # No seleccionar clases excluidas aunque figuren en el CSV
    quotas = quotas.loc[~quotas["code"].astype(int).isin(CLASES_EXCLUIDAS)].copy()

    puros, _det = cargar_segmentos_puros(RUTA_ENTRADA, PUREZA_MIN, TOL_PUREZA)
    candidatos, umbrales, resumen = filtrar_candidatos_calibracion(
        puros,
        clases_excluidas=CLASES_EXCLUIDAS,
        area_min_regla=AREA_MIN_REGLA,
        area_min_percentil=AREA_MIN_PERCENTIL,
        borde_min_m=BORDE_MIN_M,
    )
    # Actualizar "available" real tras filtros (útil para el resumen)
    avail_real = candidatos.groupby(candidatos["class_code"].astype(int)).size()
    quotas["available"] = quotas["code"].astype(int).map(avail_real).fillna(0).astype(int)

    if ECO_STRATA_CSV:
        eco_plan = pd.read_csv(ECO_STRATA_CSV)
        print(f"Estratos eco cargados desde: {ECO_STRATA_CSV}")
    else:
        eco_plan = planificar_estratos_eco(candidatos, quotas, ESTRATIFICACION_ECO)
        print(
            f"Estratos eco generados ({ESTRATIFICACION_ECO}): "
            f"{int((eco_plan['proposed_quota']>0).sum())} celdas clase×eco con cuota>0"
        )

    print("Calculando diámetros equivalentes para distancia de separación...")
    diams_m = candidatos["eq_diam_km"] * 1000.0
    med_diam = float(diams_m.median()) if len(candidatos) else float("nan")

    if DISTANCIA_MINIMA_M is None:
        dist_min = FACTOR_SEP * med_diam
        print(
            f"DISTANCIA_MINIMA_M auto = {FACTOR_SEP} × mediana(eq_diam) "
            f"= {FACTOR_SEP} × {med_diam:.2f} m = {dist_min:.2f} m"
        )
    else:
        dist_min = float(DISTANCIA_MINIMA_M)
        print(f"DISTANCIA_MINIMA_M fija = {dist_min:.2f} m "
              f"(mediana eq_diam = {med_diam:.2f} m)")

    print("Selección greedy (rara → común, estratificada por ecorregión)...")
    sel, logro = seleccionar_greedy(
        candidatos,
        quotas,
        SEED,
        dist_min,
        NO_CONTIGUIDAD_ALCANCE,
        eco_plan=eco_plan,
    )

    run_dir = crear_dir_run(DIR_RESULTADOS)
    out_dir = run_dir / "sample"
    out_dir.mkdir(parents=True, exist_ok=True)
    por_rev = out_dir / "per_reviewer"
    if REVISORES:
        por_rev.mkdir(parents=True, exist_ok=True)

    # A) muestra seleccionada (con clase C2 propuesta / proportion — archivo de trabajo)
    sel_out_cols = _columnas_ubicacion(sel) + [
        c for c in ["class_code", "class_name", "proportion_pct"] if c in sel.columns
    ]
    geom = sel.geometry.name
    selected = sel[sel_out_cols + [geom]].copy()
    selected = selected.rename(
        columns={
            "class_code": "proposed_class",
            "class_name": "proposed_class_name",
            "proportion_pct": "proportion",
        }
    )
    selected_path = out_dir / "selected_segments.gpkg"
    gpd.GeoDataFrame(selected, geometry=geom, crs=sel.crs).to_file(
        selected_path, driver="GPKG"
    )
    print(f"Escrito: {selected_path}")

    # B) supervisor
    sup = construir_supervisor(sel, SUPERVISOR_MODE, SUPERVISOR_ORDER, SEED)
    sup_path = out_dir / "supervisor_review.gpkg"
    sup.to_file(sup_path, driver="GPKG")
    print(f"Escrito: {sup_path}")

    # C) ciego base
    blind = construir_ciego(sel, SEED, reviewer_id=None)
    blind_gpkg = out_dir / "calibration_review_blind.gpkg"
    blind_csv = out_dir / "calibration_review_blind.csv"
    blind.to_file(blind_gpkg, driver="GPKG")
    blind.drop(columns=[blind.geometry.name]).to_csv(blind_csv, index=False)
    print(f"Escrito: {blind_gpkg}")
    print(f"Escrito: {blind_csv}")

    # D) por revisor (omitido si REVISORES está vacío)
    if not REVISORES:
        print("REVISORES vacío: no se generan copias per_reviewer/.")
    for rev in REVISORES:
        rev_gdf = construir_ciego(sel, SEED, reviewer_id=rev)
        rev_path = por_rev / f"review_{rev}.gpkg"
        rev_gdf.to_file(rev_path, driver="GPKG")
        print(f"Escrito: {rev_path}")

    params_logged = dict(params)
    params_logged["DISTANCIA_MINIMA_M_APLICADA"] = dist_min
    params_logged["mediana_eq_diam_m"] = med_diam
    escribir_readme_run(
        out_dir / "README_run.md", dist_min, logro, len(sel), params_logged
    )
    # Copia también en raíz del run
    escribir_readme_run(
        run_dir / "README_run.md", dist_min, logro, len(sel), params_logged
    )

    logro_path = out_dir / "selection_summary.csv"
    logro.to_csv(logro_path, index=False)
    eco_out = out_dir / "eco_strata_used.csv"
    eco_plan.to_csv(eco_out, index=False)

    print("\n══ RESUMEN FASE 2 ══")
    print(f"  Run dir              : {run_dir}")
    print(f"  Seleccionados total  : {len(sel)}")
    print(f"  Distancia mín. (m)   : {dist_min:.2f}")
    print(logro.to_string(index=False))
    dsum = int(logro["deficit_noncontig"].sum())
    print(f"  Déficit no-contigüidad (suma) = {dsum}")


if __name__ == "__main__":
    main()
