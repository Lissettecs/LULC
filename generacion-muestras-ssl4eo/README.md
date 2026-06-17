# Generación de muestras SSL4EO-L para Land Cover Chile

Este repositorio documenta y organiza el flujo de generación, selección, revisión y auditoría de rectángulos de muestreo para la posterior generación de chips multitemporales SSL4EO-L/Landsat. El flujo está diseñado para apoyar la clasificación anual de cobertura y uso del suelo de Chile, con un producto objetivo 1996-2025 y una referencia operativa MapBiomas Chile Collection 2 para 1999-2024.

La rama sugerida para incorporar este material es:

```bash
generacion-muestras-ssl4eo
```

Se evita usar espacios o tildes en el nombre de la rama para reducir problemas con Git, terminales remotas y herramientas de integración continua. Una alternativa válida sería `feature/generacion-muestras`.


## Trabajo local en PC

Este repositorio está preparado para ejecutarse desde un computador local con Windows, usando PowerShell, Git Bash, Cursor o VS Code. No es necesario trabajar desde el cluster para subir los archivos a GitHub.

Flujo recomendado:

```bash
git clone https://github.com/Lissettecs/LULC.git
cd LULC
git switch main
git pull origin main
git switch -c generacion-muestras-ssl4eo
```

Luego se copia el contenido de este paquete dentro de la carpeta local `LULC/`, se revisa con `git status -sb`, se confirma con `git commit` y se sube con `git push -u origin generacion-muestras-ssl4eo`.

## Objetivo

El objetivo de este flujo es construir un conjunto controlado de rectángulos de muestreo que represente la variabilidad espacial, ecológica, temática y temporal del territorio chileno antes de generar chips de entrenamiento. La unidad primaria de diseño es el rectángulo; el chip-año se deriva posteriormente. Esto permite controlar la representatividad por ecorregión, clase dominante, estabilidad temporal, cambio, presencia de clases críticas y partición train/validation/test.

## Principio metodológico

El diseño separa tres niveles de trabajo:

1. **Grilla candidata**: universo de rectángulos posibles, generado por huso UTM y tamaño de rectángulo.
2. **Rectángulos seleccionados**: subconjunto balanceado y revisable, filtrado por calidad, ecorregión, clase, estabilidad y cambio.
3. **Chips multitemporales**: unidades finales de entrenamiento derivadas desde los rectángulos aprobados.

Regla central: todos los chips derivados desde un mismo rectángulo deben heredar el mismo split. No se deben mezclar chips del mismo rectángulo entre entrenamiento, validación y prueba, porque eso puede producir fuga espacial y sobreestimar el desempeño del modelo.

## Flujo general

```text
Tiles MGRS + huso UTM
        ↓
Grilla candidata por tamaño de rectángulo
        ↓
Caracterización con MapBiomas, ecorregiones y métricas temporales
        ↓
Descarga/compactación de grillas exportadas desde Google Drive
        ↓
Selección balanceada de rectángulos
        ↓
Revisión, auditoría y visualización de reportes
        ↓
Plan de años de revisión por rectángulo
        ↓
Consolidación nacional del plan de revisión
        ↓
Generación posterior de chips SSL4EO-L
```

## Estructura propuesta

```text
.
├── README.md
├── requirements.txt
├── environment.yml
├── .gitignore
├── COMANDOS_GITHUB.md
├── scripts/
│   ├── 01_caracterizacion_grillas_gee.py
│   ├── 02_descargar_grillas_drive.py
│   ├── 03_seleccion_rectangulos.py
│   ├── 04_anotar_taxonomia_grillas.py
│   ├── 05_revision_seleccion_rectangulos.py
│   ├── 06_auditoria_balanceo.py
│   ├── 07_visualizar_reportes.py
│   ├── 09_generar_plan_revision_rectangulos.py
│   ├── 10_consolidar_plan_revision_nacional.py
│   ├── rutas_proyecto.py
│   ├── taxonomia_clases.py
│   ├── clases_criticas.py
│   └── balanceo_seleccion.py
├── docs/
│   └── metodologia_grillas_seleccion_ssl4eo.docx
├── data/
│   └── raw/
├── archivos_intermedios/
│   ├── gee_caracterizacion/
│   └── revision/
├── muestras_finales/
└── reportes_revision/
```

Los directorios `data/`, `archivos_intermedios/`, `muestras_finales/` y `reportes_revision/` se dejan preparados para el flujo operativo, pero los archivos pesados derivados de Earth Engine, shapefiles, GeoPackage, GeoJSON, CSV de resultados y reportes no se versionan por defecto. Para compartir productos pesados se recomienda usar almacenamiento externo o Git LFS, no commits directos al repositorio principal.

## Insumos principales

El flujo depende de tres insumos espaciales principales en Google Earth Engine:

| Insumo | Uso |
|---|---|
| MapBiomas Chile Collection 2 | Clase dominante, clase reciente, estabilidad, cambio y presencia de clases críticas para 1999-2024. |
| Ecorregiones Collection 3 | Estratificación ecológica y ecorregión dominante de cada rectángulo. |
| Tiles MGRS Sentinel Chile | Organización espacial por tile y derivación del huso UTM. |

El producto final apunta al periodo 1996-2025, pero la caracterización preliminar de grillas usa la serie MapBiomas disponible 1999-2024. Los años 1996-1998 y 2025 deben tratarse en la etapa posterior mediante revisión/anclaje temporal o extrapolación cautelosa, no como verdad automática derivada de la referencia 1999-2024.

## Sistemas de referencia

La grilla se genera por huso UTM Sur con EPSG explícitos:

| Huso | EPSG | Uso esperado |
|---|---:|---|
| 12S | EPSG:32712 | Isla de Pascua |
| 17S | EPSG:32717 | Archipiélago Juan Fernández |
| 18S | EPSG:32718 | Chile continental occidental/norte-centro |
| 19S | EPSG:32719 | Chile continental centro-sur, sur y Patagonia |

La ejecución por lotes por huso es preferible a una ejecución nacional única, porque reduce errores de memoria y facilita el control de solapes en zonas de frontera entre husos.

## Tamaños de rectángulos

El tamaño base considera chips SSL4EO-L/Landsat de 264 × 264 píxeles. Con píxel Landsat de 30 m, cada chip cubre aproximadamente 7,92 km por lado.

| Tipo operativo | Chips por lado | Dimensión aproximada | Uso |
|---|---:|---:|---|
| Homogéneo/reducido | 2 × 2 | 15,84 × 15,84 km | Zonas fragmentadas, costeras, clases raras y muestras homogéneas. |
| Mixto/estándar | 3 × 3 | 23,76 × 23,76 km | Muestreo general y contexto espacial mixto. |
| Ampliado | 4 × 4 | 31,68 × 31,68 km | Paisajes extensos y homogéneos; no forma parte del set principal actual si no se ejecuta explícitamente. |

La grilla candidata se genera sin solape. El solape, si se usa, debe incorporarse después en la generación de chips y mantenerse dentro del mismo split del rectángulo padre.

## Tipos de muestra usados en la selección

El script de selección organiza los rectángulos según dimensión temporal y espacial:

| Tipo | Dimensión temporal | Dimensión espacial | Descripción |
|---|---|---|---|
| `estable_homogenea` | Estable | Homogénea | Firma relativamente pura y persistente. |
| `estable_simple_media` | Estable | Simple/media | Mosaico estable con pocas clases. |
| `anual_homogenea` | Anual | Homogénea | Clase pura en un año de referencia. |
| `anual_simple_media` | Anual | Simple/media | Dinámica anual en contexto espacial real. |
| `transicion_homogenea` | Transición | Homogénea | Cambio temporal entre clases dominantes relativamente puras. |
| `transicion_simple_media` | Transición | Simple/media | Cambio temporal en contexto mixto. |

También se consideran pools dedicados para clases críticas o raras, como arena/playa/duna, salar, bosque achaparrado, bosque norte y pastizal, dependiendo de los parámetros activos.

## Scripts incluidos

| Script | Función principal | Entradas esperadas | Salidas esperadas |
|---|---|---|---|
| `01_caracterizacion_grillas_gee.py` | Genera y caracteriza grillas candidatas en Earth Engine. | Assets de MapBiomas, ecorregiones, MGRS; parámetros UTM, tamaño y escala. | Exportaciones a Google Drive. |
| `02_descargar_grillas_drive.py` | Descarga y empaqueta shapefiles exportados desde Drive. | Carpeta `GEE_exports` o prefijos específicos. | ZIPs de grillas en `archivos_intermedios/gee_caracterizacion/`. |
| `03_seleccion_rectangulos.py` | Selecciona rectángulos balanceados por tipo, ecorregión, clase, estabilidad y cambio. | ZIP/SHP homogéneo 2×2 y/o mixto 3×3. | GPKG, GeoJSON, CSV y shapefile en `muestras_finales/`. |
| `04_anotar_taxonomia_grillas.py` | Añade columnas de taxonomía N1/N2/N3 a grillas o selecciones. | CSV/GPKG/GeoJSON con `mode_id` o `lulc_mode_id`. | Archivo anotado con taxonomía. |
| `05_revision_seleccion_rectangulos.py` | Genera reportes de revisión de la selección. | Selecciones finales GeoJSON/GPKG. | CSVs de resumen e informe TXT. |
| `06_auditoria_balanceo.py` | Audita balance nacional contra metas operativas. | Selecciones UTM18/UTM19. | Informe `AUDITORIA_BALANCEO.txt`. |
| `07_visualizar_reportes.py` | Visualiza reportes en Streamlit. | Reportes CSV y selecciones GeoJSON. | Dashboard local interactivo. |
| `09_generar_plan_revision_rectangulos.py` | Define años de revisión por rectángulo. | Selección final GeoJSON/GPKG. | CSV con `review_years`, regla y prioridad. |
| `10_consolidar_plan_revision_nacional.py` | Consolida planes UTM18 y UTM19. | Planes de revisión por huso. | Plan nacional y resúmenes por año/tipo/regla/prioridad. |

## Dependencias

Instalación mínima con `pip`:

```bash
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
# .venv\Scripts\activate       # Windows PowerShell
pip install -r requirements.txt
```

En entornos con geoespacial complejo, se recomienda Conda/Mamba:

```bash
mamba env create -f environment.yml
mamba activate lulc-muestras
```

Módulos auxiliares incluidos en `scripts/`:

```text
rutas_proyecto.py
taxonomia_clases.py
clases_criticas.py
balanceo_seleccion.py
```

Estos módulos concentran rutas del proyecto, taxonomía N1/N2/N3, definición de clases críticas y utilidades de balanceo. Se mantienen junto a los scripts para que las importaciones funcionen al ejecutar el flujo desde la raíz del repositorio.

## Configuración inicial de Earth Engine

Autenticación inicial:

```bash
python scripts/01_caracterizacion_grillas_gee.py --authenticate
```

Ejecución base para el proyecto MapBiomas Chile:

```bash
python scripts/01_caracterizacion_grillas_gee.py --project mapbiomas-chile --utm 18 --rect-side 2 --stats-scale 300
```

## Flujo de ejecución recomendado

### 1. Caracterizar grillas candidatas

Ejecutar las cuatro combinaciones principales `scale300`:

```bash
python scripts/01_caracterizacion_grillas_gee.py --utm 18 --rect-side 2 --stats-scale 300
python scripts/01_caracterizacion_grillas_gee.py --utm 18 --rect-side 3 --stats-scale 300
python scripts/01_caracterizacion_grillas_gee.py --utm 19 --rect-side 2 --stats-scale 300
python scripts/01_caracterizacion_grillas_gee.py --utm 19 --rect-side 3 --stats-scale 300
```

También se puede usar el modo integrado:

```bash
python scripts/01_caracterizacion_grillas_gee.py --run-scale300-all --wait --download
```

### 2. Descargar grillas exportadas desde Drive

```bash
python scripts/02_descargar_grillas_drive.py --scale300-all
```

La salida esperada son ZIPs de shapefile en:

```text
archivos_intermedios/gee_caracterizacion/
```

### 3. Seleccionar rectángulos por huso

Ejemplo UTM18:

```bash
python scripts/03_seleccion_rectangulos.py \
  --homogeneo archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_homogeneo_2x2_UTM18_scale300_n3.zip \
  --mixto archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_mixto_3x3_UTM18_scale300_n3.zip
```

Ejemplo UTM19:

```bash
python scripts/03_seleccion_rectangulos.py \
  --homogeneo archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_homogeneo_2x2_UTM19_scale300_n3.zip \
  --mixto archivos_intermedios/gee_caracterizacion/grilla_ssl4eo_muestras_mixto_3x3_UTM19_scale300_n3.zip
```

Los productos se guardan en `muestras_finales/`.

### 4. Revisar selección

```bash
python scripts/05_revision_seleccion_rectangulos.py --utm 18 19
```

Esto genera tablas de resumen y un informe de texto con distribución por tipo de muestra, ecorregión, clase modal, clases críticas, split y tier de revisión.

### 5. Auditar balance nacional

```bash
python scripts/06_auditoria_balanceo.py
```

La auditoría revisa metas de número total de muestras, balance UTM18/UTM19, clases críticas, split train/val/test y solapes entre husos.

### 6. Visualizar reportes

```bash
streamlit run scripts/07_visualizar_reportes.py
```

El visor permite revisar métricas generales, distribución por ecorregión/clase, tipos de muestra, clases críticas, calidad y geometrías de selección.

### 7. Generar plan de revisión por rectángulo

```bash
python scripts/09_generar_plan_revision_rectangulos.py \
  --input muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson \
  --output archivos_intermedios/revision/plan_revision_UTM18_scale300.csv

python scripts/09_generar_plan_revision_rectangulos.py \
  --input muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson \
  --output archivos_intermedios/revision/plan_revision_UTM19_scale300.csv
```

### 8. Consolidar plan nacional

```bash
python scripts/10_consolidar_plan_revision_nacional.py \
  --input archivos_intermedios/revision/plan_revision_UTM18_scale300.csv \
          archivos_intermedios/revision/plan_revision_UTM19_scale300.csv \
  --out-dir archivos_intermedios/revision
```

## Criterios de revisión temporal

El plan de revisión usa distintas reglas según el tipo de rectángulo:

| Tipo | Años sugeridos |
|---|---|
| Estable | Años ancla, típicamente inicio, periodo medio y año reciente. |
| Anual | Año de referencia asignado por `ref_year`. |
| Transición | Ventanas alrededor de cambios entre periodos o años no estables. |
| Clase rara | Años con presencia probable o confirmada de la clase objetivo. |

La revisión manual debe concentrarse en años ancla y casos críticos. La inferencia final puede generar chip-año para todos los años, pero no todos requieren revisión manual exhaustiva.

## Salidas esperadas

Productos principales:

```text
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.geojson
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.geojson
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM18_scale300.csv
muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM19_scale300.csv
archivos_intermedios/revision/plan_revision_UTM18_scale300.csv
archivos_intermedios/revision/plan_revision_UTM19_scale300.csv
archivos_intermedios/revision/plan_revision_nacional_scale300.csv
archivos_intermedios/revision/listado_revision_manual.csv
```

Reportes principales:

```text
reportes_revision/REVISION_COMPLETA.txt
reportes_revision/AUDITORIA_BALANCEO.txt
reportes_revision/01_resumen_general.csv
reportes_revision/02_por_tipo_muestra.csv
reportes_revision/08_clases_criticas_resumen.csv
reportes_revision/09_calidad_por_tipo.csv
```

## Control de calidad mínimo

Antes de generar chips se debe comprobar:

- No hay solape entre rectángulos seleccionados de UTM18 y UTM19.
- Cada `grid_id` es único en el plan nacional.
- El split se asignó a nivel de rectángulo.
- Las clases críticas tienen representación suficiente.
- Las ecorregiones prioritarias no quedaron subrepresentadas.
- Los rectángulos con `review_priority` alta tienen años de revisión asignados.
- Los archivos pesados no fueron añadidos accidentalmente al repositorio.

## Convenciones de nombres

Rama sugerida:

```text
generacion-muestras-ssl4eo
```

Commit sugerido:

```text
Agregar flujo de generacion de muestras SSL4EO
```

Los nombres de ramas y commits se escriben sin tildes para evitar problemas de codificación en terminales remotas.

## Notas operativas

Este paquete sube scripts y documentación, no datos pesados. Los productos intermedios y finales deben regenerarse desde Earth Engine, Drive y los scripts del flujo. Si se decide versionar selecciones finales livianas, revisar primero tamaño y sensibilidad metodológica antes de hacer commit.

