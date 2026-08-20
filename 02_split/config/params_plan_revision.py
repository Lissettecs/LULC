"""Parámetros para la derivación de años de revisión."""

from pathlib import Path

from config import params_seleccion as P
from config.corridas_ref import SEL_RUN_REF

DATA_ROOT = P.DATA_ROOT
SEL_ROOT = P.OUT_ROOT
SEL_RUN_TAG = SEL_RUN_REF

# Periodos alineados con eras Landsat (mismo criterio que v02 / plan de revisión).
# Ojo: no son los periodos de la caracterización CIM (P1 1999–2004, …).
PERIODOS = {
    "P1": (1999, 2005),
    "P2": (2006, 2012),
    "P3": (2013, 2018),
    "P4": (2019, 2024),
}
ANIO_MEDIO_PERIODO = {"P1": 2002, "P2": 2009, "P3": 2015, "P4": 2021}
ORDEN_PERIODOS = ["P1", "P2", "P3", "P4"]

ANIO_MIN = 1999
ANIO_MAX = 2024
SENTINEL = -9999

UMBRAL_TRANSICION = P.TIPOLOGIA_DEFAULT.get("TR_MIN_TR_PCT", 3.0)
UMBRAL_ESTABLE = P.TIPOLOGIA_DEFAULT.get("E_S_MIN_STAB_RUN", 6)

TIPOS_ANUAL = frozenset({"anual_homogenea", "anual_simple_media"})
TIPOS_ESTABLE = frozenset({"estable_homogenea", "estable_simple_media"})
TIPOS_TRANSICION = frozenset({"transicion_homogenea", "transicion_simple_media"})
TIPOS_PRESENCIA = frozenset({"presencia_censo", "presencia_refuerzo"})
TIPO_RELLENO = "relleno_presupuesto"

ROLES_VALIDOS = frozenset({
    "anual",
    "ancla",
    "control_sensor",
    "durante_cambio",
    "antes",
    "despues",
    "representativo_clase",
})
