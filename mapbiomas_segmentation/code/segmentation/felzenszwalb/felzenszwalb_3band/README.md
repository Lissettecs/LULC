# Felzenszwalb segmentation for sample labeling

Visual calibration test of segmentation over multiband mosaics (NIR, SWIR1, red) before assigning MapBiomas Collection 2 classes to polygons.

Runs a **parameter grid** (`scale` × `sigma`) per MGRS tile and year, exporting label GeoTIFFs, PNG quicklooks, and a summary CSV with segment-size statistics.

## Structure

```text
segmentation-labeling/
├── seg_felzenszwalb_grid.py              ← scale × sigma grid; exports TIF, PNG and CSV
├── regenerate_quicklooks_felzenszwalb.py ← regenerates PNGs from already-exported TIFs
├── visualize_seg_felzenszwalb_grid.py    ← interactive HTML dashboard
└── README.md
```

## Cluster inputs

Mosaics normalized to 0–1, stored outside this repository:

```text
/home/lserey/mapbiomas_land/test/image_segmentation/
└── nir_swir1_red_normalized_mosaics/
    └── {tile}_{year}_nir_swir1_red_0-1.tif
```

Band convention in the GeoTIFF: `0=nir`, `1=swir1`, `2=red`. RGB visualization: red, swir1, nir.

Common test tiles: `18HYD`, `19KDU`, `19JCJ`, `19HCD`, `18GXP`, `18FXH`.

## Outputs

By default in `.../image_segmentation/seg_felzenszwalb/`:

```text
seg_{tile}_{year}_s{scale}_sig{sigma}.tif   ← INT32 labels (nodata=0)
seg_{tile}_{year}_s{scale}_sig{sigma}.png   ← RGB quick-look + colored polygons
summary_{tile}_{year}.csv                   ← statistics per parameter combination
viewer_felzenszwalb.html                    ← dashboard (visualize script)
layers/                                     ← per-layer PNGs for the HTML explorer
```

The scripts **do not overwrite** existing files; delete them or change `--output-dir` before re-running.

## Installation

```bash
cd segmentation-labeling
python -m pip install rasterio scikit-image matplotlib
```

On the cluster, activate the environment where those dependencies already exist (e.g. `mb_labels` from [labeling-samples](../labeling-samples/)).

## Quick start

```bash
cd segmentation-labeling

# List available tiles for a year
python seg_felzenszwalb_grid.py --list-tiles --year 2010

# Run the grid over a tile/year (defaults: 18HYD, 2010)
python seg_felzenszwalb_grid.py --tile 18HYD --year 2010

# Regenerate PNGs if the quick-look logic changed
python regenerate_quicklooks_felzenszwalb.py --output-dir /path/seg_felzenszwalb

# HTML dashboard (requires prior grid outputs)
python visualize_seg_felzenszwalb_grid.py --output-dir /path/seg_felzenszwalb
cd /path/seg_felzenszwalb && python3 -m http.server 8765
# → http://localhost:8765/viewer_felzenszwalb.html
```

## Grid parameters (editable in `seg_felzenszwalb_grid.py`)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `SCALE_LIST` | 25, 50, 100, 150, 200 | Felzenszwalb scale (relative segment size) |
| `SIGMA_LIST` | 0.1, 0.5, 0.8 | Gaussian pre-smoothing |
| `MIN_SIZE` | 20 | Minimum segment size (pixels) |
| `STANDARDIZE` | `False` | Per-band z-score (mutually exclusive with `NORMALIZE_01`) |
| `NORMALIZE_01` | `False` | Mosaics already come in 0–1 |
| `PIXEL_HA` | 0.09 | 30 m resolution → ha per pixel in the CSV |

CLI for `seg_felzenszwalb_grid.py`:

| Argument | Default | Description |
|----------|---------|-------------|
| `--tile` | `18HYD` | MGRS tile |
| `--year` | `2010` | Mosaic year |
| `--mosaic-dir` | see script | Directory of `{tile}_{year}_nir_swir1_red_0-1.tif` mosaics |
| `--output-dir` | see script | Output directory for TIF/PNG/CSV |
| `--list-tiles` | — | Lists tiles in `--mosaic-dir` and exits |

## Future scope (not implemented)

- Class attribution by majority vote vs MapBiomas Collection 2
- Spectral indices (NDVI, MNDWI, NDSI, BSI) with z-score
- Replacement with OTB Large-Scale Mean-Shift at national scale

## Generated data

Do not version output rasters, PNGs or CSVs. Regenerate them with the scripts or store outside Git (see [.gitignore](../.gitignore)).
