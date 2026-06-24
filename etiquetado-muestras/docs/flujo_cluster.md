# Flujo de etiquetado en cluster

## Estructura de insumos

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/
│   │   ├── UTM18/
│   │   │   ├── homogeneo_2x2/seleccion_*.geojson
│   │   │   └── mixto_3x3/seleccion_*.geojson
│   │   └── UTM19/
│   │       ├── homogeneo_2x2/seleccion_*.geojson
│   │       └── mixto_3x3/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/classification_{year}.tif
```

## Estructura de salida en prod/labels/

```text
prod/labels/
├── rectangulos/               ← rasters sieved por rectángulo-año
│   ├── UTM18/{grid_id}_{year}.tif   (EPSG:32718)
│   └── UTM19/{grid_id}_{year}.tif   (EPSG:32719)
├── anuales/
│   ├── UTM18/subdivisiones_C2_anuales_UTM18.gpkg
│   └── UTM19/subdivisiones_C2_anuales_UTM19.gpkg
├── estables/    UTM18/ UTM19/
├── transiciones/ UTM18/ UTM19/
└── clases_raras/ UTM18/ UTM19/
```

Los GeoPackages se mantienen en la CRS nativa UTM (EPSG:32718 o EPSG:32719), coherente con la proyección esperada por SSL4EO-L.

---

## 1. Verificar entradas

```bash
cd /home/lserey/repositorios/LULC/etiquetado-muestras
bash cluster/run_check_inputs.sh
```

Comprueba:
- GeoJSON en `final_samples/UTM{18|19}/{homogeneo_2x2|mixto_3x3}/`
- Plan en `intermediate_files/review/listado_revision_manual.csv`
- Rasters C2 en `ancillary_data/landcover_col2/classification_{year}.tif`

## 2. Piloto (5 rectángulos, solo anuales)

```bash
bash cluster/run_pilot_anuales.sh
```

Ejecuta en secuencia:
- Extrae 5 rectángulos con sieve → `prod/labels/rectangulos/UTM18/` y `UTM19/`
- Genera GeoPackages anuales → `prod/labels/anuales/UTM18/` y `UTM19/`

Revisar en QGIS:
```text
prod/labels/anuales/UTM18/subdivisiones_C2_anuales_UTM18.gpkg
prod/labels/anuales/UTM19/subdivisiones_C2_anuales_UTM19.gpkg
```

## 3. Pipeline completo

```bash
bash cluster/run_all_by_group.sh
```

Equivalente a:

### Paso 1 — Extraer rectángulos con sieve

```bash
bash cluster/run_sieve.sh
```

O manualmente:

```bash
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir    /home/lserey/mapbiomas_land/prod/labels \
  --sieve-size    9 \
  --overwrite
```

`--sieve-size` es el número mínimo de píxeles de un parche para no ser eliminado. Con `0` se desactiva.

### Paso 2 — Generar GeoPackages

```bash
bash cluster/run_gpkg.sh
```

O por grupo individual:

```bash
python scripts/03_generate_labels_gpkg.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --overwrite
```

## 4. Opciones adicionales

### Filtrar por zona UTM

```bash
python scripts/02_extract_sieve_rectangles.py ... --only-zones UTM18
python scripts/03_generate_labels_gpkg.py     ... --only-zones UTM18
```

### Conservar parches individuales (sin disolver por clase)

```bash
python scripts/03_generate_labels_gpkg.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --patches \
  --overwrite
```

### Filtrar por año

```bash
python scripts/02_extract_sieve_rectangles.py ... --only-years 2020 2021
python scripts/03_generate_labels_gpkg.py     ... --only-years 2020 2021
```
