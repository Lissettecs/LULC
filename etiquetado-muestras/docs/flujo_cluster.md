# Flujo de etiquetado en cluster

Repositorio: `/home/lserey/repositorio/LULC/etiquetado-muestras`

## 1. Verificar entradas

```bash
cd /home/lserey/repositorio/LULC/etiquetado-muestras
source cluster/activate_mb_labels.sh
bash cluster/run_check_inputs.sh
```

Comprueba:
- Plan en `prod/samples/intermediate_files/review/listado_revision_manual.csv`
- Rectángulos en `prod/samples/final_samples/UTM*/**/seleccion_*.geojson`
- Rasters C2 en `ancillary_data/landcover_col2/classification_{year}.tif`

## 2. Piloto rápido (5 rectángulos anuales)

```bash
sbatch cluster/labels_pilot_annual_samples.slurm
# o:
bash cluster/run_pilot_annual_samples.sh
```

Salida: `tmp/labels_pilot_annual_samples_v2/UTM{18|19}/`

## 3. Piloto por ecorregión (15 rects, 1 por eco)

```bash
sbatch cluster/labels_pilot_ecoregion.slurm
# o:
bash cluster/run_pilot_ecoregion_coverage.sh
```

Genera `pilot_grid_ids_por_ecorregion.csv` y etiqueta esos `grid_id`.

Salida: `tmp/labels_pilot_ecoregion/UTM{18|19}/`

## 4. Etiquetado nacional (anuales)

```bash
mkdir -p ~/logs
sbatch cluster/labels_annual_samples.slurm
```

Producto QA: `prod/labels/annual/UTM{18|19}/annual_samples.gpkg`

## 5. Diagnóstico MMU (calibración de umbrales)

Editar `INPUT_DIR` y `SELECTION_TABLE` en `scripts/distribucion_parches_raster.py`, luego:

```bash
bash cluster/run_distribucion_parches.sh
```

Reportes: `distribucion_parches_por_clase.csv`, `clases_ausentes.csv`, cobertura por tile/año/ecorregión.

## 6. Filtro sieve (speckle → máscaras de entrenamiento)

Editar `INPUT_DIR` / `OUTPUT_DIR` en `scripts/filtro_sieve_etiquetas.py`, luego:

```bash
bash cluster/run_filtro_sieve.sh
```

Entrada: `*_classes.tif` · Salida: `*_classes_sieve.tif` (no sobrescribe originales).

## 7. Producción por grupo

```bash
bash cluster/run_all_by_group.sh
```

## 8. Parches individuales (conectividad rook)

Por defecto el paso 02 usa **conectividad 4** (rook) al vectorizar. Para comparar con queen:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --connectivity 8 \
  --overwrite
```

## Estructura de salida (paso 02)

```text
labels-dir/
├── UTM18/
│   ├── annual_samples.gpkg
│   ├── resumen_annual_samples.csv
│   └── raster/
│       ├── classes/{grid_id}_{year}_classes.tif
│       └── labels/{grid_id}_{year}_labels.tif
└── UTM19/
    └── ...
```

Tras el sieve:

```text
labels-dir/sieved/
└── UTM18/raster/classes/{grid_id}_{year}_classes_sieve.tif
```
