"""Path helpers for SSL4EO sample selections under prod/samples."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_SAMPLES_DIR = Path("/home/lserey/mapbiomas_land/prod/samples")
DEFAULT_LANDCOVER_DIR = Path("/home/lserey/mapbiomas_land/ancillary_data/landcover_col2")
DEFAULT_PLAN_NAME = "listado_revision_manual.csv"

GRID_TAGS = ("homogeneo_2x2", "mixto_3x3")
LEGACY_SELECTION_GLOB = "seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"
FINAL_SELECTION_GLOB = "UTM*/**/seleccion_*.geojson"


def samples_root(samples_dir: Path | None = None) -> Path:
    if samples_dir is not None:
        return Path(samples_dir)
    env = os.environ.get("SAMPLES_DIR") or os.environ.get("GRILLAS_ROOT")
    return Path(env) if env else DEFAULT_SAMPLES_DIR


def final_samples_dir(samples_dir: Path) -> Path:
    return samples_dir / "final_samples"


def review_dir(samples_dir: Path) -> Path:
    return samples_dir / "intermediate_files" / "review"


def resolve_plan_path(samples_dir: Path, plan_name: str | None = None) -> Path:
    name = plan_name or DEFAULT_PLAN_NAME
    candidates = [
        review_dir(samples_dir) / name,
        samples_dir / name,
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


def discover_selection_geojsons(samples_dir: Path) -> list[Path]:
    finals_dir = final_samples_dir(samples_dir)
    if finals_dir.is_dir():
        files = sorted(
            p
            for p in finals_dir.glob(FINAL_SELECTION_GLOB)
            if p.is_file() and "taxonomia" not in p.name.lower()
        )
        if files:
            return files
    legacy = sorted(samples_dir.glob(LEGACY_SELECTION_GLOB))
    return legacy


def infer_selection_crs(path: Path):
    upper = path.as_posix().upper()
    if "UTM18" in upper:
        return "EPSG:32718"
    if "UTM19" in upper:
        return "EPSG:32719"
    raise ValueError(f"CRS no definido y UTM no inferible en {path}")


def infer_grid_tag(path: Path) -> str:
    for tag in GRID_TAGS:
        if tag in path.parts:
            return tag
    name = path.stem.upper()
    if "HOMOGENEO" in name and "2X2" in name:
        return "homogeneo_2x2"
    if "MIXTO" in name and "3X3" in name:
        return "mixto_3x3"
    return "combined"


def infer_utm_zone(path: Path) -> str:
    upper = path.as_posix().upper()
    if "UTM18" in upper:
        return "UTM18"
    if "UTM19" in upper:
        return "UTM19"
    raise ValueError(f"UTM zone no inferible en {path}")
