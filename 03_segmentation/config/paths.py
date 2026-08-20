"""Helpers de rutas de la etapa 03 — mosaicos CIM y layout de salida de segmentación."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "pipeline_paths", _PIPELINE / "config" / "paths.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

MAPBIOMAS_ROOT = Path(
    os.environ.get("MAPBIOMAS_ROOT", str(_mod.MAPBIOMAS_ROOT))
).resolve()
PIPELINE_ROOT = _mod.PIPELINE_ROOT
PROD_ROOT = MAPBIOMAS_ROOT / "prod"
TMP_ROOT = MAPBIOMAS_ROOT / "tmp"

MOSAIC_CIM_GLOB = "CHILE-{tile}-{year}-*_masked.tif"
MOSAIC_CIM_11B_GLOB = "CHILE-{tile}-{year}-*-11B.tif"
MOSAIC_FILENAME_LEGACY = "TMP-CHILE-{tile}-{year}-SBAND-184B_masked.tif"


def mosaic_root(year: int) -> Path:
    """Mosaicos CIM enmascarados: mosaic_184bands_mask_water/{year}/."""
    return MAPBIOMAS_ROOT / "mosaic_184bands_mask_water" / str(year)


def segmentation_dir(rev_year: int) -> Path:
    """Salida de segmentación: prod/03_segmentation_cim/{YEAR}/."""
    return PROD_ROOT / "03_segmentation_cim" / str(rev_year)


output_dir = segmentation_dir


def labeling_dir(year: int) -> Path:
    """Directorio de etiquetado (etapa 04)."""
    return _mod.labeling_dir(year)


def landcover_dir() -> Path:
    """Directorio de land cover de referencia."""
    return _mod.landcover_dir()


def landcover_path(year: int) -> Path:
    """Ruta del raster de land cover para un año."""
    return _mod.landcover_path(year)


def _pick_unique(matches: list[Path], prefer_substr: str | None = None) -> Path | None:
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    if prefer_substr:
        prefer = [p for p in matches if prefer_substr in p.name]
        if len(prefer) == 1:
            return prefer[0]
    return matches[0]


def masked_mosaic_path(mosaic_root_dir: Path, tile: str, year: int) -> Path | None:
    """Resuelve mosaico CIM 184 masked o 11B para (tile, year), o None si falta."""
    tile_u = tile.upper()
    root = mosaic_root_dir

    # 184 masked (prefer) then 11B, in root or root/{year}
    search_roots = [root]
    year_dir = root / str(year)
    if year_dir.is_dir():
        search_roots.append(year_dir)

    for base in search_roots:
        masked = _pick_unique(
            sorted(base.glob(MOSAIC_CIM_GLOB.format(tile=tile_u, year=year))),
            prefer_substr="184F-HARM_masked",
        )
        if masked is not None:
            return masked
        eleven = _pick_unique(
            sorted(base.glob(MOSAIC_CIM_11B_GLOB.format(tile=tile_u, year=year))),
            prefer_substr="184F-HARM-11B",
        )
        if eleven is not None:
            return eleven

    tile_dir = root / tile_u
    if tile_dir.is_dir():
        legacy = sorted(
            tile_dir.glob(MOSAIC_FILENAME_LEGACY.format(tile=tile_u, year=year))
        )
        if len(legacy) == 1:
            return legacy[0]
    return None


def rect_dir(output_root: Path, tile: str, grid_id: str) -> Path:
    """Carpeta de salida de un rectángulo: {output_root}/{TILE}/{grid_id}/."""
    return output_root / tile.upper() / grid_id


def summary_path(
    output_root: Path,
    tile: str,
    grid_id: str,
    year: int | None = None,
) -> Path:
    """Ruta del summary.json del rectángulo (con o sin year en el nombre)."""
    d = rect_dir(output_root, tile, grid_id)
    if year is not None:
        return d / f"{grid_id}_{year}_summary.json"
    return d / f"{grid_id}_summary.json"


def labeling_summary_path(labeling_root: Path, tile: str, grid_id: str) -> Path:
    """Ruta del labeling_summary.json en la etapa 04."""
    return rect_dir(labeling_root, tile, grid_id) / f"{grid_id}_labeling_summary.json"


__all__ = [
    "MAPBIOMAS_ROOT",
    "PIPELINE_ROOT",
    "PROD_ROOT",
    "TMP_ROOT",
    "landcover_dir",
    "landcover_path",
    "labeling_dir",
    "labeling_summary_path",
    "masked_mosaic_path",
    "mosaic_root",
    "output_dir",
    "rect_dir",
    "segmentation_dir",
    "summary_path",
]
