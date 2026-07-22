#!/usr/bin/env bash
# Etiquetado C2 + fusión adyacente — 6 tiles MGRS 2010, τ = 0.95/0.90/0.85/0.80.
#
# Uso:
#   cd coverage_test/labeling/mapbiomas_segmentation/jobs/shell
#   bash run_all_tiles_tau.sh
#   bash run_all_tiles_tau.sh --force

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LABEL_CODE="${REPO_ROOT}/code/labeling"
DATA_ROOT="/home/lserey/mapbiomas_land/test/image_segmentation"
YEAR=2010
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_labels/bin/python}"
FORCE=0
LOG="${DATA_ROOT}/logs/run_all_tiles_tau.log"

if [[ ! -x "${PYTHON}" ]]; then
  PYTHON="/home/lserey/.conda/envs/mb_coverage/bin/python"
fi

if [[ "${1:-}" == "--force" ]]; then
  FORCE=1
fi

APPEND_LOG="${APPEND_LOG:-0}"
if [[ "${APPEND_LOG}" -eq 0 ]]; then
  : > "${LOG}"
fi

declare -a TILES=("18FXH" "18GXP" "18HYD" "19HCD" "19JCJ" "19KDU")
declare -a TAUS=("0.95" "0.90" "0.85" "0.80")

if [[ -n "${TILE:-}" ]]; then
  TILES=("${TILE}")
fi

tau_tag() {
  local tau="$1"
  if [[ "${tau}" == "0.95" ]]; then
    echo "95"
  else
    echo "${tau/./}"
  fi
}

run_one() {
  local tile="$1"
  local tau="$2"
  local name="$3"
  local seg="$4"
  local c2="${DATA_ROOT}/landcover_tiles/${tile}_classification_${YEAR}.tif"
  local out="${DATA_ROOT}/labeling_tau$(tau_tag "${tau}")/tile_${tile}_${YEAR}/${name}"

  if [[ ! -f "${seg}" ]]; then
    echo "[SKIP] Falta segmentación: ${seg}" | tee -a "${LOG}"
    return 0
  fi
  if [[ ! -f "${c2}" ]]; then
    echo "[SKIP] Falta C2: ${c2}" | tee -a "${LOG}"
    return 0
  fi
  if [[ "${FORCE}" -eq 0 && -f "${out}/summary.json" ]]; then
    echo "[SKIP] Ya existe: ${out}" | tee -a "${LOG}"
    return 0
  fi

  echo "" | tee -a "${LOG}"
  echo "========== tile=${tile} τ=${tau} ${name} $(date -Is) ==========" | tee -a "${LOG}"
  "${PYTHON}" -u "${LABEL_CODE}/label_and_merge.py" \
    --segments-raster "${seg}" \
    --c2-raster "${c2}" \
    --out-dir "${out}" \
    --tau-purity "${tau}" \
    --write-raster 2>&1 | tee -a "${LOG}"
}

echo "[START] $(date -Is) python=${PYTHON} tiles=${TILES[*]}" | tee -a "${LOG}"

for tile in "${TILES[@]}"; do
  felz="${DATA_ROOT}/seg_felzenszwalb/seg_${tile}_${YEAR}_s50_sig0.1.tif"
  slic="${DATA_ROOT}/seg_slic/pipeline_a/seg_${tile}_${YEAR}_s50_sig0.1_ragp10.tif"
  for tau in "${TAUS[@]}"; do
    run_one "${tile}" "${tau}" "felzenszwalb_s50_sig01" "${felz}"
    run_one "${tile}" "${tau}" "slic_s50_sig01_ragp10" "${slic}"
  done
done

echo "" | tee -a "${LOG}"
echo "[OK] Etiquetado completo $(date -Is)" | tee -a "${LOG}"
