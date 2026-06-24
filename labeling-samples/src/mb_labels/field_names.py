#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nombres de campo canonicos (<=10 chars) para GeoPackage y Earth Engine."""

from __future__ import annotations

# ESRI Shapefile / ingestion GEE: maximo 10 caracteres por campo.
FIELD_RENAME: dict[str, str] = {
    "review_year": "rev_year",
    "review_rule": "rev_rule",
    "review_priority": "rev_prior",
    "review_tier": "rev_tier",
    "review_status": "rev_status",
    "review_notes": "rev_notes",
    "review_desc": "rev_desc",
    "n_review_years": "n_rev_yrs",
    "sample_type": "samp_type",
    "dim_temporal": "dim_temp",
    "dim_espacial": "dim_esp",
    "class_name": "class_nm",
    "es_transversal": "es_transv",
    "es_critica_n3": "es_crit_n3",
    "target_rare_class": "rare_class",
    "lulc_mode_id": "lulc_md_id",
    "lulc_mode_name": "lulc_name",
    "eco_dom_name": "eco_dom_nm",
    "source_raster": "src_raster",
    "rect_area_m2": "rect_a_m2",
    "transition_pct": "trans_pct",
    "stable_years": "stab_years",
    "max_stab_run": "max_stab",
    "ref_period": "ref_period",
    "ref_sensor": "ref_sensor",
    "fuente_plan": "fuente",
    "rectangle_qa": "rect_qa",
    "rectangle_note": "rect_note",
    "polygon_qa": "poly_qa",
    "polygon_note": "poly_note",
    "qa_scope": "qa_scope",
    "error_type": "err_type",
    "corrected_class_id": "corr_id",
    "label_id": "lbl_id",
    "coverage_rect_pct": "cov_rect",
    "qa_version": "qa_ver",
    "qa_user": "qa_user",
    "qa_date": "qa_date",
    "poly_uid": "poly_uid",
}

DISSOLVE_KEYS = ("grid_id", "rev_year", "class_id")
PLAN_META_SKIP = frozenset({"review_years", "label_group", "grid_id", "review_year"})


def rect_plan_attrs(rect_row) -> dict:
    """Metadatos del plan de muestreo con nombres canonicos (<=10 chars)."""
    attrs: dict = {}
    for key, val in rect_row.items():
        if key in PLAN_META_SKIP:
            continue
        attrs[canonical_field_name(str(key))] = val
    return attrs


def class_attrs(class_id: int) -> dict:
    from mb_labels.taxonomy import lookup_taxonomy

    return rename_field_dict(lookup_taxonomy(class_id))


def canonical_field_name(name: str) -> str:
    if name in FIELD_RENAME:
        return FIELD_RENAME[name]
    if len(name) <= 10:
        return name
    short = name[:10]
    if short not in FIELD_RENAME.values():
        return short
    return name[:8] + "_x"


def rename_field_dict(record: dict) -> dict:
    return {canonical_field_name(k): v for k, v in record.items()}


def rename_geodataframe_columns(gdf):
    rename = {
        col: canonical_field_name(col)
        for col in gdf.columns
        if col != "geometry" and canonical_field_name(col) != col
    }
    if rename:
        gdf = gdf.rename(columns=rename)
    long_cols = [c for c in gdf.columns if c != "geometry" and len(c) > 10]
    if long_cols:
        raise ValueError(
            "Columnas demasiado largas para export GEE (max 10 chars): "
            + ", ".join(sorted(long_cols))
        )
    return gdf
