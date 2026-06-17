# Final samples pipeline (2×2 / 3×3, scale300)

Run all commands from the root of this directory.

| Step | Script | Description |
|------|--------|-------------|
| 01 | `01_gee_grid_characterization.py` | Characterizes candidate grids in GEE (export SHP to Drive, v3.1) |
| 02 | `02_download_grids_drive.py` | Downloads characterized ZIPs → `intermediate_files/gee_characterization/` |
| 03 | `03_rectangle_selection.py` | Selection by sample type → `final_samples/` (anti-overlap within zone and UTM18/UTM19 border) |
| 04 | `04_annotate_grid_taxonomy.py` | N1/N2/N3 taxonomy on selection (`*_taxonomia_n3`) |
| 05 | `05_rectangle_selection_review.py` | Review reports → `intermediate_files/review/` |
| 06 | `06_balance_audit.py` | Balancing checklist vs targets (14 criteria) |
| 07 | `07_visualize_reports.py` | Streamlit dashboard for review reports |
| 08 | — | *No script.* Prefix `08_` = critical-class tables from step 05 |
| 09 | `09_generate_rectangle_review_plan.py` | Review-year plan per rectangle |
| 10 | `10_consolidate_national_review_plan.py` | Consolidates UTM18/UTM19 plans into national plan |

## Visualization dashboard

```powershell
streamlit run scripts/07_visualize_reports.py
python scripts/07_visualize_reports.py --export-html revision_dashboard.html
```

Reads reports from `intermediate_files/review/`, geometries from `final_samples/`, and can overlay 1×1 chips (optional, disabled by default).

## UTM19 example (full workflow 02–10)

```powershell
python scripts/02_download_grids_drive.py --scale300-all

python scripts/03_rectangle_selection.py `
  --homogeneo intermediate_files/gee_characterization/grilla_ssl4eo_muestras_homogeneo_2x2_UTM19_scale300_n3.zip `
  --mixto intermediate_files/gee_characterization/grilla_ssl4eo_muestras_mixto_3x3_UTM19_scale300_n3.zip `
  --no-auto-previous

python scripts/04_annotate_grid_taxonomy.py `
  -i final_samples/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.csv

python scripts/05_rectangle_selection_review.py --utm 19
python scripts/06_balance_audit.py

python scripts/09_generate_rectangle_review_plan.py `
  -i final_samples/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson `
  -o intermediate_files/review/plan_revision_UTM19_scale300.csv

python scripts/10_consolidate_national_review_plan.py `
  --input intermediate_files/review/plan_revision_UTM18_scale300.csv `
          intermediate_files/review/plan_revision_UTM19_scale300.csv `
  --out-dir intermediate_files/review
```

## Helper modules

- `selection_balancing.py` — balancing, spatial split, fill
- `critical_classes.py` — rare / critical classes
- `taxonomy_classes.py` — N3 taxonomy lookup
- `project_paths.py` — paths for `final_samples/` and `intermediate_files/`
