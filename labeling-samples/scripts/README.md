# Scripts — etiquetado-muestras

Ejecutar desde la raíz del repositorio con `source cluster/activate_mb_labels.sh`.

## Pipeline principal (00–06)

| Script | Función |
|--------|---------|
| `00_check_inputs.py` | Verifica plan, GeoJSON en `final_samples/` y rasters C2 |
| `01_split_plan_by_type.py` | Divide el plan en CSV por `dim_temporal` |
| `02_generate_labels_c2_cluster.py` | Etiquetas raster + GPKG por UTM; conectividad 4 por defecto |
| `03_export_labels_gee_asset.py` | Re-exporta GPKG existente a GEE |
| `04_init_qa_fields.py` | Backfill campos QA en GPKG |
| `05_validate_qa_export.py` | Validación pre-publicación QA |
| `06_publish_qa_version.py` | Publica versión QA desde borrador JSON |

## Selección de pilotos

| Script | Función |
|--------|---------|
| `select_pilot_by_ecoregion.py` | 1 rectángulo anual por ecorregión → CSV de `grid_id` |

## Calibración y limpieza MMU (post-etiquetado)

| Script | Función |
|--------|---------|
| `distribucion_parches_raster.py` | Diagnóstico conect 4 vs 8; columna `confiable`; cobertura |
| `filtro_sieve_etiquetas.py` | Filtro speckle MMU (conect-8) → `*_classes_sieve.tif` |

Editar el bloque **PARÁMETROS** al inicio de cada script auxiliar.

## Módulos (`src/mb_labels/`)

| Módulo | Uso |
|--------|-----|
| `sample_paths.py` | Rutas `final_samples/`, plan de revisión, UTM |
| `raster_io.py` | Escritura GeoTIFF de clases/labels |
| `field_names.py` | Nombres canónicos ≤10 chars |
| `taxonomy.py` | Lookup taxonomía C2 N3 |
| `qa_fields.py` | Esquema QA |
| `gee_export.py` | Export a Earth Engine |

## Flags útiles del paso 02

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --only-groups anuales \
  --grid-ids-file tmp/pilot_grid_ids_por_ecorregion.csv \
  --product-name annual_samples \
  --connectivity 4 \
  --split-by-utm \
  --write-rasters \
  --overwrite
```
