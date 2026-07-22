#!/usr/bin/env python3
"""Label segments with C2 (purity threshold) and merge adjacent same-class regions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from segmentation_labels import config as cfg  # noqa: E402
from segmentation_labels.assign import assign_labels, print_assignment_summary  # noqa: E402
from segmentation_labels.export_gpkg import export_labeled_gpkg  # noqa: E402
from segmentation_labels.io_rasters import load_raster_pair  # noqa: E402
from segmentation_labels.merge_same_class import (  # noqa: E402
    export_merged_class_raster,
    export_merged_gpkg,
    merge_labeled_segments,
    print_merge_summary,
    summarize_merge,
)
from segmentation_labels.stats import compute_segment_stats  # noqa: E402


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="C2 labeling with purity threshold + merge adjacent same-class polygons."
    )
    p.add_argument("--segments-raster", type=Path, required=True)
    p.add_argument("--c2-raster", type=Path, required=True)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--tau-purity", type=float, default=0.95)
    p.add_argument("--kappa-coverage", type=float, default=cfg.KAPPA_COVERAGE)
    p.add_argument("--n-min-pixels", type=int, default=cfg.N_MIN_PIXELS)
    p.add_argument("--no-merge", action="store_true", help="Skip adjacent same-class merge")
    p.add_argument("--write-raster", action="store_true", help="Write merged class GeoTIFF")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== label + merge (MapBiomas C2) ===")
    print(f"segments: {args.segments_raster}")
    print(f"c2:       {args.c2_raster}")
    print(f"tau:      {args.tau_purity}")
    print(f"out:      {out_dir}")

    pair = load_raster_pair(
        args.segments_raster,
        args.c2_raster,
        subset=False,
        subset_window=None,
    )

    stats = compute_segment_stats(
        pair.segments,
        pair.c2,
        cfg.C2_NODATA,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )
    print(f"segments: {stats.segment_ids.size:,} unique")

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

    export_labeled_gpkg(
        pair.segments,
        pair.transform,
        pair.crs,
        stats,
        out_dir / "segments_labeled.gpkg",
        assignment=assignment,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )

    summary = {
        "segments_raster": str(args.segments_raster),
        "c2_raster": str(args.c2_raster),
        "tau_purity": args.tau_purity,
        "kappa_coverage": args.kappa_coverage,
        "n_min_pixels": args.n_min_pixels,
    }
    summary.update(
        {
            "ok": int((assignment.reason == "ok").sum()),
            "mixed": int((assignment.reason == "mixed").sum()),
            "no_data": int((assignment.reason == "no_data").sum()),
        }
    )

    if not args.no_merge:
        merge = merge_labeled_segments(
            pair.segments,
            stats,
            assignment,
            background_id=cfg.BACKGROUND_SEGMENT_ID,
        )
        print("Merge summary:")
        print_merge_summary(merge)
        summary.update(summarize_merge(stats, assignment, merge))

        export_merged_gpkg(
            merge,
            pair.transform,
            pair.crs,
            out_dir / "segments_merged.gpkg",
        )
        if args.write_raster:
            export_merged_class_raster(
                merge,
                out_dir / "C2_labels_merged.tif",
                transform=pair.transform,
                crs=pair.crs,
                background_id=cfg.BACKGROUND_SEGMENT_ID,
            )

    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Saved summary: {out_dir / 'summary.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
