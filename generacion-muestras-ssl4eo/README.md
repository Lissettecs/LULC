# Generación de muestras SSL4EO-L para Land Cover Chile

Flujo de generación, selección, revisión y auditoría de rectángulos de muestreo (2×2 y 3×3, `scale300`) para chips multitemporales SSL4EO-L/Landsat. Diseñado para la clasificación anual de cobertura y uso del suelo de Chile (objetivo 1996–2025), con referencia MapBiomas Chile Collection 2 para 1999–2024.

Ejecutar los comandos desde la raíz de este directorio.

## Pipeline de scripts (01–10)

Referencia rápida. Ejemplos completos en [scripts/README.md](scripts/README.md).

| Paso | Script | Qué hace | Entrada | Salida |
|------|--------|----------|---------|--------|
| 01 | `01_caracterizacion_grillas_gee.py` | Caracteriza grillas candidatas en Earth Engine (v3.1) y exporta SHP a Drive | Assets MapBiomas C2, ecorregiones C3, tiles MGRS | Carpeta `GEE_exports` en Drive |
| 02 | `02_descargar_grillas_drive.py` | Descarga y empaqueta shapefiles desde Drive | `GEE_exports` (prefijos `scale300`) | `archivos_intermedios/gee_caracterizacion/*.zip` |
| 03 | `03_seleccion_rectangulos.py` | Selección balanceada por 6 tipos de muestra + clases críticas; anti-solape intra-huso y frontera UTM18/UTM19 | ZIP 2×2 (`--homogeneo`) y/o 3×3 (`--mixto`) | `muestras_finales/seleccion_*` y `reservas_*` |
| 04 | `04_anotar_taxonomia_grillas.py` | Añade columnas taxonomía N1/N2/N3 (requiere IDs nativos C2 nivel 3) | CSV/GPKG de selección | `*_taxonomia_n3.csv` (u otro formato de entrada) |
| 05 | `05_revision_seleccion_rectangulos.py` | Tablas de revisión e informe de texto | GeoJSON/GPKG de `muestras_finales/` | `archivos_intermedios/revision/` (`01_`–`09_`, `REVISION_COMPLETA*.txt`) |
| 06 | `06_auditoria_balanceo.py` | Checklist de balanceo nacional vs metas operativas | GeoJSON de selección | `archivos_intermedios/revision/AUDITORIA_BALANCEO.txt` |
| 07 | `07_visualizar_reportes.py` | Dashboard Streamlit de reportes y mapas | Reportes CSV + geometrías | Vista interactiva o HTML exportado |
| 08 | — | *Sin script.* El prefijo `08_` identifica tablas de clases críticas generadas por el paso 05 | — | `08_clases_criticas_*`, `08_achaparrado_detalle_*` |
| 09 | `09_generar_plan_revision_rectangulos.py` | Define `review_years`, regla y prioridad por rectángulo | GeoJSON/GPKG de selección | `plan_revision_UTM*_scale300.csv` |
| 10 | `10_consolidar_plan_revision_nacional.py` | Fusiona planes UTM18/UTM19 y genera resúmenes | CSV de planes por huso | Plan nacional + tablas resumen en `archivos_intermedios/revision/` |

## Estructura del flujo

```text
generacion-muestras-ssl4eo/
├── README.md
├── requirements.txt
├── environment.yml
├── scripts/
│   ├── README.md
│   ├── 01_…10_*.py
│   └── rutas_proyecto.py, taxonomia_clases.py, clases_criticas.py, balanceo_seleccion.py
├── archivos_intermedios/
│   ├── gee_caracterizacion/    ← ZIPs descargados [02]
│   └── revision/               ← reportes [05–07], auditoría [06], planes [09–10]
└── muestras_finales/           ← selección [03–04]
```

## Principio metodológico

1. **Grilla candidata** — universo de rectángulos por huso UTM y tamaño (2×2 homogéneo, 3×3 mixto).
2. **Rectángulos seleccionados** — subconjunto balanceado (~300–350 nacional) filtrado por calidad, ecorregión, clase, estabilidad y cambio.
3. **Chips multitemporales** — unidades finales derivadas de rectángulos aprobados.

Regla central: todos los chips de un mismo rectángulo heredan el mismo `split` (train/val/test). El script 03 asigna split a nivel de `grid_id` con estratificación por cluster espacial para evitar fuga.

## Insumos en Earth Engine (script 01)

| Asset | Ruta GEE |
|---|---|
| MapBiomas Chile C2 | `projects/mapbiomas-chile/assets/LULC/COLLECTION-02/CLASSIFICATIONS/classification-final/clasificacion-final-4` |
| Ecorregiones C3 | `projects/mapbiomas-chile/assets/LULC/COLLECTION-03/ANCILLARY_DATA/ECORREGIONES_RASTER/ecorregiones_col3_30m` |
| Tiles MGRS Chile | `projects/mapbiomas-chile/assets/LULC/COLLECTION-03/ANCILLARY_DATA/Tiles_Chile_Sentinel` |

Periodos de caracterización: P1 (1999–2005), P2 (2006–2012), P3 (2013–2018), P4 (2019–2024).

Parámetros clave del script 01:

- `--project mapbiomas-chile` (proyecto GCP por defecto)
- `--class-level n3` — IDs nativos C2 nivel 3 (recomendado; el sufijo de export es `_n3`)
- `--stats-scale 300` — escala de reducción estadística
- `--rect-side 2` (homogéneo) o `3` (mixto)
- `--utm 18` o `19` (también 12, 17 para islas)
- `--run-scale300-all --wait --download` — las 4 corridas + espera + descarga automática

## Tipos de muestra (script 03)

Seis tipos esenciales (dimensión temporal × espacial):

| `sample_type` | Temporal | Espacial | Criterio resumido |
|---|---|---|---|
| `estable_homogenea` | Estable | Homogénea | `mode_pct ≥ 85`, racha estable ≥ 5 años |
| `estable_simple_media` | Estable | Simple/media | Mosaico estable 2–4 clases |
| `anual_homogenea` | Anual | Homogénea | Clase pura en un `ref_year` |
| `anual_simple_media` | Anual | Simple/media | Dinámica anual en contexto mixto |
| `transicion_homogenea` | Transición | Homogénea | Cambio entre clases dominantes puras |
| `transicion_simple_media` | Transición | Simple/media | Cambio en contexto mixto |

Además, pools dedicados para clases críticas: arena/playa/duna (23), salar (61), bosque achaparrado (67), bosque norte y pastizal. Las clases transversales (humedal, urbano, agro fina, etc.) se excluyen del modelo general y se reservan para modelos especializados.

Perfil `scale300`: meta nacional **300–350** rectángulos (~138 UTM18 + ~192 UTM19).

## Muestras finales

Set operativo: **330 rectángulos** sin solape geométrico. Convenciones de archivos en [muestras_finales/README.md](muestras_finales/README.md).

Salidas típicas del script 03 (por huso):

```text
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.gpkg
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.csv
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300_shp/
muestras_finales/reservas_grilla_ssl4eo_muestras_UTM19_scale300.csv   ← suplentes
```

Tras el script 04:

```text
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM*_scale300_taxonomia_n3.csv
```

## Dependencias

```bash
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt
# o: mamba env create -f environment.yml && mamba activate lulc-muestras
```

Módulos auxiliares: `rutas_proyecto.py`, `taxonomia_clases.py`, `clases_criticas.py`, `balanceo_seleccion.py`.

## Flujo de ejecución

### 01 — Caracterizar grillas en GEE

```bash
python scripts/01_caracterizacion_grillas_gee.py --authenticate
python scripts/01_caracterizacion_grillas_gee.py --project mapbiomas-chile --utm 18 --rect-side 2 --stats-scale 300 --class-level n3
python scripts/01_caracterizacion_grillas_gee.py --utm 18 --rect-side 3 --stats-scale 300
python scripts/01_caracterizacion_grillas_gee.py --utm 19 --rect-side 2 --stats-scale 300
python scripts/01_caracterizacion_grillas_gee.py --utm 19 --rect-side 3 --stats-scale 300
```

Integrado (export + espera + descarga):

```bash
python scripts/01_caracterizacion_grillas_gee.py --run-scale300-all --wait --download
```

### 02 — Descargar desde Drive

```bash
python scripts/02_descargar_grillas_drive.py --scale300-all
```

Descarga los 4 ZIP con prefijos `homogeneo_2x2` y `mixto_3x3` para UTM18 y UTM19. Usa el token OAuth de Earth Engine (scope Drive).

### 03 — Seleccionar rectángulos

```bash
python scripts/03_seleccion_rectangulos.py \
  --homogeneo archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_homogeneo_2x2_UTM18_scale300_n3.zip \
  --mixto archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_mixto_3x3_UTM18_scale300_n3.zip
```

Flags relevantes:

- `--no-auto-previous` — no reutiliza selecciones previas del mismo huso como restricción de solape
- `--previous archivo.geojson` — excluye rectángulos ya seleccionados
- `--max-overlap 0.0` — tolerancia de solape (por defecto cero)

Repetir para UTM19. Por defecto también evita solapes con selección del otro huso en zona de frontera.

### 04 — Anotar taxonomía N3

```bash
python scripts/04_anotar_taxonomia_grillas.py \
  -i muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.csv
```

### 05 — Generar reportes de revisión

```bash
python scripts/05_revision_seleccion_rectangulos.py --utm 18 19
```

Produce, por huso y combinado:

| Prefijo | Contenido |
|---|---|
| `01_resumen_general` | Totales, split, tiers, calidad media |
| `02_por_tipo_muestra` | Conteos por `sample_type` |
| `03_eco_x_clase_*` | Ecorregión × clase modal |
| `04_eco_x_tipo_*` | Ecorregión × tipo de muestra |
| `05_clase_x_tipo_*` | Clase modal × tipo |
| `06_grid_mode_x_tipo` | Modo de grilla × tipo |
| `07_split_x_tipo` | Split × tipo |
| `08_clases_criticas_*` | Resumen y detalle de clases críticas |
| `08_achaparrado_detalle` | Detalle bosque achaparrado |
| `09_calidad_por_tipo` | Métricas de calidad por tipo |
| `REVISION_COMPLETA*.txt` | Informe de texto consolidado |

### 06 — Auditar balanceo

```bash
python scripts/06_auditoria_balanceo.py
```

Verifica 14 criterios, entre ellos:

- Total nacional 300–350
- Balance UTM18 (~100–130) / UTM19 (~140–180)
- Estables, transiciones homogéneas, ecorregiones prioritarias (E7, E8, E9, E12, E15)
- Cupos de arena, salar, pastizal, bosque norte
- Split ~70/15/15 y solape cero entre husos

### 07 — Visualizar reportes

```bash
streamlit run scripts/07_visualizar_reportes.py
python scripts/07_visualizar_reportes.py --export-html revision_dashboard.html
```

Lee `archivos_intermedios/revision/`, geometrías de `muestras_finales/` y puede superponer chips 1×1 (opcional).

### 09 — Plan de revisión por rectángulo

```bash
python scripts/09_generar_plan_revision_rectangulos.py \
  -i muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson \
  -o archivos_intermedios/revision/plan_revision_UTM18_scale300.csv
```

Reglas de `review_rule` asignadas según `dim_temporal`:

| Regla | Cuándo aplica | Años típicos |
|---|---|---|
| `estable_anclas_temporales` | Rectángulos estables | 1999, 2013, 2024 (o años estables más cercanos) |
| `anual_ref_year` | Tipos anuales | `ref_year` del rectángulo |
| `transicion_cambio_modal_entre_periodos` | Cambio de clase modal entre P1–P4 | Ventanas en límites de periodo |
| `transicion_anios_no_estables` | Años no estables respecto al modo | Ventanas ±1 año |
| `transicion_sin_anio_exacto_usar_anclas` | Fallback de transición | Anclas 1999, 2013, 2024 |

Campos de salida: `review_years`, `n_review_years`, `review_rule`, `review_priority`, `review_notes`.

### 10 — Consolidar plan nacional

```bash
python scripts/10_consolidar_plan_revision_nacional.py \
  --input archivos_intermedios/revision/plan_revision_UTM18_scale300.csv \
          archivos_intermedios/revision/plan_revision_UTM19_scale300.csv \
  --out-dir archivos_intermedios/revision
```

Salidas adicionales:

```text
plan_revision_nacional_scale300.csv
listado_revision_manual.csv
plan_revision_por_rectangulo_anio.csv
resumen_revision_por_utm.csv
resumen_revision_por_tipo.csv
resumen_revision_por_regla.csv
resumen_revision_por_prioridad.csv
resumen_revision_por_anio.csv
```

## Control de calidad mínimo

- Solape cero entre UTM18 y UTM19 (script 06, criterio [14]).
- `grid_id` único en plan nacional (script 10, `validate_outputs`).
- Split asignado a nivel de rectángulo, no de chip-año.
- Clases críticas y ecorregiones prioritarias dentro de metas.
- Rectángulos con `review_priority` baja revisados en años ancla.
- Sin archivos pesados en el repositorio Git.

## Notas operativas

Este paquete versiona scripts y documentación, no datos derivados. Los productos se regeneran desde Earth Engine, Drive y los scripts del flujo.