#!/usr/bin/env bash
#SBATCH --job-name=label_consol
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:30:00

set -euo pipefail

PIPELINE="${SEGLABEL_PIPELINE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PIPELINE}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
YEAR="${YEAR:-${REV_YEAR:-2015}}"
LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/04_labeling_cim/${YEAR}}"

echo "Consolidando etiquetado → ${LABEL_DIR}/consolidado/"
"${PYTHON}" "${PIPELINE}/consolidate_pipeline_outputs.py" \
  --rev-year "${YEAR}" \
  --year "${YEAR}" \
  --labeling-dir "${LABEL_DIR}" \
  --stage labeling

echo "Consolidación etiquetado OK"
