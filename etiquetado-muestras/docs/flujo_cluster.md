# Flujo de etiquetado en cluster

## Estructura de insumos

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/
│   │   ├── UTM18/{homogeneo_2x2,mixto_3x3}/seleccion_*.geojson
│   │   └── UTM19/{homogeneo_2x2,mixto_3x3}/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/classification_{year}.tif
```

## Estructura de salida

```text
prod/labels/
├── raster/{annual|stable|transition|rare_classes}/UTM{18|19}/{year}.tif
└── vector/{annual|stable|transition|rare_classes}/UTM{18|19}/*_samples_UTM*.gpkg
```

Un mosaico por año y zona UTM (homogéneo + mixto combinados). CRS nativa UTM del huso.

---

## 1. Verificar entradas

```bash
cd /home/lserey/repositorio/LULC/etiquetado-muestras
bash cluster/run_check_inputs.sh
```

## 2. Piloto (5 rectángulos anuales)

```bash
bash cluster/run_pilot_anuales.sh
```

## 3. Producción por grupo y zona

Cada script ejecuta sieve → GeoPackage para un grupo y un huso UTM:

| Grupo | Carpeta raster/vector | Script bash | SLURM |
|-------|----------------------|-------------|-------|
| anuales | `annual/` | `run_anuales_utm18.sh` | `labels_annual_utm18.slurm` |
| estables | `stable/` | `run_estables_utm18.sh` | `labels_stable_utm18.slurm` |
| transiciones | `transition/` | `run_transiciones_utm18.sh` | `labels_transition_utm18.slurm` |
| clases_raras | `rare_classes/` | `run_clases_raras_utm18.sh` | `labels_rare_classes_utm18.slurm` |

(Misma tabla con `utm19` para UTM19.)

```bash
source cluster/activate_mb_labels.sh
bash cluster/run_estables_utm18.sh
```

## 4. Enviar jobs SLURM

```bash
mkdir -p /home/lserey/logs

# Pendientes: stable + transition + rare
bash cluster/submit_labels_groups.sh

# Incluir annual (re-ejecución)
bash cluster/submit_labels_groups.sh --all

# Un grupo
bash cluster/submit_labels_groups.sh stable
sbatch cluster/labels_transition_utm19.slurm
```

Memoria SLURM: **32G** (annual, stable), **64G** (transition, rare_classes).

Logs en `/home/lserey/logs/labels_{grupo}_utm{18|19}_JOBID.{out,err}`.

## 5. Opciones adicionales (CLI)

```bash
python scripts/02_extract_sieve_rectangles.py ... --only-years 2020 2021
python scripts/03_generate_labels_gpkg.py     ... --only-years 2020 2021
python scripts/03_generate_labels_gpkg.py     ... --patches   # parches sin disolver
```
