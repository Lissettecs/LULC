"""Parámetros de la etapa de selección."""

from pathlib import Path

DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_v02")
GRID_DIR = DATA_ROOT / "01_caracterizacion"
GRID_RUN_TAG = None
MATRIZ_PRESENCIA = DATA_ROOT / "_insumos/clase_x_ecorregion.csv"
OUT_ROOT = DATA_ROOT / "02_seleccion"
RUN_TAG = None
RESUME = False

ECORREGIONES = list(range(1, 16))
HUSOS = [18, 19]
ECO_AGRUPADAS = {}

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

ORDEN_TAMANOS = [3, 2]
RELLENO_ORDEN_TAMANOS = [3, 2]
TOPE_RELLENO_PCT = 0.15
