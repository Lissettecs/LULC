#!/bin/bash
#SBATCH -J export-gee-annual-samples
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem=32G
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 04:00:00
#SBATCH -o /home/lserey/logs/export_gee_annual_samples_%j.out
#SBATCH -e /home/lserey/logs/export_gee_annual_samples_%j.err

# Exporta annual_samples.gpkg a Earth Engine.
# Ejecutar despues de labels_annual_samples.slurm:
#   sbatch --dependency=afterok:JOBID_LABELS cluster/export_gee_annual_samples.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_export_gee_annual_samples.sh

echo "Fin: $(date)"
