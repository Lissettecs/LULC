"""Load and filter SSL4EO rectangles from the revision plan."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config.paths import masked_mosaic_path, summary_path
from config.run_refs import GPKG_UTM18, GPKG_UTM19

TILE_FROM_GRID = re.compile(r"^(\d{2}[A-Z]{3})")


def tile_from_grid_id(grid_id: str) -> str:
    m = TILE_FROM_GRID.match(grid_id)
    if not m:
        raise ValueError(f"Cannot infer MGRS tile from grid_id={grid_id!r}")
    return m.group(1)


def tile_from_row(row: pd.Series) -> str:
    if "mgrs_dom" in row.index and pd.notna(row["mgrs_dom"]):
        return str(row["mgrs_dom"]).upper()
    return tile_from_grid_id(str(row["grid_id"]))


@dataclass
class RectPlan:
    grid_id: str
    tile: str
    rev_year1: int
    rev_role1: str
    source_gpkg: str
    mosaic_path: str | None = None
    mosaic_ok: bool = False
    already_processed: bool = False
    summary_path: str | None = None
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "grid_id": self.grid_id,
            "tile": self.tile,
            "rev_year1": self.rev_year1,
            "rev_role1": self.rev_role1,
            "source_gpkg": self.source_gpkg,
            "mosaic_path": self.mosaic_path,
            "mosaic_ok": self.mosaic_ok,
            "already_processed": self.already_processed,
            "summary_path": self.summary_path,
            "error": self.error,
        }


@dataclass
class SegmentationPlan:
    rev_year: int
    year: int
    mosaic_root: str
    output_dir: str
    rects: list[RectPlan] = field(default_factory=list)

    @property
    def ready(self) -> list[RectPlan]:
        return [r for r in self.rects if r.mosaic_ok and not r.already_processed and not r.error]

    @property
    def missing_mosaic(self) -> list[RectPlan]:
        return [r for r in self.rects if not r.mosaic_ok]

    @property
    def already_done(self) -> list[RectPlan]:
        return [r for r in self.rects if r.already_processed]

    def summary(self) -> dict:
        return {
            "rev_year": self.rev_year,
            "year": self.year,
            "mosaic_root": self.mosaic_root,
            "output_dir": self.output_dir,
            "n_total": len(self.rects),
            "n_mosaic_ok": sum(1 for r in self.rects if r.mosaic_ok),
            "n_ready": len(self.ready),
            "n_already_processed": len(self.already_done),
            "n_missing_mosaic": len(self.missing_mosaic),
            "tiles_missing_mosaic": sorted({r.tile for r in self.missing_mosaic}),
            "rects": [r.to_dict() for r in self.rects],
        }


def load_selection_gpkg(
    gpkg_utm18: Path = GPKG_UTM18,
    gpkg_utm19: Path = GPKG_UTM19,
    rev_year: int = 2015,
    test_tile: str | None = None,
    grid_id: str | None = None,
) -> list[gpd.GeoDataFrame]:
    out: list[gpd.GeoDataFrame] = []
    for path in (gpkg_utm18, gpkg_utm19):
        if not path.is_file():
            raise FileNotFoundError(path)
        gdf = gpd.read_file(path)
        gdf = gdf[gdf["rev_year1"] == rev_year].copy()
        if gdf.empty:
            continue
        gdf["_source_gpkg"] = path.name
        gdf["_tile"] = gdf.apply(tile_from_row, axis=1)
        if test_tile:
            gdf = gdf[gdf["_tile"] == test_tile.upper()].copy()
        if grid_id:
            gdf = gdf[gdf["grid_id"] == grid_id].copy()
        if not gdf.empty:
            out.append(gdf)
    if not out:
        raise ValueError("No rectangles after filtering rev_year / tile / grid_id")
    return out


def build_plan(
    *,
    rev_year: int,
    year: int,
    mosaic_root_dir: Path,
    output_root: Path,
    gpkg_utm18: Path = GPKG_UTM18,
    gpkg_utm19: Path = GPKG_UTM19,
    test_tile: str | None = None,
    grid_id: str | None = None,
) -> SegmentationPlan:
    plan = SegmentationPlan(
        rev_year=rev_year,
        year=year,
        mosaic_root=str(mosaic_root_dir),
        output_dir=str(output_root),
    )
    for gdf in load_selection_gpkg(gpkg_utm18, gpkg_utm19, rev_year, test_tile, grid_id):
        for _, row in gdf.iterrows():
            gid = str(row["grid_id"])
            tile = str(row["_tile"])
            mosaic = masked_mosaic_path(mosaic_root_dir, tile, year)
            summ = summary_path(output_root, tile, gid)
            item = RectPlan(
                grid_id=gid,
                tile=tile,
                rev_year1=int(row["rev_year1"]),
                rev_role1=str(row.get("rev_role1", "")),
                source_gpkg=str(row["_source_gpkg"]),
                mosaic_path=str(mosaic) if mosaic else None,
                mosaic_ok=mosaic is not None and mosaic.is_file(),
                already_processed=summ.is_file(),
                summary_path=str(summ) if summ.is_file() else None,
            )
            if year != rev_year:
                item.error = f"year ({year}) != rev_year ({rev_year})"
            plan.rects.append(item)

    plan.rects.sort(key=lambda r: (r.tile, r.grid_id))
    return plan


def filter_plan(
    plan: SegmentationPlan,
    *,
    require_mosaic: bool = False,
    skip_existing: bool = False,
) -> list[RectPlan]:
    rects = plan.rects
    if require_mosaic:
        rects = [r for r in rects if r.mosaic_ok]
    if skip_existing:
        rects = [r for r in rects if not r.already_processed]
    return rects


def iter_plan_rows(plan: SegmentationPlan) -> list[gpd.GeoDataFrame]:
    """Rebuild GeoDataFrames for rectangles in the plan."""
    if not plan.rects:
        return []
    ids = {r.grid_id for r in plan.rects}
    gdfs = load_selection_gpkg(rev_year=plan.rev_year)
    out: list[gpd.GeoDataFrame] = []
    for gdf in gdfs:
        sub = gdf[gdf["grid_id"].isin(ids)].copy()
        if not sub.empty:
            out.append(sub)
    return out


def save_plan(plan: SegmentationPlan, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan.summary(), indent=2, ensure_ascii=False), encoding="utf-8")
