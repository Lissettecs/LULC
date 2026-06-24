#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/activate_mb_labels.sh"
cd "${SCRIPT_DIR}/.."

LABELS_DIR="${LABELS_DIR:-/home/lserey/mapbiomas_land/prod/labels}"

python scripts/03_export_labels_gee_asset.py \
  --labels-dir "${LABELS_DIR}" \
  --group anuales \
  --overwrite
