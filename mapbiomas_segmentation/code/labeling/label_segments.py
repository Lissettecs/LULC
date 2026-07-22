#!/usr/bin/env python3
"""Label image segments with MapBiomas Collection 2 majority vote.

Phase 1 (calibration): SUBSET=True, TAU_PURITY=None → purity histogram + percentiles.
Phase 2 (verification): set TAU_PURITY → GPKG with ok/mixed/no_data audit fields.
Phase 3 (full tile): SUBSET=False, WRITE_RASTER=True if a label raster is needed.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from segmentation_labels import config as cfg  # noqa: E402
from segmentation_labels.assign import assign_labels, print_assignment_summary  # noqa: E402
from segmentation_labels.export_gpkg import export_labeled_gpkg  # noqa: E402
from segmentation_labels.io_rasters import load_raster_pair  # noqa: E402
from segmentation_labels.plot_purity import plot_purity_histogram  # noqa: E402
from segmentation_labels.stats import compute_segment_stats  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Assign C2 land-cover labels to segment polygons (auditable GPKG)."
    )
    p.add_argument("--segments-raster", type=Path, default=cfg.SEGMENTS_RASTER)
    p.add_argument("--c2-raster", type=Path, default=cfg.C2_RASTER)
    p.add_argument("--out-dir", type=Path, default=cfg.OUT_DIR)
    p.add_argument("--subset", action=argparse.BooleanOptionalAction, default=cfg.SUBSET)
    p.add_argument(
        "--subset-window",
        type=int,
        nargs=4,
        metavar=("COL", "ROW", "WIDTH", "HEIGHT"),
        default=cfg.SUBSET_WINDOW,
    )
    p.add_argument("--tau-purity", type=float, default=cfg.TAU_PURITY)
    p.add_argument("--kappa-coverage", type=float, default=cfg.KAPPA_COVERAGE)
    p.add_argument("--n-min-pixels", type=int, default=cfg.N_MIN_PIXELS)
    p.add_argument("--write-raster", action=argparse.BooleanOptionalAction, default=cfg.WRITE_RASTER)
    return p.parse_args()


def write_labels_raster(
    segments: np.ndarray,
    segment_ids: np.ndarray,
    label_final: np.ndarray,
    out_path: Path,
    *,
    transform: rasterio.Affine,
    crs: str,
    background_id: int,
    label_nodata: int,
    label_mixed: int,
    c2_classes: set[int],
) -> None:
    """Map segment_id → label_final and write an optional uint8 label GeoTIFF."""
    max_id = int(segment_ids.max())
    lut = np.full(max_id + 1, label_nodata, dtype=np.uint8)
    for seg_id, label in zip(segment_ids, label_final):
        lut[int(seg_id)] = np.uint8(label)

    out = np.zeros(segments.shape, dtype=np.uint8)
    foreground = segments != background_id
    out[foreground] = lut[segments[foreground].astype(np.int64)]

    allowed = set(c2_classes) | {label_nodata, label_mixed, background_id}
    unique = set(np.unique(out).tolist())
    assert unique.issubset(allowed), f"Unexpected output values: {unique - allowed}"

    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": segments.shape[0],
        "width": segments.shape[1],
        "transform": transform,
        "crs": crs,
        "nodata": background_id,
        "compress": "deflate",
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(out, 1)
    print(f"Saved label raster: {out_path}")


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stem = args.segments_raster.stem.replace("_labels", "")
    out_gpkg = out_dir / "segments_labeled.gpkg"
    out_hist = out_dir / "purity_hist.png"
    out_pct = out_dir / "purity_percentiles.json"
    out_summary = out_dir / "assignment_summary.json"
    out_tif = out_dir / "C2_labels.tif"

    print("=== segment labeling (MapBiomas C2) ===")
    print(f"segments: {args.segments_raster}")
    print(f"c2:       {args.c2_raster}")
    print(f"subset:   {args.subset} {args.subset_window if args.subset else ''}")

    pair = load_raster_pair(
        args.segments_raster,
        args.c2_raster,
        subset=args.subset,
        subset_window=tuple(args.subset_window) if args.subset_window else None,
    )

    stats = compute_segment_stats(
        pair.segments,
        pair.c2,
        cfg.C2_NODATA,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )
    print(f"segments: {stats.segment_ids.size} unique (excl. background)")

    if args.tau_purity is None:
        print("\n--- Phase 1: purity calibration ---")
        plot_purity_histogram(
            stats,
            out_hist,
            n_min_pixels=args.n_min_pixels,
            percentiles_json=out_pct,
        )
        print("Set TAU_PURITY in config (or --tau-purity) and re-run for phase 2.")
        return 0

    print(f"\n--- Phase 2/3: assign labels (tau={args.tau_purity}) ---")
    assignment = assign_labels(
        stats,
        tau_purity=args.tau_purity,
        kappa_coverage=args.kappa_coverage,
        n_min_pixels=args.n_min_pixels,
        label_mixed=cfg.LABEL_MIXED,
        label_nodata=cfg.LABEL_NODATA,
    )
    print("Assignment summary:")
    print_assignment_summary(assignment.reason)

    summary = {
        "segments_raster": str(args.segments_raster),
        "c2_raster": str(args.c2_raster),
        "subset": args.subset,
        "tau_purity": args.tau_purity,
        "kappa_coverage": args.kappa_coverage,
        "n_min_pixels": args.n_min_pixels,
        "n_segments": int(stats.segment_ids.size),
        "ok": int((assignment.reason == "ok").sum()),
        "mixed": int((assignment.reason == "mixed").sum()),
        "no_data": int((assignment.reason == "no_data").sum()),
    }
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved assignment summary: {out_summary}")

    export_labeled_gpkg(
        pair.segments,
        pair.transform,
        pair.crs,
        stats,
        out_gpkg,
        assignment=assignment,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )

    if args.write_raster:
        c2_classes = set(np.unique(pair.c2[~np.isin(pair.c2, cfg.C2_NODATA)]).tolist())
        write_labels_raster(
            pair.segments,
            stats.segment_ids,
            assignment.label_final,
            out_tif,
            transform=pair.transform,
            crs=pair.crs,
            background_id=cfg.BACKGROUND_SEGMENT_ID,
            label_nodata=cfg.LABEL_NODATA,
            label_mixed=cfg.LABEL_MIXED,
            c2_classes=c2_classes,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
