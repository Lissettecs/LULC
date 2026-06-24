# MapBiomas C2 Labels Cluster

Generation of **sieved raster mosaics** and **label GeoPackages** from MapBiomas Chile Collection 2 landcover (GeoTIFFs on cluster).

Two-step pipeline per **temporal group** and **UTM zone** (EPSG:32718 / EPSG:32719), consistent with SSL4EO-L.

## Repository structure

```text
labeling-samples/
├── src/mb_labels/
│   ├── taxonomy.py          ← C2 N1/N2/N3 taxonomy lookup
│   └── sample_paths.py      ← GeoJSON and review plan discovery
├── scripts/
│   ├── 00_check_inputs.py
│   ├── 02_extract_sieve_rectangles.py   ← step 1: sieved mosaics {year}.tif
│   └── 03_generate_labels_gpkg.py       ← step 2: GeoPackages
├── cluster/
│   ├── activate_mb_labels.sh
│   ├── run_check_inputs.sh
│   ├── run_pilot_anuales.sh
│   ├── run_{anuales|estables|transiciones|clases_raras}_utm{18|19}.sh
│   ├── labels_{annual|stable|transition|rare_classes}_utm{18|19}.slurm
│   └── submit_labels_groups.sh
└── docs/
    └── cluster_workflow.md
```

## Inputs on cluster

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/UTM{18|19}/{homogeneo_2x2|mixto_3x3}/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/classification_{year}.tif
```

## Outputs in prod/labels/

```text
prod/labels/
├── raster/
│   ├── annual/UTM18/{year}.tif
│   ├── stable/UTM18/{year}.tif
│   ├── transition/UTM18/{year}.tif
│   └── rare_classes/UTM18/{year}.tif
└── vector/
    ├── annual/UTM18/annual_samples_UTM18.gpkg
    ├── stable/UTM18/stable_samples_UTM18.gpkg
    ├── transition/UTM18/transition_samples_UTM18.gpkg
    └── rare_classes/UTM18/rare_class_samples_UTM18.gpkg
```

(Same structure for UTM19.)

## Installation

```bash
cd /home/lserey/repositorio/LULC/labeling-samples
mamba create -n mb_labels python=3.11 --file requirements.txt -c conda-forge
```

## Quick start

```bash
source cluster/activate_mb_labels.sh

# Verify inputs
bash cluster/run_check_inputs.sh

# Pilot run (5 annual rectangles)
bash cluster/run_pilot_anuales.sh

# Production via SLURM (stable + transition + rare)
mkdir -p /home/lserey/logs
bash cluster/submit_labels_groups.sh

# Or a single job
sbatch cluster/labels_stable_utm18.slurm
```

## Key parameters

| Script | Parameter | Default | Description |
|--------|-----------|---------|-------------|
| `02_extract_sieve_rectangles.py` | `--label-group` | anuales | `anuales`, `estables`, `transiciones`, `clases_raras` |
| `02_extract_sieve_rectangles.py` | `--sieve-size` | 9 | Minimum pixels per patch (0 = off) |
| `02_extract_sieve_rectangles.py` | `--only-zones` | all | `UTM18`, `UTM19` |
| `03_generate_labels_gpkg.py` | `--only-groups` | all | Same groups as above |
| `03_generate_labels_gpkg.py` | `--only-zones` | all | `UTM18`, `UTM19` |
| `03_generate_labels_gpkg.py` | `--write-rare-copy` | off | Required for `clases_raras` |

See `docs/cluster_workflow.md` for the full cluster workflow.
