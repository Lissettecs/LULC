# Sample review calibration — MapBiomas Chile Collection 3

Blind calibration test for label reviewers on **100% pure** segments (single Collection-2 class across the whole segment). Fits in one workday and aims to cover every evaluable class with non-contiguous segments.

## Framework (read carefully)

**The test reference is the class confirmed by the supervisor, not the raw C2 label.**

Human workflow:

1. The supervisor validates or corrects the class of each selected segment → that produces the **answer key**.
2. Reviewers classify the same segments **blind** (no proposed class / proportion).
3. Scoring compares each reviewer against the supervisor-confirmed key.

This measures **reviewer agreement with the supervisor-confirmed key on 100% pure segments**. It is **not** a validation of Collection 2.

## Repository layout

```
sample_review_calibration/
  README.md
  requirements.txt
  .gitignore
  legend/                 # optional code→name mapping
  src/
    01_analyze_proportion.py
    02_select_sample.py
    03_evaluate_calibration.py
```

## Paths

| Role | Path |
|------|------|
| Input (read-only) | `/home/lserey/mapbiomas_land/prod/04_labeling_cim/2015/consolidado/labeled_segments_rev2015.gpkg` |
| Code repo | `/home/lserey/repositorio/webapp/sample_review_calibration` |
| Results base | `/home/lserey/mapbiomas_land/prod/sample_review_calibration` |

Every run writes under a non-destructive timestamp folder: `<results>/<YYYYMMDD_HHMMSS>/…`.

CRS: input is EPSG:4326 (CIM). The canonical GPKG is **never** reprojected. Metric area/distance use per-centroid UTM query geometries or geodesic distance (`pyproj.Geod`).

## Environment

```bash
# recommended: existing MapBiomas labels env
/home/lserey/.conda/envs/mb_labels/bin/python -m pip install -r requirements.txt  # if needed
```

Set parameters in the `# ═══` block at the top of each script before running.

## Phase 1 — proportion analysis and quota proposal only

```bash
cd /home/lserey/repositorio/webapp/sample_review_calibration
/home/lserey/.conda/envs/mb_labels/bin/python src/01_analyze_proportion.py
```

Outputs under `<run>/analysis/`:

- `class_proportion_distribution.csv`
- `proposed_quotas.csv` (**editable** — review before Phase 2)
- `analysis_report.md`

**Stop here** until quotas are approved. Do not run Phase 2 until then.

## Phase 2 — sample selection + supervisor / blind packages

1. Point `QUOTAS_CSV` at the approved `proposed_quotas.csv` (or an edited copy).
2. Adjust `REVISORES`, `SEED`, separation params, `SUPERVISOR_MODE` as needed.

```bash
/home/lserey/.conda/envs/mb_labels/bin/python src/02_select_sample.py
```

Outputs under `<run>/sample/`:

- `supervisor_review.gpkg` — supervisor work file (not blind in `confirmar` mode)
- `calibration_review_blind.gpkg` / `.csv` — blind baseline
- `per_reviewer/review_<revisor>.gpkg` — one blind copy per reviewer
- `README_run.md` — run parameters and workflow notes

### After Phase 2 (human, parallel)

| Role | File | Action |
|------|------|--------|
| Supervisor | `supervisor_review.gpkg` | Fill/confirm `supervisor_class`, mark `supervisor_confirmed` |
| Reviewers | `per_reviewer/review_*.gpkg` | Fill `reviewer_class` (blind) |

## Phase 3 — scoring (after reviews are complete)

Point `SUPERVISOR_FILE` and `REVIEWER_FILES` at the filled files, then:

```bash
/home/lserey/.conda/envs/mb_labels/bin/python src/03_evaluate_calibration.py
```

Outputs under `<run>/results/`:

- `accuracy_overall.csv`, `accuracy_per_class.csv`, `confusion_matrix.csv`
- `agreement.csv` (if >1 reviewer)
- `c2_vs_supervisor_corrections.csv` (only if supervisor file has `proposed_class`)

Rows without `supervisor_class` are excluded from scoring.

## Conventions

- Script **filenames**: **English**
- Code, comments, console messages: **Spanish**
- Output column names and data file names: **English**
- README / `README_run.md`: **English**
- Fixed seed; parameters logged every run
