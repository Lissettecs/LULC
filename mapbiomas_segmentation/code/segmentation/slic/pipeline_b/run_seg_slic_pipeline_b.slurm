#!/usr/bin/env bash
# Pipeline B: SLIC → RAG hierarchical → filtro tamaño selectivo — tile 18HYD 2010.
#
# Grid: 2 scales × 1 sigma × 2 percentiles = 4 combinaciones.
#
# Submit array (una combinación por tarea):
#   cd labeling/image_segmentation/seg_slic
#   mkdir -p logs
#   sbatch --array=0-3 run_seg_slic_pipeline_b.slurm
#
# Submit todo en un solo job:
#   sbatch run_seg_slic_pipeline_b.slurm
#
# Resume:
#   RESUME=1 sbatch run_seg_slic_pipeline_b.slurm

#SBATCH --job-name=seg_slic_pb
#SBATCH --partition=main
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/seg_slic_pb_%A_%a.out
#SBATCH --error=logs/seg_slic_pb_%A_%a.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
TILE="${TILE:-18HYD}"
YEAR="${YEAR:-2010}"
RESUME_FLAG=""
if [[ "${RESUME:-1}" == "1" ]]; then
  RESUME_FLAG="--resume"
fi

COMBO_FLAG=""
if [[ -n "${SLURM_ARRAY_TASK_ID:-}" ]]; then
  COMBO_FLAG="--combo-index ${SLURM_ARRAY_TASK_ID}"
fi

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local} task=${SLURM_ARRAY_TASK_ID:-all}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE} year=${YEAR} resume=${RESUME:-1}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_grid.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  ${RESUME_FLAG} \
  ${COMBO_FLAG}
