# Stage 04 — C2 segment labeling (CIM)

Assign MapBiomas Collection 2 statistics to each SLIC+RAG segment.

## Input / output

| | Path (relative to `MAPBIOMAS_ROOT`) |
|---|------|
| Segmentation | `prod/03_segmentation_cim/{year}/` |
| C2 landcover | `ancillary_data/landcover_col2/classification_{year}.tif` |
| Output | `prod/04_labeling_cim/{year}/` |

Per rectangle:

```
{grid_id}_{year}_labeled_segments.gpkg
{grid_id}_{year}_labeled_segments.csv
{grid_id}_{year}_labeling_summary.json
```

## Local usage

```bash
export MAPBIOMAS_ROOT=/path/to/mapbiomas_land
export PYTHON=/path/to/mb_coverage/bin/python3
cd 04_labeling
$PYTHON label_segments_c2.py --year 2015 --grid-id SI-19-Y-A_2x2_c009_r002 --force
```

## SLURM production

```bash
export MAPBIOMAS_ROOT=...
./jobs/submit_labeling_array.sh
```

## Environment variables

See `env.example` at the repository root.
