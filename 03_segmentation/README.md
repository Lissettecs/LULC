# Stage 03 — SLIC segmentation (multiannual)

SLIC (scale 50, σ 0.1) + **RAG threshold p10** on CIM sample rectangles from the
national revision plan (`rev_year1/2/3`). Uses **red, nir, swir1** from masked
CIM 184-band mosaics (water + glacier already nodata). An **ecoregion mask**
further excludes ocean / out-of-coverage pixels.

## Language convention

| Surface | Language |
|---------|----------|
| Code (functions, variables, logs) | Spanish |
| Output column names, filenames, this README | English |

## Layout

```
03_segmentation/
├── config/
│   ├── bands_184b.py
│   ├── run_refs.py          # GPKG_SELECCION + ecoregion path
│   ├── params_slic.py
│   └── paths.py             # CIM mosaic + prod/03_segmentation_cim/{YEAR}
├── rectangles.py            # cargar_plan_multianual (melt + dedupe)
├── ecoregion_mask.py        # nearest-neighbour warp to mosaic window
├── run_slic_segmentation.py # driver
├── characterize_segments.py # unified segments.gpkg (+ optional Parquet)
├── mosaic_io.py
├── rag.py
└── jobs/
```

Set **`MAPBIOMAS_ROOT`** (default `/home/lserey/mapbiomas_land`).

## CRS model (EPSG:4326 end-to-end for clip)

| Step | CRS |
|------|-----|
| Selection GPKG + mosaic + clip | **EPSG:4326** (no reprojection to clip) |
| Spectral stats / SLIC | 4326 (pixel spectra unaffected by area distortion) |
| `area_ha`, `perimeter_m`, compactness, elongation | measured after reprojecting **segment geometries** to **UTM** (`utm_epsg` from `utm_zone` or centroid longitude) |
| Stored `geometry` in `segments.gpkg` | stays **EPSG:4326** |

## Mosaic input + features.parquet (parameterized)

| Param | CLI | Env | Notes |
|-------|-----|-----|-------|
| Mosaic kind | `--mosaic-kind` | `MOSAIC_KIND` | `184_mask_water` (default) or `11b` |
| Mosaic root | `--mosaic-root` | `MOSAIC_ROOT` | Overrides kind preset path |
| Band layout | `--band-layout` | `BAND_LAYOUT` | `auto` \| `184` \| `11b` |
| Features Parquet | `--features-parquet` / `--no-features-parquet` | `FEATURES_PARQUET=0\|1` | Policy if unset: **ON** for 184, **OFF** for 11b |

Presets (`config/mosaic_presets.py`):

- `184_mask_water` → `mosaic_184bands_mask_water/{year}/`
- `11b` → `mosaic_11bands_mask_water/{year}/` (`*_masked.tif` or `*-11B.tif`)

For **11-band masked** runs, Parquet spectral features stay **pending** (not written). Re-run later with `--features-parquet` or `FEATURES_PARQUET=1` when ready. Summary records `features_parquet_skip`.

```bash
# 184 masked (Parquet ON by default)
python run_slic_segmentation.py --rev-year 2015 --mosaic-kind 184_mask_water --require-mosaic

# 11B masked (Parquet OFF / pendiente)
python run_slic_segmentation.py --rev-year 2009 --mosaic-kind 11b --require-mosaic --grid-id …

# Force Parquet on 11B later
FEATURES_PARQUET=1 python run_slic_segmentation.py … --mosaic-kind 11b --features-parquet
```

SLURM: `jobs/submit_segmentation_array.sh` (generic) and `jobs/submit_segmentation_11b_plan.sh` (11B lists + `FEATURES_PARQUET=0`).

## Multiannual plan + mosaic gate

1. Load national GPKG (`selection_with_rev_years.gpkg`, legacy `seleccion_con_rev_years.gpkg`).
2. Melt `rev_year1/2/3` (+ roles) → long form; drop null / `-9999`.
3. Dedupe by `(grid_id, rev_year)` (keep lowest `rev_slot`; extra slots in summary).
4. Process only if year ∈ `ANIOS_PERMITIDOS` (184 default `[2015]`; 11b = all) **and** mosaic exists.
5. Missing mosaic → `omitido: mosaico_ausente` in plan JSON; do not abort the batch.

**Scaling to another year:** drop the new masked mosaic under the kind root and
re-run with `--rev-year` / `--year` (and matching `--mosaic-kind`).

## Inputs / outputs

| | Path |
|---|---|
| Selection + rev years | `prod/samples_cim/02_selection/…/selection_with_rev_years.gpkg` (legacy `02_seleccion` / `seleccion_con_rev_years.gpkg`) |
| Masked mosaics (184) | `mosaic_184bands_mask_water/{year}/CHILE-{TILE}-{year}-*_masked.tif` |
| Masked mosaics (11B) | `mosaic_11bands_mask_water/{year}/…_masked.tif` |
| Ecoregions | `ancillary_data/ecorregiones_col3_30m_alineado_lulc.tif` (0 = ocean/nodata) |
| Output root | `prod/03_segmentation_cim/{year}/{TILE}/{grid_id}/` |

Per rectangle–year:

```
{grid_id}_{year}_slic_ragp10_s50_sig0.1_labels.tif
{grid_id}_{year}_segments.gpkg          # sole vector product (reviewer)
{grid_id}_{year}_features.parquet       # 184: default ON; 11b: pendiente
{grid_id}_{year}_summary.json
```

Filenames match `04_labeling` globs (`*_slic_ragp*_labels.tif`, `*_segments.gpkg`).

## Output schemas

One **Polygon** row per segment (no `MultiPolygon`). Geometry CRS = **EPSG:4326**.
`segment_uid` = `{grid_id}_{rev_year}_{label:06d}`. `area_ha` from UTM geometry
(**not** `n_pixels × 0.09`). Characterization owns the single GPKG (`revision.gpkg` removed).

### `{grid_id}_{year}_segments.gpkg`

~31 columns. Review / labeling product (also consumed by `04_labeling`).

| Column | Type | Description |
|--------|------|-------------|
| `segment_id` | int | Local raster label (INTEGER) |
| `segment_uid` | text | Global id: `{grid_id}_{rev_year}_{label:06d}` |
| `grid_id` | text | Sample rectangle id |
| `rect_id` | text | Rectangle id from selection plan |
| `rev_year` | int | Revision year (mosaic / labeling year) |
| `rev_slot` | int | Slot in plan (`1`/`2`/`3` from `rev_year1/2/3`) |
| `rev_role` | text | Role from selection plan |
| `reviewed_class` | float/null | Empty at write time; filled in review |
| `n_valid_pixels` | int | Valid (non-nodata) pixels in segment |
| `nodata_frac` | float | Fraction of nodata inside segment footprint |
| `n_pixels` | int | Total pixels in segment footprint |
| `spectral_variation` | float | Mean of signature-band `_std` values |
| `blue_mean` … `swir2_mean` | float | Mean of optical signature bands |
| `blue_std` … `swir2_std` | float | Std of optical signature bands |
| `eco_dom_id` | int | Dominant ecoregion code |
| `eco_dom_name` | text | Dominant ecoregion name |
| `utm_epsg` | int | UTM EPSG used for area / shape metrics |
| `utm_zone` | int | UTM zone |
| `mgrs_dom` | text | Dominant MGRS / CIM tile |
| `area_ha` | float | Area in hectares (UTM) |
| `geometry` | polygon | Segment polygon, EPSG:4326 |

Signature bands (GPKG only): `blue`, `green`, `red`, `nir`, `swir1`, `swir2`
(resolved by name for both 184 and 11B stacks).

Year consolidation may add `source_file` (path of the per-rectangle GPKG).

### `{grid_id}_{year}_features.parquet`

Default **ON** for `184_mask_water` (~383 columns); **pending / OFF** for `11b`.
One row per `segment_uid`. Join to GPKG on `segment_uid`.

| Column | Type | Description |
|--------|------|-------------|
| `segment_uid` | text | Same key as GPKG |
| `segment_id` | int | Local raster label |
| `grid_id` | text | Sample rectangle id |
| `rev_year` | int | Revision year |
| `rev_slot` | int | Plan slot |
| `n_valid_pixels` | int | Valid pixels |
| `nodata_frac` | float | Nodata fraction |
| `area_px` | int | Footprint pixels |
| `area_ha` | float | Area (ha, UTM) |
| `perimeter_m` | float | Perimeter (m, UTM) |
| `compactness` | float | Shape compactness |
| `elongation` | float | Shape elongation |
| `{mosaic_band}_median` | float | Per-segment median of mosaic band |
| `{mosaic_band}_std` | float | Per-segment std of mosaic band |
| `aspect_sin_median` / `_std` | float | Circular aspect (sin), if present |
| `aspect_cos_median` / `_std` | float | Circular aspect (cos), if present |

Spectral columns use the 184-band CIM catalog (`config/catalogo_bandas.py`), e.g.
`ndvi_median_median`, `ndvi_median_std`, `elevation_median`, `slope_std`,
`blue_amp_median`, … (~186 mosaic features × `{median,std}` ≈ 371 spectral columns).

Requires a full / near-full stack (`BANDAS_PARQUET_MINIMAS`); short 11B stacks skip
Parquet unless forced later with `--features-parquet`.

## Valid mask

```
valid &= (~mosaic_nodata) & inside_rectangle & ecoregion_land
```

Ecoregion alignment uses **nearest** resampling (grid origins/signs differ from
per-tile mosaics). Summary records `ocean_masked_frac`.

## Run

```bash
export MAPBIOMAS_ROOT=/home/lserey/mapbiomas_land
cd 03_segmentation

# Plan only
python plan_segmentation.py --rev-year 2015 --require-mosaic

# Pilot: one zone-18 and one zone-19 rectangle
python run_slic_segmentation.py --rev-year 2015 --require-mosaic \
  --grid-id SK-18-Z-A_3x3_c006_r000
python run_slic_segmentation.py --rev-year 2015 --require-mosaic \
  --grid-id SI-19-Y-A_2x2_c009_r002

# Batch
python run_slic_segmentation.py --rev-year 2015 --require-mosaic --skip-existing
```

## Compatibility with `04_labeling`

- Do **not** edit stage 04.
- `segment_id` remains INTEGER → `merge(on="segment_id")` unchanged.
- Extra GPKG columns are carried by `dissolve(aggfunc="first")`.

## Out of scope (phase 2)

National Parquet consolidation, per-segment ecoregion mode, percentiles / IQR,
any change to `04_labeling`.
