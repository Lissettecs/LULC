# MapBiomas C2 Labels Cluster

Generación de **mosaicos raster sieved** y **GeoPackages de etiquetas** desde landcover MapBiomas Chile Collection 2 (GeoTIFF en cluster).

Pipeline en dos pasos por **grupo temporal** y **zona UTM** (EPSG:32718 / EPSG:32719), coherente con SSL4EO-L.

## Estructura del repositorio

```text
etiquetado-muestras/
├── src/mb_labels/
│   ├── taxonomy.py          ← taxonomía N1/N2/N3 de clases C2
│   └── sample_paths.py      ← descubrimiento de GeoJSON y plan
├── scripts/
│   ├── 00_check_inputs.py
│   ├── 02_extract_sieve_rectangles.py   ← paso 1: mosaicos {year}.tif
│   └── 03_generate_labels_gpkg.py       ← paso 2: GeoPackages
├── cluster/
│   ├── activate_mb_labels.sh
│   ├── run_check_inputs.sh
│   ├── run_pilot_anuales.sh
│   ├── run_{anuales|estables|transiciones|clases_raras}_utm{18|19}.sh
│   ├── labels_{annual|stable|transition|rare_classes}_utm{18|19}.slurm
│   └── submit_labels_groups.sh
└── docs/
    └── flujo_cluster.md
```

## Entradas en cluster

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/UTM{18|19}/{homogeneo_2x2|mixto_3x3}/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/classification_{year}.tif
```

## Salidas en prod/labels/

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

(Misma estructura para UTM19.)

## Instalación

```bash
cd /home/lserey/repositorio/LULC/etiquetado-muestras
mamba create -n mb_labels python=3.11 --file requirements.txt -c conda-forge
```

## Uso rápido

```bash
source cluster/activate_mb_labels.sh

# Verificar insumos
bash cluster/run_check_inputs.sh

# Piloto (5 rectángulos anuales)
bash cluster/run_pilot_anuales.sh

# Producción vía SLURM (stable + transition + rare)
mkdir -p /home/lserey/logs
bash cluster/submit_labels_groups.sh

# O un job individual
sbatch cluster/labels_stable_utm18.slurm
```

## Parámetros clave

| Script | Parámetro | Default | Descripción |
|--------|-----------|---------|-------------|
| `02_extract_sieve_rectangles.py` | `--label-group` | anuales | `anuales`, `estables`, `transiciones`, `clases_raras` |
| `02_extract_sieve_rectangles.py` | `--sieve-size` | 9 | Mínimo píxeles por parche (0 = off) |
| `02_extract_sieve_rectangles.py` | `--only-zones` | todas | `UTM18`, `UTM19` |
| `03_generate_labels_gpkg.py` | `--only-groups` | todos | Mismos grupos que arriba |
| `03_generate_labels_gpkg.py` | `--only-zones` | todas | `utm18`, `utm19` |
| `03_generate_labels_gpkg.py` | `--write-rare-copy` | off | Requerido para `clases_raras` |

Ver `docs/flujo_cluster.md` para el flujo completo en cluster.
