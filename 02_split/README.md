# 02_split

Generación de muestras para MapBiomas Chile sobre la grilla **CIM 1:250.000**, la
misma grilla de cartas con la que se producen los mosaicos Landsat
(`MOSAICS/cartas-chile-2`).

Es una reimplementación de [`ssl4eo-sample-generation_v02`](../ssl4eo-sample-generation_v02)
cambiando la grilla: donde v02 usaba tiles MGRS (`Tiles_Chile_Sentinel`) y una malla
métrica en UTM, aquí se usan las cartas CIM y una malla en coordenadas geográficas.
No se reutiliza ni se traduce ningún resultado de v02: la caracterización y la
selección se corren de nuevo desde cero.

## Estado

| Etapa | Estado |
|---|---|
| 00 — Grillas `2x2` y `3x3` | **lista** |
| 01 — Caracterización | **lista y corrida** (`nacional_20260806`) |
| 02 — Selección | **lista y corrida** (`20260806_2005`, 405 celdas) |
| 03 — Plan de revisión | **lista y corrida** (`plan_revision_20260806_2006`) |

## Las grillas

Un CRS único, **EPSG:4326**, para todo el pipeline. No hay husos ni zonas UTM.

Se generan las dos escalas equivalentes a los rectángulos de v02, en píxeles de la
grilla nativa del landcover (0,00026949458523586°, 30 m en latitud):

| | `grilla_cim_2x2` | `grilla_cim_3x3` |
|---|---|---|
| Celda | 528 px (2 × 2 chips de 264) | 792 px (3 × 3 chips de 264) |
| Lado | 0,142293141° (8,54 arcmin) | 0,213439712° (12,81 arcmin) |
| Cuadrícula por carta | 10 columnas × 7 filas | 7 columnas × 4 filas |
| Celdas por carta | **70**, igual en todas | **28**, igual en todas |
| Celdas | **8.470** | **3.388** |
| Área por celda | 140,9 – 238,5 km² (media 190,5) | 318,5 – 536,6 km² (media 429,1) |
| Ancho | 8,90 – 15,15 km | 13,40 – 22,72 km |
| Alto | 15,75 – 15,84 km | 23,62 – 23,76 km |
| Cobertura de las cartas | **94,49%** | **85,13%** |

Cartas: 121 de 124. Se excluyen las 3 que quedan fuera del ráster de landcover
(`SG-12-Z-D` en Isla de Pascua y `SI-17-X-C/D`, oceánicas).

### Cómo se nombra cada escala

La escala se identifica por el número de chips (`2x2`, `3x3`) y no por el lado en
píxeles, en archivos, capas e identificadores:

| | |
|---|---|
| GeoPackage y capa | `grilla_cim_2x2`, `grilla_cim_3x3` |
| `grid_id` | `{carta}_{escala}_c{columna}_r{fila}`, p.ej. `SK-18-X-A_2x2_c000_r000` |
| Caracterización | `caracterizacion_cim_2x2.gpkg` (capa `caract_2x2`), `por_carta/SK-18-X-A_2x2.parquet` |

Los scripts aceptan la escala en cualquiera de las dos formas: `--escala 2x2` o
`--escala 528`. El lado en píxeles sigue disponible en la columna `celda_px`.

### Desde dónde arranca

Cada carta se subdivide **de forma independiente, desde su esquina noroeste**,
avanzando hacia el este y hacia el sur. **Ninguna celda cruza a la carta vecina**:
la columna del extremo este y la fila del extremo sur se descartan si no caben
completas.

El ancla se corre al primer borde de píxel del ráster de landcover que queda dentro
de la carta, a lo más un píxel (30 m) de la esquina; el desfase máximo medido es de
**28,84 m**. Gracias a ese ajuste cada celda sigue siendo una ventana de píxeles
enteros: se lee con `Window(px_col_off, px_row_off, lado, lado)` **sin remuestrear
ni reproyectar**.

Ejemplo: la carta `SK-18-X-A` tiene su esquina NO en (−75, −40) y su celda
`c000_r000` arranca en (−74,9998041, −40,0000033).

### Franja sin cubrir en cada carta

Una carta CIM mide 1,5° × 1,0°, que no es múltiplo entero de ninguno de los dos
lados de celda. Lo interesante es que **las dos escalas desperdician superficie en
bordes opuestos**:

| | Este–oeste | Norte–sur |
|---|---|---|
| `2x2` | 1,5 / 0,142293 = 10,54 → 10 columnas, sobra 0,0771° | 1,0 / 0,142293 = 7,03 → 7 filas, sobra 0,0039° |
| `3x3` | 1,5 / 0,213440 = 7,03 → 7 columnas, sobra 0,0059° | 1,0 / 0,213440 = 4,69 → 4 filas, sobra 0,1462° |

En kilómetros:

| Latitud | `2x2`: este | `2x2`: sur | `3x3`: este | `3x3`: sur |
|---|---|---|---|---|
| −17° | 8,21 km | 0,44 km | 0,63 km | 16,18 km |
| −33° | 7,20 km | 0,44 km | 0,55 km | 16,22 km |
| −48° | 5,75 km | 0,44 km | 0,44 km | 16,26 km |
| −56° | 4,81 km | 0,44 km | 0,37 km | 16,28 km |

La grilla `2x2` encaja casi exacta en la vertical y deja una franja apreciable
al este; la `3x3` es la inversa, y por eso cubre menos: la franja sur de
~16,2 km es el 14,6% de la altura de cada carta. Ese 85,13% de cobertura es el
costo de exigir que ninguna celda cruce de carta, no un defecto de la
implementación. La alternativa —dejar que las celdas se asomen a la carta
vecina— cubriría el 100% pero rompería la correspondencia una celda ↔ una carta.

### Por qué en grados y no en metros

En v02 la celda se definía en metros (528 px × 30 m = 15.840 m exactos) sobre una
malla UTM. Eso da un área idéntica en todo el país, pero exige un CRS proyectado, y
Chile necesita dos zonas UTM (18 y 19): en el meridiano que las separa las dos
mallas se pisan.

Trabajar en 4326 deja un solo CRS y un solo archivo, al precio de que la celda ya no
cubre la misma superficie en todas las latitudes: la `2x2` pasa de 238 km² en el
norte a 141 km² en Magallanes, porque un grado de longitud se acorta hacia el polo.
El alto se mantiene en ~15,8 km; lo que se angosta es el ancho (la razón ancho/alto
va de 0,96 a 0,56).

Esa variación **no invalida el muestreo** siempre que las cuotas se calculen con el
área real de cada celda y no con un valor nominal constante. Por eso tanto la grilla
como la caracterización traen el área real medida celda a celda.

No es posible tener las dos cosas a la vez: un trapecio en lat/long no se puede
embaldosar con cuadrados métricos iguales.

## La caracterización

Cada celda se describe con composición de coberturas, dinámica temporal 1999–2024 y
métricas espaciales: **65 columnas fijas** más una tríada `pct_{id}` / `ha_{id}` /
`pctp_{id}` por cada clase presente en la corrida (114 columnas en la prueba de dos
cartas, 18 clases). La lógica de las métricas es la de v02; lo que cambia es cómo se
lee el dato y cómo se mide la superficie.

### Diferencias de fondo con v02

**1. No hay reproyección.** Como las celdas se construyeron sobre la grilla nativa
del ráster, cada una es una ventana de píxeles enteros y se lee tal cual. En v02
cada rectángulo UTM había que reproyectarlo desde 4326, con el remuestreo y la
distorsión que eso arrastra. Aquí desaparecen el remuestreo, el factor de
distorsión UTM y el concepto de huso.

El ráster de ecorregiones ya está alineado píxel a píxel con el landcover
(`ecorregiones_col3_30m_alineado_lulc.tif`, misma `transform` y mismo tamaño), así
que se reutiliza la misma ventana y tampoco requiere alineación previa.

**2. El píxel no tiene área constante, y eso cambia los números.** En EPSG:4326 un
píxel de 0,00026949° mide ~30 m en latitud pero ~30·cos(lat) m en longitud:

| Latitud | Área de un píxel |
|---|---|
| −17,5° | 0,0854 ha |
| −55,9° | 0,0506 ha (40,7% menos) |

v02 usaba `PIXEL_HA = 0,09` constante, que es correcto en UTM pero no aquí.
Aplicarlo a esta grilla sobreestimaría el área válida de las celdas de Magallanes
**entre un 74% y un 78%** (medido sobre `SN-19-Y-D`). Por eso todos los porcentajes
y hectáreas se ponderan por el área real de la fila del píxel, no por conteo:

- `pct_{id}` = 100 · ha de la clase / `area_valida_ha`
- `ha_{id}` = hectáreas reales de la clase

Dentro de una misma celda la variación de área entre la fila norte y la sur es de
apenas 0,15%, así que lo que importa no es el gradiente interno sino la escala
absoluta. Las métricas temporales sí se dejan sin ponderar: son tasas
adimensionales por bloque y ese 0,15% no las mueve.

El área se calcula con la fórmula exacta del cuadrángulo elipsoidal vía latitud
autálica (`geodesia.py`), contrastada contra `pyproj.Geod` con los bordes
densificados (coinciden a 1e-13). Es el único módulo de áreas del pipeline, así que
la grilla y la caracterización informan siempre la misma cifra.

**3. Escala de las métricas temporales: 11 px en vez de 10.** Las métricas de
dinámica se calculan sobre bloques agregados por moda, para que midan cambio de
paisaje y no ruido de clasificación. v02 usaba bloques de 10 px (300 m) y descartaba
el sobrante de la celda (528/10 = 52,8). 11 px divide exacto **los dos** tamaños de
celda —48 bloques por lado en 528 px, 72 en 792 px— así que no se pierde ningún
píxel, a cambio de pasar de 300 a 330 m.

**4. La moda va vectorizada.** v02 la calculaba con `np.apply_along_axis` +
`np.bincount`, un bucle de Python con una llamada por píxel. Contar una máscara
booleana por clase presente es unas 6 veces más rápido (0,074 s contra 0,5 s por
moda de una celda de 528 px) y da un resultado **idéntico**, incluido el desempate
por ID más chico y la exclusión de nodata; está contrastado contra la
implementación original.

### Métricas

| Grupo | Columnas |
|---|---|
| Grilla | `grid_id`, `cim_name`, `cim_zona`, `celda_px`, `n_chips`, `px_col_off`, `px_row_off`, `col_idx`, `row_idx`, coordenadas, `ancho_km`, `alto_km`, `razon_ancho_alto`, `area_km2`, `area_ha` |
| Superficie | `area_celda_ha`, `area_valida_ha`, `n_valid`, `valid_area_pct`, `nodata_raster_pct`, `noobs_pct`, `area_ha_pixel_min/max` |
| Composición | `pct_{id}`, `ha_{id}` por clase presente; `transversal_pct`, `mascara_pct`, `general_pct` |
| Composición por periodo | `pctp_{id}`: máximo % de la clase como moda de P1–P4 |
| Espacial | `lulc_mode_id/name/pct`, `lulc_last_id/pct`, `n_mode_classes`, `shannon_idx`, `heterogeneidad_idx`, `eco_dom_id/name/pct`, `conf_risk_pct`, `cim_dom_pct` |
| Temporal | `transition_pct`, `stable_mode_pct`, `stable_yr_pct`, `max_stab_run`, `stab_run_start/end`, `md_id_P1..P4`, `md_pct_P1..P4`, `n_stb_P1..P4`, `stats_bloque_px`, `stats_bloques`, `n_bloques_validos` |

La clase de cada píxel es su **moda temporal** en los 26 años. Las clases 0 (nodata)
y 27 (no observado) se excluyen del denominador y se enmascaran año a año en las
métricas temporales: si contaran como una clase más, un bloque con vacíos parecería
inestable cuando en realidad solo faltaba información.

`pctp_{id}` existe para detectar coberturas que dominaron un tramo de la serie pero
que la moda de 26 años diluye. Que aparezca `pctp_15` sin su `pct_15` es
precisamente eso: Pastura fue moda de algún periodo sin llegar a ser moda global.

## Uso

Entorno: `~/.conda/envs/mb_coverage`.

```bash
python scripts/01_generar_grilla.py          # las dos grillas
python scripts/02_verificar_insumos.py       # antes de caracterizar
python scripts/03_generar_lista_cartas.py    # abre la corrida

jobs/caracterizar.sh 8                       # 8 procesos; consolida al terminar
```

Por partes o para depurar una carta:

```bash
python scripts/04_caracterizar_carta.py --carta SK-18-X-A
python scripts/04_caracterizar_carta.py --carta SK-18-X-A --escala 2x2 --no-resume
python scripts/05_consolidar.py
```

En SLURM, una tarea por carta:

```bash
python scripts/03_generar_lista_cartas.py
sbatch jobs/run_caracterizacion.slurm
sbatch --dependency=afterok:$JOBID jobs/run_consolidar.slurm
```

Para probar en pocas cartas antes de lanzar el país completo:

```bash
python scripts/03_generar_lista_cartas.py --run-tag prueba --carta SE-19-V-D --carta SN-19-Y-D
```

Todo es reanudable: las cartas ya escritas se omiten, así que se puede relanzar tras
una caída sin perder lo hecho.

### Selección y plan de revisión

```bash
# presupuesto (dry-run) → selección → informe → plan de revisión
jobs/seleccionar.sh
jobs/seleccionar.sh /ruta/a/01_caracterizacion/nacional_20260806

# por partes
python scripts/06_presupuesto_seleccion.py
python scripts/07_seleccionar_rectangulos.py
python scripts/09_generar_informe_seleccion.py --seleccion 02_seleccion/20260806_2005
python scripts/10_generar_plan_revision.py --seleccion 02_seleccion/20260806_2005
```

### Costo

Medido en `mb_coverage`, por carta y para **los dos** tamaños de celda: 24 s en el
norte árido, 43 s en Magallanes (más clases, moda más costosa). Las 121 cartas salen
en algo así como 1 h en serie, o pocos minutos con el array. Cada carta lee su
ventana completa una vez: ~550 MB en `uint8` para los 26 años. La selección nacional
completa (presupuesto + selección + informe + plan) tarda ~1 minuto.

## Salidas

Todo bajo `/home/lserey/mapbiomas_land/prod/samples_cim/`:

```
00_grilla/
├── grilla_cim_2x2.gpkg          # capa grilla_cim_2x2, EPSG:4326
├── grilla_cim_2x2.csv           # atributos sin geometría
├── grilla_cim_2x2_resumen.json  # parámetros + validación
└── (ídem para 3x3)

01_caracterizacion/
├── _verificacion_insumos.json
└── {RUN_TAG}/
    ├── cartas.txt                          # índice del array de tareas
    ├── auditoria.csv                       # estado y tiempo por carta
    ├── log_caracterizacion.txt
    ├── summary_corrida.json
    ├── summary_consolidado.json
    ├── por_carta/{CARTA}_{escala}.parquet
    ├── caracterizacion_cim_2x2.gpkg      # capa caract_2x2, EPSG:4326
    ├── caracterizacion_cim_2x2.csv
    └── (ídem para 3x3)

02_seleccion/{RUN}/
├── seleccion_nacional.gpkg               # EPSG:4326
├── seleccion_nacional.csv
├── informe_seleccion.md
├── auditoria_*.csv
├── por_ecorregion/
└── plan_revision_{ts}/
```

## Validación

`01_generar_grilla.py` deja su informe en `_resumen.json`. Ambas grillas:

| Comprobación | `2x2` | `3x3` |
|---|---|---|
| `grid_id` únicos | sí | sí |
| Celdas duplicadas | 0 | 0 |
| Pares de celdas solapadas | **0** | **0** |
| Celdas que se salen de su carta | **0** | **0** |
| Paso regular por carta | sí | sí |
| Celdas por carta | 70 en las 121 | 28 en las 121 |
| Cartas sin celdas | 0 | 0 |
| Desfase del ancla respecto de la esquina NO | ≤ 0,96 px (28,84 m) | ídem |
| Lado constante | dentro de 1e-6 mm | ídem |

`02_verificar_insumos.py` comprueba antes de caracterizar que la serie de landcover
esté completa y con la misma grilla, que las ecorregiones estén alineadas píxel a
píxel, que las ventanas de las celdas caigan dentro del ráster, que el lado sea
divisible por el bloque de estadísticas y que la fórmula de área coincida con
`pyproj.Geod`.

`05_consolidar.py` deja en `summary_consolidado.json` las cifras de control:

| Comprobación | Resultado |
|---|---|
| `sum(pct_*)` en celdas con área válida | 99,9997 – 100,0003 (0 fuera de rango) |
| `sum(ha_*)` contra `area_valida_ha` | coincide a 1e-6 relativo |
| `nodata_pct + noobs_pct + valid_pct` | 100,000000 exacto |
| `area_celda_ha` contra el `area_ha` de la grilla | coincide a 3e-7 relativo |

Las celdas enteramente oceánicas o fuera del mosaico no tienen área válida y su
composición es legítimamente 0; se cuentan aparte
(`n_celdas_sin_area_valida`) y no se les exige sumar 100.

## Corrida nacional `nacional_20260806`

Las 121 cartas en las dos escalas, 242 parquets, sin errores, en unos 20 minutos con
12 procesos.

| | `2x2` | `3x3` |
|---|---|---|
| Celdas | 8.470 | 3.388 |
| Con área válida | 5.132 | 2.146 |
| Área válida total | 80,23 Mha | 72,34 Mha |
| — de la cual agua y hielo | 14,36 Mha | 13,04 Mha |
| — resto (tierra) | 65,87 Mha | 59,30 Mha |
| Clases presentes | 18 | 18 |
| Ecorregiones presentes | 15 + sin asignar | 15 + sin asignar |

Como control de plausibilidad: la tierra caracterizada es el **87,1%** de la
superficie de Chile con la grilla `2x2` y el **78,4%** con la `3x3`. Su cociente
(0,90) reproduce exactamente el de las coberturas de las dos grillas
(85,13 / 94,49 = 0,90), que es lo que debe pasar si ambas muestrean el mismo
territorio con distinto desperdicio de borde.

La composición apenas se mueve entre escalas —agua 11,1% en las dos, bosque
primario 11,0%, matorral 10,2% contra 10,1%— pese a que cubren superficies
distintas, lo que es otra señal de que el cálculo es consistente.

## Selección

La lógica de modos, cuotas, pools tipológicos y split es la de v02. Lo que cambia
es el soporte espacial:

| | v02 | CIM |
|---|---|---|
| Unidad espacial | tile MGRS (`mgrs_dom`) | carta CIM (`cim_name`, alias `mgrs_dom`) |
| CRS | husos 18/19, export por huso | **EPSG:4326**, un solo GPKG |
| Tracking de solape | UTM nativo | proyectado a EPSG:32719 solo para medir área |
| Área en la cuota | 240 km² fijos | **190,5 km²** (media de la celda `2x2`) |
| `ha_*` | `pct × área` con píxel constante | ya ponderadas por área real |

`seleccion/cargar.py` sintetiza las columnas que el algoritmo espera
(`rect_side`, `grid_mode`, `mgrs_dom`, `en_bbox_3`) a partir de `n_chips`,
`cim_name` y la geometría.

### Corrida `20260806_2005`

| | |
|---|---|
| Celdas seleccionadas | **405** (314 `2x2` + 91 `3x3`) |
| Cartas representadas | 74 de 121 |
| Ecorregiones | las 15 |
| Split | train 282 / val 63 / test 60 (~70/15/15) |
| Solapes geométricos | **0** (287 pares solo tocan borde) |
| Censo/refuerzo que cumplen objetivo | **36 / 36** |
| Celdas clase×eco cubiertas | 118 / 118 |

| `sample_type` | n |
|---|---|
| `presencia_refuerzo` | 214 |
| `presencia_censo` | 58 |
| `relleno_presupuesto` | 49 |
| `anual_homogenea` | 40 |
| `anual_simple_media` | 16 |
| `transicion_*` | 20 |
| `estable_homogenea` | 8 |

Más celdas que las 341 de v02: la grilla CIM cubre distinto el territorio y el
área nominal de cuota es menor (190,5 vs 240 km²), así que cada segmento se
traduce en más rectángulos. La composición de pools y el cumplimiento de
cobertura se mantienen.

## Plan de revisión

Deriva `rev_year1/2/3` y roles a partir de `sample_type`, `md_id_P*` y
`stab_run_*`. Los periodos que etiquetan el año medio son las eras Landsat
(P1 1999–2005, …), **igual que en v02**; las columnas `md_*` vienen de los
periodos de la caracterización (P1 1999–2004, …). Esa asimetría ya estaba en
v02 y se conserva a propósito.

Corrida `plan_revision_20260806_2006`: 405 celdas, 451 pares año–rectángulo,
roles `representativo_clase` (272), `anual` (56), `durante_cambio` (39),
`ancla`/`control_sensor` (38 cada uno), `antes`/`despues` (4). Salida en
EPSG:4326.

## Insumos

| Insumo | Ruta |
|---|---|
| Cartas CIM | `ancillary_data/cim_world-1-250000.gpkg` (campo `name`, 124 cartas) |
| Landcover | `ancillary_data/landcover_col2/classification_{year}.tif` (1999–2024, 26 años) |
| Ecorregiones | `ancillary_data/ecorregiones_col3_30m_alineado_lulc.tif` |
| Matriz clase × ecorregión | `prod/samples_cim/_insumos/clase_x_ecorregion.csv` |

## Estructura

```
config/params_grilla.py           # cartas, tamaños de celda, anclaje
config/params_caracterizacion.py  # serie temporal, periodos, escala de bloques
config/params_seleccion.py        # presupuesto, filtros, tipología, split
config/params_plan_revision.py    # eras Landsat y roles de revisión
config/diccionarios.py            # clases, ecorregiones, pares de confusión
config/corridas_ref.py            # tags de corridas validadas
geodesia.py                       # áreas exactas por latitud (fuente única)
grilla/construir.py               # celdas por carta desde la esquina NO
caracterizacion/                  # lectura, moda, composición, temporal, espacial
seleccion/cargar.py               # normaliza CIM → columnas que espera el selector
seleccion/selector.py             # orquestador; exporta un solo GPKG en 4326
seleccion/{presupuesto,pools,scores,tracker,split,...}.py
plan_revision/{derivar,exportar,validar,reporte}.py
reauditoria/cobertura.py          # cobertura alcanzable sobre la grilla 2x2
scripts/01..05                    # grilla y caracterización
scripts/06..10                    # presupuesto, selección, vista, informe, plan
jobs/                             # caracterizar.sh, seleccionar.sh, SLURM
```

Salidas bajo `prod/samples_cim/02_seleccion/{RUN}/`:

```
seleccion_nacional.gpkg           # EPSG:4326
seleccion_nacional.csv
universo_por_ecorregion.csv
presupuesto_por_ecorregion.csv
auditoria_{cobertura_celdas,nacional,solape}.csv
informe_seleccion.md
por_ecorregion/E{eco}/
plan_revision_{ts}/
├── seleccion_con_rev_years.gpkg  # EPSG:4326
├── seleccion_con_rev_years.csv
├── plan_revision_expandido.csv
└── reporte_plan_revision.md
```
