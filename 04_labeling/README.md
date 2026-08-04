# Stage 04 — C2 segment labeling

Assign MapBiomas Collection 2 statistics to each SLIC+RAG segment.

## Input / output

| | Path (relative to `MAPBIOMAS_ROOT`) |
|---|------|
| Segmentation | `prod/segmentacion_slic_rev{year}/` |
| C2 landcover | `ancillary_data/landcover_col2/classification_{year}.tif` |
| Output | `prod/labeling_slic_rev{year}/` |

## Local usage

```bash
source ../env.local   # or export MAPBIOMAS_ROOT=...
cd 04_labeling
python etiquetar_segmentos_c2.py --year 2015
python etiquetar_segmentos_c2.py --grid-id 18GXA_3x3_c003_r003 --force
```

## SLURM production (all UTM18+19 rectangles)

```bash
source env.local
./jobs/submit_labeling_array.sh
```

After segmentation completes (chained):

```bash
source env.local
../run_pipeline.sh all
```

## Environment variables

See `env.example` at the repository root.
