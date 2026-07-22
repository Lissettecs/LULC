#!/usr/bin/env bash
# Pipeline A — RAG threshold p10 sobre SLIC s=50 σ=0.1 existente.
#
# Tiles pendientes (18FXH y 19JCJ ya tienen ragp10):
#   18GXP  19HCD  19KDU
#
# Requiere fix NaN en seg_slic/common.py (construir_features + _feats_para_rag).
#
# Uso:
#   cd labeling/image_segmentation/seg_slic/pipeline_a
#   mkdir -p ../logs
#   sbatch run_ragp10_s50_batch.slurm
#
# Un solo tile:
#   TILE=19KDU sbatch --array=2 run_ragp10_s50_batch.slurm

#SBATCH --job-name=slic_ragp10
#SBATCH --partition=main
#SBATCH --array=0-2%3
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=01:30:00
#SBATCH --output=../logs/slic_ragp10_%A_%a.out
#SBATCH --error=../logs/slic_ragp10_%A_%a.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/../logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

TILES=(18GXP 19HCD 19KDU)
YEAR="${YEAR:-2010}"
SCALE="${SCALE:-50}"
SIGMA="${SIGMA:-0.1}"
RAG_PCT="${RAG_PCT:-10}"
TASK_ID="${SLURM_ARRAY_TASK_ID:-0}"
TILE="${TILE:-${TILES[$TASK_ID]}}"

OUT_DIR="/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a"
OUT_TIF="${OUT_DIR}/seg_${TILE}_${YEAR}_s${SCALE}_sig0.1_ragp${RAG_PCT}.tif"
if [[ -f "${OUT_TIF}" ]] && [[ "${FORCE:-0}" != "1" ]]; then
  echo "[INFO] Ya existe ${OUT_TIF}; omitir (FORCE=1 para recalcular)"
  exit 0
fi

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local} array=${TASK_ID}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE} year=${YEAR} scale=${SCALE} sigma=${SIGMA} ragp=${RAG_PCT}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_pipeline_a.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --scale "${SCALE}" \
  --sigma "${SIGMA}" \
  --rag-percentil "${RAG_PCT}" \
  --resume
