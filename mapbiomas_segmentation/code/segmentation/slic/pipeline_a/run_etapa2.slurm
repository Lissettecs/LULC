#!/usr/bin/env bash
# Pipeline A etapa 2: RAG hierarchical (p10/p20) — tile 18HYD 2010.
#
# Grid: 2 scales × 1 sigma × 2 percentiles = 4 tareas.
#
# Submit array:
#   cd labeling/image_segmentation/seg_slic/pipeline_a
#   sbatch --array=0-3 run_etapa2.slurm
#
# Resume:
#   RESUME=1 sbatch --array=0-3 run_etapa2.slurm

#SBATCH --job-name=seg_slic_a2
#SBATCH --partition=main
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=../logs/seg_slic_a2_%A_%a.out
#SBATCH --error=../logs/seg_slic_a2_%A_%a.err

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

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_pipeline_a.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --solo-rag-hierarchical \
  ${RESUME_FLAG} \
  ${COMBO_FLAG}
