"""Parámetros de caracterización (pipeline v02, grilla UTM nativa)."""

from pathlib import Path

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_v02")
ANCILLARY = Path("/home/lserey/mapbiomas_land/ancillary_data")
OUT_ROOT = DATA_ROOT / "01_caracterizacion"

CHIP_PX = 264
PIXEL_M = 30.0
PIXEL_HA = (PIXEL_M**2) / 10_000  # 0.09 ha por píxel 30 m
STATS_SCALE = 300
START_YEAR = 1999
END_YEAR = 2024

LULC_DIR = ANCILLARY / "landcover_col2"
LULC_PATRON = "classification_{year}.tif"
MGRS_VECTOR = ANCILLARY / "Tiles_Chile_Sentinel.gpkg"
MGRS_CAMPO_NOMBRE = "Name"
# Raster alineado píxel a píxel con landcover (requerido para ventanas 4326 compartidas)
ECO_RASTER = ANCILLARY / "ecorregiones_col3_30m_alineado_landcover.tif"
ECO_RASTER_ORIGINAL = ANCILLARY / "ecorregiones_col3_30m.tif"
ECO_RASTER_ALINEADO = ANCILLARY / "ecorregiones_col3_30m_alineado_landcover.tif"
ECO_NODATA = 0
ECO_CROP_COL_OFFSET = 1
ECO_CROP_ROW_OFFSET = 1

RUN_TAG = ""
RESUME = True

MAX_CLASS_ID = 81
CLASE_NODATA_RASTER = 0
CLASE_NO_OBSERVADO = 27
COMPOSICION_A_30M = True

PERIODOS = {
    "P1": (1999, 2004),
    "P2": (2005, 2010),
    "P3": (2011, 2016),
    "P4": (2017, 2024),
}
UMBRAL_ANIO_ESTABLE = 0.80

HUSOS = [18, 19]
UTM_EPSG = {18: 32718, 19: 32719}
RECT_SIDES = [2, 3]
LADO_M = {2: 2 * CHIP_PX * PIXEL_M, 3: 3 * CHIP_PX * PIXEL_M}  # 15840, 23760 m
ORIGEN_MALLA_XY = {18: (100_000.0, 3_000_000.0), 19: (100_000.0, 3_000_000.0)}
MERIDIANO_CENTRAL = {18: -75.0, 19: -69.0}
MAX_DISTORSION_UTM = 0.005
CRS_RASTER = "EPSG:4326"
