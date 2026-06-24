#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

python scripts/00_check_inputs.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2
