# MapBiomas C2 Labels Cluster

Repositorio para generar **rectángulos etiquetados** y **subdivisiones internas por clase** usando los landcovers de **MapBiomas Chile Collection 2** disponibles como GeoTIFF en cluster.

El flujo está pensado para el proyecto SSL4EO-L / MapBiomas Chile Collection 3.

## Entradas esperadas en el cluster

Los datos principales se mantienen fuera del repositorio:

```text
/home/lserey/mapbiomas_land/
├── prod/
│   ├── samples/
│   │   ├── listado_revision_manual.csv
│   │   ├── seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson
│   │   └── seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson
│   └── labels/
└── landcover_col2/
    ├── classification_1999.tif
    ├── classification_2000.tif
    ├── ...
    └── classification_2024.tif
```

## Salidas esperadas

```text
/home/lserey/mapbiomas_land/prod/labels/
├── anuales/
│   └── subdivisiones_C2_anuales.gpkg
├── estables/
│   └── subdivisiones_C2_estables.gpkg
├── transiciones/
│   └── subdivisiones_C2_transiciones.gpkg
└── clases_raras/
    └── subdivisiones_C2_clases_raras.gpkg
```

Cada GeoPackage contiene polígonos derivados desde el raster C2 correspondiente a cada año de revisión.

La unidad de salida es:

```text
grid_id + review_year + class_id
```

Si se usa `--patches`, la unidad es:

```text
grid_id + review_year + class_id + patch_id
```

## Instalación en el cluster

Desde el cluster:

```bash
cd /home/lserey
mkdir -p repositorios
cd repositorios

git clone <URL_DEL_REPOSITORIO>
cd LULC/etiquetado-muestras
```

Instalar dependencias en el ambiente Python que uses:

```bash
pip install -r requirements.txt
```

Si usas conda/mamba:

```bash
mamba create -n mb_labels python=3.11 geopandas rasterio pyogrio shapely pandas numpy tqdm -c conda-forge
mamba activate mb_labels
```

## Verificar insumos

```bash
python scripts/00_check_inputs.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2
```

## Crear planes por tipo

```bash
python scripts/01_split_plan_by_type.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --out-dir /home/lserey/mapbiomas_land/prod/samples/planes_por_tipo
```

Esto genera `plan_anuales.csv`, `plan_estables.csv`, `plan_transiciones.csv` y `plan_clases_raras.csv`.

## Ejecutar un piloto

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --max-rows 5 \
  --overwrite
```

## Ejecutar por grupo

Anuales:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --overwrite
```

Estables:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups estables \
  --overwrite
```

Transiciones:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups transiciones \
  --overwrite
```

Clases raras:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups clases_raras \
  --write-rare-copy \
  --overwrite
```

## Campos principales de salida

```text
grid_id
review_year
class_id
class_name
n1_cd, n1_nm
n2_cd, n2_nm
n3_cd, n3_nm
es_transversal
es_critica_n3
area_m2
area_ha
pct_rect
sample_type
dim_temporal
dim_espacial
review_rule
split
target_rare_class
geometry
```

## Notas metodológicas

- El mismo rectángulo puede aparecer en varios años.
- La clave de revisión es `grid_id + review_year`.
- El split se hereda desde el rectángulo. No se deben separar años o chips del mismo rectángulo en train/val/test distintos.
- Por defecto, el script disuelve parches por `grid_id + review_year + class_id` para reducir tamaño.
- Usa `--patches` si necesitas conservar cada parche separado.
