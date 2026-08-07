#!/usr/bin/env bash
#SBATCH --job-name=selec_v02
#SBATCH --partition=main
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=logs/selec_%j.out
#SBATCH --error=logs/selec_%j.err

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

GRID_RUN="$(tr -d '\n' < .ultima_corrida_caract)"
echo "[INFO] Caracterización: ${GRID_RUN}"
# Sin --resume: aborta si colisiona el directorio de selección (regla no destructiva).
"${PYTHON}" scripts/07_seleccionar_rectangulos.py --grid-run-dir "${GRID_RUN}"
