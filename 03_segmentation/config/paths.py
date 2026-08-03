"""Reexporta rutas compartidas del pipeline."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "pipeline_paths", _PIPELINE / "config" / "paths.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

mosaic_root = _mod.mosaic_root
output_dir = _mod.output_dir
segmentation_dir = _mod.segmentation_dir
labeling_dir = _mod.labeling_dir
landcover_dir = _mod.landcover_dir
landcover_path = _mod.landcover_path
masked_mosaic_path = _mod.masked_mosaic_path
rect_dir = _mod.rect_dir
summary_path = _mod.summary_path
labeling_summary_path = _mod.labeling_summary_path
MAPBIOMAS_ROOT = _mod.MAPBIOMAS_ROOT
PIPELINE_ROOT = _mod.PIPELINE_ROOT
PROD_ROOT = _mod.PROD_ROOT
TMP_ROOT = _mod.TMP_ROOT

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
