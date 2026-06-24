#!/bin/bash
#SBATCH -J labels-annual-samples
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 12:00:00
#SBATCH -o /home/lserey/logs/labels_annual_samples_%j.out
#SBATCH -e /home/lserey/logs/labels_annual_samples_%j.err

# Genera annual_samples.gpkg para todo el grupo anuales (~295 rectangulo-año).
# Enviar:
#   mkdir -p /home/lserey/logs
#   sbatch /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/labels_annual_samples.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_annual_samples.sh

echo "Fin: $(date)"
