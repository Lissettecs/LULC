#!/usr/bin/env bash
# Lista rectángulos segmentados sin etiquetado C2.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MAPBIOMAS_ROOT="${MAPBIOMAS_ROOT:?Defina MAPBIOMAS_ROOT}"
REV_YEAR="${REV_YEAR:-2015}"
YEAR="${YEAR:-${REV_YEAR}}"

SEG_DIR="${SEG_DIR:-${MAPBIOMAS_ROOT}/prod/03_segmentation_cim/${REV_YEAR}}"
LABEL_DIR="${LABEL_DIR:-${MAPBIOMAS_ROOT}/prod/04_labeling_cim/${YEAR}}"
LOG_DIR="${LOG_DIR:-${LABEL_DIR}/logs}"
LIST="${LIST:-${LOG_DIR}/pending_labeling_rev${YEAR}.lst}"

mkdir -p "${LOG_DIR}"
export SEG_DIR LABEL_DIR LIST YEAR

"${PYTHON}" - <<'PY'
import os
from pathlib import Path

seg = Path(os.environ["SEG_DIR"])
label = Path(os.environ["LABEL_DIR"])
year = os.environ.get("YEAR", "")
pending = []
skip = {"logs", "consolidado", "work"}
if seg.is_dir():
    for summary in sorted(seg.glob("*/*/*_summary.json")):
        if summary.parent.parent.name in skip:
            continue
        # Prefer year-aware segment summaries; skip labeling summaries if misplaced
        if summary.name.endswith("_labeling_summary.json"):
            continue
        grid_id = summary.parent.name
        tile = summary.parent.parent.name
        if year:
            done = label / tile / grid_id / f"{grid_id}_{year}_labeling_summary.json"
            done_legacy = label / tile / grid_id / f"{grid_id}_labeling_summary.json"
            if done.is_file() or done_legacy.is_file():
                continue
        else:
            done = label / tile / grid_id / f"{grid_id}_labeling_summary.json"
            if done.is_file():
                continue
        pending.append(grid_id)

path = Path(os.environ["LIST"])
path.write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
print(f"Pendientes etiquetado: {len(pending)} → {path}")
PY
