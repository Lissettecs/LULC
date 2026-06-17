"""Rutas comunes del proyecto MapBiomas muestras SSL4EO (scale300)."""

from pathlib import Path

GRILLAS_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = GRILLAS_ROOT / "scripts"
FINALES_DIR = GRILLAS_ROOT / "final_samples"
INTERMEDIOS_DIR = GRILLAS_ROOT / "intermediate_files"
GEE_CARACTERIZACION_DIR = INTERMEDIOS_DIR / "gee_characterization"
REVISION_DIR = INTERMEDIOS_DIR / "review"
CHIPS_DIR = INTERMEDIOS_DIR / "chips_1x1"
LEGACY_SCRIPTS_DIR = INTERMEDIOS_DIR / "scripts_legacy"
