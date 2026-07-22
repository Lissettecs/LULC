#!/usr/bin/env bash
# Piloto: etiquetado C2 τ=0.95 + fusión adyacente misma clase — tile 18HYD 2010.
#
# Segmentadores:
#   Felzenszwalb  s=50 σ=0.1
#   SLIC + RAG    s=50 σ=0.1 p10
#
# Uso:
#   cd test/image_segmentation/segmentation_labels
#   bash run_pilot_18HYD_tau95.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="/home/lserey/mapbiomas_land/test/image_segmentation"
C2="${DATA_ROOT}/landcover_tiles/18HYD_classification_2010.tif"
OUT_ROOT="${DATA_ROOT}/labeling_tau95/tile_18HYD_2010"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_labels/bin/python}"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="/home/lserey/.conda/envs/mb_coverage/bin/python"
fi

run_one() {
  local name="$1"
  local seg="$2"
  local out="${OUT_ROOT}/${name}"
  echo ""
  echo "========== ${name} =========="
  "${PYTHON}" -u "${SCRIPT_DIR}/label_and_merge.py" \
    --segments-raster "${seg}" \
    --c2-raster "${C2}" \
    --out-dir "${out}" \
    --tau-purity 0.95 \
    --write-raster
}

run_one "felzenszwalb_s50_sig01" \
  "${DATA_ROOT}/seg_felzenszwalb/seg_18HYD_2010_s50_sig0.1.tif"

run_one "slic_s50_sig01_ragp10" \
  "${DATA_ROOT}/seg_slic/pipeline_a/seg_18HYD_2010_s50_sig0.1_ragp10.tif"

echo ""
echo "[OK] Piloto completo → ${OUT_ROOT}"
