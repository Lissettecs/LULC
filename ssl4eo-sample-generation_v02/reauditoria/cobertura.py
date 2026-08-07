"""Cobertura de clase alcanzable vs absoluta (A.1–A.3)."""

from __future__ import annotations

import logging
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, CLASES_MODELO_GENERAL
from seleccion.presencia_rect import ha_clase_series, presencia_clase_por_ha, piso_presencia_ha

logger = logging.getLogger("reauditoria")


def _ha_columna(df: pd.DataFrame, class_id: int) -> pd.Series:
    """Superficie de la clase en ha; deriva de pct×area_valida si hace falta."""
    try:
        return ha_clase_series(df, class_id)
    except ValueError:
        return pd.Series(0.0, index=df.index)


def cargar_candidatos_2x2(caract_dir: Path) -> gpd.GeoDataFrame:
    """Grilla 2x2 consolidada de ambos husos en EPSG:32719 (partición no solapada)."""
    partes: list[gpd.GeoDataFrame] = []
    for huso in P.HUSOS:
        path = caract_dir / "consolidado" / f"grilla_utm{huso}_2x2.gpkg"
        if not path.is_file():
            logger.warning("Falta consolidado 2x2: %s", path)
            continue
        g = gpd.read_file(path)
        if g.crs is None or g.crs.to_epsg() != 32719:
            g = g.to_crs(32719)
        partes.append(g)
    if not partes:
        raise FileNotFoundError(f"Sin grillas 2x2 en {caract_dir}/consolidado")
    return gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:32719")


def cargar_seleccion(sel_dir: Path) -> pd.DataFrame:
    csv = sel_dir / "seleccion_nacional.csv"
    if not csv.is_file():
        raise FileNotFoundError(csv)
    return pd.read_csv(csv)


def cargar_seleccion_geoms(sel_dir: Path) -> gpd.GeoDataFrame:
    """Geometrías de la selección unificadas a EPSG:32719."""
    partes: list[gpd.GeoDataFrame] = []
    for huso, _epsg in ((18, 32718), (19, 32719)):
        path = sel_dir / f"seleccion_nacional_utm{huso}.gpkg"
        if not path.is_file():
            continue
        g = gpd.read_file(path)
        if g.crs is None or g.crs.to_epsg() != 32719:
            g = g.to_crs(32719)
        partes.append(g)
    if not partes:
        raise FileNotFoundError(f"Sin GPKG de selección en {sel_dir}")
    return gpd.GeoDataFrame(pd.concat(partes, ignore_index=True), crs="EPSG:32719")


def cargar_matriz(matriz_path: Path) -> pd.DataFrame:
    return pd.read_csv(matriz_path)


def celdas_a_auditar(matriz: pd.DataFrame, presupuesto: pd.DataFrame | None) -> pd.DataFrame:
    """
    Celdas clase×eco del modelo general con presencia confirmada/presente.
    Las marginales se excluyen del indicador principal (igual que la auditoría v03).
    """
    sub = matriz[
        matriz["clase_id"].isin(CLASES_MODELO_GENERAL)
        & (matriz["area_ha"] > 0)
        & (matriz["presencia"].astype(str).str.lower().isin(["presente", "confirmada"]))
    ].copy()
    if presupuesto is not None and not presupuesto.empty:
        modos = presupuesto[["ecorregion_id", "clase_id", "modo"]].drop_duplicates()
        sub = sub.merge(
            modos,
            left_on=["ecorregion_id", "clase_id"],
            right_on=["ecorregion_id", "clase_id"],
            how="left",
        )
    else:
        sub["modo"] = "estandar"
    return sub


def _indices_2x2_cubiertos(
    candidatos_2x2: gpd.GeoDataFrame,
    seleccion_gdf: gpd.GeoDataFrame,
) -> dict[int, pd.Index]:
    """
    Por ecorregión: índices de celdas 2x2 que intersectan algún rectángulo seleccionado
    de esa misma ecorregión.

    Así el numerador A.1 es un subconjunto del denominador (misma partición 2x2) y
    no puede superar el 100 %. Sumar ha_* de rectángulos 3×3 seleccionados contra
    Σ ha_* de la grilla 2x2 no es comparable: un 3×3 puede atribuir más ha de clase
    a la eco que la suma de las celdas 2x2 con eco_dom_id de esa eco.
    """
    out: dict[int, pd.Index] = {}
    if seleccion_gdf.empty or candidatos_2x2.empty:
        return out

    sel = seleccion_gdf[["eco_dom_id", "geometry"]].copy()
    sel["eco_dom_id"] = sel["eco_dom_id"].astype(int)
    cand = candidatos_2x2[["eco_dom_id", "geometry"]].copy()
    cand["eco_dom_id"] = cand["eco_dom_id"].astype(int)
    cand["_idx"] = cand.index

    for eco_id, cand_eco in cand.groupby("eco_dom_id"):
        sel_eco = sel[sel["eco_dom_id"] == int(eco_id)]
        if sel_eco.empty:
            out[int(eco_id)] = pd.Index([])
            continue
        hits = gpd.sjoin(
            cand_eco[["_idx", "geometry"]],
            sel_eco[["geometry"]],
            predicate="intersects",
            how="inner",
        )
        out[int(eco_id)] = pd.Index(hits["_idx"].unique())
    return out


def auditoria_cobertura_corregida(
    seleccion: pd.DataFrame,
    candidatos_2x2: gpd.GeoDataFrame,
    matriz: pd.DataFrame,
    presupuesto: pd.DataFrame | None = None,
    seleccion_gdf: gpd.GeoDataFrame | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Retorna (auditoria_corregida, ratio_fuentes_por_celda).

    pct_cubierto_alcanzable = ha_2x2_cubiertas / ha_candidatos_2x2  (principal, ≤ 100 %)
    pct_cubierto_absoluto   = ha_sel_rects / ha_matriz               (referencia)
    ratio_fuentes           = ha_candidatos_2x2 / ha_matriz
    """
    celdas = celdas_a_auditar(matriz, presupuesto)
    cubiertos = {}
    if seleccion_gdf is not None and not seleccion_gdf.empty:
        logger.info("Calculando intersección selección ∩ grilla 2x2 por ecorregión…")
        cubiertos = _indices_2x2_cubiertos(candidatos_2x2, seleccion_gdf)
    else:
        logger.warning(
            "Sin geometrías de selección: A.1 usará Σ ha de rects (puede superar 100 %% con 3×3)."
        )

    filas: list[dict] = []

    for _, row in celdas.iterrows():
        eco_id = int(row["ecorregion_id"])
        cid = int(row["clase_id"])
        modo = str(row.get("modo", "estandar") or "estandar")
        ha_matriz = float(row["area_ha"])

        eco_sel = seleccion[seleccion["eco_dom_id"].astype(int) == eco_id]
        eco_cand = candidatos_2x2[candidatos_2x2["eco_dom_id"].astype(int) == eco_id]

        ha_sel_s = _ha_columna(eco_sel, cid) if not eco_sel.empty else pd.Series(dtype=float)
        ha_cand_s = _ha_columna(eco_cand, cid) if not eco_cand.empty else pd.Series(dtype=float)

        # A.2 / reporte: ha atribuida a los rectángulos seleccionados (attrs)
        ha_seleccionada = float(ha_sel_s.sum()) if len(ha_sel_s) else 0.0
        # Denominador A.1 / A.3: partición 2x2 de la eco
        ha_candidatos = float(ha_cand_s.sum()) if len(ha_cand_s) else 0.0

        # Numerador A.1: misma partición, solo celdas 2x2 intersectadas por la selección
        if eco_id in cubiertos and len(cubiertos[eco_id]):
            idx = cubiertos[eco_id]
            idx = idx.intersection(eco_cand.index)
            if len(idx):
                ha_alc_s = _ha_columna(eco_cand.loc[idx], cid)
                ha_alcanzable_num = float(ha_alc_s.sum())
            else:
                ha_alcanzable_num = 0.0
        elif not cubiertos:
            # Fallback sin geoms
            ha_alcanzable_num = ha_seleccionada
        else:
            ha_alcanzable_num = 0.0

        pct_alc = (
            (ha_alcanzable_num / ha_candidatos)
            if ha_candidatos > 0
            else (0.0 if ha_alcanzable_num == 0 else float("nan"))
        )
        pct_abs = (ha_seleccionada / ha_matriz) if ha_matriz > 0 else float("nan")
        ratio = (ha_candidatos / ha_matriz) if ha_matriz > 0 else float("nan")

        if modo == "censo":
            objetivo = float(P.COBERTURA_OBJETIVO_CENSO)
        elif modo == "refuerzo":
            objetivo = float(P.COBERTURA_OBJETIVO_RARAS)
        else:
            objetivo = float("nan")

        if pd.isna(pct_alc):
            cumple = False
            estado = "vacia" if ha_alcanzable_num <= 0 else "parcial"
        elif ha_alcanzable_num <= 0:
            cumple = False
            estado = "vacia"
        elif not pd.isna(objetivo) and pct_alc + 1e-12 >= objetivo:
            cumple = True
            estado = "cubierta"
        elif not pd.isna(objetivo):
            cumple = False
            estado = "parcial"
        else:
            cumple = ha_alcanzable_num > 0
            estado = "cubierta" if ha_alcanzable_num > 0 else "vacia"

        n_rects = 0
        if not eco_sel.empty:
            try:
                n_rects = int(presencia_clase_por_ha(eco_sel, cid).sum())
            except ValueError:
                n_rects = int((ha_sel_s >= piso_presencia_ha(cid)).sum())

        filas.append(
            {
                "eco_id": eco_id,
                "class_id": cid,
                "class_name": CLASS_NAMES.get(cid, row.get("clase", str(cid))),
                "modo": modo,
                "presencia": row.get("presencia", ""),
                "ha_seleccionada": round(ha_seleccionada, 4),
                "ha_capturada_2x2": round(ha_alcanzable_num, 4),
                "ha_candidatos_2x2": round(ha_candidatos, 4),
                "ha_matriz_presencia": round(ha_matriz, 4),
                "pct_cubierto_alcanzable": round(pct_alc, 6) if pd.notna(pct_alc) else None,
                "pct_cubierto_absoluto": round(pct_abs, 6) if pd.notna(pct_abs) else None,
                "ratio_fuentes": round(ratio, 6) if pd.notna(ratio) else None,
                "objetivo": objetivo if pd.notna(objetivo) else None,
                "cumple_objetivo": bool(cumple) if modo in ("censo", "refuerzo") else None,
                "estado": estado,
                "n_rects_con_clase": n_rects,
            }
        )

    aud = pd.DataFrame(filas)
    ratio_df = aud[
        ["eco_id", "class_id", "class_name", "ha_candidatos_2x2", "ha_matriz_presencia", "ratio_fuentes"]
    ].copy()
    return aud, ratio_df
