#!/bin/bash
# Login node: label all tiles with C2 (phase 1 subset → phase 2 full tile).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SEG_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

DATA_ROOT="${DATA_ROOT:-/home/lserey/mapbiomas_land/test/image_segmentation}"
PYTHON="${PYTHON:-${HOME}/.conda/envs/mb_coverage/bin/python3}"
YEAR="${YEAR:-2010}"
TAU_PERCENTILE="${TAU_PERCENTILE:-p75}"

TILES=(18HYD 18FXH 18GXP 19HCD 19JCJ 19KDU)
METHODS=(watershed slic felzenszwalb)

SUBSET_WINDOW="${SUBSET_WINDOW:-0 0 2000 2000}"
read -r COL ROW WIDTH HEIGHT <<< "${SUBSET_WINDOW}"

LOG_ROOT="${DATA_ROOT}/labeling/logs"
mkdir -p "${LOG_ROOT}"
MAIN_LOG="${LOG_ROOT}/run_all_tiles_labeling.log"
exec > >(tee -a "${MAIN_LOG}") 2>&1

export OMP_NUM_THREADS="${OMP_NUM_THREADS:-1}"
export OPENBLAS_NUM_THREADS="${OPENBLAS_NUM_THREADS:-1}"
export MKL_NUM_THREADS="${MKL_NUM_THREADS:-1}"
export NUMEXPR_NUM_THREADS="${NUMEXPR_NUM_THREADS:-1}"

echo "=== labeling batch start $(date -Iseconds) ==="
echo "DATA_ROOT=${DATA_ROOT}"
echo "TAU_PERCENTILE=${TAU_PERCENTILE}"

for TILE in "${TILES[@]}"; do
  SEG_TILE="${DATA_ROOT}/tile_${TILE}_${YEAR}"
  C2_RASTER="${DATA_ROOT}/landcover_tiles/${TILE}_classification_${YEAR}.tif"
  for METHOD in "${METHODS[@]}"; do
    SEGMENTS="${SEG_TILE}/${METHOD}_labels.tif"
    OUT_BASE="${DATA_ROOT}/labeling/tile_${TILE}_${YEAR}/${METHOD}"
    OUT_SUBSET="${OUT_BASE}/subset"
    OUT_FULL="${OUT_BASE}/full"

    echo
    echo "########## ${TILE} | ${METHOD} ##########"

    if [[ ! -f "${SEGMENTS}" ]]; then
      echo "SKIP missing segments: ${SEGMENTS}"
      continue
    fi
    if [[ ! -f "${C2_RASTER}" ]]; then
      echo "SKIP missing C2: ${C2_RASTER}"
      continue
    fi

    mkdir -p "${OUT_SUBSET}" "${OUT_FULL}"

    echo "--- phase 1: subset calibration ---"
    "${PYTHON}" "${SCRIPT_DIR}/label_segments.py" \
      --segments-raster "${SEGMENTS}" \
      --c2-raster "${C2_RASTER}" \
      --out-dir "${OUT_SUBSET}" \
      --subset \
      --subset-window "${COL}" "${ROW}" "${WIDTH}" "${HEIGHT}"

    PCT_JSON="${OUT_SUBSET}/purity_percentiles.json"
    TAU="$("${PYTHON}" -c "import json; print(json.load(open('${PCT_JSON}'))['${TAU_PERCENTILE}'])")"
    echo "auto tau (${TAU_PERCENTILE}) = ${TAU}"

    echo "--- phase 2: full tile ---"
    "${PYTHON}" "${SCRIPT_DIR}/label_segments.py" \
      --segments-raster "${SEGMENTS}" \
      --c2-raster "${C2_RASTER}" \
      --out-dir "${OUT_FULL}" \
      --no-subset \
      --tau-purity "${TAU}"
  done
done

echo
echo "=== labeling batch done $(date -Iseconds) ==="
"${PYTHON}" - <<'PY'
import json
from pathlib import Path

base = Path("/home/lserey/mapbiomas_land/test/image_segmentation/labeling")
tiles = ["18HYD", "18FXH", "18GXP", "19HCD", "19JCJ", "19KDU"]
methods = ["watershed", "slic", "felzenszwalb"]
print(f"{'tile':<8} {'method':<14} {'tau':>6} {'ok%':>6} {'mixed%':>7} {'n_seg':>7}")
for tile in tiles:
    for method in methods:
        summary = base / f"tile_{tile}_2010" / method / "full" / "assignment_summary.json"
        pct = base / f"tile_{tile}_2010" / method / "subset" / "purity_percentiles.json"
        if not summary.is_file():
            print(f"{tile:<8} {method:<14}  MISSING")
            continue
        s = json.loads(summary.read_text())
        tau = s.get("tau_purity", 0)
        n = s["n_segments"]
        ok = 100 * s["ok"] / n if n else 0
        mixed = 100 * s["mixed"] / n if n else 0
        print(f"{tile:<8} {method:<14} {tau:6.3f} {ok:5.1f}% {mixed:6.1f}% {n:7d}")
PY

echo "Results: ${DATA_ROOT}/labeling/"
echo "Log: ${MAIN_LOG}"
