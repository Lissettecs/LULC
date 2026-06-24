# Scripts — labeling-samples

Run from the repository root with `source cluster/activate_mb_labels.sh`.

## Main pipeline (00–03)

| Script | Purpose |
|--------|---------|
| `00_check_inputs.py` | Verify plan, GeoJSONs in `final_samples/`, and C2 rasters |
| `02_extract_sieve_rectangles.py` | Step 1: sieved raster mosaics per UTM zone/year |
| `03_generate_labels_gpkg.py` | Step 2: GeoPackages with taxonomy + plan metadata |

## `src/mb_labels/` modules

| Module | Purpose |
|--------|---------|
| `sample_paths.py` | Paths for `final_samples/`, review plan, UTM zone helpers |
| `taxonomy.py` | C2 N1/N2/N3 taxonomy lookup |

## Useful flags

```bash
# Step 1 — extract and sieve
python scripts/02_extract_sieve_rectangles.py \
  --label-group  anuales \
  --only-zones   UTM18 \
  --only-years   2020 2021 \
  --sieve-size   9 \
  --overwrite

# Step 2 — generate GeoPackages
python scripts/03_generate_labels_gpkg.py \
  --only-groups  anuales \
  --only-zones   utm18 \
  --only-years   2020 2021 \
  --overwrite
```
