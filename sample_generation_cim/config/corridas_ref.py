"""Tags de corridas de referencia (producción validada)."""

from pathlib import Path

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_cim")

CARACT_RUN_REF = "nacional_20260806"
SEL_RUN_REF = "20260806_2005"
PLAN_REVISION_SUFFIX = "20260806_2006"

# Primera selección CIM: ella misma es el punto de partida, no hay baseline previa.
SEL_BASELINE_REF = SEL_RUN_REF
CARACT_BASELINE_REF = CARACT_RUN_REF

CARACT_RUN_REF_DIR = DATA_ROOT / "01_caracterizacion" / CARACT_RUN_REF
SEL_RUN_REF_DIR = DATA_ROOT / "02_seleccion" / SEL_RUN_REF
PLAN_REVISION_DIR = SEL_RUN_REF_DIR / f"plan_revision_{PLAN_REVISION_SUFFIX}"
