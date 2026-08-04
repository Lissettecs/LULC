#!/usr/bin/env bash
# List segmented rectangles without C2 labeling.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

PYTHON="${PYTHON:-python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Set MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"

SEG_DIR="${SEG_DIR:-${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev${REV_YEAR}}"
LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/labeling_slic_rev${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_labeling_rev${YEAR}.lst}"

mkdir -p "${LOG_DIR}"
export SEG_DIR LABEL_DIR LIST

"${PYTHON}" - <<'PY'
import os
from pathlib import Path

seg = Path(os.environ["SEG_DIR"])
label = Path(os.environ["LABEL_DIR"])
pending = []
if seg.is_dir():
    for summary in sorted(seg.glob("*/*/*_summary.json")):
        grid_id = summary.parent.name
        tile = summary.parent.parent.name
        done = label / tile / grid_id / f"{grid_id}_labeling_summary.json"
        if not done.is_file():
            pending.append(grid_id)

path = Path(os.environ["LIST"])
path.write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
print(f"Pending labeling: {len(pending)} → {path}")
PY
