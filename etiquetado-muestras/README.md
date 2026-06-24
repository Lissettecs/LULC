# MapBiomas C2 Labels Cluster

Generación de **etiquetas raster y vectoriales** por rectángulo SSL4EO desde landcovers **MapBiomas Chile Collection 2** (GeoTIFF en cluster), más calibración MMU y filtro sieve para máscaras de entrenamiento.

Incluye esquema QA para revisión manual en GEE (`gee_app/`) y scripts de publicación versionada.

## Entradas (cluster)

```text
/home/lserey/mapbiomas_land/
├── prod/samples/
│   ├── final_samples/UTM{18|19}/{homogeneo_2x2|mixto_3x3}/seleccion_*.geojson
│   └── intermediate_files/review/listado_revision_manual.csv
└── ancillary_data/landcover_col2/
    └── classification_{1999..2024}.tif
```

El plan y las geometrías los produce `ssl4eo-sample-generation` (repo `coverage`).

## Salidas (paso 02)

Por zona UTM, raster + GeoPackage:

```text
prod/labels/annual/
├── UTM18/
│   ├── annual_samples.gpkg
│   ├── resumen_annual_samples.csv
│   └── raster/
│       ├── classes/{grid_id}_{year}_classes.tif
│       └── labels/{grid_id}_{year}_labels.tif
└── UTM19/
    └── ...
```

Tras el filtro sieve (`scripts/filtro_sieve_etiquetas.py`):

```text
.../sieved/UTM18/raster/classes/{grid_id}_{year}_classes_sieve.tif
```

## Instalación

```bash
cd ~/repositorio/LULC/etiquetado-muestras
source cluster/activate_mb_labels.sh
pip install -r requirements.txt   # si falta scipy u otros
```

## Flujo resumido

1. **Verificar insumos** — `bash cluster/run_check_inputs.sh`
2. **Etiquetar** — `sbatch cluster/labels_annual_samples.slurm` (o piloto eco: `labels_pilot_ecoregion.slurm`)
3. **Diagnosticar MMU** — editar paths en `scripts/distribucion_parches_raster.py` → `bash cluster/run_distribucion_parches.sh`
4. **Filtrar speckle** — editar paths en `scripts/filtro_sieve_etiquetas.py` → `bash cluster/run_filtro_sieve.sh`
5. **QA GEE** — scripts 04–06 + `gee_app/`

Detalle: [docs/flujo_cluster.md](docs/flujo_cluster.md) · Scripts: [scripts/README.md](scripts/README.md)

## Piloto por ecorregión

```bash
python scripts/select_pilot_by_ecoregion.py \
  --out-csv /home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion/pilot_grid_ids_por_ecorregion.csv

python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/ancillary_data/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion \
  --only-groups anuales \
  --grid-ids-file /home/lserey/mapbiomas_land/tmp/labels_pilot_ecoregion/pilot_grid_ids_por_ecorregion.csv \
  --product-name annual_samples_ecoregion_pilot \
  --connectivity 4 --split-by-utm --write-rasters --overwrite
```

## Metodología de parches

- **Vectorización (paso 02):** conectividad **4 (rook)** por defecto — píxeles diagonales = parches distintos.
- **Sieve (máscaras):** conectividad **8 (queen)** + MMU por clase en píxeles; clases raras con umbral bajo (2 px).
- Unidad vectorial: `grid_id + rev_year + class_id + patch_id`.

## Campos principales GPKG

`grid_id`, `rev_year`, `class_id`, `class_nm`, taxonomía N1–N3, `area_ha`, `pct_rect`, `split`, campos QA (`poly_uid`, `rect_qa`, `poly_qa`, …).

## Revisión QA (muestras anuales)

Ver sección QA en documentación anterior y [gee_app/README.md](gee_app/README.md).

```bash
python scripts/04_init_qa_fields.py \
  --gpkg /home/lserey/mapbiomas_land/prod/labels/annual/UTM18/annual_samples.gpkg \
  --layer annual_samples --overwrite
```

## SLURM (cluster leftraru)

| Job | Script |
|-----|--------|
| Piloto 5 rects | `cluster/labels_pilot_annual_samples.slurm` |
| Piloto 15 ecos | `cluster/labels_pilot_ecoregion.slurm` |
| Anuales nacional | `cluster/labels_annual_samples.slurm` |
| Por grupo | `cluster/labels_anuales.slurm` |

Logs: `/home/lserey/logs/`
