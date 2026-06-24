#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Campos y utilidades de QA para revision de poligonos SSL4EO."""

from __future__ import annotations

import pandas as pd

from mb_labels.taxonomy import NIVEL3_CLASS_IDS

QA_SCHEMA_VERSION = "1"

# Nombres canonicos (<=10 chars) para GeoPackage y Earth Engine.
QA_POLYGON_FIELDS: tuple[str, ...] = (
    "poly_uid",
    "poly_qa",
    "qa_scope",
    "corr_id",
    "err_type",
    "poly_note",
    "qa_user",
    "qa_date",
    "lbl_id",
    "cov_rect",
    "qa_ver",
)

QA_RECT_FIELDS: tuple[str, ...] = (
    "rect_qa",
    "rect_note",
)

POLY_QA_VALUES = frozenset({"", "aprobado", "rechazado"})
RECT_QA_VALUES = frozenset({"pendiente", "aprobado", "rechazado", "parcial"})
QA_SCOPE_VALUES = frozenset({"auto", "poligono", "clase"})
ERR_TYPE_VALUES = frozenset({"ninguno", "clase", "borde", "sombra", "agua", "nube", "otro"})

COV_TARGET_TIER = {0: 100.0, 1: 85.0, 2: 90.0, 3: 95.0}
DEFAULT_COV_TARGET = 90.0


def make_poly_uid(grid_id, rev_year, class_id, patch_id) -> str:
    return f"{grid_id}|{int(rev_year)}|{int(class_id)}|{int(patch_id)}"


def _empty_str_series(index) -> pd.Series:
    return pd.Series([""] * len(index), index=index, dtype="object")


def _resolve_rev_year_col(gdf) -> str:
    if "rev_year" in gdf.columns:
        return "rev_year"
    if "review_year" in gdf.columns:
        return "review_year"
    raise ValueError("Falta columna rev_year o review_year")


def ensure_poly_uid(gdf) -> pd.DataFrame:
    yr_col = _resolve_rev_year_col(gdf)
    if "poly_uid" in gdf.columns and gdf["poly_uid"].astype(str).str.len().gt(0).all():
        return gdf
    patch = gdf["patch_id"] if "patch_id" in gdf.columns else 1
    gdf = gdf.copy()
    gdf["poly_uid"] = [
        make_poly_uid(g, y, c, p)
        for g, y, c, p in zip(
            gdf["grid_id"].astype(str),
            gdf[yr_col].astype(int),
            gdf["class_id"].astype(int),
            patch.astype(int),
        )
    ]
    return gdf


def init_qa_defaults(gdf) -> pd.DataFrame:
    """Inicializa campos QA vacios en un GeoDataFrame de poligonos."""
    gdf = ensure_poly_uid(gdf)
    gdf = gdf.copy()
    defaults: dict[str, object] = {
        "poly_qa": "",
        "qa_scope": "auto",
        "corr_id": -9999,
        "err_type": "ninguno",
        "poly_note": "",
        "qa_user": "",
        "qa_date": "",
        "lbl_id": -9999,
        "cov_rect": 0.0,
        "qa_ver": QA_SCHEMA_VERSION,
        "rect_qa": "pendiente",
        "rect_note": "",
    }
    for col, val in defaults.items():
        if col not in gdf.columns:
            if isinstance(val, float):
                gdf[col] = float(val)
            elif isinstance(val, int):
                gdf[col] = int(val)
            else:
                gdf[col] = _empty_str_series(gdf.index) if val == "" else val
    gdf["lbl_id"] = compute_lbl_id(gdf)
    gdf["cov_rect"] = compute_cov_rect(gdf)
    return gdf


def compute_lbl_id(gdf) -> pd.Series:
    corr = pd.to_numeric(gdf.get("corr_id", -9999), errors="coerce").fillna(-9999).astype(int)
    cls = pd.to_numeric(gdf["class_id"], errors="coerce").fillna(-9999).astype(int)
    return corr.where((corr > 0) & (corr != -9999), cls)


def compute_cov_rect(gdf) -> pd.Series:
    """Porcentaje del area del rectangulo-año con poly_qa=aprobado."""
    yr_col = _resolve_rev_year_col(gdf)
    gdf = gdf.copy()
    gdf["_rect_key"] = gdf["grid_id"].astype(str) + "|" + gdf[yr_col].astype(str)
    area = pd.to_numeric(gdf["area_ha"], errors="coerce").fillna(0.0)
    approved = area.where(gdf.get("poly_qa", "").astype(str) == "aprobado", 0.0)
    totals = gdf.groupby("_rect_key")["area_ha"].transform(
        lambda s: pd.to_numeric(s, errors="coerce").fillna(0.0).sum()
    )
    approved_sum = approved.groupby(gdf["_rect_key"]).transform("sum")
    cov = (approved_sum / totals.replace(0, pd.NA) * 100.0).fillna(0.0)
    gdf.drop(columns=["_rect_key"], inplace=True)
    return cov.round(2)


def cov_target_for_tier(rev_tier) -> float:
    try:
        tier = int(float(rev_tier))
    except (TypeError, ValueError):
        tier = 2
    return COV_TARGET_TIER.get(tier, DEFAULT_COV_TARGET)


def is_valid_class_id(class_id) -> bool:
    try:
        return int(class_id) in NIVEL3_CLASS_IDS
    except (TypeError, ValueError):
        return False


def validate_gdf(gdf) -> tuple[bool, list[str]]:
    """Valida esquema QA, lbl_id y cobertura por rectangulo-año."""
    errors: list[str] = []
    warnings: list[str] = []
    yr = _resolve_rev_year_col(gdf)

    required = {
        "poly_uid", "grid_id", yr, "class_id", "area_ha", "split",
        "poly_qa", "rect_qa", "lbl_id", "cov_rect",
    }
    missing = required - set(gdf.columns)
    if missing:
        errors.append(f"Faltan columnas: {sorted(missing)}")
        return False, errors

    if gdf["poly_uid"].duplicated().any():
        n = int(gdf["poly_uid"].duplicated().sum())
        errors.append(f"poly_uid duplicados: {n}")

    invalid_poly_qa = ~gdf["poly_qa"].astype(str).isin(POLY_QA_VALUES)
    if invalid_poly_qa.any():
        vals = sorted(gdf.loc[invalid_poly_qa, "poly_qa"].astype(str).unique())
        errors.append(f"poly_qa invalidos: {vals}")

    invalid_rect = ~gdf["rect_qa"].astype(str).isin(RECT_QA_VALUES)
    if invalid_rect.any():
        vals = sorted(gdf.loc[invalid_rect, "rect_qa"].astype(str).unique())
        errors.append(f"rect_qa invalidos: {vals}")

    approved = gdf[gdf["poly_qa"].astype(str) == "aprobado"]
    if not approved.empty:
        bad_lbl = approved[~approved["lbl_id"].apply(is_valid_class_id)]
        if not bad_lbl.empty:
            errors.append(f"lbl_id invalido en {len(bad_lbl)} poligonos aprobados")

        corr = pd.to_numeric(approved.get("corr_id", -9999), errors="coerce").fillna(-9999)
        has_corr = (corr > 0) & (corr != -9999)
        if has_corr.any():
            mismatch = approved[has_corr & (approved["lbl_id"].astype(int) != corr.astype(int))]
            if not mismatch.empty:
                errors.append(f"lbl_id no coincide con corr_id en {len(mismatch)} filas")

    gdf = gdf.copy()
    gdf["_rect_key"] = gdf["grid_id"].astype(str) + "|" + gdf[yr].astype(str)
    for rect_key, sub in gdf.groupby("_rect_key"):
        splits = sub["split"].astype(str).unique()
        if len(splits) > 1:
            errors.append(f"split inconsistente en {rect_key}: {list(splits)}")

        rect_qa = str(sub["rect_qa"].iloc[0])
        if rect_qa not in {"aprobado", "parcial"}:
            continue

        area = pd.to_numeric(sub["area_ha"], errors="coerce").fillna(0.0)
        total = float(area.sum())
        approved_area = float(area[sub["poly_qa"].astype(str) == "aprobado"].sum())
        cov = (approved_area / total * 100.0) if total > 0 else 0.0
        tier = sub["rev_tier"].iloc[0] if "rev_tier" in sub.columns else 2
        target = cov_target_for_tier(tier)
        if cov < target:
            warnings.append(
                f"{rect_key}: cov_rect={cov:.1f}% < meta {target:.0f}% (tier {tier}, rect_qa={rect_qa})"
            )

    msgs = errors + [f"ADVERTENCIA: {w}" for w in warnings]
    return len(errors) == 0, msgs
