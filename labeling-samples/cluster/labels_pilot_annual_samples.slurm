#!/bin/bash
#SBATCH -J labels-pilot-annual
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 4
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 02:00:00
#SBATCH -o /home/lserey/logs/labels_pilot_annual_samples_%j.out
#SBATCH -e /home/lserey/logs/labels_pilot_annual_samples_%j.err

# Piloto: etiquetar 5 rectangulos anuales desde prod/samples/final_samples.
#   mkdir -p /home/lserey/logs
#   sbatch /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/labels_pilot_annual_samples.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_pilot_annual_samples.sh

echo "Fin: $(date)"
