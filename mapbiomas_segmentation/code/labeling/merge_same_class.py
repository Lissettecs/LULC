"""Merge adjacent labeled regions that share the same C2 class."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from scipy.ndimage import label as cc_label
from shapely.geometry import shape

from segmentation_labels.assign import AssignmentResult
from segmentation_labels.stats import SegmentStats


@dataclass(frozen=True)
class MergeResult:
    class_raster: np.ndarray
    merged_ids: np.ndarray
    merged_class: np.ndarray
    region_ids: np.ndarray
    region_class: np.ndarray
    n_ok_segments: int
    n_merged_regions: int


def build_class_raster(
    segments: np.ndarray,
    segment_ids: np.ndarray,
    label_final: np.ndarray,
    valid: np.ndarray,
    *,
    background_id: int = 0,
) -> np.ndarray:
    """Per-pixel C2 class for ok segments; 0 elsewhere (mixed/no_data/background)."""
    max_id = int(segment_ids.max()) if segment_ids.size else 0
    seg_to_class = np.zeros(max_id + 1, dtype=np.int32)
    for seg_id, label, ok in zip(segment_ids, label_final, valid):
        if ok:
            seg_to_class[int(seg_id)] = int(label)

    class_raster = np.zeros(segments.shape, dtype=np.int32)
    foreground = segments != background_id
    if foreground.any():
        class_raster[foreground] = seg_to_class[segments[foreground].astype(np.int64)]
    return class_raster


def merge_adjacent_same_class(class_raster: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Connected components per class; adjacent pixels with same class → one region."""
    merged_ids = np.zeros(class_raster.shape, dtype=np.int32)
    merged_class = np.zeros(class_raster.shape, dtype=np.int32)
    region_ids: list[int] = []
    region_class: list[int] = []
    next_id = 1

    for class_id in np.unique(class_raster):
        if class_id == 0:
            continue
        mask = class_raster == int(class_id)
        components, n_comp = cc_label(mask)
        for comp_id in range(1, int(n_comp) + 1):
            comp_mask = components == comp_id
            merged_ids[comp_mask] = next_id
            merged_class[comp_mask] = int(class_id)
            region_ids.append(next_id)
            region_class.append(int(class_id))
            next_id += 1

    return (
        merged_ids,
        merged_class,
        np.array(region_ids, dtype=np.int32),
        np.array(region_class, dtype=np.int32),
    )


def merge_labeled_segments(
    segments: np.ndarray,
    stats: SegmentStats,
    assignment: AssignmentResult,
    *,
    background_id: int = 0,
) -> MergeResult:
    """Assign classes (ok only) then merge touching regions with the same class."""
    class_raster = build_class_raster(
        segments,
        stats.segment_ids,
        assignment.label_final,
        assignment.valid,
        background_id=background_id,
    )
    merged_ids, merged_class, region_ids, region_class = merge_adjacent_same_class(class_raster)
    n_ok = int(assignment.valid.sum())
    n_regions = int(region_ids.size)
    return MergeResult(
        class_raster=class_raster,
        merged_ids=merged_ids,
        merged_class=merged_class,
        region_ids=region_ids,
        region_class=region_class,
        n_ok_segments=n_ok,
        n_merged_regions=n_regions,
    )


def export_merged_gpkg(
    merge: MergeResult,
    transform: rasterio.Affine,
    crs: str,
    out_path: Path,
) -> gpd.GeoDataFrame:
    """Polygonize merged regions (one polygon per connected same-class patch)."""
    mask = merge.merged_ids > 0
    if not mask.any():
        raise ValueError("No merged labeled regions to export.")

    geoms: list = []
    ids: list[int] = []
    classes: list[int] = []
    for geom, value in features.shapes(
        merge.merged_ids.astype(np.int32),
        mask=mask,
        transform=transform,
    ):
        region_id = int(value)
        if region_id <= 0:
            continue
        idx = np.where(merge.region_ids == region_id)[0]
        if idx.size == 0:
            continue
        geoms.append(shape(geom))
        ids.append(region_id)
        classes.append(int(merge.region_class[idx[0]]))

    gdf = gpd.GeoDataFrame(
        {"region_id": ids, "label_final": classes},
        geometry=geoms,
        crs=crs,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG")
    print(f"Saved merged GPKG ({len(gdf)} regions): {out_path}")
    return gdf


def export_merged_class_raster(
    merge: MergeResult,
    out_path: Path,
    *,
    transform: rasterio.Affine,
    crs: str,
    background_id: int = 0,
) -> None:
    """Write C2 class raster after adjacent merge (0 = unlabeled/background)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    profile = {
        "driver": "GTiff",
        "dtype": "uint8",
        "count": 1,
        "height": merge.merged_class.shape[0],
        "width": merge.merged_class.shape[1],
        "transform": transform,
        "crs": crs,
        "nodata": background_id,
        "compress": "deflate",
    }
    with rasterio.open(out_path, "w", **profile) as dst:
        dst.write(merge.merged_class.astype(np.uint8), 1)
    print(f"Saved merged class raster: {out_path}")


def summarize_merge(
    stats: SegmentStats,
    assignment: AssignmentResult,
    merge: MergeResult,
) -> dict:
    """Summary dict for JSON export."""
    return {
        "n_segments_total": int(stats.segment_ids.size),
        "n_ok_before_merge": merge.n_ok_segments,
        "n_merged_regions": merge.n_merged_regions,
        "reduction_pct": round(
            100.0 * (1.0 - merge.n_merged_regions / merge.n_ok_segments)
            if merge.n_ok_segments
            else 0.0,
            2,
        ),
        "ok": int((assignment.reason == "ok").sum()),
        "mixed": int((assignment.reason == "mixed").sum()),
        "no_data": int((assignment.reason == "no_data").sum()),
    }


def print_merge_summary(merge: MergeResult) -> None:
    print(
        f"  ok segments: {merge.n_ok_segments:,} → merged regions: {merge.n_merged_regions:,}",
        end="",
    )
    if merge.n_ok_segments:
        pct = 100.0 * (1.0 - merge.n_merged_regions / merge.n_ok_segments)
        print(f" ({pct:.1f}% reduction)")
    else:
        print()
