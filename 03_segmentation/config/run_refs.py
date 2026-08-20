"""Referencias al GPKG de selección y datos auxiliares de la etapa 03 (CIM)."""

from __future__ import annotations

import os
from pathlib import Path

from config.paths import MAPBIOMAS_ROOT, PROD_ROOT

SAMPLES_ROOT = Path(
    os.environ.get("SAMPLES_ROOT", str(PROD_ROOT / "samples_cim"))
).resolve()

SEL_RUN_REF = os.environ.get("SEL_RUN_REF", "20260806_2221")
# Sufijo sin prefijo review_plan_/plan_revision_
PLAN_REVISION_SUFFIX = os.environ.get("PLAN_REVISION_SUFFIX", "20260808_1526")


def _resolve_sel_run_dir() -> Path:
    for name in ("02_selection", "02_seleccion"):
        cand = SAMPLES_ROOT / name / SEL_RUN_REF
        if cand.is_dir():
            return cand
    return SAMPLES_ROOT / "02_selection" / SEL_RUN_REF


def _resolve_plan_dir(sel_dir: Path) -> Path:
    raw = PLAN_REVISION_SUFFIX
    for prefix in ("review_plan_", "plan_revision_"):
        if raw.startswith(prefix):
            raw = raw[len(prefix) :]
            break
    for prefix in ("review_plan_", "plan_revision_"):
        cand = sel_dir / f"{prefix}{raw}"
        if cand.is_dir():
            return cand
    return sel_dir / f"review_plan_{raw}"


def _resolve_gpkg(plan_dir: Path) -> Path:
    for name in ("selection_with_rev_years.gpkg", "seleccion_con_rev_years.gpkg"):
        cand = plan_dir / name
        if cand.is_file():
            return cand.resolve()
    env = os.environ.get("GPKG_SELECCION")
    if env:
        return Path(env).resolve()
    return (plan_dir / "selection_with_rev_years.gpkg").resolve()


SEL_RUN_DIR = _resolve_sel_run_dir()
PLAN_REVISION_DIR = _resolve_plan_dir(SEL_RUN_DIR)
GPKG_SELECCION = _resolve_gpkg(PLAN_REVISION_DIR)

# Aliases dual-huso apuntan al mismo GPKG nacional (dedupe en rectangles.py).
GPKG_UTM18 = Path(os.environ.get("GPKG_UTM18", str(GPKG_SELECCION)))
GPKG_UTM19 = Path(os.environ.get("GPKG_UTM19", str(GPKG_SELECCION)))

_csv = None
for name in ("selection_with_rev_years.csv", "seleccion_con_rev_years.csv"):
    cand = PLAN_REVISION_DIR / name
    if cand.is_file():
        _csv = cand
        break
GPKG_CSV = _csv or (PLAN_REVISION_DIR / "selection_with_rev_years.csv")

RASTER_ECORREGIONES = Path(
    os.environ.get(
        "RASTER_ECORREGIONES",
        str(MAPBIOMAS_ROOT / "ancillary_data" / "ecorregiones_col3_30m_alineado_lulc.tif"),
    )
).resolve()

__all__ = [
    "GPKG_CSV",
    "GPKG_SELECCION",
    "GPKG_UTM18",
    "GPKG_UTM19",
    "PLAN_REVISION_DIR",
    "PLAN_REVISION_SUFFIX",
    "RASTER_ECORREGIONES",
    "SEL_RUN_DIR",
    "SEL_RUN_REF",
    "SAMPLES_ROOT",
]
