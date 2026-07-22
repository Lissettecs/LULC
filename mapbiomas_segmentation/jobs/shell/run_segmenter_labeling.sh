#!/bin/bash
# Etiqueta polígonos de segmentadores (seg_*) con landcover Col2.
#
# Reutiliza label_segments.py del cluster (mapbiomas_land).
#
# Uso:
#   cd labeling/image_segmentation/segmentation_labels
#   bash run_segmenter_labeling.sh
#
# Variables: TILE SEG_YEAR LC_YEAR TAU_PERCENTILE OUT_ROOT

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

DATA_ROOT="${DATA_ROOT:-/home/lserey/mapbiomas_land/test/image_segmentation}"
LABEL_SCRIPT="${LABEL_SCRIPT:-${DATA_ROOT}/segmentation_labels/label_segments.py}"
PYTHON="${PYTHON:-${HOME}/.conda/envs/mb_labels/bin/python3}"

TILE="${TILE:-18HYD}"
SEG_YEAR="${SEG_YEAR:-2010}"
LC_YEAR="${LC_YEAR:-2015}"
TAU_PERCENTILE="${TAU_PERCENTILE:-p75}"
OUT_ROOT="${OUT_ROOT:-${DATA_ROOT}/labeling_segmenters}"
SUBSET_WINDOW="${SUBSET_WINDOW:-0 0 2000 2000}"
read -r COL ROW WIDTH HEIGHT <<< "${SUBSET_WINDOW}"

C2_RASTER="${DATA_ROOT}/landcover_tiles/${TILE}_classification_${LC_YEAR}.tif"
LOG_ROOT="${OUT_ROOT}/logs"
mkdir -p "${LOG_ROOT}"
MAIN_LOG="${LOG_ROOT}/run_segmenter_labeling_${TILE}_${SEG_YEAR}_lc${LC_YEAR}.log"
exec > >(tee -a "${MAIN_LOG}") 2>&1

echo "=== etiquetado segmentadores $(date -Iseconds) ==="
echo "tile=${TILE} segmentos=${SEG_YEAR} landcover=${LC_YEAR}"
echo "salida=${OUT_ROOT}"

if [[ ! -f "${LABEL_SCRIPT}" ]]; then
  echo "[ERROR] No se encuentra label_segments.py: ${LABEL_SCRIPT}"
  exit 1
fi

if [[ ! -f "${C2_RASTER}" ]]; then
  echo "[INFO] Preparando landcover ${LC_YEAR}..."
  "${PYTHON}" "${SCRIPT_DIR}/prepare_landcover_tile.py" --tile "${TILE}" --year "${LC_YEAR}"
fi

SEGMENTERS=(
  "felzenszwalb_3b|seg_felzenszwalb/seg_${TILE}_${SEG_YEAR}_s200_sig0.1.tif"
  "felzenszwalb_rf_n|seg_felzenszwalb_rf_n/seg_${TILE}_${SEG_YEAR}_lv1_rfn_s200_sig0.1.tif"
  "felzenszwalb_rfn_podado|seg_felzenszwalb_rfn/seg_rfn_${TILE}_${SEG_YEAR}_s200_sig0.1.tif"
  "slic_pipeline_b|seg_slic/pipeline_b/seg_${TILE}_${SEG_YEAR}_s100_sig0.1_hier_p10_min150.tif"
  "ablacion_medianas|seg_felzenszwalb_ablacion/seg_abl_${TILE}_${SEG_YEAR}_medianas.tif"
)

for ENTRY in "${SEGMENTERS[@]}"; do
  METHOD="${ENTRY%%|*}"
  REL_PATH="${ENTRY#*|}"
  SEGMENTS="${DATA_ROOT}/${REL_PATH}"
  OUT_BASE="${OUT_ROOT}/tile_${TILE}_${SEG_YEAR}_lc${LC_YEAR}/${METHOD}"
  OUT_SUBSET="${OUT_BASE}/subset"
  OUT_FULL="${OUT_BASE}/full"

  echo
  echo "########## ${METHOD} ##########"

  if [[ ! -f "${SEGMENTS}" ]]; then
    echo "SKIP — no existe: ${SEGMENTS}"
    continue
  fi

  mkdir -p "${OUT_SUBSET}" "${OUT_FULL}"

  echo "--- fase 1: calibración pureza ---"
  (cd "${DATA_ROOT}" && "${PYTHON}" "${LABEL_SCRIPT}" \
    --segments-raster "${SEGMENTS}" \
    --c2-raster "${C2_RASTER}" \
    --out-dir "${OUT_SUBSET}" \
    --subset \
    --subset-window "${COL}" "${ROW}" "${WIDTH}" "${HEIGHT}")

  TAU="$("${PYTHON}" -c "import json; print(json.load(open('${OUT_SUBSET}/purity_percentiles.json'))['${TAU_PERCENTILE}'])")"
  echo "tau (${TAU_PERCENTILE}) = ${TAU}"

  echo "--- fase 2: tile completo ---"
  (cd "${DATA_ROOT}" && "${PYTHON}" "${LABEL_SCRIPT}" \
    --segments-raster "${SEGMENTS}" \
    --c2-raster "${C2_RASTER}" \
    --out-dir "${OUT_FULL}" \
    --no-subset \
    --tau-purity "${TAU}")
done

echo
echo "=== resumen ==="
"${PYTHON}" - <<PY
import json
from pathlib import Path

base = Path("${OUT_ROOT}") / "tile_${TILE}_${SEG_YEAR}_lc${LC_YEAR}"
if not base.is_dir():
    print("(sin salidas)")
    raise SystemExit(0)
print(f"{'method':<22} {'tau':>6} {'ok%':>6} {'mixed%':>7} {'n_seg':>8}")
for sub in sorted(base.iterdir()):
    sfile = sub / "full" / "assignment_summary.json"
    if not sfile.is_file():
        continue
    s = json.loads(sfile.read_text())
    n = s["n_segments"]
    ok = 100 * s["ok"] / n if n else 0
    mixed = 100 * s["mixed"] / n if n else 0
    print(f"{sub.name:<22} {s['tau_purity']:6.3f} {ok:5.1f}% {mixed:6.1f}% {n:8d}")
PY

echo "GPKG: ${OUT_ROOT}/tile_${TILE}_${SEG_YEAR}_lc${LC_YEAR}/*/full/segments_labeled.gpkg"
