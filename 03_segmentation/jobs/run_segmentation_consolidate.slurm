#!/usr/bin/env bash
#SBATCH --job-name=seg_consol
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${REV_YEAR}}"
MOSAIC_ROOT="${MOSAIC_ROOT:-${MAPBIOMAS_ROOT}/mosaic_184bands_mask_water/${YEAR}}"

"${PYTHON}" consolidate_run_summary.py \
  --rev-year "${REV_YEAR}" \
  --year "${YEAR}" \
  --output-dir "${OUTPUT_DIR}" \
  --mosaic-root "${MOSAIC_ROOT}"

echo "Consolidación segmentación rev${REV_YEAR} OK"
