# Image segmentation — visual calibration

Experimental scripts to compare **classical segmenters** (Felzenszwalb and SLIC) on normalized Sentinel-2 mosaics before assigning MapBiomas Collection 2 classes to polygons or moving to large-scale backends (e.g. OTB Mean-Shift).

**Índice de experimentos:** [EXPERIMENT.md](EXPERIMENT.md)

## Layout

```text
labeling/image_segmentation/
├── README.md
├── EXPERIMENT.md                     ← catálogo FELZ-01…07, SLIC, LABEL-01
├── segmenters_viewer.py              ← dashboard Felzenszwalb + RF_N + SLIC
├── segmenters_labeling_viewer.py     ← dashboard extendido + overlays Col2
├── incremental_results_viewer.py       ← FELZ-05 (incremental)
├── lv3_results_viewer.py             ← FELZ-06 + FELZ-07 (Lv3)
├── seg_felzenszwalb/                 ← FELZ-01: 3 bandas (nir/swir1/red)
├── seg_felzenszwalb_rf_n/            ← FELZ-02: bandas RF_N (grid)
├── seg_felzenszwalb_rfn/             ← FELZ-03: RF_N podado
├── seg_felzenszwalb_ablacion/        ← FELZ-04: ablación Lv1
├── seg_felzenszwalb_incremental/     ← FELZ-05: constructivo base+incremento
├── seg_felzenszwalb_rf_lv3/          ← FELZ-06: 34 bandas Lv3 (REPORT)
├── seg_felzenszwalb_ablacion_lv3/    ← FELZ-07: ablación Lv3
├── segmentation_labels/              ← LABEL-01: landcover Col2
└── seg_slic/
    ├── pipeline_a/                   ← SLIC-01 (legado)
    ├── pipeline_b/                   ← SLIC-02 (actual)
    └── README.md
```

## Pipelines SLIC

| Pipeline | Descripción | Salidas (data root) | Visualizador |
|----------|-------------|---------------------|--------------|
| **A** (legado) | 3 etapas: SLIC+RAG → hier → min150 | `pipeline_a/` | SLIC, SLIC+RAG hier, SLIC+min150 |
| **B** (actual) | Flujo unificado: SLIC → RAG hier → min150 | `pipeline_b/` | Pipeline B |

Detalle: [seg_slic/README.md](seg_slic/README.md)

## Context

Both pipelines read **3-band mosaics** (nir, swir1, red) normalized to 0–1, run the same **scale × sigma** grid, and export label GeoTIFFs, quick-look PNGs, and a summary CSV. HTML viewers stack mosaic / segment overlay / boundaries with progressive resolution (1024 / 2048 / 4096 px) and synchronized zoom in compare mode.

| ID | Algorithm | Module | Output directory |
|----|-----------|--------|------------------|
| FELZ-01 | Felzenszwalb (3 bandas) | `seg_felzenszwalb/seg_felzenszwalb_grid.py` | `seg_felzenszwalb/` |
| FELZ-02 | Felzenszwalb RF_N | `seg_felzenszwalb_rf_n/seg_felzenszwalb_rf_n_grid.py` | `seg_felzenszwalb_rf_n/` |
| SLIC-01 | SLIC Pipeline A | `seg_slic/pipeline_a/seg_slic_pipeline_a.py` | `seg_slic/pipeline_a/` |
| SLIC-02 | SLIC Pipeline B | `seg_slic/pipeline_b/seg_slic_pipeline_b.py` | `seg_slic/pipeline_b/` |

Cluster data root (outside this repo):

```text
/home/lserey/mapbiomas_land/test/image_segmentation/
├── nir_swir1_red_normalized_mosaics/
├── seg_felzenszwalb/
├── seg_felzenszwalb_rf_n/
├── seg_felzenszwalb_rfn/
├── seg_felzenszwalb_ablacion/
├── seg_felzenszwalb_incremental/
├── seg_felzenszwalb_rf_lv3/
├── seg_felzenszwalb_ablacion_lv3/
├── seg_slic/
│   ├── pipeline_a/
│   └── pipeline_b/
├── labeling_segmenters/
├── viewer_felzenszwalb.html
├── segmenters_viewer.html
├── segmenters_labeling_viewer.html
├── incremental_results_viewer.html
└── lv3_results_viewer.html
```

## Tests performed (July 2026)

| Item | Value |
|------|--------|
| Tile | `18HYD` |
| Year | `2010` |
| Mosaic | `{tile}_{year}_nir_swir1_red_0-1.tif` |
| Grid | 5 scales × 3 sigmas = **15 combinations** per algorithm |
| `SCALE_LIST` | 25, 50, 100, 150, 200 |
| `SIGMA_LIST` | 0.1, 0.5, 0.8 |
| `MIN_SIZE` | 20 px |
| SLIC `compactness` | 10 |
| RGB display | bands 2, 1, 0 → red, swir1, nir |

Example SLIC result at `scale=100`: ~128k segments, mean size ~104 px (~9 ha at 30 m).

## Quick start

### Segmentación

```bash
# FELZ-01: Felzenszwalb grid
cd seg_felzenszwalb
python seg_felzenszwalb_grid.py --tile 18HYD --year 2010

# FELZ-02: Felzenszwalb RF_N grid
cd ../seg_felzenszwalb_rf_n
python seg_felzenszwalb_rf_n_grid.py --tile 18HYD --year 2010

# SLIC Pipeline B
cd ../seg_slic/pipeline_b
sbatch --array=0-3%1 run_seg_slic_pipeline_b_from_rag.slurm
python consolidar_pipeline_b_csv.py --tile 18HYD --year 2010

# Unified viewer (export layers first if capas/ is missing)
cd ../..
python segmenters_viewer.py
```

### Experimentos dirigidos (FELZ-03…07)

```bash
# FELZ-03: RF_N podado
python seg_felzenszwalb_rfn/seg_felzenszwalb_rfn_podado.py --tile 18HYD --year 2010

# FELZ-04: ablación Lv1
python seg_felzenszwalb_ablacion/seg_felzenszwalb_ablacion.py --tile 18HYD --year 2010

# FELZ-05: incremental
python seg_felzenszwalb_incremental/seg_felzenszwalb_incremental.py --tile 18HYD --year 2010

# FELZ-06: Lv3 completo
python seg_felzenszwalb_rf_lv3/seg_felzenszwalb_rf_lv3.py --tile 18HYD --year 2010

# FELZ-07: ablación Lv3
python seg_felzenszwalb_ablacion_lv3/seg_felzenszwalb_ablacion_lv3.py --tile 18HYD --year 2010
```

### Etiquetado con landcover Col2

```bash
cd labeling/image_segmentation/segmentation_labels

python prepare_landcover_tile.py --tile 18HYD --year 2015
bash run_segmenter_labeling.sh
python export_label_overlays.py --tile 18HYD --resume
cd ..
python segmenters_labeling_viewer.py --skip-layers --skip-export
```

Salidas GPKG: `/home/lserey/mapbiomas_land/test/image_segmentation/labeling_segmenters/`

Requiere entorno `mb_labels` (geopandas). Reutiliza `label_segments.py` del cluster.

Serve the dashboard from the data root:

```bash
cd /home/lserey/mapbiomas_land/test/image_segmentation
python3 -m http.server 8765 --bind 0.0.0.0
```

## Dependencies

```bash
python -m pip install rasterio scikit-image matplotlib pillow numpy
```

Use the cluster env where these are already installed (e.g. `mb_coverage` or `mb_labels`).

## Branch

Developed on **`feat/image-seg-felzenszwalb`** (tracks `origin/feat/image-seg-felzenszwalb`).

## Not implemented

- ~~Majority-vote class assignment vs MapBiomas Collection 2~~ → ver `segmentation_labels/` (LABEL-01)
- Spectral indices (NDVI, MNDWI, NDSI, BSI) with z-score
- National-scale OTB Large-Scale Mean-Shift
