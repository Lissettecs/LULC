#!/bin/bash
#SBATCH -J labels-anuales-c2
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 04:00:00
#SBATCH -o /home/lserey/logs/labels_anuales_c2_%j.out
#SBATCH -e /home/lserey/logs/labels_anuales_c2_%j.err

# Genera subdivisiones C2 para todo el grupo anuales (249 rectangulo-año).
# Enviar:
#   mkdir -p /home/lserey/logs
#   sbatch /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/labels_anuales.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_anuales.sh

echo "Fin: $(date)"
