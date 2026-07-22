#!/usr/bin/env bash
# Pipeline A etapa 3: size filter min150 (45 combos en paralelo).
#
# Submit:
#   cd labeling/image_segmentation/seg_slic/pipeline_a
#   sbatch run_etapa3.slurm
#
# Consolidar CSV tras el array:
#   sbatch --dependency=afterok:<JOBID> run_etapa3_csv.slurm

#SBATCH --job-name=seg_slic_a3
#SBATCH --partition=main
#SBATCH --array=0-44%15
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=04:00:00
#SBATCH --output=../logs/seg_slic_a3_%A_%a.out
#SBATCH --error=../logs/seg_slic_a3_%A_%a.err

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
COMBO_IDX="${SLURM_ARRAY_TASK_ID:?Falta SLURM_ARRAY_TASK_ID}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local} array=${COMBO_IDX}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE} year=${YEAR} combo_index=${COMBO_IDX}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_pipeline_a.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --solo-size-filter \
  --combo-index "${COMBO_IDX}" \
  --resume
