#!/usr/bin/env python3
"""
Export Col2 label overlays and assignment summaries for all segment TIFs.

For each segment raster:
  1. Compute per-segment majority-vote stats vs landcover C2
  2. Assign labels with method-specific tau
  3. Write PNG overlays at 1024/2048/4096 px tiers
  4. Save assignment_summary.json keyed by segment stem

Usage:
  cd labeling/image_segmentation/segmentation_labels
  python export_label_overlays.py --tile 18HYD --resume
  python export_label_overlays.py --segmenter felzenszwalb --skip-existing
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import numpy as np

_SCRIPT_DIR = Path(__file__).resolve().parent
_SEG_ROOT = _SCRIPT_DIR.parent
_DATA_ROOT = Path("/home/lserey/mapbiomas_land/test/image_segmentation")
_LABEL_PKG = _DATA_ROOT / "segmentation_labels"

if str(_LABEL_PKG.parent) not in sys.path:
    sys.path.insert(0, str(_LABEL_PKG.parent))
if str(_SEG_ROOT) not in sys.path:
    sys.path.insert(0, str(_SEG_ROOT))

if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from col2_palette import build_lut  # noqa: E402
from segmentation_labels.assign import assign_labels  # noqa: E402
from segmentation_labels import config as cfg  # noqa: E402
from segmentation_labels.io_rasters import load_raster_pair  # noqa: E402
from segmentation_labels.stats import compute_segment_stats  # noqa: E402

from seg_felzenszwalb.seg_felzenszwalb_grid import (  # noqa: E402
    guardar_rgba_png,
    reducir_para_quicklook,
)

RES_TIERS = [1024, 2048, 4096]
CAPAS_SUBDIR = "capas"

# Tau calibrated per segmenter family (p75 subset, tile 18HYD).
TAU_BY_SEGMENTER: dict[str, float] = {
    "felzenszwalb": 0.875,
    "felzenszwalb_rf_n": 1.0,
    "felzenszwalb_rfn_podado": 1.0,
    "lv3_rf": 1.0,
    "slic": 0.875,
    "slic_rag": 0.875,
    "slic_min": 0.875,
    "slic_hier": 0.875,
    "slic_pipeline_b": 0.9067840247159914,
    "incremental": 0.875,
    "ablacion": 0.975,
    "ablacion_lv3": 0.975,
}

SEGMENTER_DIRS: dict[str, Path] = {
    "felzenszwalb": _DATA_ROOT / "seg_felzenszwalb",
    "felzenszwalb_rf_n": _DATA_ROOT / "seg_felzenszwalb_rf_n",
    "felzenszwalb_rfn_podado": _DATA_ROOT / "seg_felzenszwalb_rfn",
    "lv3_rf": _DATA_ROOT / "seg_felzenszwalb_rf_lv3",
    "slic": _DATA_ROOT / "seg_slic/pipeline_a",
    "slic_rag": _DATA_ROOT / "seg_slic/pipeline_a",
    "slic_min": _DATA_ROOT / "seg_slic/pipeline_a/size_filter",
    "slic_hier": _DATA_ROOT / "seg_slic/pipeline_a/rag_hierarchical",
    "slic_pipeline_b": _DATA_ROOT / "seg_slic/pipeline_b",
    "ablacion": _DATA_ROOT / "seg_felzenszwalb_ablacion",
    "ablacion_lv3": _DATA_ROOT / "seg_felzenszwalb_ablacion_lv3",
    "incremental": _DATA_ROOT / "seg_felzenszwalb_incremental",
}

RF_N_TIF = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_lv\d+_rfn_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)\.tif$"
)
FELZ_TIF = re.compile(r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)\.tif$")
RFN_PODADO_TIF = re.compile(r"^seg_rfn_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)\.tif$")
ABL_TIF = re.compile(r"^seg_abl_(?P<tile>[^_]+)_(?P<year>\d+)_(?P<variant>.+)\.tif$")
ABL_LV3_TIF = re.compile(r"^seg_abl_lv3_(?P<tile>[^_]+)_(?P<year>\d+)_(?P<variant>.+)\.tif$")
LV3_RF_TIF = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_lv3_rf_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)\.tif$"
)
SLIC_TIF = re.compile(
    r"^seg_(?P<tile>[^_]+)_(?P<year>\d+)_s(?P<scale>\d+)_sig(?P<sigma>[\d.]+)(?P<suffix>.*)\.tif$"
)
INC_TIF = re.compile(r"^seg_inc_(?P<tile>[^_]+)_(?P<year>\d+)_(?P<variant>.+)\.tif$")


def discover_segment_tifs(seg_id: str, output_dir: Path, tile: str, year: str) -> list[Path]:
    """Return segment GeoTIFFs for a segmenter, filtered by tile/year."""
    if not output_dir.is_dir():
        return []
    out: list[Path] = []
    for path in sorted(output_dir.glob("seg_*.tif")):
        name = path.name
        if seg_id == "felzenszwalb_rf_n":
            m = RF_N_TIF.match(name)
        elif seg_id == "felzenszwalb_rfn_podado":
            m = RFN_PODADO_TIF.match(name)
        elif seg_id == "ablacion_lv3":
            m = ABL_LV3_TIF.match(name)
        elif seg_id == "ablacion":
            m = ABL_TIF.match(name)
        elif seg_id == "lv3_rf":
            m = LV3_RF_TIF.match(name)
        elif seg_id == "incremental":
            m = INC_TIF.match(name)
        else:
            m = SLIC_TIF.match(name) if seg_id.startswith("slic") else FELZ_TIF.match(name)
        if not m:
            continue
        if m.group("tile") != tile or m.group("year") != year:
            continue
        if seg_id == "felzenszwalb" and ("_rag" in name or "_hier" in name or "_min" in name):
            continue
        if seg_id == "slic" and ("_rag" in name or "_hier" in name or "_min" in name):
            continue
        if seg_id == "slic_rag":
            if "_ragp" not in name or "_hier" in name or "_min" in name:
                continue
        if seg_id == "slic_hier" and "_hier" not in name:
            continue
        if seg_id == "slic_pipeline_b" and "_min" not in name:
            continue
        out.append(path)
    return out


def write_labels_raster(
    segments: np.ndarray,
    segment_ids: np.ndarray,
    label_final: np.ndarray,
    *,
    background_id: int,
    label_nodata: int,
) -> np.ndarray:
    """Map segment_id → label_final into a uint8 raster."""
    max_id = int(segment_ids.max())
    lut = np.full(max_id + 1, label_nodata, dtype=np.uint8)
    for seg_id, label in zip(segment_ids, label_final):
        lut[int(seg_id)] = np.uint8(label)
    out = np.zeros(segments.shape, dtype=np.uint8)
    foreground = segments != background_id
    out[foreground] = lut[segments[foreground].astype(np.int64)]
    return out


def render_label_rgba(labels: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """RGBA overlay from Col2 label raster."""
    palette, _ = build_lut(255)
    h, w = labels.shape
    rgb = np.zeros((h, w, 3), dtype=np.float32)
    for cls_id, color in enumerate(palette):
        if cls_id == 0:
            continue
        mask = labels == cls_id
        if mask.any():
            rgb[mask] = color
    alpha = np.where((labels > 0) & validos, 0.78, 0.0).astype(np.float32)
    return np.dstack([rgb, alpha])


def export_landcover_reference(
    c2_path: Path,
    out_dir: Path,
    validos: np.ndarray | None = None,
    *,
    resume: bool,
) -> dict[str, str]:
    """Export landcover C2 reference PNG tiers."""
    import rasterio

    capas_dir = out_dir / CAPAS_SUBDIR
    capas_dir.mkdir(parents=True, exist_ok=True)
    stem = c2_path.stem
    tiers: dict[str, str] = {}

    with rasterio.open(c2_path) as src:
        c2 = src.read(1).astype(np.int32)

    if validos is None:
        validos = c2 != 0

    labels_u8 = np.clip(c2, 0, 255).astype(np.uint8)
    for lado in RES_TIERS:
        rel = f"{CAPAS_SUBDIR}/{stem}_lc_l{lado}.png"
        out_path = out_dir / rel
        tiers[str(lado)] = rel
        if resume and out_path.is_file():
            continue
        _, labels_q, validos_q = reducir_para_quicklook(
            np.zeros((*labels_u8.shape, 3), dtype=np.float32),
            labels_u8.astype(np.int32),
            validos,
            lado,
        )
        rgba = render_label_rgba(labels_q, validos_q)
        guardar_rgba_png(out_path, rgba)
        print(f"  → {out_path.name}")
    return tiers


def build_visual_label_raster(
    segments: np.ndarray,
    segment_ids: np.ndarray,
    label_mode: np.ndarray,
    reason: np.ndarray,
    *,
    background_id: int,
    label_nodata: int,
) -> np.ndarray:
    """Color overlays with majority class; only no_data uses sentinel 254."""
    visual = label_mode.astype(np.int64).copy()
    visual[reason == "no_data"] = label_nodata
    return write_labels_raster(
        segments,
        segment_ids,
        visual,
        background_id=background_id,
        label_nodata=label_nodata,
    )


def build_purity_raster(
    segments: np.ndarray,
    segment_ids: np.ndarray,
    purity: np.ndarray,
    reason: np.ndarray,
    *,
    background_id: int,
) -> np.ndarray:
    """Map per-segment purity (majority class share) onto the segment grid."""
    max_id = int(segment_ids.max())
    lut = np.full(max_id + 1, np.nan, dtype=np.float32)
    for seg_id, p, r in zip(segment_ids, purity, reason):
        if r != "no_data":
            lut[int(seg_id)] = float(p)
    out = np.full(segments.shape, np.nan, dtype=np.float32)
    foreground = segments != background_id
    out[foreground] = lut[segments[foreground].astype(np.int64)]
    return out


def reducir_float_raster(arr: np.ndarray, validos: np.ndarray, max_lado: int) -> tuple[np.ndarray, np.ndarray]:
    """Downsample a float raster preserving per-segment constant values."""
    h, w = arr.shape
    factor = max(1, int(np.ceil(max(h, w) / max_lado)))
    if factor == 1:
        return arr, validos
    return arr[::factor, ::factor], validos[::factor, ::factor]


def purity_to_rgb(purity: np.ndarray) -> np.ndarray:
    """Map purity in [0, 1] to RGB (red → yellow → green)."""
    p = np.clip(purity, 0.0, 1.0)
    rgb = np.zeros((*p.shape, 3), dtype=np.float32)
    low = p <= 0.5
    high = ~low
    t_low = p[low] / 0.5
    rgb[low, 0] = 0.84 + (1.0 - 0.84) * t_low
    rgb[low, 1] = 0.19 + (0.88 - 0.19) * t_low
    rgb[low, 2] = 0.15 + (0.55 - 0.15) * t_low
    t_high = (p[high] - 0.5) / 0.5
    rgb[high, 0] = 1.0 + (0.10 - 1.0) * t_high
    rgb[high, 1] = 0.88 + (0.60 - 0.88) * t_high
    rgb[high, 2] = 0.55 + (0.31 - 0.55) * t_high
    return rgb


def render_purity_rgba(purity: np.ndarray, validos: np.ndarray) -> np.ndarray:
    """RGBA overlay: purity of the chosen majority class per segment."""
    mask = validos & np.isfinite(purity)
    rgb = np.zeros((*purity.shape, 3), dtype=np.float32)
    if mask.any():
        rgb[mask] = purity_to_rgb(purity[mask])
    alpha = np.where(mask, 0.82, 0.0).astype(np.float32)
    return np.dstack([rgb, alpha])


def export_purity_tiers(
    purity_raster: np.ndarray,
    validos: np.ndarray,
    capas_dir: Path,
    stem: str,
    *,
    resume: bool,
    rerender: bool,
) -> dict[str, str]:
    """Write multi-resolution purity PNG tiers."""
    purity_tiers: dict[str, str] = {}
    for lado in RES_TIERS:
        rel = f"{CAPAS_SUBDIR}/{stem}_purity_l{lado}.png"
        out_path = capas_dir / f"{stem}_purity_l{lado}.png"
        purity_tiers[str(lado)] = rel
        if resume and not rerender and out_path.is_file():
            continue
        purity_q, validos_q = reducir_float_raster(purity_raster, validos, lado)
        rgba = render_purity_rgba(purity_q, validos_q)
        guardar_rgba_png(out_path, rgba)
    return purity_tiers


def process_segment_tif(
    seg_path: Path,
    c2_path: Path,
    out_dir: Path,
    tau: float,
    *,
    resume: bool,
    rerender_png: bool,
    purity_only: bool = False,
) -> dict | None:
    """Label one segment raster and export overlay tiers + summary."""
    stem = seg_path.stem
    capas_dir = out_dir / CAPAS_SUBDIR
    capas_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / f"{stem}_assignment.json"

    label_tier_paths = [capas_dir / f"{stem}_labels_l{t}.png" for t in RES_TIERS]
    purity_tier_paths = [capas_dir / f"{stem}_purity_l{t}.png" for t in RES_TIERS]
    if (
        resume
        and summary_path.is_file()
        and all(p.is_file() for p in label_tier_paths)
        and all(p.is_file() for p in purity_tier_paths)
        and not rerender_png
    ):
        return json.loads(summary_path.read_text(encoding="utf-8"))

    if purity_only and summary_path.is_file() and all(p.is_file() for p in purity_tier_paths) and not rerender_png:
        return json.loads(summary_path.read_text(encoding="utf-8"))

    pair = load_raster_pair(seg_path, c2_path, subset=False, subset_window=None)
    stats = compute_segment_stats(
        pair.segments,
        pair.c2,
        cfg.C2_NODATA,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )
    assignment = assign_labels(
        stats,
        tau_purity=tau,
        kappa_coverage=cfg.KAPPA_COVERAGE,
        n_min_pixels=cfg.N_MIN_PIXELS,
        label_mixed=cfg.LABEL_MIXED,
        label_nodata=cfg.LABEL_NODATA,
    )

    validos = pair.segments != cfg.BACKGROUND_SEGMENT_ID
    purity_raster = build_purity_raster(
        pair.segments,
        stats.segment_ids,
        stats.purity,
        assignment.reason,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
    )
    purity_tiers = export_purity_tiers(
        purity_raster,
        validos,
        capas_dir,
        stem,
        resume=resume,
        rerender=rerender_png,
    )

    if purity_only and summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summary["purity_tiers"] = purity_tiers
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"  purity {stem}")
        return summary

    label_raster = build_visual_label_raster(
        pair.segments,
        stats.segment_ids,
        stats.label_mode,
        assignment.reason,
        background_id=cfg.BACKGROUND_SEGMENT_ID,
        label_nodata=cfg.LABEL_NODATA,
    )

    label_tiers: dict[str, str] = {}
    if not purity_only:
        for lado in RES_TIERS:
            _, labels_q, validos_q = reducir_para_quicklook(
                np.zeros((*label_raster.shape, 3), dtype=np.float32),
                label_raster.astype(np.int32),
                validos,
                lado,
            )
            rel = f"{CAPAS_SUBDIR}/{stem}_labels_l{lado}.png"
            out_path = out_dir / rel
            label_tiers[str(lado)] = rel
            if resume and not rerender_png and out_path.is_file():
                continue
            rgba = render_label_rgba(labels_q, validos_q)
            guardar_rgba_png(out_path, rgba)

    n = stats.segment_ids.size
    summary = {
        "segments_raster": str(seg_path),
        "stem": stem,
        "tau_purity": tau,
        "kappa_coverage": cfg.KAPPA_COVERAGE,
        "n_min_pixels": cfg.N_MIN_PIXELS,
        "n_segments": n,
        "ok": int((assignment.reason == "ok").sum()),
        "mixed": int((assignment.reason == "mixed").sum()),
        "no_data": int((assignment.reason == "no_data").sum()),
        "ok_pct": round(100.0 * (assignment.reason == "ok").sum() / n, 2) if n else 0.0,
        "mixed_pct": round(100.0 * (assignment.reason == "mixed").sum() / n, 2) if n else 0.0,
        "label_tiers": label_tiers,
        "purity_tiers": purity_tiers,
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"  OK {stem}: {summary['ok_pct']}% ok · {n:,} seg")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Export Col2 label overlays for segment TIFs.")
    parser.add_argument("--tile", default="18HYD")
    parser.add_argument("--seg-year", type=int, default=2010)
    parser.add_argument("--lc-year", type=int, default=None, help="Landcover year (default: same as --seg-year)")
    parser.add_argument("--data-root", type=Path, default=_DATA_ROOT)
    parser.add_argument(
        "--segmenter",
        action="append",
        choices=sorted(SEGMENTER_DIRS.keys()),
        help="Process only these segmenters (repeatable). Default: all.",
    )
    parser.add_argument("--resume", action="store_true", help="Skip if outputs already exist.")
    parser.add_argument("--skip-existing", action="store_true", dest="resume")
    parser.add_argument(
        "--rerender-png",
        action="store_true",
        help="Regenerate PNG overlays (palette/visual mode) even when assignment JSON exists.",
    )
    parser.add_argument(
        "--purity-only",
        action="store_true",
        help="Only export missing purity raster tiers (reuse existing label assignments).",
    )
    args = parser.parse_args()

    data_root = args.data_root.resolve()
    lc_year = args.lc_year if args.lc_year is not None else args.seg_year
    c2_path = data_root / "landcover_tiles" / f"{args.tile}_classification_{lc_year}.tif"
    if not c2_path.is_file():
        print(f"[ERROR] Missing landcover: {c2_path}")
        return 1

    out_root = data_root / "labeling_overlays" / f"tile_{args.tile}_{args.seg_year}_lc{lc_year}"
    out_root.mkdir(parents=True, exist_ok=True)

    seg_ids = args.segmenter or sorted(SEGMENTER_DIRS.keys())
    manifest: dict[str, list[dict]] = {}

    print(f"[INFO] Landcover: {c2_path}")
    print(f"[INFO] Output: {out_root}")
    print("[INFO] Exporting landcover reference...")
    lc_tiers = export_landcover_reference(
        c2_path, out_root, resume=args.resume and not args.rerender_png
    )
    (out_root / "landcover_tiers.json").write_text(
        json.dumps({"c2_raster": str(c2_path), "tiers": lc_tiers}, indent=2),
        encoding="utf-8",
    )

    for seg_id in seg_ids:
        output_dir = SEGMENTER_DIRS[seg_id]
        tau = TAU_BY_SEGMENTER[seg_id]
        seg_out = out_root / seg_id
        seg_out.mkdir(parents=True, exist_ok=True)
        tifs = discover_segment_tifs(seg_id, output_dir, args.tile, str(args.seg_year))
        print(f"\n[INFO] {seg_id}: {len(tifs)} TIFs · tau={tau}")
        entries: list[dict] = []
        for tif in tifs:
            print(f"  · {tif.name}")
            summary = process_segment_tif(
                tif,
                c2_path,
                seg_out,
                tau,
                resume=args.resume,
                rerender_png=args.rerender_png,
                purity_only=args.purity_only,
            )
            if summary:
                entries.append(summary)
        manifest[seg_id] = entries

    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"\n[OK] Manifest: {manifest_path}")
    total = sum(len(v) for v in manifest.values())
    print(f"[OK] {total} segment rasters labeled")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
