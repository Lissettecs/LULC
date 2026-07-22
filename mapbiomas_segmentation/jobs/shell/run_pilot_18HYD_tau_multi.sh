#!/usr/bin/env bash
# Etiquetado C2 + fusión adyacente — tile 18HYD 2010, varios umbrales de pureza.
#
# Uso:
#   cd test/image_segmentation/segmentation_labels
#   bash run_pilot_18HYD_tau_multi.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="/home/lserey/mapbiomas_land/test/image_segmentation"
C2="${DATA_ROOT}/landcover_tiles/18HYD_classification_2010.tif"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_labels/bin/python}"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="/home/lserey/.conda/envs/mb_coverage/bin/python"
fi

declare -a TAUS=("0.90" "0.85" "0.80")

run_one() {
  local tau="$1"
  local tau_tag="$2"
  local name="$3"
  local seg="$4"
  local out="${DATA_ROOT}/labeling_tau${tau_tag}/tile_18HYD_2010/${name}"
  echo ""
  echo "========== τ=${tau} ${name} =========="
  "${PYTHON}" -u "${SCRIPT_DIR}/label_and_merge.py" \
    --segments-raster "${seg}" \
    --c2-raster "${C2}" \
    --out-dir "${out}" \
    --tau-purity "${tau}" \
    --write-raster
}

for tau in "${TAUS[@]}"; do
  tau_tag="${tau/./}"
  run_one "${tau}" "${tau_tag}" "felzenszwalb_s50_sig01" \
    "${DATA_ROOT}/seg_felzenszwalb/seg_18HYD_2010_s50_sig0.1.tif"
  run_one "${tau}" "${tau_tag}" "slic_s50_sig01_ragp10" \
    "${DATA_ROOT}/seg_slic/pipeline_a/seg_18HYD_2010_s50_sig0.1_ragp10.tif"
done

echo ""
echo "[OK] Etiquetado τ=0.90, 0.85, 0.80 → labeling_tau90|85|80/tile_18HYD_2010"
