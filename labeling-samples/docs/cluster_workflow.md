# Cluster labeling workflow

## Input structure

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/
│   │   ├── UTM18/{homogeneo_2x2,mixto_3x3}/seleccion_*.geojson
│   │   └── UTM19/{homogeneo_2x2,mixto_3x3}/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/classification_{year}.tif
```

## Output structure

```text
prod/labels/
├── raster/{annual|stable|transition|rare_classes}/UTM{18|19}/{year}.tif
└── vector/{annual|stable|transition|rare_classes}/UTM{18|19}/*_samples_UTM*.gpkg
```

One mosaic per year and UTM zone (homogeneo + mixto combined). Native UTM CRS per zone.

---

## 1. Verify inputs

```bash
cd /home/lserey/repositorio/LULC/labeling-samples
bash cluster/run_check_inputs.sh
```

## 2. Pilot run (5 annual rectangles)

```bash
bash cluster/run_pilot_anuales.sh
```

## 3. Production by group and zone

Each script runs sieve → GeoPackage for one group and one UTM zone:

| Group | raster/vector folder | Bash script | SLURM |
|-------|----------------------|-------------|-------|
| anuales | `annual/` | `run_anuales_utm18.sh` | `labels_annual_utm18.slurm` |
| estables | `stable/` | `run_estables_utm18.sh` | `labels_stable_utm18.slurm` |
| transiciones | `transition/` | `run_transiciones_utm18.sh` | `labels_transition_utm18.slurm` |
| clases_raras | `rare_classes/` | `run_clases_raras_utm18.sh` | `labels_rare_classes_utm18.slurm` |

(Same table with `utm19` for UTM19.)

```bash
source cluster/activate_mb_labels.sh
bash cluster/run_estables_utm18.sh
```

## 4. Submit SLURM jobs

```bash
mkdir -p /home/lserey/logs

# Pending: stable + transition + rare
bash cluster/submit_labels_groups.sh

# Include annual (re-run)
bash cluster/submit_labels_groups.sh --all

# Single group
bash cluster/submit_labels_groups.sh stable
sbatch cluster/labels_transition_utm19.slurm
```

SLURM memory: **32G** (annual, stable), **64G** (transition, rare_classes).

Logs at `/home/lserey/logs/labels_{group}_utm{18|19}_{JOBID}.{out,err}`.

## 5. Additional CLI options

```bash
python scripts/02_extract_sieve_rectangles.py ... --only-years 2020 2021
python scripts/03_generate_labels_gpkg.py     ... --only-years 2020 2021
python scripts/03_generate_labels_gpkg.py     ... --patches   # patches without dissolving
```
