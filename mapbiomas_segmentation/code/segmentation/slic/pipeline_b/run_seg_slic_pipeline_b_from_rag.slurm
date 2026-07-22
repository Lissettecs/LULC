#!/usr/bin/env bash
# Pipeline B etapa 3 solamente: lee post-RAG desde pipeline_a/rag_hierarchical/ y aplica min150.
#
# Grid: 2 scales × 1 sigma × 2 percentiles = 4 combinaciones.
#
# Submit:
#   cd labeling/image_segmentation/seg_slic
#   mkdir -p logs
#   sbatch --array=0-3 run_seg_slic_pipeline_b_from_rag.slurm
#
# Consolidar CSV tras el array (opcional):
#   python consolidar_pipeline_b_csv.py --tile 18HYD --year 2010

#SBATCH --job-name=seg_slic_pb3
#SBATCH --partition=main
#SBATCH --array=0-3%1
#SBATCH --cpus-per-task=4
#SBATCH --mem=32G
#SBATCH --time=08:00:00
#SBATCH --output=logs/seg_slic_pb3_%A_%a.out
#SBATCH --error=logs/seg_slic_pb3_%A_%a.err

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
RAG_DIR="${RAG_DIR:-/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/rag_hierarchical}"
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
echo "[INFO] tile=${TILE} year=${YEAR} rag_dir=${RAG_DIR} resume=${RESUME:-1}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_grid.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  --from-rag-dir "${RAG_DIR}" \
  ${RESUME_FLAG} \
  ${COMBO_FLAG}
