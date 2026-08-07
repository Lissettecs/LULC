#!/usr/bin/env bash
#SBATCH --job-name=caract_cim
#SBATCH --partition=main
#SBATCH --array=1-121%20
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=2
#SBATCH --mem=8G
#SBATCH --time=01:00:00
#SBATCH --output=logs/caract_%A_%a.out
#SBATCH --error=logs/caract_%A_%a.err

# Una tarea por carta CIM. El índice del array es la línea de cartas.txt, así que
# el rango del --array debe coincidir con el número de cartas (121 con landcover).
#
#   python scripts/03_generar_lista_cartas.py
#   sbatch jobs/run_caracterizacion.slurm
#   sbatch --dependency=afterok:$JOBID jobs/run_consolidar.slurm
#
# Memoria: se lee la ventana completa de la carta para los 26 años, ~550 MB en
# uint8 más el ráster de ecorregiones. 8G deja holgura de sobra.

set -euo pipefail

REPO="/home/lserey/repositorio/coverage/sample_generation_cim"
PYTHON="${PYTHON:-/home/lserey/.conda/envs/mb_coverage/bin/python}"
cd "${REPO}"
mkdir -p logs

echo "[$(date -Iseconds)] Tarea ${SLURM_ARRAY_TASK_ID}"
"${PYTHON}" scripts/04_caracterizar_carta.py --indice "${SLURM_ARRAY_TASK_ID}" --resume
echo "[$(date -Iseconds)] Fin tarea ${SLURM_ARRAY_TASK_ID}"
