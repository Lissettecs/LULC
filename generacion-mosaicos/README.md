# LULC — Land Use and Land Cover Chile (1996–2026)

Repositorio de scripts para la generación de mosaicos Landsat y 
clasificación de cobertura y uso de suelo en Chile, basado en el 
framework MapBiomas y el modelo SSL4EO-L.

## Contenido

### `generate_mgrs_params.ipynb`
Notebook de preprocesamiento que extrae los blacklists de imágenes 
con mala calidad desde la grilla CIM (1:250.000) y los traspasa a 
tiles MGRS (100×100 km), fusionando las escenas descartadas de todos 
los tiles CIM que intersectan cada tile MGRS.

**Entrada:** `params.tsv`  
**Salida:** `input_params_mgrs.json`

### `mapbiomas_Chile_mosaics_MGRS_v2.py`
Script principal para la generación de mosaicos Landsat anuales 
(184 bandas) por tile MGRS en Google Earth Engine. Procesa imágenes 
Landsat Collection 2 (L4–L9) con corrección atmosférica, máscara de 
nubes, análisis de mezcla espectral (SMA) e índices espectrales.

**Entrada:** `input_params_mgrs.json`  
**Salida:** Asset GEE `projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF`

### `input_params_mgrs.json`
Archivo de parámetros con blacklist fusionado para los 6 tiles MGRS 
de prueba: `18FXH`, `18GXP`, `18HYD`, `19HCD`, `19JCJ`, `19KDU`.

### `modules/`
Módulos Python de MapBiomas para procesamiento de imágenes Landsat:
- `BandNames.py` — nombres de bandas por sensor
- `CloudAndShadowMaskC2.py` — máscara de nubes y sombras Collection 2
- `Collection.py` — filtrado y carga de colecciones Landsat
- `DataType.py` — tipos de datos y bandas del mosaico
- `Miscellaneous.py` — topografía y textura (DEM ALOS)
- `Mosaic.py` — generación del mosaico por percentiles
- `SmaAndNdfi.py` — análisis de mezcla espectral (SMA)
- `SpectralIndexes.py` — índices espectrales (NDVI, EVI2, NDWI, etc.)

## Tiles de prueba

| Tile MGRS | Zona UTM | Área aproximada |
|---|---|---|
| 19KDU | EPSG:32719 | Atacama / Coquimbo |
| 19JCJ | EPSG:32719 | Maule / O'Higgins |
| 19HCD | EPSG:32719 | Patagonia sur |
| 18HYD | EPSG:32718 | Biobío / Araucanía |
| 18GXP | EPSG:32718 | Los Lagos |
| 18FXH | EPSG:32718 | Aysén |

## Período temporal
1996 – 2026

## Dependencias
- Python 3.x
- `earthengine-api`
- Google Earth Engine con acceso a `mapbiomas-chile`

## Uso

### 1. Generar parámetros MGRS
Ejecutar el notebook `generate_mgrs_params.ipynb` con el archivo 
`params.tsv` del repositorio MapBiomas Chile.

### 2. Generar mosaicos
```bash
python mapbiomas_Chile_mosaics_MGRS_v2.py
```