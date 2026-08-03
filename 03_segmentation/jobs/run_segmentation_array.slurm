#!/usr/bin/env bash
# Logs SLURM: pasar --output/--error al sbatch (ver submit_*.sh).
#SBATCH --job-name=seg_slic
#SBATCH --partition=main
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:30:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT (see env.example)}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
MOSAIC_ROOT="${MOSAIC_ROOT:-${MAPBIOMAS_ROOT}/tmp/mask_mosaic_${YEAR}}"
LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_rects_rev${REV_YEAR}.lst}"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export MKL_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export OPENBLAS_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"
export NUMEXPR_NUM_THREADS="${SLURM_CPUS_PER_TASK:-4}"

if [[ ! -s "${LIST}" ]]; then
  echo "ERROR: missing ${LIST} — run jobs/prepare_segmentation_array.sh"
  exit 1
fi

N_LINES=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( SLURM_ARRAY_TASK_ID >= N_LINES )); then
  echo "[SKIP] task ${SLURM_ARRAY_TASK_ID} >= ${N_LINES} rectangles"
  exit 0
fi

GRID_ID=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "${LIST}")
TILE="${GRID_ID%%_*}"
SUMMARY="${OUTPUT_DIR}/${TILE}/${GRID_ID}/${GRID_ID}_summary.json"

echo "[TASK ${SLURM_ARRAY_TASK_ID}] ${GRID_ID} on $(hostname) · $(date -Iseconds)"

if [[ -f "${SUMMARY}" ]]; then
  echo "[SKIP] already processed: ${SUMMARY}"
  exit 0
fi

"${PYTHON}" run_slic_segmentation.py \
  --rev-year "${REV_YEAR}" \
  --year "${YEAR}" \
  --mosaic-root "${MOSAIC_ROOT}" \
  --output-dir "${OUTPUT_DIR}" \
  --grid-id "${GRID_ID}"

echo "[OK] ${GRID_ID} · $(date -Iseconds)"
