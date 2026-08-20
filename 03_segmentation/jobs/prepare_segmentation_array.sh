#!/usr/bin/env bash
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"
MOSAIC_KIND="${MOSAIC_KIND:-184_mask_water}"
MOSAIC_ROOT="${MOSAIC_ROOT:-}"
OUTPUT_DIR="${OUTPUT_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${REV_YEAR}}"
LOG_DIR="${LOG_DIR:-${OUTPUT_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_rects_rev${REV_YEAR}.lst}"

mkdir -p "${LOG_DIR}"
export REV_YEAR YEAR OUTPUT_DIR LIST PYTHON MOSAIC_KIND MOSAIC_ROOT

PLAN_ARGS=(
  --rev-year "${REV_YEAR}"
  --year "${YEAR}"
  --output-dir "${OUTPUT_DIR}"
  --require-mosaic
  --skip-existing
  --export-plan "${OUTPUT_DIR}/plan_rev${REV_YEAR}.json"
)
[[ -n "${MOSAIC_ROOT}" ]] && PLAN_ARGS+=(--mosaic-root "${MOSAIC_ROOT}")
[[ -n "${MOSAIC_KIND}" ]] && PLAN_ARGS+=(--mosaic-kind "${MOSAIC_KIND}")

"${PYTHON}" plan_segmentation.py "${PLAN_ARGS[@]}" >/dev/null

"${PYTHON}" - <<'PY'
import json
from pathlib import Path
import os

rev = os.environ["REV_YEAR"]
out = Path(os.environ["OUTPUT_DIR"])
plan = json.loads((out / f"plan_rev{rev}.json").read_text(encoding="utf-8"))
ids = [
    r["grid_id"]
    for r in plan["rects"]
    if r.get("mosaic_ok") and not r.get("already_processed")
]
path = Path(os.environ["LIST"])
path.write_text("\n".join(ids) + ("\n" if ids else ""), encoding="utf-8")
print(f"Pendientes segmentación: {len(ids)} → {path}")
PY
