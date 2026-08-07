"""Parámetros de la etapa de selección sobre la grilla CIM.

La lógica de modos, cuotas, pools tipológicos y split es la de v02. Lo que cambia
es el soporte espacial: un solo CRS (EPSG:4326), sin husos, y escalas nombradas
2x2 / 3x3. El tracking de solape se hace en un CRS métrico temporal y la salida
vuelve a 4326.
"""

from pathlib import Path

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_cim")
GRID_DIR = DATA_ROOT / "01_caracterizacion"
GRID_RUN_TAG = "nacional_20260806"
MATRIZ_PRESENCIA = DATA_ROOT / "_insumos/clase_x_ecorregion.csv"
OUT_ROOT = DATA_ROOT / "02_seleccion"
RUN_TAG = None
RESUME = False

ECORREGIONES = list(range(1, 16))
# Alias vacío: se deja para no romper código que itera HUSOS; la selección CIM
# no reparte por huso.
HUSOS: list[int] = []
ECO_AGRUPADAS = {}

# Escalas: 2 = 2x2 (528 px), 3 = 3x3 (792 px)
ORDEN_TAMANOS = [3, 2]
RELLENO_ORDEN_TAMANOS = [3, 2]

# Área nominal para convertir cuota de segmentos → rectángulos. En v02 eran
# ~240 km² fijos (UTM). Aquí la celda 2x2 promedia 190,5 km² (la de cobertura
# medible); usamos ese valor porque FASE 0 y la auditoría de cobertura trabajan
# sobre la grilla 2x2.
AREA_KM2_CUOTA = 190.5

# CRS métrico usado solo para tracking de solape y verificación de área.
# EPSG:32719 (UTM 19S) cubre la mayor parte del territorio continental chileno;
# el error de distorsión en la zona 18 no afecta la exclusión exclusiva.
CRS_PROCESO = "EPSG:32719"
CRS_SALIDA = "EPSG:4326"

UMBRAL_RAREZA_PCT_ECO = 1.0
UMBRAL_PRESENCIA_HA = 500
UMBRAL_CENSO_SEGMENTOS = 1500
PISO_PRESENCIA_HA = 50.0
PISO_PRESENCIA_HA_POR_CLASE: dict[int, float] = {}
UMBRAL_CENSO_RECTS = 3

EXCEPCIONES_MODO = {
    (1, 3): "refuerzo",
    (2, 3): "refuerzo",
    (5, 3): "refuerzo",
}

PRESUPUESTO_SEGMENTOS_TOTAL = 100_000
SEGMENTOS_POR_1000HA = 50
RENDIMIENTO_SEG_OK = {"homogenea": 0.35, "intermedia": 0.26, "heterogenea": 0.12}
PESO_AREA_GENERAL = 0.40
PESO_N_CLASES = 0.35
PESO_N_RARAS = 0.25
MIN_SEGMENTOS_ECO = 2000

COBERTURA_OBJETIVO_RARAS = 0.50
COBERTURA_OBJETIVO_CENSO = 0.30
CUOTA_CLASE_ES_OBJETIVO = True
CUOTA_MIN_2X2_PCT = 0.45
CUOTA_MIN_3X3_PCT = 0.25

FILTRO_BASE = {"valid_area_pct": 40, "eco_dom_pct": 50, "noobs_pct": 10}
FILTRO_RELAJADO = {"valid_area_pct": 25, "eco_dom_pct": 30, "noobs_pct": 15}
FILTRO_BASE_OVERRIDES: dict[int, dict] = {}

TIPOLOGIA_DEFAULT = {
    "E_H_MIN_STAB_RUN": 8,
    "E_H_MAX_TR_PCT": 2.0,
    "E_H_MIN_STAB_PCT": 80,
    "E_H_MIN_MODE_PCT": 85,
    "E_H_MAX_SHANNON": 0.5,
    "E_S_MIN_STAB_RUN": 6,
    "E_S_MAX_TR_PCT": 4.0,
    "E_S_MIN_MODE_PCT": 45,
    "E_S_MAX_MODE_PCT": 85,
    "E_S_MIN_N_MODE": 2,
    "E_S_MAX_N_MODE": 4,
    "A_H_MIN_STAB_YRS": 4,
    "A_H_MIN_MODE_PCT": 80,
    "TR_MIN_TR_PCT": 3.0,
}
CALIBRAR_TIPOLOGIA_POR_ECO = True
RANGO_MODE_PCT_HOMOGENEA = (55, 90)
TIPOLOGIA_OVERRIDES = {}

SPLIT_PROPORCIONES = {"train": 0.70, "val": 0.15, "test": 0.15}
SPLIT_MIN_PCT_TRAIN = 0.50
SPLIT_MARGEN_TECHO = 0.05
SPLIT_MIN_CLUSTERS = {"train": 1, "val": 2, "test": 2}
CENSO_PARTICIPA_SPLIT = False
CLUSTER_VECINDAD = 1
RANDOM_SEED = 42

TOPE_RELLENO_PCT = 0.15
