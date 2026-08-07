#!/usr/bin/env bash
# Lanza caracterización nacional en lotes SLURM (partition main) y consolida al final.
set -euo pipefail

REPO="/home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02"
cd "${REPO}"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
TAMANO_LOTE=${TAMANO_LOTE:-10}
INTERVALO_SONDEO=${INTERVALO_SONDEO:-60}
LISTA_TILES=${LISTA_TILES:-tiles.txt}
SCRIPT_JOB=${SCRIPT_JOB:-jobs/run_caracterizacion.slurm}
LOG_LOTES=${LOG_LOTES:-logs/caract_lotes_$(date +%Y%m%d_%H%M).log}

if [[ ! -f .ultima_corrida_caract ]]; then
  echo "ERROR: falta .ultima_corrida_caract — ejecute primero:"
  echo "  python main.py caracterizar --generar-lista-tiles"
  exit 1
fi

if [[ ! -f "${LISTA_TILES}" ]]; then
  echo "ERROR: falta ${LISTA_TILES}"
  exit 1
fi

N_TILES=$(grep -cve '^[[:space:]]*$' "${LISTA_TILES}")
N_LOTES=$(( (N_TILES + TAMANO_LOTE - 1) / TAMANO_LOTE ))
mkdir -p logs
echo "[$(date)] Nacional UTM · tiles=${N_TILES} · lotes=${N_LOTES} · run=$(cat .ultima_corrida_caract)" | tee -a "${LOG_LOTES}"

for (( lote=0; lote<N_LOTES; lote++ )); do
    INICIO=$(( lote * TAMANO_LOTE ))
    FIN=$(( INICIO + TAMANO_LOTE - 1 ))
    (( FIN >= N_TILES )) && FIN=$(( N_TILES - 1 ))
    echo "[$(date)] Lote $((lote+1))/${N_LOTES} · índices ${INICIO}-${FIN}" | tee -a "${LOG_LOTES}"
    JOBID=$(sbatch --parsable --array=${INICIO}-${FIN}%${TAMANO_LOTE} "${SCRIPT_JOB}")
    echo "[$(date)]   job ${JOBID}" | tee -a "${LOG_LOTES}"
  while true; do
    PENDIENTES=$(squeue -h -j "${JOBID}" | wc -l)
    [[ "${PENDIENTES}" -eq 0 ]] && break
        echo "[$(date)]   ${PENDIENTES} tareas activas" | tee -a "${LOG_LOTES}"
        sleep "${INTERVALO_SONDEO}"
    done
    FALLIDAS=$(sacct -j "${JOBID}" --format=JobID,State --noheader -P \
               | grep -E '\.batch|' \
               | grep -vc 'COMPLETED' || true)
    if [[ "${FALLIDAS}" -gt 0 ]]; then
        echo "[$(date)] ERROR: ${FALLIDAS} fallos — abortando" | tee -a "${LOG_LOTES}"
        sacct -j "${JOBID}" --format=JobID,JobName,State,ExitCode,Elapsed | tee -a "${LOG_LOTES}"
        exit 1
    fi
    echo "[$(date)] Lote $((lote+1)) OK" | tee -a "${LOG_LOTES}"
done

RUN_DIR=$(cat .ultima_corrida_caract | tr -d '\n')
echo "[$(date)] Consolidando ${RUN_DIR}" | tee -a "${LOG_LOTES}"
"${PYTHON}" scripts/05_consolidar_grillas.py --run-dir "${RUN_DIR}" 2>&1 | tee -a "${LOG_LOTES}"
echo "[$(date)] Caracterización nacional lista en ${RUN_DIR}/consolidado" | tee -a "${LOG_LOTES}"
