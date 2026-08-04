#!/usr/bin/env bash
#SBATCH --job-name=prep_label
#SBATCH --partition=main
#SBATCH --cpus-per-task=1
#SBATCH --mem=2G
#SBATCH --time=00:10:00

set -euo pipefail

REPO="${SEGLABEL_REPO:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "${REPO}"
./jobs/prepare_labeling_array.sh
