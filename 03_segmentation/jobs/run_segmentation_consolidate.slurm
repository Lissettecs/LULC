#!/usr/bin/env bash
#SBATCH --job-name=seg_consol
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015/logs/slurm_seg_consolidate_%j.out
#SBATCH --error=/home/lserey/mapbiomas_land/prod/segmentacion_slic_rev2015/logs/slurm_seg_consolidate_%j.err

# Consolidate run_summary after array completes.
# Submit with: sbatch --dependency=afterok:ARRAY_JOBID jobs/run_segmentation_consolidate.slurm

set -euo pipefail

REPO="/home/lserey/repositorio/LULC/segmentacion"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:-/home/lserey/mapbiomas_land}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
MOSAIC_ROOT="${MOSAIC_ROOT:-${MAPBIOMAS_ROOT}/tmp/mask_mosaic_${YEAR}}"

"${PYTHON}" consolidate_run_summary.py \
  --rev-year "${REV_YEAR}" \
  --year "${YEAR}" \
  --output-dir "${OUTPUT_DIR}" \
  --mosaic-root "${MOSAIC_ROOT}"
