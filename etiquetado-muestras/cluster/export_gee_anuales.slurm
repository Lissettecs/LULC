#!/bin/bash
#SBATCH -J export-gee-anuales
#SBATCH -p main
#SBATCH -n 1
#SBATCH -c 2
#SBATCH --mem-per-cpu=4096
#SBATCH --mail-user=lissette.cortes@uchile.cl
#SBATCH --mail-type=ALL
#SBATCH -t 02:00:00
#SBATCH -o /home/lserey/logs/export_gee_anuales_%j.out
#SBATCH -e /home/lserey/logs/export_gee_anuales_%j.err

# Exporta el GeoPackage anuales a Earth Engine (ingestion via GCS).
# Ejecutar despues de labels_anuales.slurm:
#   sbatch --dependency=afterok:JOBID_LABELS cluster/export_gee_anuales.slurm

set -eo pipefail

echo "Host: $(hostname)"
echo "Inicio: $(date)"
echo "Job ID: ${SLURM_JOB_ID:-local}"

bash /home/lserey/repositorio/LULC/etiquetado-muestras/cluster/run_export_gee_anuales.sh

echo "Fin: $(date)"
