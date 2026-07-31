#!/usr/bin/env bash
#SBATCH --job-name=seg_slic
#SBATCH --partition=main
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --time=01:30:00
#SBATCH --array=0-51%16
#SBATCH --output=/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015/logs/slurm_seg_%A_%a.out
#SBATCH --error=/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015/logs/slurm_seg_%A_%a.err

# Parallel SLIC+RAG segmentation: one SSL4EO rectangle per array task.
#
# Recommended resources (partition main):
#   - 4 CPUs  : SLIC/RAG + numpy (matches mask_mosaic pilot jobs)
#   - 8G RAM  : rects 528–792 px (+100 buffer); peak << 2G observed bound
#   - 1h30    : safe per-rect wall time (largest ~627k valid px)
#   - %16     : up to 16 concurrent tasks (~4 waves for 52 rects)
#
# Submit workflow:
#   cd /home/lserey/repositorio/LULC/segmentacion
#   REV_YEAR=2015 ./jobs/prepare_segmentation_array.sh
#   N=$(wc -l < prod/.../logs/pending_rects_rev2015.lst)
#   sbatch --array=0-$((N-1))%16 --export=ALL jobs/run_segmentation_array.slurm
#   sbatch --dependency=afterok:JOBID jobs/run_segmentation_consolidate.slurm
#
# Override concurrency example (faster if cluster is idle):
#   sbatch --array=0-51%20 --export=ALL jobs/run_segmentation_array.slurm

set -euo pipefail

REPO="/home/lserey/repositorio/LULC/segmentacion"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:-/home/lserey/mapbiomas_land}"
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
  echo "ERROR: missing ${LIST} — run jobs/prepare_segmentation_array.sh first"
  exit 1
fi

N_LINES=$(grep -cve '^[[:space:]]*$' "${LIST}" || true)
if (( SLURM_ARRAY_TASK_ID >= N_LINES )); then
  echo "[SKIP] array task ${SLURM_ARRAY_TASK_ID} >= ${N_LINES} rectangles"
  exit 0
fi

GRID_ID=$(sed -n "$((SLURM_ARRAY_TASK_ID + 1))p" "${LIST}")
TILE="${GRID_ID%%_*}"
SUMMARY="${OUTPUT_DIR}/${TILE}/${GRID_ID}/${GRID_ID}_summary.json"

echo "[TASK ${SLURM_ARRAY_TASK_ID}] ${GRID_ID} on $(hostname) at $(date -Iseconds)"

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

echo "[OK] ${GRID_ID} finished at $(date -Iseconds)"
