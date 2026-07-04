# Segmentación Felzenszwalb para etiquetado de muestras

Prueba de calibración visual de segmentación sobre mosaicos multibanda (NIR, SWIR1, red) antes de atribuir clases MapBiomas Colección 2 a polígonos.

Ejecuta un **grid de parámetros** (`scale` × `sigma`) por tile MGRS y año, exporta GeoTIFF de etiquetas, quicklooks PNG y un CSV resumen con estadísticas de tamaño de segmentos.

## Estructura

```text
segmentacion_etiquetas/
├── seg_felzenszwalb_grid.py              ← grid scale × sigma; exporta TIF, PNG y CSV
├── regenerar_quicklooks_felzenszwalb.py ← regenera PNG desde TIF ya exportados
├── visualizar_seg_felzenszwalb_grid.py  ← dashboard HTML interactivo
└── README.md
```

## Entradas en cluster

Mosaicos normalizados 0–1 fuera de este repositorio:

```text
/home/lserey/mapbiomas_land/test/image_segmentation/
└── nir_swir1_red_normalized_mosaics/
    └── {tile}_{year}_nir_swir1_red_0-1.tif
```

Convención de bandas en el GeoTIFF: `0=nir`, `1=swir1`, `2=red`. Visualización RGB: red, swir1, nir.

Tiles de prueba habituales: `18HYD`, `19KDU`, `19JCJ`, `19HCD`, `18GXP`, `18FXH`.

## Salidas

Por defecto en `.../image_segmentation/seg_felzenszwalb/`:

```text
seg_{tile}_{year}_s{scale}_sig{sigma}.tif   ← etiquetas INT32 (nodata=0)
seg_{tile}_{year}_s{scale}_sig{sigma}.png   ← quick-look RGB + polígonos coloreados
resumen_{tile}_{year}.csv                   ← estadísticas por combinación de parámetros
viewer_felzenszwalb.html                    ← dashboard (script visualizar)
capas/                                      ← PNG por capa para el explorador HTML
```

Los scripts **no sobrescriben** archivos existentes; hay que borrarlos o cambiar `--output-dir` antes de re-ejecutar.

## Instalación

```bash
cd segmentacion_etiquetas
python -m pip install rasterio scikit-image matplotlib
```

En cluster, activar el entorno donde ya estén esas dependencias (p. ej. `mb_labels` de [labeling-samples](../labeling-samples/)).

## Uso rápido

```bash
cd segmentacion_etiquetas

# Listar tiles disponibles para un año
python seg_felzenszwalb_grid.py --list-tiles --year 2010

# Ejecutar grid sobre tile/año (defaults: 18HYD, 2010)
python seg_felzenszwalb_grid.py --tile 18HYD --year 2010

# Regenerar PNG si cambió la lógica de quick-look
python regenerar_quicklooks_felzenszwalb.py --output-dir /ruta/seg_felzenszwalb

# Dashboard HTML (requiere salidas previas del grid)
python visualizar_seg_felzenszwalb_grid.py --output-dir /ruta/seg_felzenszwalb
cd /ruta/seg_felzenszwalb && python3 -m http.server 8765
# → http://localhost:8765/viewer_felzenszwalb.html
```

## Parámetros del grid (editable en `seg_felzenszwalb_grid.py`)

| Parámetro | Default | Descripción |
|-----------|---------|-------------|
| `SCALE_LIST` | 25, 50, 100, 150, 200 | Escala Felzenszwalb (tamaño relativo de segmentos) |
| `SIGMA_LIST` | 0.1, 0.5, 0.8 | Suavizado gaussiano previo |
| `MIN_SIZE` | 20 | Tamaño mínimo de segmento (píxeles) |
| `STANDARDIZE` | `False` | Z-score por banda (excluyente con `NORMALIZE_01`) |
| `NORMALIZE_01` | `False` | Mosaicos ya vienen en 0–1 |
| `PIXEL_HA` | 0.09 | Resolución 30 m → ha por píxel en el CSV |

CLI de `seg_felzenszwalb_grid.py`:

| Argumento | Default | Descripción |
|-----------|---------|-------------|
| `--tile` | `18HYD` | Tile MGRS |
| `--year` | `2010` | Año del mosaico |
| `--mosaic-dir` | ver script | Directorio de mosaicos `{tile}_{year}_nir_swir1_red_0-1.tif` |
| `--output-dir` | ver script | Directorio de salida TIF/PNG/CSV |
| `--list-tiles` | — | Lista tiles en `--mosaic-dir` y termina |

## Alcance futuro (no implementado)

- Atribución de clase por voto mayoritario vs MapBiomas Colección 2
- Índices espectrales (NDVI, MNDWI, NDSI, BSI) con z-score
- Reemplazo por OTB Large-Scale Mean-Shift a escala nacional

## Datos generados

No versionar rasters, PNG ni CSV de salida. Regenerar con los scripts o almacenar fuera de Git (ver [.gitignore](../.gitignore)).
