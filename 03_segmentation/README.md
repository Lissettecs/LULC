# Stage 03 — SLIC segmentation

SLIC (scale 50, σ 0.1) + **RAG threshold p10** on SSL4EO sample rectangles, using
**red, nir, swir1** from masked SBAND-184B mosaics (water + glaciers excluded).

Each segment gets a **spectral signature** (mean blue, green, red, nir, swir1, swir2)
and **`variacion_espectral`**: mean spatial standard deviation across those bands.

## Layout

```
03_segmentation/
├── config/
│   ├── bands_184b.py       # 184-band rasterio indices
│   ├── run_refs.py         # selection GPKG + revision plan paths
│   ├── params_slic.py      # SLIC / RAG / buffer constants
│   └── paths.py            # year-based paths (mask_mosaic_{year}, prod/…)
├── rectangles.py           # load GPKG, build plan, mosaic/existing filters
├── plan_segmentation.py
├── run_slic_segmentation.py
├── build_spectral_viewer.py
├── consolidate_run_summary.py
├── rag.py
└── jobs/
    ├── run_segmentation.sh
    ├── run_segmentation.slurm
    ├── prepare_segmentation_array.sh
    ├── run_segmentation_array.slurm
    ├── run_segmentation_consolidate.slurm
    └── submit_segmentation_array.sh
```

Set **`MAPBIOMAS_ROOT`** (default `/home/lserey/mapbiomas_land`) for data paths.

## Year conventions

| Item | Pattern |
|------|---------|
| Masked mosaic | `{MAPBIOMAS_ROOT}/tmp/mask_mosaic_{year}/{TILE}/TMP-CHILE-{TILE}-{year}-SBAND-184B_masked.tif` |
| Segmentation output | `{MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev{rev_year}/` |
| Rectangle filter | `rev_year1 == rev_year` in revision-plan GPKG |

For another year, build `mask_mosaic_{year}` and run with `--rev-year` and `--year`
(usually the same).

## Plan only

```bash
cd 03_segmentation
python plan_segmentation.py --rev-year 2015
python plan_segmentation.py --rev-year 2015 --require-mosaic --skip-existing
```

## Pilot (one tile or rectangle)

```bash
python run_slic_segmentation.py --test-tile 18GXA
python run_slic_segmentation.py --grid-id 18GXA_3x3_c003_r003
```

## Production 2015

```bash
# Dry-run
python run_slic_segmentation.py \
  --rev-year 2015 --require-mosaic --skip-existing --dry-run

# Full run (sequential)
REV_YEAR=2015 SKIP_EXISTING=1 ./jobs/run_segmentation.sh
```

## SLURM array (parallel, recommended)

One rectangle per array task:

```bash
REV_YEAR=2015 ARRAY_THROTTLE=16 ./jobs/submit_segmentation_array.sh
```

Default resources on `main`: 4 CPUs, 8G RAM, 1h30 per task, throttle `%16`.

## Outputs per rectangle

`prod/segmentacion_slic_rev{year}/{TILE}/{grid_id}/`:

- `{grid_id}_slic_ragp10_s50_sig0.1_labels.tif` — segment_id raster (post-RAG)
- `{grid_id}_slic_ragp10_segments.gpkg` — polygons + band stats + variation
- `{grid_id}_summary.json`

Run level:

- `plan_rev{year}.json` — rectangle / mosaic / status inventory
- `run_summary_rev{year}.json` — results and errors

## SLIC parameters

| Parameter | Value |
|-----------|-------|
| scale | 50 |
| sigma | 0.1 |
| compactness | 10 |
| perimeter buffer | 100 px |
| RAG | p10 |
| n_segments | max(2, n_valid_pixels // scale) |

Band indices: `config/bands_184b.py`.

## Spectral signature viewer

```bash
python build_spectral_viewer.py --grid-id 18GXA_3x3_c003_r003

cd "${MAPBIOMAS_ROOT}/prod/segmentacion_slic_rev2015"
python3 -m http.server 8765
# → http://localhost:8765/viewer/segment_signatures_viewer.html
```

## Inputs (reference)

| Resource | Path |
|----------|------|
| Selection UTM18/19 | `config/run_refs.py` → `seleccion_con_rev_years_utm{18,19}.gpkg` |
| 2015 mosaics | `{MAPBIOMAS_ROOT}/tmp/mask_mosaic_2015/{TILE}/` |
