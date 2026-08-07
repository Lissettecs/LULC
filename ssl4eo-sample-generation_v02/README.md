# Pipeline SSL4EO v02 — muestreo por ecorregión

Repositorio nuevo para caracterización y selección de rectángulos según estrategia v05.
**No usa Google Earth Engine** — todo en cluster con rasterio.

Referencia de lógica (solo lectura): `coverage/ssl4eo-sample-generation`.

## Scripts numerados (orden de ejecución)

| # | Script | Qué hace |
|---|--------|----------|
| 00 | `scripts/00_estado_pipeline.py` | Estado de corridas (solo lectura) |
| 01 | `scripts/01_verificar_insumos.py` | Verifica MGRS, 26 años landcover, grillas eco↔lulc |
| 02 | `scripts/02_alinear_ecorregiones.py` | Recorta ecorregiones a grilla landcover (islas fuera) |
| 03 | `scripts/03_generar_lista_tiles.py` | Escribe `tiles.txt` + abre corrida |
| 04 | `scripts/04_caracterizar_tile.py` | Caracteriza **un** tile MGRS (tarea array SLURM) |
| 05 | `scripts/05_consolidar_grillas.py` | Une parciales → GeoPackage por huso/tamaño |
| 06 | `scripts/06_presupuesto_seleccion.py` | **Dry-run**: universo local y cuotas (punto de control) |
| 07 | `scripts/07_seleccionar_rectangulos.py` | Selección por ecorregión |
| 08 | `scripts/08_visualizar_seleccion.py` | Dashboard interactivo (Streamlit / HTML) |
| 09 | `scripts/09_generar_informe_seleccion.py` | Informe markdown vs baseline |
| 10 | `scripts/10_generar_plan_revision.py` | Años de revisión `rev_year1/2/3` (derivación local) |

## Orden recomendado

```bash
cd /home/lserey/repositorio/coverage/ssl4eo-sample-generation_v02
conda activate mb_coverage

# Preparación (una vez)
python scripts/01_verificar_insumos.py          # fallará si eco no alineado
python scripts/02_alinear_ecorregiones.py
python scripts/01_verificar_insumos.py          # debe pasar

# Piloto un tile
python scripts/04_caracterizar_tile.py --tile 18HYD

# Producción caracterización
N=$(python scripts/03_generar_lista_tiles.py)
sbatch --array=0-$((N-1))%20 jobs/run_caracterizacion.slurm

python scripts/00_estado_pipeline.py
sbatch jobs/run_consolidar.slurm

# Punto de control antes de seleccionar
python scripts/06_presupuesto_seleccion.py

sbatch jobs/run_seleccion.slurm

# Visualizar selección (interactivo o HTML estático)
streamlit run scripts/08_visualizar_seleccion.py
python scripts/08_visualizar_seleccion.py --export-html dashboard_seleccion.html

# Informe de selección (baseline de comparación: 20260724_1357)
python scripts/09_generar_informe_seleccion.py --seleccion 20260727_1340
python scripts/09_generar_informe_seleccion.py --seleccion TAG \
    --baseline 20260724_1357 --caracterizacion 20260727_1004

# Plan de años de revisión (no modifica la selección original)
python scripts/10_generar_plan_revision.py --seleccion 20260727_1340
python main.py plan-revision --seleccion TAG

# Tests aceptación nacional (último lanzamiento)
CARACT_RUN_TAG=20260727_1004 SEL_RUN_TAG=20260727_1340 \
  python -m pytest tests/test_aceptacion_nacional.py -v
python -m pytest tests/test_plan_revision.py -v
```

## Datos

- **Entrada (solo lectura):** `/home/lserey/mapbiomas_land/ancillary_data/`
- **Salida:** `/home/lserey/mapbiomas_land/prod/samples_v02/`
- **Matriz presencia:** `prod/samples_v02/_insumos/clase_x_ecorregion.csv`

## Notas v02 vs v1

- IDs nativos C2 (sin remapeo a leyenda general).
- Composición `pct_{id}` a **30 m exacto**; temporal a 300 m.
- Ecorregión = unidad de modelo; rareza y cuotas locales.
- `north_forest_pct` eliminado → bbox tamarugo (clase 3).
- En grillas v1, `lulc_mode_id=10` era humedal colapsado; en v02 recupera significado del diccionario.

## Composición y área válida (caracterización)

Definición explícita de porcentajes por rectángulo:

```
píxeles_totales  = todos los píxeles del rectángulo
píxeles_nodata   = clase 0 (CLASE_NODATA_RASTER) → nodata_raster_pct
píxeles_noobs    = clase 27 (No_observado)        → noobs_pct
píxeles_válidos  = totales − nodata − noobs

pct_{id}  = 100 × count(id) / píxeles_válidos     para id ∉ {0, 27}
valid_area_pct = 100 × píxeles_válidos / píxeles_totales
```

La clase 0 **no** entra al vector `pct_{id}`. Las métricas temporales enmascaran píxeles nodata antes de agregar a 300 m.

## Sistema de referencia (UTM nativo)

- Huso 18 → **EPSG:32718** · Huso 19 → **EPSG:32719**
- GeoPackage consolidados y de selección se exportan en UTM nativo por huso.
- Capas `*_inspeccion_wgs84.gpkg` son solo para inspección visual.

### Archivos de geometría (selección)

Las capas canónicas para medir lados y áreas son `seleccion_nacional_utm18.gpkg`
(EPSG:32718) y `seleccion_nacional_utm19.gpkg` (EPSG:32719), una por huso en su UTM
nativo. Las capas `*_inspeccion_*` (p. ej. `seleccion_e10_inspeccion_no_metrica.gpkg`)
mezclan husos en un CRS común y **deforman la geometría**; sirven solo para
visualización. Tienen columna `_uso = inspeccion_visual_no_medir_geometria`.

## Diagnóstico y corrección

```bash
python diagnostico/revisar_corrida.py --caracterizacion TAG_CARACT --seleccion TAG_SEL
python main.py seleccionar --etapa presupuesto --dry-run
TAMANO_LOTE=10 bash jobs/lanzar_por_lotes.sh   # solo si hace falta recaracterizar
pytest tests/test_aceptacion_nacional.py        # CARACT_RUN_TAG=20260727_1004 SEL_RUN_TAG=20260727_1340
pytest tests/test_plan_revision.py
```

## Último lanzamiento

Ver **`docs/LANZAMIENTO_20260727.md`**: caracterización `20260727_1004`, selección
`20260727_1340`, plan revisión `plan_revision_20260727_2030`.

Informe de estrategia (caracterización + selección): **`docs/ESTRATEGIA_CARACTERIZACION_SELECCION.md`**.

## Rama git

`feature/plan-revision-years` — grilla UTM nacional, selección corregida, plan `rev_year*`.
