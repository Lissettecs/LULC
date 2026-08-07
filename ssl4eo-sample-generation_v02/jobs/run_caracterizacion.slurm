#!/usr/bin/env bash
#SBATCH --job-name=caract_v02
#SBATCH --partition=main
#SBATCH --array=0-0%20
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=12G
#SBATCH --time=03:00:00
#SBATCH --output=logs/caract_%A_%a.out
#SBATCH --error=logs/caract_%A_%a.err

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

TILE=$("${PYTHON}" - <<'PY'
import os
from pathlib import Path
idx = int(os.environ["SLURM_ARRAY_TASK_ID"])
lines = Path("tiles.txt").read_text().splitlines()
print(lines[idx])
PY
)

echo "[$(date -Iseconds)] Tarea ${SLURM_ARRAY_TASK_ID} · tile ${TILE}"
"${PYTHON}" scripts/04_caracterizar_tile.py --tile "${TILE}" --resume
echo "[$(date -Iseconds)] Fin tile ${TILE}"
