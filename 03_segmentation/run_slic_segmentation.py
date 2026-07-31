#!/usr/bin/env python3
"""
SLIC (s=50, σ=0.1) + RAG p10 segmentation on SSL4EO rectangles for a given rev_year1.

Inputs:
  - Selection GeoPackage (UTM18 / UTM19) with revision plan.
  - Masked SBAND-184B mosaic per MGRS tile (`mask_mosaic_{year}/`).

Outputs per rectangle:
  - Label GeoTIFF (segment_id, 0 = nodata/mask)
  - GeoPackage polygons with spectral signature and intra-segment variation
  - summary.json

Examples:
  python run_slic_segmentation.py --test-tile 18GXA
  python run_slic_segmentation.py --rev-year 2015 --require-mosaic --skip-existing
  python run_slic_segmentation.py --rev-year 2009 --year 2009 --require-mosaic
"""


from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio.features import geometry_mask, geometry_window, shapes
from rasterio.mask import mask
from rasterio.windows import Window
from shapely.geometry import shape
from skimage.measure import label as cc_label
from skimage.segmentation import slic

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.bands_184b import SEGMENTATION_BANDS, SIGNATURE_BANDS
from config.run_refs import GPKG_UTM18, GPKG_UTM19
from config.params_slic import (
    BUFFER_PX,
    MOSAIC_NODATA,
    OUTPUT_NODATA,
    PIXEL_AREA_HA,
    RAG_PERCENTILE,
    SLIC_COMPACTNESS,
    SLIC_SCALE,
    SLIC_SIGMA,
)
from config.paths import mosaic_root, output_dir, masked_mosaic_path
from rag import merge_rag_threshold
from rectangles import build_plan, filter_plan, save_plan, iter_plan_rows


def load_bands() -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    return list(SEGMENTATION_BANDS), list(SIGNATURE_BANDS)


def _mosaic_or_raise(mosaic_root_dir: Path, tile: str, year: int) -> Path:
    path = masked_mosaic_path(mosaic_root_dir, tile, year)
    if path is None or not path.is_file():
        raise FileNotFoundError(
            f"No masked mosaic for tile {tile} year={year} in {mosaic_root_dir}"
        )
    return path


def _rectangle_window(src: rasterio.io.DatasetReader, geom) -> Window:
    win = geometry_window(src, [geom], pad_x=0, pad_y=0)
    return win.round_offsets().round_lengths()


def _buffer_window(
    win: Window,
    buffer_px: int,
    raster_w: int,
    raster_h: int,
) -> tuple[Window, dict[str, int]]:
    col_off = int(win.col_off)
    row_off = int(win.row_off)
    width = int(win.width)
    height = int(win.height)
    col0 = max(0, col_off - buffer_px)
    row0 = max(0, row_off - buffer_px)
    col1 = min(raster_w, col_off + width + buffer_px)
    row1 = min(raster_h, row_off + height + buffer_px)
    effective = {
        "left": col_off - col0,
        "right": col1 - (col_off + width),
        "top": row_off - row0,
        "bottom": row1 - (row_off + height),
    }
    return Window(col0, row0, col1 - col0, row1 - row0), effective


def _crop_center(arr: np.ndarray, buffer_effective: dict[str, int]) -> np.ndarray:
    t = buffer_effective
    row0 = t["top"]
    row1 = arr.shape[0] - t["bottom"] if t["bottom"] else arr.shape[0]
    col0 = t["left"]
    col1 = arr.shape[1] - t["right"] if t["right"] else arr.shape[1]
    return arr[row0:row1, col0:col1].copy()


def _relabel_connected_components(labels: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out = np.zeros_like(labels, dtype=np.int32)
    fg = (labels > 0) & valid
    if not fg.any():
        return out
    next_id = 1
    for seg_id in np.unique(labels[fg]):
        mask_seg = (labels == seg_id) & fg
        cc = cc_label(mask_seg, connectivity=2)
        cc_pos = cc > 0
        if not cc_pos.any():
            continue
        cc[cc_pos] += next_id - 1
        out[mask_seg] = cc[mask_seg]
        next_id = int(out.max()) + 1
    return out


def _read_bands_window(
    src: rasterio.io.DatasetReader,
    window: Window,
    band_indices: list[int],
) -> np.ndarray:
    return np.stack(
        [src.read(i, window=window).astype(np.float32) for i in band_indices],
        axis=-1,
    )


def _read_expanded_window(
    src: rasterio.io.DatasetReader,
    geom,
    band_indices: list[int],
    buffer_px: int,
) -> tuple[np.ndarray, np.ndarray, Window, dict[str, int], rasterio.Affine]:
    """Read mosaic with perimeter buffer; return arrays before cropping to the rectangle."""
    win_rect = _rectangle_window(src, geom)
    win_buf, buffer_effective = _buffer_window(
        win_rect, buffer_px, src.width, src.height
    )
    stack_buf = _read_bands_window(src, win_buf, band_indices)
    valid_buf = np.all(np.isfinite(stack_buf), axis=-1) & (
        stack_buf != MOSAIC_NODATA
    ).all(axis=-1)
    transform_rect = src.window_transform(win_rect)
    return stack_buf, valid_buf, win_rect, buffer_effective, transform_rect


def _finalize_rectangle_crop(
    labels_buf: np.ndarray,
    valid_buf: np.ndarray,
    buffer_effective: dict[str, int],
    geom,
    transform_rect: rasterio.Affine,
) -> tuple[np.ndarray, np.ndarray]:
    labels = _crop_center(labels_buf, buffer_effective)
    valid = _crop_center(valid_buf.astype(np.int8), buffer_effective).astype(bool)
    inside = geometry_mask(
        [geom],
        out_shape=labels.shape[:2],
        transform=transform_rect,
        invert=True,
    )
    valid &= inside
    labels[~valid] = 0
    return _relabel_connected_components(labels, valid), valid


def _read_bands(
    src: rasterio.io.DatasetReader,
    geom,
    band_indices: list[int],
) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return (H,W,C) array, valid mask, and window metadata."""
    out_image, out_transform = mask(src, [geom], crop=True, filled=True, nodata=MOSAIC_NODATA)
    stack = np.stack([out_image[i - 1].astype(np.float32) for i in band_indices], axis=-1)
    valid = np.all(np.isfinite(stack), axis=-1) & (stack != MOSAIC_NODATA).all(axis=-1)
    meta = {
        "transform": out_transform,
        "width": stack.shape[1],
        "height": stack.shape[0],
        "crs": src.crs.to_string(),
    }
    return stack, valid, meta


def _prepare_slic_image(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    out_arr = feats.astype(np.float32, copy=True)
    for c in range(out_arr.shape[-1]):
        band = out_arr[..., c]
        if np.any(valid):
            median = float(np.median(band[valid]))
        else:
            median = 0.0
        band[~valid] = median
        out_arr[..., c] = band
    return out_arr


def run_slic(feats: np.ndarray, valid: np.ndarray) -> np.ndarray:
    n_valid = int(valid.sum())
    n_segments = max(2, n_valid // SLIC_SCALE)
    img = _preparar_imagen_slic(feats, valid)
    labels = slic(
        img,
        n_segments=n_segments,
        compactness=SLIC_COMPACTNESS,
        sigma=SLIC_SIGMA,
        channel_axis=-1,
        enforce_connectivity=True,
        start_label=1,
    ).astype(np.int32)
    labels[~valid] = 0
    return labels


def segment_statistics(
    labels: np.ndarray,
    valid: np.ndarray,
    firma: np.ndarray,
    sig_names: list[str],
) -> pd.DataFrame:
    """Per-band means and intra-segment variation (mean spatial std per band)."""
    ids = labels[valid]
    pix = firma[valid]
    if ids.size == 0:
        return pd.DataFrame()

    uniq, inv = np.unique(ids, return_inverse=True)
    n_seg = len(uniq)
    n_bands = pix.shape[1]

    # Per-segment band means
    sums = np.zeros((n_seg, n_bands), dtype=np.float64)
    counts = np.zeros(n_seg, dtype=np.int64)
    np.add.at(sums, inv, pix)
    np.add.at(counts, inv, 1)
    means = sums / np.maximum(counts, 1)[:, None]

    # Spatial std per band (intra-segment variation)
    sumsq = np.zeros((n_seg, n_bands), dtype=np.float64)
    np.add.at(sumsq, inv, pix * pix)
    var = np.maximum(sumsq / np.maximum(counts, 1)[:, None] - means**2, 0.0)
    std_per_band = np.sqrt(var)
    variacion = std_per_band.mean(axis=1)

    rows = []
    for i, seg_id in enumerate(uniq):
        row = {
            "segment_id": int(seg_id),
            "n_pixels": int(counts[i]),
            "area_ha": round(counts[i] * PIXEL_AREA_HA, 4),
            "variacion_espectral": round(float(variacion[i]), 6),
        }
        for j, name in enumerate(sig_names):
            row[f"mean_{name}"] = round(float(means[i, j]), 6)
            row[f"std_{name}"] = round(float(std_per_band[i, j]), 6)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("segment_id").reset_index(drop=True)


def labels_to_polygons(
    labels: np.ndarray,
    transform,
    crs: str,
    stats: pd.DataFrame,
    grid_id: str,
) -> gpd.GeoDataFrame:
    if stats.empty:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs)

    stats_idx = stats.set_index("segment_id")
    geoms = []
    seg_ids = []
    for geom, val in shapes(labels.astype(np.int32), mask=labels > 0, transform=transform):
        seg_id = int(val)
        if seg_id == 0 or seg_id not in stats_idx.index:
            continue
        geoms.append(shape(geom))
        seg_ids.append(seg_id)

    if not geoms:
        return gpd.GeoDataFrame(columns=["geometry"], crs=crs)

    gdf = gpd.GeoDataFrame({"segment_id": seg_ids, "geometry": geoms}, crs=crs)
    gdf = gdf.merge(stats, on="segment_id", how="left")
    gdf.insert(0, "grid_id", grid_id)
    return gdf


def process_rectangle(
    row: pd.Series,
    mosaic_root: Path,
    year: int,
    out_dir: Path,
    seg_bands: list[tuple[str, int]],
    sig_bands: list[tuple[str, int]],
    buffer_px: int = BUFFER_PX,
) -> dict:
    grid_id = row["grid_id"]
    tile = row["_tile"]
    mosaic_path = _mosaic_or_raise(mosaic_root, tile, year)

    idx_seg = [i for _, i in seg_bands]
    idx_firma = [i for _, i in sig_bands]
    sig_names = [n for n, _ in sig_bands]
    idx_all = sorted(set(idx_seg + idx_firma))

    rect_dir = out_dir / tile / grid_id
    rect_dir.mkdir(parents=True, exist_ok=True)

    with rasterio.open(mosaic_path) as src:
        if buffer_px > 0:
            feats_buf, valid_buf, _, buffer_effective, transform_rect = _read_expanded_window(
                src, row.geometry, idx_seg, buffer_px
            )
            stack_all_buf, valid2_buf, _, _, _ = _read_expanded_window(
                src, row.geometry, idx_all, buffer_px
            )
            valid_buf &= valid2_buf

            labels_slic_buf = run_slic(feats_buf, valid_buf)
            labels_buf, rag_stats = merge_rag_threshold(
                labels_slic_buf, feats_buf, valid_buf, RAG_PERCENTILE
            )
            labels, valid = _finalizar_recorte_rectangulo(
                labels_buf, valid_buf, buffer_effective, row.geometry, transform_rect
            )
            pos = {idx: j for j, idx in enumerate(idx_all)}
            firma = _crop_center(
                np.stack([stack_all_buf[..., pos[i]] for i in idx_firma], axis=-1),
                buffer_effective,
            )
            meta = {
                "transform": transform_rect,
                "width": labels.shape[1],
                "height": labels.shape[0],
                "crs": src.crs.to_string(),
            }
        else:
            feats_seg, valid, meta = _read_bands(src, row.geometry, idx_seg)
            stack_all, valid2, _ = _read_bands(src, row.geometry, idx_all)
            if not np.array_equal(valid, valid2):
                valid = valid & valid2
            pos = {idx: j for j, idx in enumerate(idx_all)}
            firma = np.stack([stack_all[..., pos[i]] for i in idx_firma], axis=-1)
            labels_slic = run_slic(feats_seg, valid)
            labels, rag_stats = merge_rag_threshold(labels_slic, feats_seg, valid, RAG_PERCENTILE)
            buffer_effective = {"left": 0, "right": 0, "top": 0, "bottom": 0}

    if valid.sum() < SLIC_SCALE:
        raise ValueError(f"{grid_id}: insufficient valid pixels ({int(valid.sum())})")
    stats = segment_statistics(labels, valid, firma, sig_names)

    label_path = rect_dir / f"{grid_id}_slic_ragp10_s{SLIC_SCALE}_sig{SLIC_SIGMA:.1f}_labels.tif"
    profile = {
        "driver": "GTiff",
        "dtype": "int32",
        "count": 1,
        "width": meta["width"],
        "height": meta["height"],
        "crs": meta["crs"],
        "transform": meta["transform"],
        "nodata": 0,
        "compress": "deflate",
    }
    out_labels = labels.copy()
    out_labels[~valid] = 0
    with rasterio.open(label_path, "w", **profile) as dst:
        dst.write(out_labels, 1)

    gpkg_path = rect_dir / f"{grid_id}_slic_ragp10_segments.gpkg"
    gdf_seg = labels_to_polygons(labels, meta["transform"], meta["crs"], stats, grid_id)
    if not gdf_seg.empty:
        gdf_seg.to_file(gpkg_path, driver="GPKG")

    summary = {
        "grid_id": grid_id,
        "tile": tile,
        "rev_year1": int(row["rev_year1"]),
        "rev_role1": str(row.get("rev_role1", "")),
        "mosaic_path": str(mosaic_path),
        "n_pixels_valid": int(valid.sum()),
        "n_segments": int(len(stats)),
        "n_segments_slic": rag_stats["n_segments_slic"],
        "n_segments_rag": rag_stats["n_segments_rag"],
        "rag_percentil": rag_stats["rag_percentil"],
        "rag_threshold": rag_stats["rag_threshold"],
        "rag_reduction_pct": rag_stats["rag_reduction_pct"],
        "slic_scale": SLIC_SCALE,
        "slic_sigma": SLIC_SIGMA,
        "buffer_px": buffer_px,
        "buffer_effective_px": buffer_effective,
        "rag_mode": "threshold",
        "bands_segmentation": [n for n, _ in seg_bands],
        "bands_signature": sig_names,
        "label_raster": str(label_path),
        "segments_gpkg": str(gpkg_path) if not gdf_seg.empty else None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    summary_path = rect_dir / f"{grid_id}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="SLIC s50 σ0.1 on SSL4EO rectangles (rev_year1).")
    p.add_argument("--gpkg-utm18", type=Path, default=GPKG_UTM18)
    p.add_argument("--gpkg-utm19", type=Path, default=GPKG_UTM19)
    p.add_argument("--rev-year", type=int, default=2015, help="Filter rev_year1 in selection GPKG")
    p.add_argument(
        "--year",
        type=int,
        default=None,
        help="Masked mosaic year (default: same as --rev-year)",
    )
    p.add_argument(
        "--mosaic-root",
        type=Path,
        default=None,
        help="Mosaic root (default: tmp/mask_mosaic_{year})",
    )
    p.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output root (default: prod/segmentacion_slic_rev{rev-year})",
    )
    p.add_argument("--test-tile", type=str, default=None, help="Only rectangles in this MGRS tile")
    p.add_argument("--grid-id", type=str, default=None, help="Single rectangle")
    p.add_argument(
        "--require-mosaic",
        action="store_true",
        help="Skip rectangles without masked mosaic for tile/year",
    )
    p.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip rectangles with existing summary.json",
    )
    p.add_argument(
        "--force",
        action="store_true",
        help="Reprocess even if summary exists (ignores --skip-existing)",
    )
    p.add_argument("--dry-run", action="store_true", help="Plan only; do not segment")
    p.add_argument("--limit", type=int, default=None, help="Maximum rectangles to process")
    p.add_argument(
        "--export-plan",
        type=Path,
        default=None,
        help="Export plan JSON before segmenting",
    )
    p.add_argument(
        "--buffer-px",
        type=int,
        default=BUFFER_PX,
        help="Perimeter buffer in pixels before SLIC (0 = none)",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    year = args.year if args.year is not None else args.rev_year
    mroot = args.mosaic_root or mosaic_root(year)
    out = args.output_dir or output_dir(args.rev_year)
    skip_existing = args.skip_existing and not args.force

    plan = build_plan(
        rev_year=args.rev_year,
        year=year,
        mosaic_root_dir=mroot,
        output_root=out,
        gpkg_utm18=args.gpkg_utm18,
        gpkg_utm19=args.gpkg_utm19,
        test_tile=args.test_tile,
        grid_id=args.grid_id,
    )

    res = plan.summary()
    to_process = filter_plan(
        plan,
        require_mosaic=args.require_mosaic,
        skip_existing=skip_existing,
    )
    print(f"Plan rev_year1={args.rev_year} · mosaic year={year}")
    print(f"  Total: {res['n_total']} · mosaic OK: {res['n_mosaic_ok']} · "
          f"already done: {res['n_already_processed']} · to process: {len(to_process)}")
    if res["tiles_missing_mosaic"]:
        print(f"  Tiles missing mosaic: {', '.join(res['tiles_missing_mosaic'])}")

    plan_path = args.export_plan or (out / f"plan_rev{args.rev_year}.json")
    save_plan(plan, plan_path)
    print(f"  Plan → {plan_path}")

    if args.dry_run:
        print("Dry-run: no rectangles segmented.")
        return 0

    if args.limit is not None:
        to_process = to_process[: args.limit]

    if not to_process:
        print("Nothing to process.")
        return 0

    seg_bands, sig_bands = load_bands()
    ids = {r.grid_id for r in to_process}
    groups = iter_plan_rows(plan)
    groups = [gdf[gdf["grid_id"].isin(ids)] for gdf in groups]
    groups = [g for g in groups if not g.empty]

    out.mkdir(parents=True, exist_ok=True)
    print(f"Segmenting {sum(len(g) for g in groups)} rectangle(s)…")

    results = []
    errors = []
    skipped = res["n_already_processed"] if skip_existing else 0
    for gdf in groups:
        for _, row in gdf.iterrows():
            gid = row["grid_id"]
            try:
                print(f"  → {gid} (tile {row['_tile']})…", flush=True)
                rect_result = process_rectangle(
                    row,
                    mroot,
                    year,
                    out,
                    seg_bands,
                    sig_bands,
                    buffer_px=args.buffer_px,
                )
                print(f"     OK: {rect_result['n_segments']} segments", flush=True)
                results.append(rect_result)
            except Exception as exc:
                print(f"     ERROR: {exc}", flush=True)
                errors.append({"grid_id": gid, "error": str(exc)})

    run_summary = {
        "rev_year": args.rev_year,
        "year": year,
        "n_ok": len(results),
        "n_error": len(errors),
        "n_skipped_existing": skipped,
        "mosaic_root": str(mroot),
        "output_dir": str(out),
        "plan_path": str(plan_path),
        "require_mosaic": args.require_mosaic,
        "skip_existing": skip_existing,
        "results": results,
        "errors": errors,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    run_path = out / f"run_summary_rev{args.rev_year}.json"
    run_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSummary: {len(results)} OK · {len(errors)} errors · "
          f"{skipped} skipped → {run_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
