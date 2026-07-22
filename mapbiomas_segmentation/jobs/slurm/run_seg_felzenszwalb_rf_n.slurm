#!/usr/bin/env bash
# Pipeline Felzenszwalb RF_N — bandas seleccionadas Random Forest.
#
# 15 combos = 5 scales × 3 sigmas. Cada tarea del array = 1 combo (paralelizable).
#
# Submit combos restantes (resume omite los ya hechos):
#   sbatch --array=0,2-14%8 run_seg_felzenszwalb_rf_n.slurm
#
# Grid (índice → scale, σ):
#   0-2: scale=25  |  3-5: scale=50  |  6-8: scale=100  |  9-11: scale=150  |  12-14: scale=200
#   σ por grupo: 0.1, 0.5, 0.8
#
# Parámetros orientados a velocidad:
#   - %8 paralelo (scales ≥50 terminan mucho antes que scale=25)
#   - cpus=2 (Felzenszwalb no usa multi-hilo; menos CPUs = cola más rápida)
#   - mem=32G (39 bandas + scale=25 requieren ~22 GB pico)
#   - time=01:30:00 (suficiente salvo scale=25)
# Consolidar CSV:
#   python consolidar_rf_n_csv.py --tile 18HYD --year 2010

#SBATCH --job-name=seg_felz_rfn
#SBATCH --partition=main
#SBATCH --array=0-14%8
#SBATCH --cpus-per-task=2
#SBATCH --mem=32G
#SBATCH --time=01:30:00
#SBATCH --output=../logs/seg_felz_rfn_%A_%a.out
#SBATCH --error=../logs/seg_felz_rfn_%A_%a.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/../logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
TILE="${TILE:-18HYD}"
YEAR="${YEAR:-2010}"
RF_LEVEL="${RF_LEVEL:-1}"
COMBO_IDX="${SLURM_ARRAY_TASK_ID:-0}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local} array=${COMBO_IDX}"
echo "[INFO] tile=${TILE} year=${YEAR} rf_level=${RF_LEVEL} combo=${COMBO_IDX}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_felzenszwalb_rf_n_grid.py" \
  --rf-level "${RF_LEVEL}" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --combo-index "${COMBO_IDX}" \
  --resume
