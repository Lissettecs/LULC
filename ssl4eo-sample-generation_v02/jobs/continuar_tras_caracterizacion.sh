#!/usr/bin/env bash
# Continúa el pipeline v03 cuando termina lanzar_por_lotes.sh
# Uso: bash jobs/continuar_tras_caracterizacion.sh
set -euo pipefail

REPO="/home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

LOG="logs/continuar_v03_$(date +%Y%m%d_%H%M).log"
exec > >(tee -a "${LOG}") 2>&1

echo "[$(date)] Esperando fin de lanzar_por_lotes.sh…"
while pgrep -f 'bash jobs/lanzar_por_lotes.sh' >/dev/null 2>&1; do
  sleep 60
  n=$(ls "$(cat .ultima_corrida_caract | tr -d '\n')/por_tile" 2>/dev/null | wc -l || echo 0)
  echo "[$(date)]   launcher activo · parquet=${n}"
done

CARACT=$(cat .ultima_corrida_caract | tr -d '\n')
echo "[$(date)] Caracterización finalizada: ${CARACT}"
ls "${CARACT}/consolidado/" 2>/dev/null || {
  echo "[$(date)] ERROR: sin consolidado en ${CARACT}"
  exit 1
}

echo "[$(date)] Verificación rápida suma pct / ha…"
"${PYTHON}" - <<PY
from pathlib import Path
import pandas as pd
car = Path("${CARACT}") / "por_tile"
files = list(car.glob("*.parquet"))[:30]
assert files, "sin parquet"
bad = 0
for f in files:
    df = pd.read_parquet(f)
    pct = [c for c in df.columns if c.startswith("pct_") and c[4:].isdigit()]
    if not pct:
        continue
    s = df[pct].sum(axis=1)
    bad += int(((s < 99.9) | (s > 100.1)).sum())
    assert "pct_0" not in df.columns
print(f"OK: {len(files)} tiles muestreados, filas fuera de rango={bad}")
if bad:
    raise SystemExit(1)
PY

echo "[$(date)] Dry-run presupuesto…"
"${PYTHON}" main.py seleccionar --etapa presupuesto --dry-run

echo "[$(date)] Lanzando selección en partition=main…"
JOBID=$(sbatch --parsable jobs/run_seleccion.slurm)
echo "[$(date)] job selección ${JOBID}"
while squeue -j "${JOBID}" -h >/dev/null 2>&1; do
  sleep 60
  echo "[$(date)]   selección ${JOBID} activa"
done
sacct -j "${JOBID}" --format=JobID,State,ExitCode,Elapsed,MaxRSS | tee -a "${LOG}"
STATE=$(sacct -j "${JOBID}" --format=State --noheader -P | head -1 | cut -d'|' -f1)
[[ "${STATE}" == "COMPLETED" ]] || { echo "ERROR: selección terminó en ${STATE}"; exit 1; }

SEL=$(ls -td /home/lserey/mapbiomas_land/prod/samples_v02/02_seleccion/2026* 2>/dev/null | head -1)
echo "[$(date)] Selección en ${SEL}"

echo "[$(date)] Tests de aceptación nacional…"
CARACT_RUN_TAG=$(basename "${CARACT}") SEL_RUN_TAG=$(basename "${SEL}") \
  "${PYTHON}" -m pytest tests/test_aceptacion_nacional.py -q --tb=line

echo "[$(date)] Generando informe vs baseline 20260724_1357…"
"${PYTHON}" scripts/09_generar_informe_seleccion.py \
  --seleccion "$(basename "${SEL}")" \
  --baseline 20260724_1357 \
  --caracterizacion "$(basename "${CARACT}")"

echo "[$(date)] Pipeline v03 completo."
echo "  Caracterización: ${CARACT}"
echo "  Selección:       ${SEL}"
echo "  Informe:         ${SEL}/informe_seleccion.md"
