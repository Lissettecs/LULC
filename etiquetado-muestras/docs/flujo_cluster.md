# Flujo de etiquetado en cluster

## Estructura de salida en prod/labels/

```text
prod/labels/
├── rectangulos/               ← rasters sieved por rectángulo-año
│   ├── utm18/
│   │   └── {grid_id}_{year}.tif   (EPSG:32718)
│   └── utm19/
│       └── {grid_id}_{year}.tif   (EPSG:32719)
├── anuales/
│   ├── utm18/
│   │   ├── subdivisiones_C2_anuales_utm18.gpkg
│   │   └── resumen_C2_anuales_utm18.csv
│   └── utm19/
│       ├── subdivisiones_C2_anuales_utm19.gpkg
│       └── resumen_C2_anuales_utm19.csv
├── estables/    utm18/ utm19/
├── transiciones/ utm18/ utm19/
└── clases_raras/ utm18/ utm19/
```

Los GeoPackages se mantienen en la CRS nativa UTM del rectángulo (EPSG:32718
o EPSG:32719), coherente con la proyección esperada por SSL4EO-L.

---

## 1. Verificar entradas

```bash
cd /home/lserey/repositorios/LULC/etiquetado-muestras
bash cluster/run_check_inputs.sh
```

## 2. Piloto (5 rectángulos, solo anuales)

```bash
bash cluster/run_pilot_anuales.sh
```

Esto ejecuta los dos pasos del piloto:
- Extrae 5 rectángulos con sieve → `prod/labels/rectangulos/{utm18,utm19}/`
- Genera GeoPackages anuales → `prod/labels/anuales/{utm18,utm19}/`

Revisar en QGIS:
```text
prod/labels/anuales/utm18/subdivisiones_C2_anuales_utm18.gpkg
prod/labels/anuales/utm19/subdivisiones_C2_anuales_utm19.gpkg
```

## 3. Pipeline completo

```bash
bash cluster/run_all_by_group.sh
```

Equivalente a ejecutar en secuencia:

### Paso 1 — Extraer rectángulos con sieve

```bash
python scripts/02_extract_sieve_rectangles.py \
  --samples-dir   /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir    /home/lserey/mapbiomas_land/prod/labels \
  --sieve-size    9 \
  --overwrite
```

El parámetro `--sieve-size` indica el número mínimo de píxeles de un parche
para que no sea eliminado. Con `--sieve-size 0` se desactiva el filtro.

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

### Separar por zona UTM

```bash
python scripts/03_generate_labels_gpkg.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --labels-dir  /home/lserey/mapbiomas_land/prod/labels \
  --only-zones  utm18 \
  --overwrite
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
