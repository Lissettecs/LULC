#!/usr/bin/env bash
#SBATCH --job-name=label_consol
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00

set -euo pipefail

PIPELINE="${SEGLABEL_PIPELINE:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
cd "${PIPELINE}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"
YEAR="${YEAR:-${REV_YEAR:-2015}}"

echo "Consolidating labeling rev${YEAR}…"
"${PYTHON}" "${PIPELINE}/consolidate_pipeline_outputs.py" \
  --rev-year "${YEAR}" \
  --year "${YEAR}" \
  --stage labeling

echo "Labeling consolidation OK"
