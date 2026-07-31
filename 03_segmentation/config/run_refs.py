"""Reference production runs for segmentation inputs."""

import os
from pathlib import Path

MAPBIOMAS_ROOT = Path(os.environ.get("MAPBIOMAS_ROOT", "/home/lserey/mapbiomas_land"))
DATA_ROOT = MAPBIOMAS_ROOT / "prod" / "samples_v02"

# National selection + revision plan (2026-07-27)
SEL_RUN_REF = "20260727_1340"
PLAN_REVISION_SUFFIX = "plan_revision_20260727_2030"

SEL_RUN_DIR = DATA_ROOT / "02_seleccion" / SEL_RUN_REF
PLAN_REVISION_DIR = SEL_RUN_DIR / PLAN_REVISION_SUFFIX

GPKG_UTM18 = PLAN_REVISION_DIR / "seleccion_con_rev_years_utm18.gpkg"
GPKG_UTM19 = PLAN_REVISION_DIR / "seleccion_con_rev_years_utm19.gpkg"
GPKG_CSV = PLAN_REVISION_DIR / "seleccion_con_rev_years.csv"
