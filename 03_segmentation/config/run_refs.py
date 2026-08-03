"""Reexporta referencias GPKG compartidas."""

from __future__ import annotations

import importlib.util
from pathlib import Path

_PIPELINE = Path(__file__).resolve().parents[2]
_spec = importlib.util.spec_from_file_location(
    "pipeline_run_refs", _PIPELINE / "config" / "run_refs.py"
)
_mod = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_mod)

GPKG_UTM18 = _mod.GPKG_UTM18
GPKG_UTM19 = _mod.GPKG_UTM19
GPKG_CSV = _mod.GPKG_CSV
SEL_RUN_REF = _mod.SEL_RUN_REF
PLAN_REVISION_SUFFIX = _mod.PLAN_REVISION_SUFFIX
SEL_RUN_DIR = _mod.SEL_RUN_DIR
PLAN_REVISION_DIR = _mod.PLAN_REVISION_DIR
SAMPLES_ROOT = _mod.SAMPLES_ROOT

__all__ = [
    "GPKG_CSV",
    "GPKG_UTM18",
    "GPKG_UTM19",
    "PLAN_REVISION_DIR",
    "PLAN_REVISION_SUFFIX",
    "SEL_RUN_DIR",
    "SEL_RUN_REF",
    "SAMPLES_ROOT",
]
