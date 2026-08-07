"""Parámetros de caracterización sobre la grilla CIM en EPSG:4326.

Diferencias de fondo con el pipeline v02 (grilla UTM):

1. No hay reproyección. Cada celda es una ventana de píxeles enteros del ráster
   nativo, así que se lee con rasterio.windows y se procesa tal cual. Desaparecen
   el remuestreo, la distorsión UTM y el concepto de huso.

2. El píxel no tiene área constante. En EPSG:4326 un píxel de 0.00026949° mide
   ~30 m en latitud pero ~30·cos(lat) m en longitud, así que su área en el suelo
   baja de ~0.083 ha en el norte a ~0.048 ha en Magallanes. Todos los porcentajes
   y hectáreas se ponderan por el área real del píxel (ver caracterizacion/areas.py),
   no por conteo. Sin eso, las hectáreas del sur quedarían sobreestimadas ~70%.
"""

from pathlib import Path

# --- Rutas -------------------------------------------------------------------
ANCILLARY = Path("/home/lserey/mapbiomas_land/ancillary_data")
DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_cim")
OUT_ROOT = DATA_ROOT / "01_caracterizacion"

LULC_DIR = ANCILLARY / "landcover_col2"
LULC_PATRON = "classification_{year}.tif"

# Alineado píxel a píxel con landcover: misma transform, mismo tamaño. Permite
# reutilizar la misma ventana para landcover y ecorregiones.
ECO_RASTER = ANCILLARY / "ecorregiones_col3_30m_alineado_lulc.tif"
ECO_NODATA = 0

# --- Serie temporal ----------------------------------------------------------
START_YEAR = 1999
END_YEAR = 2024

PERIODOS = {
    "P1": (1999, 2004),
    "P2": (2005, 2010),
    "P3": (2011, 2016),
    "P4": (2017, 2024),
}
UMBRAL_ANIO_ESTABLE = 0.80

# --- Clases ------------------------------------------------------------------
MAX_CLASS_ID = 81
CLASE_NODATA_RASTER = 0
CLASE_NO_OBSERVADO = 27

# --- Escala de las métricas temporales ---------------------------------------
# Las métricas de dinámica se calculan sobre bloques agregados por moda, para que
# midan cambio de paisaje y no ruido de píxel. v02 usaba 10 px (300 m) y descartaba
# el resto de la celda; 11 px divide exacto tanto 528 (48 bloques) como 792
# (72 bloques), así que no se pierde ningún píxel a cambio de pasar de 300 a 330 m.
STATS_BLOQUE_PX = 11

# --- Ejecución ---------------------------------------------------------------
CELDAS_PX = [528, 792]
RUN_TAG = ""
RESUME = True

# Años leídos de una vez por celda. La celda de 792 px son 792*792*26 bytes
# (~16 MB en uint8), así que cabe completa sin trocear.
CHUNK_ANIOS = 0  # 0 = sin trocear
