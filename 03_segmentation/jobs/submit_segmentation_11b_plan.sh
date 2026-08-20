#!/usr/bin/env bash
# Prepare pending YEAR\tGRID_ID list for 11B masked mosaics + pendientes sin mosaico.
# Also submits SLURM array. Parquet off by default for 11B (FEATURES_PARQUET=0).
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"

BASE="${MAPBIOMAS_ROOT:-/home/lserey/mapbiomas_land}"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python3}"
MOSAIC_KIND="${MOSAIC_KIND:-11b}"
MOSAIC_ROOT="${MOSAIC_ROOT:-${BASE}/mosaic_11bands_mask_water}"
BAND_LAYOUT="${BAND_LAYOUT:-11b}"
FEATURES_PARQUET="${FEATURES_PARQUET:-0}"
ARRAY_THROTTLE="${ARRAY_THROTTLE:-8}"
GPKG="${GPKG_SELECCION:-${BASE}/prod/samples_cim/02_seleccion/20260806_2221/plan_revision_20260808_1526/seleccion_con_rev_years.gpkg}"
OUT_ROOT="${OUTPUT_ROOT:-${BASE}/prod/03_segmentation_cim}"
LOG_DIR="${LOG_DIR:-${OUT_ROOT}/logs}"
LIST_READY="${LIST_READY:-${OUT_ROOT}/pending_segmentation_11b.lst}"
LIST_PENDING="${LIST_PENDING:-${OUT_ROOT}/pending_no_mosaic_11b.lst}"

mkdir -p "${LOG_DIR}" "${OUT_ROOT}"

export BASE MOSAIC_ROOT GPKG OUT_ROOT LIST_READY LIST_PENDING PYTHON
"${PYTHON}" - <<'PY'
from __future__ import annotations

import os
import re
from collections import defaultdict
from pathlib import Path

import geopandas as gpd

mosaic_root = Path(os.environ["MOSAIC_ROOT"])
gpkg = Path(os.environ["GPKG"])
out_root = Path(os.environ["OUT_ROOT"])
list_ready = Path(os.environ["LIST_READY"])
list_pending = Path(os.environ["LIST_PENDING"])

avail = defaultdict(set)
for p in mosaic_root.glob("*/*_masked.tif"):
    m = re.match(r"CHILE-(.+)-(\d{4})-", p.name)
    if m:
        avail[int(m.group(2))].add(m.group(1))

g = gpd.read_file(gpkg)
g["_tile"] = g["grid_id"].astype(str).str.split("_").str[0]

ready: list[str] = []
pending: list[str] = []
seen_ready: set[tuple[int, str]] = set()
seen_pend: set[tuple[int, str]] = set()

for _, row in g.iterrows():
    gid = str(row["grid_id"])
    tile = str(row["_tile"])
    for i in (1, 2, 3):
        try:
            y = int(row[f"rev_year{i}"])
        except Exception:
            continue
        if y <= 0:
            continue
        key = (y, gid)
        summ = out_root / str(y) / tile / gid / f"{gid}_{y}_summary.json"
        if tile in avail.get(y, set()):
            if summ.is_file():
                continue
            if key not in seen_ready:
                ready.append(f"{y}\t{gid}")
                seen_ready.add(key)
        else:
            if key not in seen_pend:
                pending.append(f"{y}\t{gid}\t{tile}\tsin_mosaico_11b_mask")
                seen_pend.add(key)

list_ready.write_text("\n".join(ready) + ("\n" if ready else ""), encoding="utf-8")
list_pending.write_text("\n".join(pending) + ("\n" if pending else ""), encoding="utf-8")
print(f"Listos a segmentar (11B mask): {len(ready)} → {list_ready}")
print(f"Pendientes sin mosaico:       {len(pending)} → {list_pending}")
by = defaultdict(int)
for line in ready:
    by[int(line.split("\t")[0])] += 1
print("Por año:", dict(sorted(by.items())))
PY

N=$(grep -cve '^[[:space:]]*$' "${LIST_READY}" || true)
if (( N == 0 )); then
  echo "Nada pendiente de segmentación 11B."
  exit 0
fi

MAX=$((N - 1))
echo "Enviando array segmentación 0-${MAX}%${ARRAY_THROTTLE} (${N} tareas)"
echo "  MOSAIC_ROOT=${MOSAIC_ROOT} MOSAIC_KIND=${MOSAIC_KIND}"
echo "  FEATURES_PARQUET=${FEATURES_PARQUET} BAND_LAYOUT=${BAND_LAYOUT}"

JOBID=$(sbatch --parsable \
  --chdir="${REPO}" \
  --array="0-${MAX}%${ARRAY_THROTTLE}" \
  --output="${LOG_DIR}/slurm_seg11b_%A_%a.out" \
  --error="${LOG_DIR}/slurm_seg11b_%A_%a.err" \
  --export=ALL,MAPBIOMAS_ROOT="${BASE}",MOSAIC_ROOT="${MOSAIC_ROOT}",MOSAIC_KIND="${MOSAIC_KIND}",BAND_LAYOUT="${BAND_LAYOUT}",FEATURES_PARQUET="${FEATURES_PARQUET}",LIST="${LIST_READY}",SEGLABEL_REPO="${REPO}",PYTHON="${PYTHON}" \
  jobs/run_segmentation_array.slurm)

echo "Segmentation array: ${JOBID}"
echo "JOBID=${JOBID}"
