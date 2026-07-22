#!/usr/bin/env bash
# SLIC + RAG (percentiles) sobre tile 18HYD 2010.
#
# Submit:
#   cd labeling/image_segmentation/seg_slic
#   mkdir -p logs
#   sbatch run_seg_slic_grid.slurm
#
# Resume (omitir salidas existentes):
#   RESUME=1 sbatch run_seg_slic_grid.slurm

#SBATCH --job-name=seg_slic_rag
#SBATCH --partition=main
#SBATCH --cpus-per-task=8
#SBATCH --mem=64G
#SBATCH --time=24:00:00
#SBATCH --output=logs/seg_slic_rag_%j.out
#SBATCH --error=logs/seg_slic_rag_%j.err

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

echo "[INFO] host=$(hostname) partition=${SLURM_JOB_PARTITION:-?} job=${SLURM_JOB_ID:-local}"
echo "[INFO] python=$(${PYTHON} --version 2>&1)"
echo "[INFO] tile=${TILE} year=${YEAR} resume=${RESUME:-1}"

exec "${PYTHON}" -u "${SCRIPT_DIR}/seg_slic_grid.py" \
  --tile "${TILE}" \
  --year "${YEAR}" \
  ${RESUME_FLAG}
