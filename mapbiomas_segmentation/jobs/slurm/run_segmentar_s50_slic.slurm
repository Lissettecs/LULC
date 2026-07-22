#!/usr/bin/env bash
# SLIC s=50 σ=0.1 — tiles pendientes (camino rápido: mediana + sin mask).
#
# Tareas array (mismo mapa que run_segmentar_s50_sig01.slurm):
#   1=18FXH  3=18GXP  5=19HCD  7=19JCJ  9=19KDU
#
# Uso:
#   sbatch run_segmentar_s50_slic.slurm
#   sbatch --array=1,3,5,7,9%5 run_segmentar_s50_slic.slurm

#SBATCH --job-name=seg_s50_slic
#SBATCH --partition=main
#SBATCH --array=1,3,5,7,9%5
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=logs/seg_s50_slic_%A_%a.out
#SBATCH --error=logs/seg_s50_slic_%A_%a.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
ANIO="${ANIO:-2010}"
SCALE="${SCALE:-50}"
SIGMA="${SIGMA:-0.1}"

TILES=(18FXH 18GXP 19HCD 19JCJ 19KDU)
SEGS=(felzenszwalb slic)

TASK_ID="${SLURM_ARRAY_TASK_ID:-1}"
TILE_IDX=$((TASK_ID / 2))
SEG_IDX=$((TASK_ID % 2))
TILE="${TILES[$TILE_IDX]}"
SEG="${SEGS[$SEG_IDX]}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID} array=${TASK_ID}"
echo "[INFO] tile=${TILE} segmentador=${SEG} scale=${SCALE} sigma=${SIGMA} anio=${ANIO}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/eval_escala_optima.py" \
  --segmentar \
  --scale-seg "${SCALE}" \
  --sigma "${SIGMA}" \
  --anio "${ANIO}" \
  --tile "${TILE}" \
  --segmentadores "${SEG}"
