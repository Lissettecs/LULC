#!/usr/bin/env bash
#SBATCH --job-name=seg_slic
#SBATCH --partition=main
#SBATCH --cpus-per-task=4
#SBATCH --mem=16G
#SBATCH --time=24:00:00
#SBATCH --output=segmentation_rev%x_%j.log

# SLIC+RAG segmentation for a revision year.
#
# Example:
#   sbatch --export=REV_YEAR=2015 jobs/run_segmentation.slurm
#   sbatch --export=REV_YEAR=2015,TEST_TILE=18GXA jobs/run_segmentation.slurm

set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO}"
exec ./jobs/run_segmentation.sh
