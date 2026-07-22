"""Polygonize segment raster and export auditable GPKG."""

from __future__ import annotations

from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
import rasterio
from rasterio import features
from shapely.geometry import MultiPolygon, shape
from shapely.ops import unary_union

from segmentation_labels.assign import AssignmentResult
from segmentation_labels.stats import SegmentStats


def _dissolve_by_segment(geoms: list, segment_ids: list[int]) -> gpd.GeoDataFrame:
    """Merge multipolygon fragments that share the same segment_id."""
    by_id: dict[int, list] = {}
    for seg_id, geom in zip(segment_ids, geoms):
        by_id.setdefault(int(seg_id), []).append(geom)

    rows = []
    for seg_id, parts in by_id.items():
        merged = unary_union(parts)
        if merged.geom_type == "Polygon":
            merged = MultiPolygon([merged])
        rows.append({"segment_id": seg_id, "geometry": merged})

    return gpd.GeoDataFrame(rows, geometry="geometry", crs=None)


def polygonize_segments(
    segments: np.ndarray,
    transform: rasterio.Affine,
    crs: str,
    background_id: int = 0,
) -> gpd.GeoDataFrame:
    """Build one dissolved polygon per segment_id from the label raster."""
    mask = segments != background_id
    shapes_iter = features.shapes(
        segments.astype(np.int32),
        mask=mask,
        transform=transform,
    )

    geoms: list = []
    ids: list[int] = []
    for geom, value in shapes_iter:
        seg_id = int(value)
        if seg_id == background_id:
            continue
        geoms.append(shape(geom))
        ids.append(seg_id)

    if not geoms:
        raise ValueError("Polygonization produced no geometries.")

    gdf = _dissolve_by_segment(geoms, ids)
    gdf = gdf.set_crs(crs)
    return gdf


def build_attribute_table(
    stats: SegmentStats,
    assignment: AssignmentResult | None = None,
) -> pd.DataFrame:
    """Tabular stats keyed by segment_id for joining to polygons."""
    data = {
        "segment_id": stats.segment_ids.astype(np.int64),
        "label_mode": stats.label_mode.astype(np.int64),
        "purity": stats.purity.astype(np.float64),
        "coverage": stats.coverage.astype(np.float64),
        "n_pixels": stats.n_total.astype(np.int64),
        "n_valid": stats.n_valid.astype(np.int64),
    }
    if assignment is not None:
        data["label_final"] = assignment.label_final.astype(np.int64)
        data["valid"] = assignment.valid.astype(bool)
        data["reason"] = assignment.reason

    return pd.DataFrame(data)


def export_labeled_gpkg(
    segments: np.ndarray,
    transform: rasterio.Affine,
    crs: str,
    stats: SegmentStats,
    out_path: Path,
    assignment: AssignmentResult | None = None,
    background_id: int = 0,
) -> gpd.GeoDataFrame:
    """Write GPKG with one polygon per segment and audit attributes."""
    gdf = polygonize_segments(segments, transform, crs, background_id=background_id)
    attrs = build_attribute_table(stats, assignment)
    gdf = gdf.merge(attrs, on="segment_id", how="left", validate="one_to_one")

    missing = gdf["purity"].isna().sum()
    if missing:
        raise RuntimeError(f"{missing} polygons have no matching segment stats.")

    n_segments = stats.segment_ids.size
    n_polygons = len(gdf)
    assert n_polygons == n_segments, (
        f"Polygon count ({n_polygons}) != unique segment count ({n_segments})."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(out_path, driver="GPKG")
    print(f"Saved GPKG ({n_polygons} polygons): {out_path}")
    return gdf
