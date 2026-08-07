"""Tags de corridas de referencia (producción validada)."""

from pathlib import Path

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_v02")

# Último lanzamiento nacional UTM + plan revisión (2026-07-27)
CARACT_RUN_REF = "20260727_1004"
SEL_RUN_REF = "20260727_1340"
PLAN_REVISION_SUFFIX = "plan_revision_20260727_2030"

# Baseline de comparación en informes (solo lectura)
SEL_BASELINE_REF = "20260724_1357"
CARACT_BASELINE_REF = "20260724_1056"

CARACT_RUN_REF_DIR = DATA_ROOT / "01_caracterizacion" / CARACT_RUN_REF
SEL_RUN_REF_DIR = DATA_ROOT / "02_seleccion" / SEL_RUN_REF
