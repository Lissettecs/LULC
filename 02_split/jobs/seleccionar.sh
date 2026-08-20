#!/usr/bin/env bash
# Selección completa en serie: presupuesto → selección → informe → plan.
#
#   jobs/seleccionar.sh
#   jobs/seleccionar.sh /ruta/a/01_caracterizacion/nacional_20260806

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
GRID_RUN="${1:-}"

cd "${REPO}"
mkdir -p logs

echo "[$(date -Iseconds)] Presupuesto"
"${PYTHON}" scripts/06_presupuesto_seleccion.py

echo "[$(date -Iseconds)] Selección"
if [[ -n "${GRID_RUN}" ]]; then
  "${PYTHON}" scripts/07_seleccionar_rectangulos.py --grid-run-dir "${GRID_RUN}"
else
  "${PYTHON}" scripts/07_seleccionar_rectangulos.py
fi

SEL_DIR="$(ls -td /home/lserey/mapbiomas_land/prod/samples_cim/02_seleccion/*/ | head -1)"
echo "[$(date -Iseconds)] Informe → ${SEL_DIR}"
"${PYTHON}" scripts/09_generar_informe_seleccion.py --seleccion "${SEL_DIR}" --baseline "${SEL_DIR}" --salida "${SEL_DIR}/informe_seleccion.md" || true

echo "[$(date -Iseconds)] Plan de revisión"
"${PYTHON}" scripts/10_generar_plan_revision.py --seleccion "${SEL_DIR}"

echo "[$(date -Iseconds)] Listo"
