#!/usr/bin/env bash
#SBATCH --job-name=seleccion_cim
#SBATCH --partition=main
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/seleccion_%j.out
#SBATCH --error=logs/seleccion_%j.err

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/02_split"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

echo "[$(date -Iseconds)] Presupuesto (dry-run)"
"${PYTHON}" scripts/06_presupuesto_seleccion.py

echo "[$(date -Iseconds)] Selección"
"${PYTHON}" scripts/07_seleccionar_rectangulos.py

echo "[$(date -Iseconds)] Informe"
SEL_DIR="$(ls -td /home/lserey/mapbiomas_land/prod/samples_cim/02_seleccion/*/ | head -1)"
"${PYTHON}" scripts/09_generar_informe_seleccion.py --seleccion "${SEL_DIR}" --baseline "${SEL_DIR}" --salida "${SEL_DIR}/informe_seleccion.md" || true

echo "[$(date -Iseconds)] Plan de revisión"
"${PYTHON}" scripts/10_generar_plan_revision.py --seleccion "${SEL_DIR}"

echo "[$(date -Iseconds)] Listo → ${SEL_DIR}"
