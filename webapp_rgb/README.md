# Webapp RGB composites

Generate per-rectangle RGB GeoTIFF composites (with internal overview pyramids)
for the SegLabel webapp.

| Suffix | R / G / B bands |
|--------|-----------------|
| `true_color` | `red_median` / `green_median` / `blue_median` |
| `swir1-nir-red` | `swir1_median` / `nir_median` / `red_median` |
| `nir-red-green` | `nir_median` / `red_median` / `green_median` |

Default output dtype is **float32** (same values as the masked mosaic; nodata `-9999`).  
`uint8` with percentile stretch is optional (`--dtype uint8`) but clips bright pixels to 255.

Overviews: power-of-2 factors down to ~**32 px** (`--overview-min-size`), resampling `average`.  
Example for 529×529 → `[2, 4, 8, 16]` (~264 / 132 / 66 / 33 px).

## Paths

| Role | Path |
|------|------|
| Rectangles (inventory) | `/home/lserey/mapbiomas_land/prod/04_labeling_cim/{year}/` |
| Labels window | `/home/lserey/mapbiomas_land/prod/03_segmentation_cim/{year}/` |
| Mosaic 184 masked | `/home/lserey/mapbiomas_land/mosaic_184bands_mask_water/{year}/` |
| Mosaic 11B masked | `/home/lserey/mapbiomas_land/mosaic_11bands_mask_water/{year}/` |
| Code | `/home/lserey/repositorio/LULC/webapp_rgb/` |
| Output | `/home/lserey/mapbiomas_land/prod/webapp/rgb/{year}/` |

Per rectangle:

```
{grid_id}_{year}_true_color.tif
{grid_id}_{year}_swir1-nir-red.tif
{grid_id}_{year}_nir-red-green.tif
```

Plus `run_rgb_{year}_{mosaic_kind}.json` after each batch.

## Environment

```bash
/home/lserey/.conda/envs/mb_labels/bin/python -m pip install -r requirements.txt  # if needed
```

## Usage

```bash
cd /home/lserey/repositorio/LULC/webapp_rgb

# all rectangles for 2015 (mosaic 184, float32)
/home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \
  --year 2015 --mosaic-kind 184 --force

# another year + 11-band mosaics
/home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \
  --year 2009 --mosaic-kind 11b --force

# one rectangle
/home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \
  --year 2015 --grid-id SI-19-Y-A_2x2_c000_r001 --force

# optional: 8-bit preview with percentile stretch (clips highs)
/home/lserey/.conda/envs/mb_labels/bin/python generate_rgb_composites.py \
  --dtype uint8 --force --grid-id SI-19-Y-A_2x2_c000_r001
```

| Flag | Default | Notes |
|------|---------|--------|
| `--year` | `2015` | Labeling / segmentation / mosaic year |
| `--mosaic-kind` | `184` | `184` or `11b` (aliases: `184_mask_water`, `11bands`, …) |
| `--dtype` | `float32` | `float32` \| `uint16` \| `uint8` |
| `--overview-min-size` | `32` | Stop building overviews below this size |
| `--force` | off | Overwrite existing GeoTIFFs |
| `--mosaic-root` / `--labeling-root` / … | derived from year+kind | Optional path overrides |

Band indices:

- **184**: same as `seglabel-pipeline/03_segmentation/config/bands_184b.py`
- **11b**: blue=1, green=2, red=3, nir=4, swir1=5
