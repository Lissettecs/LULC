#!/usr/bin/env bash
# Pipeline A etapa 1 — RAG threshold (p10/p20/p30) sobre SLIC s=50 σ=0.1 ya existente.
#
# Tiles: 18FXH 18GXP 19HCD 19JCJ 19KDU  (18HYD ya tiene RAG)
# Reutiliza seg_{tile}_2010_s50_sig0.1.tif/.png (--resume).
#
# Uso:
#   cd labeling/image_segmentation/seg_slic/pipeline_a
#   mkdir -p ../logs
#   sbatch run_etapa1_s50_batch.slurm

#SBATCH --job-name=slic_a1_s50
#SBATCH --partition=main
#SBATCH --array=0-4%5
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=../logs/slic_a1_s50_%A_%a.out
#SBATCH --error=../logs/slic_a1_s50_%A_%a.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/../logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

TILES=(18FXH 18GXP 19HCD 19JCJ 19KDU)
YEAR="${YEAR:-2010}"
SCALE="${SCALE:-50}"
SIGMA="${SIGMA:-0.1}"
TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
TILE="${TILES[$TASK_ID]}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID} array=${TASK_ID}"
echo "[INFO] tile=${TILE} year=${YEAR} scale=${SCALE} sigma=${SIGMA}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_pipeline_a.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --scale "${SCALE}" \
  --sigma "${SIGMA}" \
  --resume
