#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fusiona borrador QA (JSON) con GeoPackage base y publica version en GEE."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC = REPO_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from mb_labels.gee_export import DEFAULT_EE_PROJECT, export_gdf_to_asset  # noqa: E402
from mb_labels.qa_fields import compute_cov_rect, compute_lbl_id, validate_gdf  # noqa: E402

DEFAULT_BASE = Path("/home/lserey/mapbiomas_land/prod/labels/annual/annual_samples.gpkg")
DEFAULT_LAYER = "annual_samples"
DEFAULT_ASSET_BASE = (
    "projects/mapbiomas-chile/assets/LULC/COLLECTION-03/SAMPLES/SAMPLES_COL3/SAMPLES_LABELS_SSL4EO"
)
LOG_PATH = Path("/home/lserey/mapbiomas_land/prod/labels/annual/qa_export_log.csv")

QA_EDIT_KEYS = (
    "poly_qa", "qa_scope", "corr_id", "err_type", "poly_note",
    "qa_user", "qa_date", "rect_qa", "rect_note", "lbl_id", "cov_rect", "qa_ver",
)


def parse_args():
    p = argparse.ArgumentParser(description="Publica version QA fusionando borrador JSON con GPKG base.")
    p.add_argument("--base-gpkg", type=Path, default=DEFAULT_BASE)
    p.add_argument("--layer", default=DEFAULT_LAYER)
    p.add_argument("--draft-json", type=Path, required=True, help="Borrador QA exportado desde la app GEE.")
    p.add_argument("--version", required=True, help="Sufijo de version, ej. v1 -> annual_samples_v1")
    p.add_argument("--asset-base", default=DEFAULT_ASSET_BASE)
    p.add_argument("--output-gpkg", type=Path, default=None)
    p.add_argument("--gee-project", default=DEFAULT_EE_PROJECT)
    p.add_argument("--skip-validation", action="store_true")
    p.add_argument("--no-gee", action="store_true")
    p.add_argument("--wait", action="store_true")
    p.add_argument("--overwrite", action="store_true")
    return p.parse_args()


def load_draft(path: Path) -> tuple[dict[str, dict], dict[str, dict]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "edits" in data:
        edits = {str(k): v for k, v in data["edits"].items()}
        rect_edits = {str(k): v for k, v in (data.get("rect_edits") or {}).items()}
        return edits, rect_edits
    if isinstance(data, dict):
        return {str(k): v for k, v in data.items()}, {}
    raise ValueError("Formato JSON no reconocido; esperado {edits: {poly_uid: {...}}}")


function apply_edits(gdf: gpd.GeoDataFrame, edits: dict[str, dict], rect_edits: dict[str, dict] | None = None) -> gpd.GeoDataFrame:
    gdf = gdf.copy()
    yr_col = "rev_year" if "rev_year" in gdf.columns else "review_year"
    for uid, props in edits.items():
        mask = gdf["poly_uid"].astype(str) == str(uid)
        if not mask.any():
            continue
        for key in QA_EDIT_KEYS:
            if key in props:
                gdf.loc[mask, key] = props[key]
    if rect_edits:
        for rect_key, props in rect_edits.items():
            mask = (gdf["grid_id"].astype(str) + "|" + gdf[yr_col].astype(str)) == str(rect_key)
            if not mask.any():
                continue
            for key in ("rect_qa", "rect_note", "qa_user", "qa_date"):
                if key in props:
                    gdf.loc[mask, key] = props[key]
            if props.get("rect_qa") == "rechazado":
                gdf.loc[mask, "poly_qa"] = "rechazado"
                gdf.loc[mask, "qa_scope"] = "auto"
                gdf.loc[mask, "err_type"] = "clase"
    gdf["lbl_id"] = compute_lbl_id(gdf)
    gdf["cov_rect"] = compute_cov_rect(gdf)
    return gdf


def append_log(version: str, user: str, n_polys: int, n_edits: int, asset_id: str, gpkg: Path) -> None:
    row = {
        "version": version,
        "qa_user": user,
        "qa_date": date.today().isoformat(),
        "n_polys": n_polys,
        "n_edits": n_edits,
        "asset_id": asset_id,
        "gpkg": str(gpkg),
    }
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    if LOG_PATH.exists():
        log = pd.read_csv(LOG_PATH)
        log = pd.concat([log, pd.DataFrame([row])], ignore_index=True)
    else:
        log = pd.DataFrame([row])
    log.to_csv(LOG_PATH, index=False, encoding="utf-8-sig")


def main() -> int:
    args = parse_args()
    edits, rect_edits = load_draft(args.draft_json)
    print(f"Borrador: {len(edits)} poligonos editados, {len(rect_edits)} rect-año")

    gdf = gpd.read_file(args.base_gpkg, layer=args.layer)
    merged = apply_edits(gdf, edits, rect_edits)

    if not args.skip_validation:
        ok, msgs = validate_gdf(merged)
        for m in msgs:
            print(m)
        if not ok:
            print("Validacion fallida.")
            return 1

    version_name = f"annual_samples_{args.version}" if not args.version.startswith("annual") else args.version
    out_gpkg = args.output_gpkg or args.base_gpkg.parent / f"{version_name}.gpkg"
    if out_gpkg.exists() and not args.overwrite:
        raise FileExistsError(f"Ya existe {out_gpkg}; use --overwrite")

    merged.to_file(out_gpkg, layer=version_name, driver="GPKG")
    print(f"GPKG: {out_gpkg} [{version_name}] ({len(merged)} features)")

    asset_id = f"{args.asset_base.rstrip('/')}/{version_name}"
    geojson = out_gpkg.with_suffix(".geojson")
    if not args.no_gee:
        export_gdf_to_asset(
            merged,
            asset_id,
            project=args.gee_project,
            local_geojson=geojson,
            overwrite=args.overwrite,
            wait=args.wait,
        )
        print(f"Asset GEE: {asset_id}")

    meta = json.loads(args.draft_json.read_text(encoding="utf-8"))
    user = str(meta.get("qa_user", "")) if isinstance(meta, dict) else ""
    append_log(args.version, user, len(merged), len(edits), asset_id if not args.no_gee else "", out_gpkg)
    print(f"Log: {LOG_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
