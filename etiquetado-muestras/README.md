# MapBiomas C2 Labels Cluster

Repositorio para generar **rectángulos etiquetados** y **GeoPackages de subdivisiones** usando los landcovers de **MapBiomas Chile Collection 2** disponibles como GeoTIFF en cluster.

El flujo está pensado para el proyecto SSL4EO-L / MapBiomas Chile Collection 3. Los GeoPackages se generan en la **CRS nativa UTM** de cada rectángulo (EPSG:32718 o EPSG:32719), coherente con la proyección usada por SSL4EO-L.

## Entradas esperadas en el cluster

```text
/home/lserey/mapbiomas_land/
├── prod/
│   └── samples/
│       ├── listado_revision_manual.csv
│       ├── seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson
│       └── seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson
└── landcover_col2/
    ├── classification_1999.tif
    ├── classification_2000.tif
    ├── ...
    └── classification_2024.tif
```

## Estructura del repositorio

```text
etiquetado-muestras/
├── src/mb_labels/
│   ├── __init__.py
│   └── taxonomy.py          ← taxonomía N1/N2/N3 de clases C2
├── scripts/
│   ├── 00_check_inputs.py   ← verifica insumos
│   ├── 01_split_plan_by_type.py  ← divide plan por tipo (anual/estable/transicion)
│   ├── 02_extract_sieve_rectangles.py  ← extrae clips sieved por zona UTM
│   └── 03_generate_labels_gpkg.py      ← poligoniza y genera GeoPackages
├── cluster/
│   ├── run_check_inputs.sh
│   ├── run_pilot_anuales.sh
│   ├── run_sieve.sh         ← ejecuta solo el paso de extracción sieve
│   ├── run_gpkg.sh          ← ejecuta solo la generación de GeoPackages
│   └── run_all_by_group.sh  ← pipeline completo: sieve → GeoPackages
└── docs/
    └── flujo_cluster.md
```

## Salidas en prod/labels/

```text
prod/labels/
├── rectangulos/               ← rasters sieved por rectángulo-año
│   ├── utm18/{grid_id}_{year}.tif   (EPSG:32718)
│   └── utm19/{grid_id}_{year}.tif   (EPSG:32719)
├── anuales/
│   ├── utm18/subdivisiones_C2_anuales_utm18.gpkg
│   └── utm19/subdivisiones_C2_anuales_utm19.gpkg
├── estables/    utm18/ utm19/
├── transiciones/ utm18/ utm19/
└── clases_raras/ utm18/ utm19/
```

## Instalación en el cluster

```bash
cd /home/lserey/repositorios
git clone <URL_DEL_REPOSITORIO>
cd LULC/etiquetado-muestras
```

Instalar dependencias:

```bash
mamba create -n mb_labels python=3.11 geopandas rasterio pyogrio shapely pandas numpy tqdm -c conda-forge
mamba activate mb_labels
```

## Pipeline paso a paso

### 0. Verificar insumos

```bash
bash cluster/run_check_inputs.sh
```

### 1. (Opcional) Dividir plan por tipo

```bash
python scripts/01_split_plan_by_type.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples
```

### 2. Piloto (5 rectángulos)

```bash
bash cluster/run_pilot_anuales.sh
```

### 3. Pipeline completo

```bash
bash cluster/run_all_by_group.sh
```

## Parámetros clave

| Script | Parámetro | Default | Descripción |
|--------|-----------|---------|-------------|
| `02_extract_sieve_rectangles.py` | `--sieve-size` | 9 | Mínimo de píxeles por parche (0 = desactivar) |
| `02_extract_sieve_rectangles.py` | `--only-zones` | todas | `utm18`, `utm19` o ambas |
| `03_generate_labels_gpkg.py` | `--only-groups` | todos | `anuales`, `estables`, `transiciones`, `clases_raras` |
| `03_generate_labels_gpkg.py` | `--patches` | dissolve | Conserva parches individuales sin disolver |
| `03_generate_labels_gpkg.py` | `--area-crs` | EPSG:6933 | CRS igual-área para cálculo de áreas |

## Campos de salida en GeoPackages

```text
grid_id          review_year      class_id         class_name
n1_cd  n1_nm    n2_cd  n2_nm    n3_cd  n3_nm
es_transversal   es_critica_n3    patch_id
sample_type      dim_temporal     dim_espacial      review_rule
review_priority  review_tier      review_status     split
target_rare_class lulc_mode_id   lulc_mode_name    eco_dom_id  eco_dom_name
source_tif       utm_zone
area_m2          area_ha          rect_area_m2      pct_rect
geometry
```

## Notas metodológicas

- El filtro sieve elimina parches de píxeles aislados menores a `--sieve-size` píxeles antes de poligonizar, reduciendo ruido sal-y-pimienta en el raster C2.
- Los clips sieved se guardan en la CRS nativa UTM del rectángulo (`prod/labels/rectangulos/utm18/` o `utm19/`), permitiendo reprocesar los GeoPackages sin relectura del raster anual completo.
- Los GeoPackages también quedan en CRS nativa UTM, coherente con la proyección esperada por SSL4EO-L.
- La clave de revisión es `grid_id + review_year`. El split se hereda desde el rectángulo y no debe mezclarse entre train/val/test.
- Por defecto los parches se disuelven por `grid_id + review_year + class_id`. Usa `--patches` para conservar cada parche continuo como entidad separada.
