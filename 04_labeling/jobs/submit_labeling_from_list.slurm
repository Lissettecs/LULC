#!/usr/bin/env bash
#SBATCH --job-name=submit_lbl
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=1G
#SBATCH --time=00:05:00

# Ejecuta tras prepare_labeling_array: envía el array de etiquetado si hay pendientes.
set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"

./jobs/prepare_labeling_array.sh
exec ./jobs/submit_labeling_array.sh
