#!/usr/bin/env bash
# SLIC + RAG hierarchical (merge_hierarchical, percentiles p10/p20) — tile 18HYD 2010.
#
# Grid: 2 scales × 1 sigma × 2 percentiles = 4 tareas RAG (+ SLIC si faltan).
#
# Submit array (una combinación por tarea):
#   cd labeling/image_segmentation/seg_slic
#   mkdir -p logs
#   sbatch --array=0-3 run_seg_slic_rag_hierarchical.slurm
#
# Submit todo en un solo job:
#   sbatch run_seg_slic_rag_hierarchical.slurm
#
# Solo RAG (SLIC ya existente en seg_slic/):
#   SOLO_RAG=1 sbatch run_seg_slic_rag_hierarchical.slurm
#
# Resume:
#   RESUME=1 sbatch run_seg_slic_rag_hierarchical.slurm

#SBATCH --job-name=seg_slic_hier
#SBATCH --partition=main
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=12:00:00
#SBATCH --output=logs/seg_slic_hier_%A_%a.out
#SBATCH --error=logs/seg_slic_hier_%A_%a.err

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

SOLO_RAG_FLAG=""
if [[ "${SOLO_RAG:-0}" == "1" ]]; then
  SOLO_RAG_FLAG="--solo-rag-hierarchical"
fi

echo "[INFO] host=$(hostname) partition=${SLURM_JOB_PARTITION:-?} job=${SLURM_JOB_ID:-local} task=${SLURM_ARRAY_TASK_ID:-all}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE} year=${YEAR} resume=${RESUME:-1} solo_rag=${SOLO_RAG:-0}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_grid.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  ${RESUME_FLAG} \
  ${COMBO_FLAG} \
  ${SOLO_RAG_FLAG}
