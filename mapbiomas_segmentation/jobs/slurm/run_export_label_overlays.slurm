#!/usr/bin/env bash
# Export Col2 label overlays (PNG + assignment JSON) para segmentadores.
#
# Uso:
#   cd labeling/image_segmentation/segmentation_labels
#   sbatch run_export_label_overlays.slurm
#   SEGMENTER=felzenszwalb_rf_n LC_YEAR=2010 sbatch run_export_label_overlays.slurm
#
# Múltiples segmentadores (repetir variable o editar SEGMENTERS):
#   SEGMENTERS="felzenszwalb_rf_n slic" sbatch run_export_label_overlays.slurm

#SBATCH --job-name=export_labels
#SBATCH --partition=main
#SBATCH --cpus-per-task=2
#SBATCH --mem=24G
#SBATCH --time=02:00:00
#SBATCH --output=../logs/export_labels_%j.out
#SBATCH --error=../logs/export_labels_%j.err

set -euo pipefail

SCRIPT_DIR="${SLURM_SUBMIT_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
mkdir -p "${SCRIPT_DIR}/../logs"

if [[ -f /home/lserey/mapbiomas_land/activar_grupo.sh ]]; then
  # shellcheck disable=SC1091
  source /home/lserey/mapbiomas_land/activar_grupo.sh
fi

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
TILE="${TILE:-18HYD}"
SEG_YEAR="${SEG_YEAR:-2010}"
LC_YEAR="${LC_YEAR:-2010}"
SEGMENTER="${SEGMENTER:-felzenszwalb_rf_n}"
RERENDER_PNG="${RERENDER_PNG:-0}"

echo "[INFO] host=$(hostname) job=${SLURM_JOB_ID:-local}"
echo "[INFO] tile=${TILE} seg_year=${SEG_YEAR} lc_year=${LC_YEAR} segmenter=${SEGMENTER}"

CMD=(
  "${PYTHON}" -u "${SCRIPT_DIR}/export_label_overlays.py"
  --tile "${TILE}"
  --seg-year "${SEG_YEAR}"
  --lc-year "${LC_YEAR}"
  --segmenter "${SEGMENTER}"
  --resume
)

if [[ "${RERENDER_PNG}" == "1" ]]; then
  CMD+=(--rerender-png)
fi

exec "${CMD[@]}"
