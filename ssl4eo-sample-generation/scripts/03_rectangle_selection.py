"""
SELECCIÓN DE RECTÁNGULOS SSL4EO-L — v2.0
==========================================
Selecciona rectángulos del SHP caracterizado en GEE organizando
la selección según los 6 tipos esenciales de muestras (v1):

  Dimensión temporal × Dimensión espacial:

    1. estable_homogenea     → firma pura estable (modo_pct≥85, run≥5)
    2. estable_simple_media  → mosaico estable 2-4 clases (mejor costo/calidad)
    4. anual_homogenea       → clase pura en un año específico (dinámica)
    5. anual_simple_media    → clases dinámicas en contexto espacial real
    7. transicion_homogenea  → cambio de una clase pura a otra
    8. transicion_simple_media → cambio en contexto mixto

  Tipos opcionales (v2, no implementados aquí):
    3. estable_compleja  6. anual_compleja  9. transicion_compleja

  Exclusion modelo general:
    Rectangulos cuya clase modal (lulc_mode_id) es transversal se reservan para
    modelos especializados (humedal, agro fina, urbano, etc.) y no entran en
    pools T1/T2/T4/T5/T7/T8. Pools de clases criticas (arena/salar/achaparrado/bosque_norte)
    siguen usando candidatos sin este filtro.

Campos de output clave:
  sample_type   → tipo de muestra (ej. 'estable_homogenea')
  dim_temporal  → 'estable' | 'anual' | 'transicion'
  dim_espacial  → 'homogenea' | 'simple_media'
  ref_year      → año de referencia para tipos anuales
  ref_period    → período Landsat de referencia (P1-P4)
  ref_sensor    → sensor del año de referencia
  review_tier   → nivel de revisión requerido (0-3)
  review_status → 'pendiente'
"""

import argparse
from collections import defaultdict
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from critical_classes import (
    CRITICAL_CLASS_NAMES,
    MIN_PERIOD_PCT,
    MIN_RELAXED_PERIOD_PCT,
    NORTH_FOREST_MODE_ID,
    NORTH_FOREST_PRESENCE_COL,
    PRESENCE_THRESHOLD_PCT,
    class_present,
    class_present_mask,
    class_presence_strength,
    class_presence_strength_series,
)
from selection_balancing import (
    FRAGILE_ECOS,
    OTRA_SIN_VEG_ID,
    PASTIZAL_MODE_ID,
    WATER_MODE_ID,
    apply_modal_class_cap,
    arid_transition_mask,
    assign_cluster_aware_split,
    block_desert_otra_candidates,
    build_ecoregion_reserves,
    cap_sample_type,
    fill_ecoregion_quotas,
    fill_to_total_target,
    infer_utm_zone,
    is_otra_sin_vegetacion_exempt,
    modal_cap_for_zone,
    verify_cluster_split,
)
from taxonomy_classes import (
    GENERAL_MODAL_TRANSVERSAL_MIN_PCT,
    GENERAL_MODEL_EXCLUDED_MODAL_IDS,
    annotate_transversal_modal,
    transversal_modal_mask,
)

# ══════════════════════════════════════════════════════════════
# 1. ARGUMENTOS
# ══════════════════════════════════════════════════════════════

from project_paths import FINALES_DIR, GEE_CARACTERIZACION_DIR

SCRIPT_DIR = Path(__file__).resolve().parent

parser = argparse.ArgumentParser(
    description="Seleccion de rectangulos SSL4EO por tipo de muestra (v2).")
parser.add_argument("--homogeneo", dest="file_homogeneo", type=Path, default=None,
    help="SHP/ZIP con rectangulos 2x2 para tipos homogeneos (1 y 4).")
parser.add_argument("--mixto", dest="file_mixto", type=Path, default=None,
    help="SHP/ZIP con rectangulos 3x3 para tipos mixtos (2,5,7,8).")
parser.add_argument("--previous", "-p", dest="previous_files",
    type=Path, nargs="*", default=[])
parser.add_argument("--no-auto-previous", dest="auto_previous",
    action="store_false")
parser.add_argument("--no-cross-zone-previous", dest="cross_zone_previous",
    action="store_false")
parser.add_argument("--max-overlap", dest="max_overlap",
    type=float, default=0.0)
parser.add_argument("--overlap-tolerance", dest="overlap_tolerance",
    type=float, default=1.0)

args                 = parser.parse_args()
FILE_HOMOGENEO       = args.file_homogeneo
FILE_MIXTO           = args.file_mixto
manual_previous      = args.previous_files
AUTO_PREVIOUS        = args.auto_previous
CROSS_ZONE_PREVIOUS  = args.cross_zone_previous
MAX_OVERLAP          = args.max_overlap
OVERLAP_TOLERANCE_M2 = args.overlap_tolerance

_input_names = " ".join(str(p) for p in [FILE_HOMOGENEO, FILE_MIXTO] if p).lower()
USE_SCALE300_PROFILE = "scale300" in _input_names
UTM_ZONE = infer_utm_zone(FILE_HOMOGENEO, FILE_MIXTO)

if FILE_HOMOGENEO is None and FILE_MIXTO is None:
    parser.error("Se requiere al menos --homogeneo o --mixto.")

# Nombre base para outputs (corto: evita rutas >260 chars en Windows)
_stems = [f.stem for f in [FILE_HOMOGENEO, FILE_MIXTO] if f is not None]
base_name_combined = "__".join(_stems)


def make_output_stem(paths: list[Path | None]) -> str:
    names = " ".join(p.stem.upper() for p in paths if p)
    utm = "UTM18" if "UTM18" in names else "UTM19" if "UTM19" in names else "UTM"
    scale = (
        "scale300" if "SCALE300" in names
        else "scale900" if "SCALE900" in names
        else "scale"
    )
    return f"grilla_ssl4eo_muestras_{utm}_{scale}"

LN_MAX_CLASSES  = np.log(19)
N_YEARS_PERIOD  = 26
RANDOM_SEED     = 2026

SENSOR_MAP = {
    "P1": "Landsat_5_7", "P2": "Landsat_5_7",
    "P3": "Landsat_8",   "P4": "Landsat_8_9"
}
PERIOD_YEARS = {
    "P1": (1999, 2005, 7), "P2": (2006, 2012, 7),
    "P3": (2013, 2018, 6), "P4": (2019, 2024, 6)
}
# Preferencia al listar periodos (P4→P1); la asignacion de ref_year usa todos los que cumplen umbral
ANUAL_PERIOD_PREF = ["P4", "P3", "P2", "P1"]
ALL_PERIODS = ["P1", "P2", "P3", "P4"]


# ══════════════════════════════════════════════════════════════
# 2. RUTAS DE SALIDA
# ══════════════════════════════════════════════════════════════

_ref_file  = FILE_HOMOGENEO if FILE_HOMOGENEO is not None else FILE_MIXTO
output_dir = FINALES_DIR
output_dir.mkdir(parents=True, exist_ok=True)
base_name  = make_output_stem([FILE_HOMOGENEO, FILE_MIXTO])

output_gpkg    = output_dir / f"seleccion_{base_name}.gpkg"
output_geojson = output_dir / f"seleccion_{base_name}.geojson"
output_csv     = output_dir / f"seleccion_{base_name}.csv"
output_reserve_csv = output_dir / f"reservas_{base_name}.csv"
output_shp_dir = output_dir / f"seleccion_{base_name}_shp"
output_shp_dir.mkdir(exist_ok=True)
output_shp = output_shp_dir / "seleccion.shp"


# ══════════════════════════════════════════════════════════════
# 3. PARÁMETROS POR TIPO DE MUESTRA
# ══════════════════════════════════════════════════════════════

# ── Filtros base (todos los tipos) ────────────────────────────
MIN_VALID_AREA_PCT = 40
MIN_ECO_DOM_PCT    = 50
MAX_NOOBS_PCT      = 10

# Filtros relajados solo para pools dedicados de arena (23) y salar (61)
RARE_MIN_VALID_AREA_PCT = 30
RARE_MIN_ECO_DOM_PCT    = 35
RARE_MAX_NOOBS_PCT      = 15
MIN_ARENA_SALAR_PERIOD_PCT = MIN_RELAXED_PERIOD_PCT
DESERT_ECO_IDS = {2, 4}

# Perfil scale300: meta nacional ~300-350 (UTM18 ~145 + UTM19 ~180).
if USE_SCALE300_PROFILE:
    MIN_ARENA_SALAR_PCT = 3.0
    MIN_ARENA_SALAR_PERIOD_PCT = 5.0
    RARE_MIN_VALID_AREA_PCT = 25
    RARE_MIN_ECO_DOM_PCT = 30

    E_H_MIN_STAB_RUN  = 5
    E_H_MAX_TR_PCT    = 10
    E_H_MIN_STAB_PCT  = 60
    E_H_MIN_MODE_PCT  = 85
    E_H_MAX_SHANNON   = 0.3
    N_E_H_PER_GROUP   = 6
    MAX_E_H           = 35

    E_S_MIN_STAB_RUN  = 3
    E_S_MAX_TR_PCT    = 15
    E_S_MIN_MODE_PCT  = 45
    E_S_MAX_MODE_PCT  = 85
    E_S_MIN_N_MODE    = 2
    E_S_MAX_N_MODE    = 6
    N_E_S_PER_GROUP   = 7
    MAX_E_S           = 50

    A_H_MIN_STAB_YRS  = 3
    A_H_MIN_MODE_PCT  = 85
    N_A_H_PER_GROUP   = 5
    MAX_A_H           = 35

    A_S_MIN_STAB_YRS  = 2
    A_S_MIN_MODE_PCT  = 40
    A_S_MAX_MODE_PCT  = 88
    A_S_MIN_N_MODE    = 2
    A_S_MAX_N_MODE    = 7
    N_A_S_PER_GROUP   = 6
    MAX_A_S           = 35

    T_H_MIN_TR_PCT    = 5
    T_H_MIN_PURE_PCT  = 65
    N_T_H_PER_GROUP   = 4
    MAX_T_H           = 25

    T_S_MIN_TR_PCT    = 4
    T_S_MIN_N_MODE    = 2
    T_S_MAX_N_MODE    = 8
    T_S_MIN_MODE_PCT  = 28
    T_S_MAX_MODE_PCT  = 85
    N_T_S_PER_GROUP   = 8
    MAX_T_S           = 40

    N_ARENA_PER_GROUP = 4
    MAX_ARENA         = 12
    N_SALAR_PER_GROUP = 4
    MAX_SALAR         = 12
    N_ACHAP_PER_GROUP = 2
    MAX_ACHAP         = 8
    N_BOSQUE_NORTE_PER_GROUP = 3
    MAX_BOSQUE_NORTE  = 10
    N_PASTIZAL_PER_GROUP = 3
    MAX_PASTIZAL      = 10
    MAX_RARE = MAX_ARENA + MAX_SALAR + MAX_ACHAP + MAX_BOSQUE_NORTE + MAX_PASTIZAL
    MIN_PER_ECO       = 6
    PRIORITY_ECOS     = {7, 8, 9, 12, 15}
    ECO_FILL_MAX_ADD  = 35
    MAX_MODAL_OTRA    = modal_cap_for_zone(UTM_ZONE)
    RESERVE_PER_ECO   = 3
    if UTM_ZONE == 18:
        MAX_TOTAL     = 145
        MAX_T_S_CAP   = 35
        MAX_E_H       = 32
        MAX_E_S       = 45
        N_E_H_PER_GROUP = 8
        N_E_S_PER_GROUP = 8
        E_H_MIN_STAB_RUN = 4
        E_H_MIN_MODE_PCT = 80
        E_H_MIN_STAB_PCT = 50
        MAX_T_H       = 12
        MAX_T_S       = 35
    elif UTM_ZONE == 19:
        MAX_TOTAL     = 180
        MAX_T_S_CAP   = 50
        MAX_T_H       = 25
        MAX_T_S       = 40
    else:
        MAX_TOTAL     = 160 + MAX_RARE
        MAX_T_S_CAP   = 85
else:
    MIN_ARENA_SALAR_PCT = PRESENCE_THRESHOLD_PCT
    MIN_ARENA_SALAR_PERIOD_PCT = MIN_RELAXED_PERIOD_PCT
    MAX_T_S_CAP = 99999
    RESERVE_PER_ECO = 0
    E_H_MIN_STAB_RUN  = 5
    E_H_MAX_TR_PCT    = 10
    E_H_MIN_STAB_PCT  = 60
    E_H_MIN_MODE_PCT  = 85
    E_H_MAX_SHANNON   = 0.3
    N_E_H_PER_GROUP   = 4
    MAX_E_H           = 250

    E_S_MIN_STAB_RUN  = 3
    E_S_MAX_TR_PCT    = 15
    E_S_MIN_MODE_PCT  = 45
    E_S_MAX_MODE_PCT  = 85
    E_S_MIN_N_MODE    = 2
    E_S_MAX_N_MODE    = 6
    N_E_S_PER_GROUP   = 4
    MAX_E_S           = 200

    A_H_MIN_STAB_YRS  = 3
    A_H_MIN_MODE_PCT  = 85
    N_A_H_PER_GROUP   = 4
    MAX_A_H           = 250

    A_S_MIN_STAB_YRS  = 2
    A_S_MIN_MODE_PCT  = 45
    A_S_MAX_MODE_PCT  = 85
    A_S_MIN_N_MODE    = 2
    A_S_MAX_N_MODE    = 6
    N_A_S_PER_GROUP   = 3
    MAX_A_S           = 140

    T_H_MIN_TR_PCT    = 5
    T_H_MIN_PURE_PCT  = 70
    N_T_H_PER_GROUP   = 2
    MAX_T_H           = 80

    T_S_MIN_TR_PCT    = 5
    T_S_MIN_N_MODE    = 2
    T_S_MAX_N_MODE    = 6
    T_S_MIN_MODE_PCT  = 30
    T_S_MAX_MODE_PCT  = 80
    N_T_S_PER_GROUP   = 3
    MAX_T_S           = 120

    N_ARENA_PER_GROUP = 3
    MAX_ARENA         = 6
    N_SALAR_PER_GROUP = 3
    MAX_SALAR         = 6
    N_ACHAP_PER_GROUP = 3
    MAX_ACHAP         = 12
    N_BOSQUE_NORTE_PER_GROUP = 3
    MAX_BOSQUE_NORTE  = 10
    MAX_RARE = MAX_ARENA + MAX_SALAR + MAX_ACHAP + MAX_BOSQUE_NORTE
    MAX_TOTAL = 760 + MAX_RARE
    MIN_PER_ECO = 0
    PRIORITY_ECOS = set()
    ECO_FILL_MAX_ADD = 0
    MAX_MODAL_OTRA = 99999
    MAX_PASTIZAL = 0
    N_PASTIZAL_PER_GROUP = 0
    MAX_T_S_CAP = 99999
    RESERVE_PER_ECO = 0

# Clases criticas con cupo dedicado (caracterizacion_grillas_gee.py)
ARENA_MODE_ID          = 23
ARENA_CLASS_NAME       = CRITICAL_CLASS_NAMES[ARENA_MODE_ID]
SALAR_MODE_ID          = 61
SALAR_CLASS_NAME       = CRITICAL_CLASS_NAMES[SALAR_MODE_ID]
ACHAP_MODE_ID          = 67
ACHAP_CLASS_NAME       = CRITICAL_CLASS_NAMES[ACHAP_MODE_ID]
BOSQUE_NORTE_MODE_ID   = NORTH_FOREST_MODE_ID
BOSQUE_NORTE_CLASS_NAME = CRITICAL_CLASS_NAMES[BOSQUE_NORTE_MODE_ID]
MIN_RARE_PCT           = PRESENCE_THRESHOLD_PCT
MIN_RARE_PERIOD_PCT    = MIN_PERIOD_PCT

PASTIZAL_CLASS_NAME = "Pastizal"

RARE_CLASS_SPECS = {
    "presencia_arena_playa_duna": dict(
        class_id=ARENA_MODE_ID,
        class_name=ARENA_CLASS_NAME,
        score_col="sc_arena",
        n_per_group=N_ARENA_PER_GROUP,
        max_n=MAX_ARENA,
        min_period_pct=MIN_ARENA_SALAR_PERIOD_PCT,
        min_pct=MIN_ARENA_SALAR_PCT,
        use_relaxed_quality=True,
        review_tier=2,
    ),
    "presencia_salar": dict(
        class_id=SALAR_MODE_ID,
        class_name=SALAR_CLASS_NAME,
        score_col="sc_salar",
        n_per_group=N_SALAR_PER_GROUP,
        max_n=MAX_SALAR,
        min_period_pct=MIN_ARENA_SALAR_PERIOD_PCT,
        min_pct=MIN_ARENA_SALAR_PCT,
        use_relaxed_quality=True,
        review_tier=2,
    ),
    "presencia_achaparrado": dict(
        class_id=ACHAP_MODE_ID,
        class_name=ACHAP_CLASS_NAME,
        score_col="sc_achap",
        n_per_group=N_ACHAP_PER_GROUP,
        max_n=MAX_ACHAP,
        min_period_pct=MIN_RARE_PERIOD_PCT,
        use_relaxed_quality=False,
        review_tier=1,
    ),
    "presencia_bosque_norte": dict(
        class_id=BOSQUE_NORTE_MODE_ID,
        class_name=BOSQUE_NORTE_CLASS_NAME,
        score_col="sc_bosque_norte",
        n_per_group=N_BOSQUE_NORTE_PER_GROUP,
        max_n=MAX_BOSQUE_NORTE,
        min_period_pct=MIN_RARE_PERIOD_PCT,
        use_relaxed_quality=False,
        review_tier=1,
    ),
    "presencia_pastizal": dict(
        class_id=PASTIZAL_MODE_ID,
        class_name=PASTIZAL_CLASS_NAME,
        score_col="sc_pastizal",
        n_per_group=N_PASTIZAL_PER_GROUP,
        max_n=MAX_PASTIZAL,
        min_period_pct=MIN_RARE_PERIOD_PCT,
        use_relaxed_quality=False,
        review_tier=2,
    ),
}

# Orden de selección exclusiva: tipos escasos primero para no perderlos
# al competir por grid_id o solape geometrico con tipos ya elegidos.
SELECTION_ORDER = [
    "presencia_arena_playa_duna",
    "presencia_salar",
    "presencia_achaparrado",
    "presencia_bosque_norte",
    "presencia_pastizal",
    "transicion_homogenea",
    "anual_simple_media",
    "transicion_simple_media",
    "anual_homogenea",
    "estable_simple_media",
    "estable_homogenea",
]


print("\n====== PARÁMETROS v2.0 ======")
print(f"  Perfil:    {'scale300' if USE_SCALE300_PROFILE else 'default'}  UTM{UTM_ZONE or '?'}")
print(f"  Meta huso: {MAX_TOTAL} rect", end="")
if USE_SCALE300_PROFILE:
    print(f"  cap Otra_sin_vegetacion={MAX_MODAL_OTRA}")
else:
    print()
if FILE_HOMOGENEO: print(f"  Homogeneo 2x2: {FILE_HOMOGENEO}")
if FILE_MIXTO:     print(f"  Mixto     3x3: {FILE_MIXTO}")
print(f"  Filtros:  val_pct>={MIN_VALID_AREA_PCT}  eco_pct>={MIN_ECO_DOM_PCT}  noobs<={MAX_NOOBS_PCT}")
print(f"  Max total: {MAX_TOTAL}  (incl. hasta {MAX_RARE} clases criticas dedicadas)")
print(
    f"  Criticas:  arena<={MAX_ARENA}  salar<={MAX_SALAR}  achap<={MAX_ACHAP}  "
    f"bosque_norte<={MAX_BOSQUE_NORTE}  pastizal<={MAX_PASTIZAL}  pct>={MIN_RARE_PCT}%"
)
print(
    f"  Arena/salar: filtros relajados val>={RARE_MIN_VALID_AREA_PCT}%  "
    f"eco>={RARE_MIN_ECO_DOM_PCT}%  periodo>={MIN_ARENA_SALAR_PERIOD_PCT}%"
)
print(
    f"  Achap/bosque: filtros estrictos  periodo>={MIN_RARE_PERIOD_PCT}%  "
    f"(ID 3 / Otra_Formacion_boscosa via north_forest_pct, lat>={-33.2})"
)
print(
    f"  Modal transversal: excluida del modelo general "
    f"(IDs nativos + 14 agro; proxy 10/22 si tran_pct>={GENERAL_MODAL_TRANSVERSAL_MIN_PCT}%)"
)
print("  Ecorregion:   excluye sin_nombre / eco_id invalido")
print("  ref_year:     balanceado 1999-2024 entre todos los periodos estables P1-P4")
print(f"  Tipos:     {SELECTION_ORDER}")


# ══════════════════════════════════════════════════════════════
# 4. FUNCIONES GENERALES
# ══════════════════════════════════════════════════════════════

def read_vector(path: Path) -> gpd.GeoDataFrame:
    if not path.exists():
        raise FileNotFoundError(f"No existe: {path}")
    if path.suffix.lower() == ".zip":
        try:    return gpd.read_file(path)
        except Exception as e1:
            try: return gpd.read_file(f"zip://{path.as_posix()}")
            except Exception as e2:
                raise RuntimeError(f"No se pudo leer ZIP.\n{e1}\n{e2}")
    return gpd.read_file(path)


def get_union_geometry(gdf):
    try:    return gdf.geometry.union_all()
    except: return gdf.geometry.unary_union


def infer_crs(path: Path) -> str | None:
    n = path.name.upper()
    if "UTM12" in n: return "EPSG:32712"
    if "UTM17" in n: return "EPSG:32717"
    if "UTM18" in n: return "EPSG:32718"
    if "UTM19" in n: return "EPSG:32719"
    return None


def normalize_fields(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Renombra campos SHP ≤10 chars a nombres completos."""
    rename = {
        "grid_id":"grid_id",     "dataset":"dataset",
        "rect_side":"rect_side", "rect_m":"rect_m",
        "chip_px":"chip_px",     "chip_m":"chip_m",
        "overlap":"overlap_pct", "stride_m":"stride_m",
        "n_chips_ov":"n_chips_ov", "n_chips_b":"n_chips_base",
        "area_km2":"area_km2",   "val_pct":"valid_area_pct",
        "mgrs_dom":"mgrs_dom",   "mgrs_pct":"mgrs_dom_pct",
        "eco_id":"eco_dom_id",   "eco_name":"eco_dom_name",
        "eco_pct":"eco_dom_pct",
        "mode_id":"lulc_mode_id","mode_name":"lulc_mode_name",
        "mode_pct":"lulc_mode_pct","n_mode":"n_mode_classes",
        "last_id":"lulc_last_id","last_name":"lulc_last_name",
        "last_pct":"lulc_last_pct",
        "tr_pct":"transition_pct","stab_pct":"stable_mode_pct",
        "noobs_pct":"noobs_pct",
        "crit_pct":"critical_pct","nfor_pct":"north_forest_pct",
        "achap_pct":"achaparrado_pct",
        "tran_pct":"transversal_pct",
        "shannon":"shannon_idx", "conf_risk":"conf_risk_pct",
        "stab_yrs":"stable_years","n_stab_yrs":"n_stable_years",
        "stb_yr_pct":"stable_yr_pct",
        "mx_stb_run":"max_stab_run","run_start":"stab_run_start",
        "run_end":"stab_run_end",
        "dim_temp":"dim_temporal","dim_spat":"dim_espacial",
        "samp_type":"sample_type_gee",
        "prio_sc":"prio_sc_gee",
        "utm_zone":"utm_zone",   "utm_epsg":"utm_epsg",
        "cls_lvl":"class_level",
        "n1_cd":"n1_code", "n2_cd":"n2_code", "n3_cd":"n3_code",
        "n1_nm":"n1_name", "n2_nm":"n2_name",
        "ln1_cd":"last_n1_code", "ln2_cd":"last_n2_code", "ln3_cd":"last_n3_code",
    }
    for p in ["P1","P2","P3","P4"]:
        rename.update({
            f"md_id_{p}":f"md_id_{p}", f"md_nm_{p}":f"md_nm_{p}",
            f"md_pct_{p}":f"md_pct_{p}", f"n_stb_{p}":f"n_stb_{p}",
            f"stb_p_{p}":f"stb_p_{p}", f"stb_yrs_{p}":f"stb_yrs_{p}",
        })
    avail = {k:v for k,v in rename.items() if k in gdf.columns}
    return gdf.rename(columns=avail)


def ensure_fields(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Rellena campos faltantes con defaults (compatibilidad SHPs viejos)."""
    defaults = {
        "n_stable_years":0, "stable_yr_pct":0.0,
        "max_stab_run":0,   "stab_run_start":-9999, "stab_run_end":-9999,
        "shannon_idx":0.0,  "conf_risk_pct":0.0,
        "stable_years":"",  "critical_pct":0.0,
        "transversal_pct":0.0, "north_forest_pct":0.0,
        "achaparrado_pct":0.0,
        "dim_temporal":"",  "dim_espacial":"",
        "lulc_last_pct":0.0,
    }
    for p in ["P1","P2","P3","P4"]:
        defaults.update({
            f"md_pct_{p}":0.0, f"n_stb_{p}":0,
            f"stb_p_{p}":0.0,  f"stb_yrs_{p}":"",
            f"md_nm_{p}":"",   f"md_id_{p}":-9999,
        })
    gdf = gdf.copy()
    added = [c for c in defaults if c not in gdf.columns]
    for col in added: gdf[col] = defaults[col]
    if added:
        print(f"\nCampos con defaults: {added}")
    return gdf


class SpatialSelectionTracker:
    """Excluye candidatos que se solapan geometricamente con rectangulos ya elegidos."""

    def __init__(self, crs, max_overlap_pct: float = 0.0, tol_m2: float = 1.0):
        self.crs = crs
        self.max_overlap_pct = max_overlap_pct
        self.tol_m2 = tol_m2
        self._selected: gpd.GeoDataFrame | None = None

    def _empty(self) -> bool:
        return self._selected is None or self._selected.empty

    def _as_gdf(self, df: pd.DataFrame) -> gpd.GeoDataFrame:
        if isinstance(df, gpd.GeoDataFrame):
            return df
        return gpd.GeoDataFrame(
            df.drop(columns="geometry", errors="ignore"),
            geometry=df["geometry"].values,
            crs=self.crs,
        )

    def filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty or self._empty() or "geometry" not in df.columns:
            return df
        gdf = self._as_gdf(df)
        geoms = gdf.geometry.values
        areas = gdf.geometry.area.to_numpy()
        sidx = self._selected.sindex
        sel_geoms = self._selected.geometry.values
        keep = np.ones(len(df), dtype=bool)
        for i, geom in enumerate(geoms):
            area = areas[i]
            if area <= 0:
                keep[i] = False
                continue
            ovlp = 0.0
            for j in sidx.intersection(geom.bounds):
                inter = geom.intersection(sel_geoms[j])
                if inter.is_empty:
                    continue
                ovlp += inter.area
                if ovlp > self.tol_m2 and ovlp / area > self.max_overlap_pct:
                    keep[i] = False
                    break
        return df.loc[keep].copy()

    def register(self, df: pd.DataFrame) -> None:
        if df.empty or "geometry" not in df.columns:
            return
        chunk = self._as_gdf(df)[["grid_id", "geometry"]].copy()
        chunk["grid_id"] = chunk["grid_id"].astype(str)
        if self._empty():
            self._selected = chunk
            return
        existing = set(self._selected["grid_id"])
        chunk = chunk[~chunk["grid_id"].isin(existing)]
        if chunk.empty:
            return
        self._selected = pd.concat([self._selected, chunk], ignore_index=True)


def spatial_dedupe_rows(
    df: pd.DataFrame,
    spatial_tracker: SpatialSelectionTracker | None,
    max_n: int | None = None,
) -> pd.DataFrame:
    """Conserva filas en orden sin solape con tracker (registra las aceptadas)."""
    if df.empty or spatial_tracker is None:
        return df.head(max_n) if max_n else df
    kept: list[pd.Series] = []
    for _, row in df.iterrows():
        one = pd.DataFrame([row])
        if spatial_tracker.filter(one).empty:
            continue
        kept.append(row)
        spatial_tracker.register(one)
        if max_n and len(kept) >= max_n:
            break
    if not kept:
        return df.iloc[0:0]
    return pd.DataFrame(kept)


def exclude_overlaps(gdf, prev_files, crs, max_pct, tol_m2):
    if not prev_files:
        print("\nNo hay selecciones previas.")
        gdf["prev_ovlp_pct"] = 0.0
        return gdf
    layers = []
    print("\n-- Selecciones previas --")
    for f in prev_files:
        if not f.exists(): continue
        p = read_vector(f)
        if p.crs != crs: p = p.to_crs(crs)
        layers.append(p)
        print(f"  {f.name}: {len(p)}")
    if not layers:
        gdf["prev_ovlp_pct"] = 0.0
        return gdf
    prev_union = get_union_geometry(
        gpd.GeoDataFrame(pd.concat(layers, ignore_index=True),
                         geometry="geometry", crs=crs))
    gdf = gdf.copy()
    gdf["geometry"]  = gdf.geometry.buffer(0)
    area             = gdf.geometry.area
    ovlp             = gdf.geometry.intersection(prev_union).area
    gdf["prev_ovlp_pct"] = np.where(area > 0, ovlp / area, 0.0)
    before = len(gdf)
    gdf    = gdf[(ovlp <= tol_m2) | (gdf["prev_ovlp_pct"] <= max_pct)].copy()
    print(f"  Eliminados por solape: {before - len(gdf)}")
    return gdf


def convert_numeric(gdf, cols):
    for c in cols:
        if c in gdf.columns:
            gdf[c] = pd.to_numeric(gdf[c], errors="coerce").fillna(0)
    return gdf


def valid_ecorregion_mask(gdf: gpd.GeoDataFrame) -> pd.Series:
    """False para ecorregiones invalidas o sin_nombre (fuera de eco raster)."""
    name = gdf.get("eco_dom_name", pd.Series("", index=gdf.index)).astype(str).str.strip()
    eid = pd.to_numeric(gdf.get("eco_dom_id", -9999), errors="coerce").fillna(-9999)
    return name.ne("sin_nombre") & name.ne("") & name.ne("nan") & (eid > 0)


def select_top(df, group_cols, n, sample_type, dim_t, dim_s,
               score_col="score", tier=2):
    """Selecciona top N por grupo, asignando tipo y tier."""
    if df.empty:
        return pd.DataFrame()
    out = (df.sort_values(score_col, ascending=False)
             .groupby(group_cols, group_keys=False)
             .head(n)
             .copy())
    out["sample_type"]  = sample_type
    out["dim_temporal"] = dim_t
    out["dim_espacial"] = dim_s
    out["review_tier"]  = tier
    return out


def without_used_ids(
    df: pd.DataFrame,
    used_ids: set,
    spatial_tracker: SpatialSelectionTracker | None = None,
) -> pd.DataFrame:
    if df.empty:
        return df
    if used_ids:
        df = df[~df["grid_id"].isin(used_ids)].copy()
    if spatial_tracker is not None:
        df = spatial_tracker.filter(df)
    return df


def pick_type(pool: pd.DataFrame, used_ids: set, *, group_cols, n_per_group,
              sample_type, dim_t, dim_s, score_col, tier, max_n,
              anual_min_stab_yrs: int | None = None,
              auto_tier_mask=None,
              year_counts: dict[int, int] | None = None,
              spatial_tracker: SpatialSelectionTracker | None = None,
              ) -> tuple[pd.DataFrame, set]:
    """Selecciona un tipo y reserva grid_id + geometria para evitar solapes."""
    pool = without_used_ids(pool, used_ids, spatial_tracker)
    if pool.empty:
        return pd.DataFrame(), used_ids

    sel = select_top(
        pool, group_cols, n_per_group, sample_type, dim_t, dim_s,
        score_col=score_col, tier=tier,
    )
    if anual_min_stab_yrs is not None:
        sel = assign_anual_metadata(sel, anual_min_stab_yrs, year_counts)
    else:
        sel["ref_period"] = ""
        sel["ref_year"]   = -9999
        sel["ref_sensor"] = ""

    if auto_tier_mask is not None and not sel.empty:
        sel.loc[auto_tier_mask(sel), "review_tier"] = 0

    sel = sel.head(max_n)
    if sel.empty:
        return sel, used_ids

    sel = spatial_dedupe_rows(sel, spatial_tracker, max_n)
    if sel.empty:
        return sel, used_ids

    used_ids = used_ids | set(sel["grid_id"].tolist())
    return sel, used_ids


def achap_present(row) -> bool:
    return class_present(
        row,
        ACHAP_MODE_ID,
        min_pct=MIN_RARE_PCT,
        min_period_pct=MIN_RARE_PERIOD_PCT,
    )


def achap_presence_strength(row) -> float:
    return class_presence_strength(row, ACHAP_MODE_ID)


def infer_sample_type_for_rare(row) -> tuple[str, str, str]:
    """Asigna el tipo v1 mas adecuado a un rectangulo con clase critica."""
    gm = str(row.get("grid_mode", "mixto"))
    is_hom = gm == "homogeneo"
    tr = float(row.get("transition_pct", 0) or 0)
    n_mode = int(row.get("n_mode_classes", 0) or 0)
    mode_pct = float(row.get("lulc_mode_pct", 0) or 0)
    shannon = float(row.get("shannon_idx", 0) or 0)
    max_run = float(row.get("max_stab_run", 0) or 0)

    if tr >= T_H_MIN_TR_PCT:
        if (n_mode >= T_S_MIN_N_MODE and mode_pct < T_S_MAX_MODE_PCT):
            return "transicion_simple_media", "transicion", "simple_media"
        return "transicion_homogenea", "transicion", "homogenea"

    best_p = get_best_period(row, 1)
    if best_p is not None:
        n_stb = float(row.get(f"n_stb_{best_p}", 0) or 0)
        if is_hom and n_stb >= A_H_MIN_STAB_YRS:
            return "anual_homogenea", "anual", "homogenea"
        if n_stb >= A_S_MIN_STAB_YRS:
            return "anual_simple_media", "anual", "simple_media"

    if (is_hom and max_run >= E_H_MIN_STAB_RUN
            and mode_pct >= E_H_MIN_MODE_PCT and shannon <= E_H_MAX_SHANNON):
        return "estable_homogenea", "estable", "homogenea"
    return "estable_simple_media", "estable", "simple_media"


def assign_rare_metadata(
    df: pd.DataFrame,
    class_id: int,
    class_name: str,
    review_tier: int = 1,
) -> pd.DataFrame:
    """Marca clase rara y asigna tipo v1 segun firma temporal/espacial."""
    if df.empty:
        return df
    df = df.copy()
    types, dims_t, dims_s = [], [], []
    for _, row in df.iterrows():
        st, dt, ds = infer_sample_type_for_rare(row)
        types.append(st)
        dims_t.append(dt)
        dims_s.append(ds)
    df["sample_type"]        = types
    df["dim_temporal"]       = dims_t
    df["dim_espacial"]       = dims_s
    df["target_rare_class"]  = class_name
    df["target_rare_class_id"] = class_id
    df["rare_presence_pct"] = class_presence_strength_series(df, class_id)
    if class_id == ACHAP_MODE_ID:
        df["achap_presence_pct"] = df["rare_presence_pct"]
    if class_id == BOSQUE_NORTE_MODE_ID:
        df["north_forest_presence_pct"] = df["rare_presence_pct"]
        df["target_rare_class_source"] = NORTH_FOREST_PRESENCE_COL
    df["review_tier"] = review_tier
    return df


def pick_rare_class(
    pool: pd.DataFrame,
    used_ids: set,
    *,
    class_id: int,
    class_name: str,
    score_col: str,
    n_per_group: int,
    max_n: int,
    min_period_pct: float = MIN_RARE_PERIOD_PCT,
    min_pct: float = MIN_RARE_PCT,
    review_tier: int = 1,
    year_counts: dict[int, int] | None = None,
    spatial_tracker: SpatialSelectionTracker | None = None,
) -> tuple[pd.DataFrame, set]:
    """Selecciona rectangulos con presencia de una clase critica dedicada."""
    pool = without_used_ids(pool, used_ids, spatial_tracker)
    if pool.empty:
        return pd.DataFrame(), used_ids

    pool = pool[
        class_present_mask(
            pool,
            class_id,
            min_pct=min_pct,
            min_period_pct=min_period_pct,
        )
    ].copy()
    if pool.empty:
        return pd.DataFrame(), used_ids

    pool = pool.copy()
    if class_id in (ARENA_MODE_ID, SALAR_MODE_ID) and "eco_dom_id" in pool.columns:
        pool["_eco_bonus"] = pool["eco_dom_id"].isin(DESERT_ECO_IDS).astype(float)
        pool = pool.sort_values([score_col, "_eco_bonus"], ascending=[False, False])
    elif class_id == BOSQUE_NORTE_MODE_ID:
        pool["_nfor"] = class_presence_strength_series(pool, class_id)
        pool = pool.sort_values(["_nfor", score_col], ascending=[False, False])
    else:
        pool = pool.sort_values(score_col, ascending=False)

    sel = (
        pool.groupby("eco_dom_id", group_keys=False)
            .head(n_per_group)
            .head(max_n)
            .copy()
    )
    if len(sel) < max_n:
        extra = pool[~pool["grid_id"].isin(sel["grid_id"])].head(max_n - len(sel))
        if not extra.empty:
            sel = pd.concat([sel, extra], ignore_index=True).head(max_n)
    if sel.empty:
        return sel, used_ids

    sel = assign_rare_metadata(sel, class_id, class_name, review_tier=review_tier)
    kept = []
    for _, row in sel.iterrows():
        if row["dim_temporal"] == "anual":
            min_yrs = (A_H_MIN_STAB_YRS if row["dim_espacial"] == "homogenea"
                       else A_S_MIN_STAB_YRS)
            one = assign_anual_metadata(pd.DataFrame([row]), min_yrs, year_counts)
            if not one.empty:
                kept.append(one)
        else:
            row = row.copy()
            row["ref_period"] = ""
            row["ref_year"]   = -9999
            row["ref_sensor"] = ""
            kept.append(pd.DataFrame([row]))

    sel = pd.concat(kept, ignore_index=True).head(max_n) if kept else pd.DataFrame()
    if sel.empty:
        return sel, used_ids

    sel = spatial_dedupe_rows(sel, spatial_tracker, max_n)
    if sel.empty:
        return sel, used_ids

    used_ids = used_ids | set(sel["grid_id"].tolist())
    return sel, used_ids


# ══════════════════════════════════════════════════════════════
# 4.b FUNCIONES PARA MUESTRAS ANUALES
# ══════════════════════════════════════════════════════════════

def get_best_period(row, min_stab_yrs: int) -> str | None:
    """
    Primer periodo (P4→P1) con n_stb >= umbral.
    Usado para elegibilidad; ref_year puede provenir de cualquier periodo valido.
    """
    for pn in ANUAL_PERIOD_PREF:
        n_stb = float(row.get(f"n_stb_{pn}", 0) or 0)
        if n_stb >= min_stab_yrs:
            return pn
    return None


def qualifying_periods(row, min_stab_yrs: int) -> list[str]:
    """Periodos P1-P4 donde el rectangulo cumple n_stb >= umbral."""
    return [
        pn for pn in ANUAL_PERIOD_PREF
        if float(row.get(f"n_stb_{pn}", 0) or 0) >= min_stab_yrs
    ]


def period_for_year(year: int) -> str | None:
    """Mapea un ano al periodo Landsat que lo contiene."""
    for pn, (start, end, _) in PERIOD_YEARS.items():
        if start <= year <= end:
            return pn
    return None


def max_mode_pct_in_qualifying(row, min_stab_yrs: int) -> float:
    """Mayor md_pct entre periodos que cumplen estabilidad minima."""
    periods = qualifying_periods(row, min_stab_yrs)
    if not periods:
        return 0.0
    return max(float(row.get(f"md_pct_{pn}", 0) or 0) for pn in periods)


def list_stable_years(row, period: str) -> list[int]:
    """Anos estables disponibles en el periodo (stb_yrs_Px)."""
    yrs_str = str(row.get(f"stb_yrs_{period}", "") or "")
    if not yrs_str.strip() or yrs_str == "nan":
        return []
    return sorted(int(y) for y in yrs_str.split(",") if y.strip().isdigit())


def list_all_stable_years(row, min_stab_yrs: int) -> list[tuple[int, str]]:
    """Todos los (anio, periodo) estables en periodos que cumplen umbral."""
    out: list[tuple[int, str]] = []
    seen: set[int] = set()
    for pn in qualifying_periods(row, min_stab_yrs):
        for y in list_stable_years(row, pn):
            if y not in seen:
                out.append((y, pn))
                seen.add(y)
    return out


def pick_balanced_ref(
    row,
    min_stab_yrs: int,
    year_counts: dict[int, int] | None = None,
) -> tuple[str | None, int]:
    """
    Elige ref_period y ref_year usando todos los anos estables 1999-2024
    (P1-P4), balanceando uso global entre muestras anuales.
    """
    candidates = list_all_stable_years(row, min_stab_yrs)
    if not candidates:
        return None, -9999

    years = [y for y, _ in candidates]
    if not year_counts:
        yr = max(years)
        return period_for_year(yr), yr

    min_use = min(year_counts.get(y, 0) for y in years)
    year_cands = sorted(y for y in years if year_counts.get(y, 0) == min_use)
    if len(year_cands) == 1:
        yr = year_cands[0]
    else:
        grid_id = str(row.get("grid_id", ""))
        idx = sum(ord(c) for c in grid_id) % len(year_cands)
        yr = year_cands[idx]

    pn = period_for_year(yr)
    return pn, yr


def get_ref_year(
    row,
    period: str,
    year_counts: dict[int, int] | None = None,
) -> int:
    """
    Elige ano de referencia dentro de un periodo concreto (uso puntual).
    Para muestras anuales preferir pick_balanced_ref() sobre todos los periodos.
    """
    years = list_stable_years(row, period)
    if not years:
        return -9999
    if not year_counts:
        return max(years)

    min_use = min(year_counts.get(y, 0) for y in years)
    candidates = [y for y in years if year_counts.get(y, 0) == min_use]
    if len(candidates) == 1:
        return candidates[0]
    grid_id = str(row.get("grid_id", ""))
    idx = sum(ord(c) for c in grid_id) % len(candidates)
    return candidates[idx]


def assign_anual_metadata(
    df: pd.DataFrame,
    min_stab_yrs: int,
    year_counts: dict[int, int] | None = None,
) -> pd.DataFrame:
    """
    Asigna ref_period, ref_year y ref_sensor a cada rectangulo anual.
    ref_year se elige entre anos estables de P1-P4 (1999-2024), no solo P4.
    """
    if year_counts is None:
        year_counts = {}

    df = df.copy()
    ref_periods, ref_years, ref_sensors = [], [], []

    for _, row in df.iterrows():
        pn, yr = pick_balanced_ref(row, min_stab_yrs, year_counts)
        if pn is None or yr <= 0:
            ref_periods.append(None)
            ref_years.append(-9999)
            ref_sensors.append(None)
        else:
            ref_periods.append(pn)
            ref_years.append(yr)
            ref_sensors.append(SENSOR_MAP.get(pn, ""))
            year_counts[yr] = year_counts.get(yr, 0) + 1

    df["ref_period"] = ref_periods
    df["ref_year"]   = ref_years
    df["ref_sensor"] = ref_sensors

    df = df[df["ref_period"].notna() & (df["ref_year"] > 0)].copy()
    return df


def min_stab_yrs_for_row(row: pd.Series) -> int:
    if str(row.get("dim_espacial", "")) == "homogenea":
        return A_H_MIN_STAB_YRS
    return A_S_MIN_STAB_YRS


def try_promote_to_stable(row: pd.Series) -> tuple[str, str, str] | None:
    gm = str(row.get("grid_mode", "mixto"))
    tr = float(row.get("transition_pct", 0) or 0)
    run = float(row.get("max_stab_run", 0) or 0)
    mode_pct = float(row.get("lulc_mode_pct", 0) or 0)
    shannon = float(row.get("shannon_idx", 0) or 0)
    n_mode = int(row.get("n_mode_classes", 0) or 0)

    if (
        gm == "homogeneo"
        and run >= E_H_MIN_STAB_RUN
        and mode_pct >= E_H_MIN_MODE_PCT
        and tr <= E_H_MAX_TR_PCT
        and shannon <= E_H_MAX_SHANNON
    ):
        return "estable_homogenea", "estable", "homogenea"
    if (
        run >= E_S_MIN_STAB_RUN
        and E_S_MIN_MODE_PCT <= mode_pct < E_S_MAX_MODE_PCT
        and E_S_MIN_N_MODE <= n_mode <= E_S_MAX_N_MODE
        and tr <= E_S_MAX_TR_PCT
    ):
        return "estable_simple_media", "estable", "simple_media"
    return None


def finalize_temporal_labels(
    df: pd.DataFrame,
    year_counts: dict[int, int] | None = None,
) -> pd.DataFrame:
    """
    Repara ref_year en muestras anuales tras rellenos; promueve/recategoriza
    las que no pueden tener ano de referencia valido.
    """
    if df.empty:
        return df
    if year_counts is None:
        year_counts = {}

    out = df.copy()
    promo = (
        (out["sample_type"] == "anual_homogenea")
        & (out["max_stab_run"] >= E_H_MIN_STAB_RUN)
        & (out["lulc_mode_pct"] >= E_H_MIN_MODE_PCT)
        & (out["transition_pct"] <= E_H_MAX_TR_PCT)
        & (out["stable_yr_pct"] >= E_H_MIN_STAB_PCT)
    )
    out.loc[promo, "sample_type"] = "estable_homogenea"
    out.loc[promo, "dim_temporal"] = "estable"
    out.loc[promo, "dim_espacial"] = "homogenea"
    out.loc[promo, "ref_period"] = ""
    out.loc[promo, "ref_year"] = -9999
    out.loc[promo, "ref_sensor"] = ""

    anual_mask = out["dim_temporal"] == "anual"
    for idx in out.index[anual_mask]:
        row = out.loc[idx]
        min_yrs = min_stab_yrs_for_row(row)
        assigned = False
        for try_yrs in range(min_yrs, 0, -1):
            pn, yr = pick_balanced_ref(row, try_yrs, year_counts)
            if pn and yr > 0:
                out.at[idx, "ref_period"] = pn
                out.at[idx, "ref_year"] = yr
                out.at[idx, "ref_sensor"] = SENSOR_MAP.get(pn, "")
                year_counts[yr] = year_counts.get(yr, 0) + 1
                assigned = True
                break
        if assigned:
            continue
        stable = try_promote_to_stable(row)
        if stable:
            st, dt, ds = stable
            out.at[idx, "sample_type"] = st
            out.at[idx, "dim_temporal"] = dt
            out.at[idx, "dim_espacial"] = ds
            out.at[idx, "ref_period"] = ""
            out.at[idx, "ref_year"] = -9999
            out.at[idx, "ref_sensor"] = ""

    ref_year = pd.to_numeric(out.get("ref_year", -9999), errors="coerce").fillna(-9999)
    drop_mask = (out["dim_temporal"] == "anual") & (ref_year <= 0)
    if drop_mask.any():
        out = out[~drop_mask].copy()
    return out


def annotate_selection_profile(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    n_est = int((out["dim_temporal"] == "estable").sum())
    n = len(out)
    if n == 0:
        out["selection_profile"] = "vacio"
    elif n_est < max(25, int(0.08 * n)):
        out["selection_profile"] = "dominado_anual_transicion"
    else:
        out["selection_profile"] = "balanceado"
    if "sample_role" not in out.columns:
        out["sample_role"] = "primaria"
    else:
        out["sample_role"] = out["sample_role"].fillna("primaria")
    return out


# ══════════════════════════════════════════════════════════════
# 5. CARGA Y PREPARACIÓN
# ══════════════════════════════════════════════════════════════

def load_and_prepare(path: Path, mode_label: str) -> gpd.GeoDataFrame:
    df = read_vector(path)
    print(f"  {mode_label}: {len(df)} rectangulos  (CRS: {df.crs})")
    crs = infer_crs(path)
    if df.crs is None:
        df = df.set_crs(crs)
    elif crs and df.crs.to_string() != crs:
        df = df.to_crs(crs)
    df = normalize_fields(df)
    df = ensure_fields(df)
    if "grid_mode" not in df.columns:
        df["grid_mode"] = mode_label
    return df

print("\n====== CARGA ======")
layers = []
if FILE_HOMOGENEO:
    layers.append(load_and_prepare(FILE_HOMOGENEO, "homogeneo"))
if FILE_MIXTO:
    layers.append(load_and_prepare(FILE_MIXTO, "mixto"))

gdf = gpd.GeoDataFrame(
    pd.concat(layers, ignore_index=True),
    geometry="geometry", crs=layers[0].crs
)
print(f"  Total combinado: {len(gdf)}")
print(f"  Modos: {gdf['grid_mode'].value_counts().to_dict()}")

def matches_utm_scale(path: Path, ref_paths: list[Path | None]) -> bool:
    """True si el archivo previo corresponde al mismo huso UTM y escala."""
    ref_names = " ".join(p.stem.upper() for p in ref_paths if p)
    utm = "UTM18" if "UTM18" in ref_names else "UTM19" if "UTM19" in ref_names else ""
    scale = (
        "SCALE300" if "SCALE300" in ref_names
        else "SCALE900" if "SCALE900" in ref_names
        else ""
    )
    stem = path.stem.upper()
    if utm and utm not in stem:
        return False
    if scale and scale not in stem:
        return False
    return True


def infer_ref_utm_scale(ref_paths: list[Path | None]) -> tuple[str, str]:
    ref_names = " ".join(p.stem.upper() for p in ref_paths if p)
    utm = "UTM18" if "UTM18" in ref_names else "UTM19" if "UTM19" in ref_names else ""
    scale = (
        "scale300" if "SCALE300" in ref_names
        else "scale900" if "SCALE900" in ref_names
        else ""
    )
    return utm, scale


def is_selection_output(path: Path, base_name: str) -> bool:
    stem = path.stem.upper()
    if stem == f"SELECCION_{base_name.upper()}":
        return True
    return "_TAXONOMIA" in stem or stem.startswith("RESERVAS_")


def discover_same_zone_previous(
    output_dir: Path,
    ref_paths: list[Path | None],
    base_name: str,
) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for pattern in ("seleccion_grilla_ssl4eo_*.gpkg", "seleccion_grilla_ssl4eo_*.geojson"):
        for path in sorted(output_dir.glob(pattern)):
            resolved = path.resolve()
            if resolved in seen or is_selection_output(path, base_name):
                continue
            if not matches_utm_scale(path, ref_paths):
                continue
            seen.add(resolved)
            files.append(path)
    return files


def discover_cross_zone_previous(
    output_dir: Path,
    ref_paths: list[Path | None],
    base_name: str,
) -> list[Path]:
    utm, scale = infer_ref_utm_scale(ref_paths)
    if not utm or not scale:
        return []
    other = "UTM19" if utm == "UTM18" else "UTM18"
    files: list[Path] = []
    for ext in (".geojson", ".gpkg"):
        path = output_dir / f"seleccion_grilla_ssl4eo_muestras_{other}_{scale}{ext}"
        if path.exists() and not is_selection_output(path, base_name):
            files.append(path)
    return files


def seed_spatial_tracker_from_files(
    tracker: SpatialSelectionTracker,
    files: list[Path],
    crs,
) -> None:
    if not files:
        return
    print("\n-- Geometrias previas (tracker espacial) --")
    for path in files:
        if not path.exists():
            continue
        layer = read_vector(path)
        if layer.crs != crs:
            layer = layer.to_crs(crs)
        before = 0 if tracker._empty() else len(tracker._selected)
        tracker.register(layer)
        after = 0 if tracker._empty() else len(tracker._selected)
        print(f"  {path.name}: +{after - before} geometrias")


prev_files: list[Path] = []
if AUTO_PREVIOUS:
    prev_files.extend(discover_same_zone_previous(output_dir, [FILE_HOMOGENEO, FILE_MIXTO], base_name))
cross_zone_files: list[Path] = []
if CROSS_ZONE_PREVIOUS:
    cross_zone_files = discover_cross_zone_previous(
        output_dir, [FILE_HOMOGENEO, FILE_MIXTO], base_name
    )
for f in manual_previous:
    if f not in prev_files:
        prev_files.append(f)

overlap_files = list(prev_files)
for f in cross_zone_files:
    if f not in overlap_files:
        overlap_files.append(f)

if cross_zone_files:
    print("\n-- Seleccion del otro huso UTM (anti-solape frontera) --")
    for f in cross_zone_files:
        print(f"  {f.name}")

gdf = exclude_overlaps(gdf, overlap_files, gdf.crs, MAX_OVERLAP, OVERLAP_TOLERANCE_M2)

# Convertir numéricos
num_cols = [
    "valid_area_pct","eco_dom_pct","noobs_pct","mgrs_dom_pct",
    "lulc_mode_pct","n_mode_classes","transition_pct","stable_mode_pct",
    "critical_pct","transversal_pct","north_forest_pct","achaparrado_pct",
    "shannon_idx","conf_risk_pct","n_stable_years","stable_yr_pct",
    "max_stab_run","stab_run_start","stab_run_end","lulc_last_pct",
    "lulc_mode_id","lulc_last_id",
] + [f"md_pct_{p}" for p in ["P1","P2","P3","P4"]] \
  + [f"md_id_{p}"  for p in ["P1","P2","P3","P4"]] \
  + [f"n_stb_{p}"  for p in ["P1","P2","P3","P4"]] \
  + [f"stb_p_{p}"  for p in ["P1","P2","P3","P4"]]

gdf = convert_numeric(gdf, num_cols)

gdf["shannon_norm"]  = (gdf["shannon_idx"] / LN_MAX_CLASSES).clip(0, 1)
gdf["lulc_mode_id"]  = gdf.get("lulc_mode_id", pd.Series([-9999]*len(gdf)))

eco_ok = valid_ecorregion_mask(gdf)
n_eco_bad = int((~eco_ok).sum())
if n_eco_bad:
    print(f"\n====== FILTRO ECORREGION ======")
    print(f"  Excluidos sin_nombre/invalido: {n_eco_bad}  -> disponibles: {int(eco_ok.sum())}")
gdf = gdf[eco_ok].copy()
if gdf.empty:
    raise ValueError("Sin rectangulos tras excluir ecorregion sin_nombre.")


# ══════════════════════════════════════════════════════════════
# 6. FILTRO BASE DE CALIDAD
# ══════════════════════════════════════════════════════════════

cands = gdf[
    (gdf["valid_area_pct"] >= MIN_VALID_AREA_PCT)
    & (gdf["eco_dom_pct"]  >= MIN_ECO_DOM_PCT)
    & (gdf["noobs_pct"]    <= MAX_NOOBS_PCT)
].copy()

cands_rare_relaxed = gdf[
    (gdf["valid_area_pct"] >= RARE_MIN_VALID_AREA_PCT)
    & (gdf["eco_dom_pct"]  >= RARE_MIN_ECO_DOM_PCT)
    & (gdf["noobs_pct"]    <= RARE_MAX_NOOBS_PCT)
].copy()

gdf = annotate_transversal_modal(gdf)
cands = annotate_transversal_modal(cands)
cands_rare_relaxed = annotate_transversal_modal(cands_rare_relaxed)

cands_all = cands.copy()
cands_general = cands[cands["general_model_ok"]].copy()

if USE_SCALE300_PROFILE:
    cands_all = block_desert_otra_candidates(cands_all)
    cands_general = block_desert_otra_candidates(cands_general)
    print("  Bloqueo desierto desnudo (E1-E3 + Otra_sin_vegetacion) salvo exenciones.")

cands = cands_general

print(f"\n====== FILTRO CALIDAD ======")
print(f"  Disponibles: {len(gdf)} -> validos: {len(cands_all)}")
print(
    f"  Relajados arena/salar: {len(cands_rare_relaxed)}  "
    f"(val>={RARE_MIN_VALID_AREA_PCT}%  eco>={RARE_MIN_ECO_DOM_PCT}%  "
    f"noobs<={RARE_MAX_NOOBS_PCT}%)"
)
n_modal_tr = int(cands_all["modal_transversal"].sum())
print(
    f"  Modal transversal (excl. modelo general): {n_modal_tr}  "
    f"-> candidatos general: {len(cands_general)}"
)
if n_modal_tr and "lulc_mode_id" in cands_all.columns:
    excl = cands_all[cands_all["modal_transversal"]]
    top = (
        excl.groupby(["lulc_mode_id", "lulc_mode_name"], dropna=False)
        .size()
        .sort_values(ascending=False)
        .head(8)
    )
    print(f"  Top modal excluida:\n{top.to_string()}")

if len(cands) == 0:
    raise ValueError("Sin candidatos para modelo general tras excluir modal transversal.")


# ══════════════════════════════════════════════════════════════
# 7. SCORES POR TIPO
# ══════════════════════════════════════════════════════════════

base = (cands["valid_area_pct"] / 100) * 2 + (cands["eco_dom_pct"] / 100) * 1

# 1 — Estable homogénea: racha larga + pureza + estabilidad global
cands["sc_e_h"] = (
    (cands["max_stab_run"]    / N_YEARS_PERIOD) * 5
    + (cands["stable_yr_pct"] / 100)             * 4
    + (cands["lulc_mode_pct"] / 100)             * 3
    + (1 - cands["shannon_norm"])                * 2
    + base
)

# 2 — Estable simple-media: racha + diversidad equilibrada
cands["sc_e_s"] = (
    (cands["max_stab_run"]        / N_YEARS_PERIOD) * 4
    + (cands["stable_yr_pct"]     / 100)             * 3
    + (cands["lulc_mode_pct"]     / 100)             * 3
    + (cands["n_mode_classes"].clip(2,4) / 4)        * 2
    + base
)

# 4 y 5 — Anuales: score del mejor periodo con estabilidad (cualquier P1-P4)
def anual_score(row, mode_pct_col):
    best_score = 0.0
    for pn in ANUAL_PERIOD_PREF:
        n_stb = float(row.get(f"n_stb_{pn}", 0) or 0)
        if n_stb < 1:
            continue
        n_yrs   = PERIOD_YEARS[pn][2]
        stb_p   = float(row.get(f"stb_p_{pn}", 0) or 0)
        md_pct  = float(row.get(f"md_pct_{pn}", 0) or 0)
        val_pct = float(row.get("valid_area_pct", 0) or 0)
        eco_pct = float(row.get("eco_dom_pct", 0) or 0)
        score = ((n_stb / n_yrs) * 5 + (stb_p / 100) * 4
                 + (md_pct / 100) * 3
                 + (val_pct / 100) * 2 + (eco_pct / 100) * 1)
        best_score = max(best_score, score)
    return best_score

cands["sc_a_h"] = cands.apply(lambda r: anual_score(r, "lulc_mode_pct"), axis=1)
cands["sc_a_s"] = cands.apply(lambda r: anual_score(r, "lulc_mode_pct"), axis=1)

# 7 — Transición homogénea: alta transición + al menos un extremo puro
best_purity = cands[["lulc_mode_pct","lulc_last_pct"]].max(axis=1)
cands["sc_t_h"] = (
    (cands["transition_pct"] / 100) * 5
    + (best_purity / 100)            * 4
    + (cands["critical_pct"] / 100)  * 2
    + base
)

# 8 — Transición simple-media: alta transición + diversidad + conf_risk
cands["sc_t_s"] = (
    (cands["transition_pct"]          / 100) * 5
    + (cands["n_mode_classes"].clip(2,4) / 4)* 3
    + (cands["conf_risk_pct"]          / 100)* 3
    + (cands["critical_pct"]           / 100)* 2
    + base
)

def rare_class_score_df(df: pd.DataFrame, class_id: int, base_score: pd.Series) -> pd.Series:
    strength = class_presence_strength_series(df, class_id) / 100 * 5
    score = strength + (df["critical_pct"] / 100) * 2 + base_score
    if class_id in (ARENA_MODE_ID, SALAR_MODE_ID) and "eco_dom_id" in df.columns:
        score = score + df["eco_dom_id"].isin(DESERT_ECO_IDS).astype(float) * 1.5
    return score


base_relaxed = (
    (cands_rare_relaxed["valid_area_pct"] / 100) * 2
    + (cands_rare_relaxed["eco_dom_pct"] / 100) * 1
)

cands_rare_relaxed["sc_arena"] = rare_class_score_df(
    cands_rare_relaxed, ARENA_MODE_ID, base_relaxed
)
cands_rare_relaxed["sc_salar"] = rare_class_score_df(
    cands_rare_relaxed, SALAR_MODE_ID, base_relaxed
)
base_all = (
    (cands_all["valid_area_pct"] / 100) * 2
    + (cands_all["eco_dom_pct"] / 100) * 1
)
cands_all["sc_achap"] = rare_class_score_df(cands_all, ACHAP_MODE_ID, base_all)
cands_all["sc_bosque_norte"] = rare_class_score_df(
    cands_all, BOSQUE_NORTE_MODE_ID, base_all
)
cands_all["sc_pastizal"] = rare_class_score_df(cands_all, PASTIZAL_MODE_ID, base_all)


# ══════════════════════════════════════════════════════════════
# 8. DEFINICIÓN DE POOLS
# ══════════════════════════════════════════════════════════════

print("\n====== POOLS POR TIPO ======")
# Separar candidatos por modo de grilla
gm = cands.get("grid_mode", pd.Series("mixto", index=cands.index))
cands_hom = cands[gm == "homogeneo"].copy()
cands_mix = cands[gm != "homogeneo"].copy()
if len(cands_hom) == 0: cands_hom = cands.copy()
if len(cands_mix) == 0: cands_mix = cands.copy()
if USE_SCALE300_PROFILE:
    cands_hom = block_desert_otra_candidates(cands_hom)
    cands_mix = block_desert_otra_candidates(cands_mix)
print(f"  Candidatos homogeneo: {len(cands_hom)}  mixto: {len(cands_mix)}")

def build_rare_pool(
    df: pd.DataFrame,
    class_id: int,
    *,
    min_period_pct: float,
    min_pct: float = MIN_RARE_PCT,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    mask = class_present_mask(
        df,
        class_id,
        min_pct=min_pct,
        min_period_pct=min_period_pct,
    )
    return df[mask].copy()


pool_arena = build_rare_pool(
    cands_rare_relaxed,
    ARENA_MODE_ID,
    min_period_pct=MIN_ARENA_SALAR_PERIOD_PCT,
    min_pct=MIN_ARENA_SALAR_PCT,
)
pool_salar = build_rare_pool(
    cands_rare_relaxed,
    SALAR_MODE_ID,
    min_period_pct=MIN_ARENA_SALAR_PERIOD_PCT,
    min_pct=MIN_ARENA_SALAR_PCT,
)
pool_achap = cands_all[
    class_present_mask(
        cands_all,
        ACHAP_MODE_ID,
        min_pct=MIN_RARE_PCT,
        min_period_pct=MIN_RARE_PERIOD_PCT,
    )
].copy()
pool_bosque_norte = cands_all[
    class_present_mask(
        cands_all,
        BOSQUE_NORTE_MODE_ID,
        min_pct=MIN_RARE_PCT,
        min_period_pct=MIN_RARE_PERIOD_PCT,
    )
].copy()
pool_pastizal = cands_all[
    class_present_mask(
        cands_all,
        PASTIZAL_MODE_ID,
        min_pct=MIN_RARE_PCT,
        min_period_pct=MIN_RARE_PERIOD_PCT,
    )
].copy()
print(
    f"  0. presencia_arena_playa:  {len(pool_arena):4d}  "
    f"(relajado  id={ARENA_MODE_ID}  periodo>={MIN_ARENA_SALAR_PERIOD_PCT}%)"
)
print(
    f"  0. presencia_salar:        {len(pool_salar):4d}  "
    f"(relajado  id={SALAR_MODE_ID}  periodo>={MIN_ARENA_SALAR_PERIOD_PCT}%)"
)
print(
    f"  0. presencia_achaparrado:  {len(pool_achap):4d}  "
    f"(estricto  id={ACHAP_MODE_ID}  periodo>={MIN_RARE_PERIOD_PCT}%)"
)
print(
    f"  0. presencia_bosque_norte: {len(pool_bosque_norte):4d}  "
    f"(ID 3 Otra_Formacion_boscosa  north_forest_pct>={MIN_RARE_PCT}%)"
)
print(
    f"  0. presencia_pastizal:     {len(pool_pastizal):4d}  "
    f"(id={PASTIZAL_MODE_ID}  max={MAX_PASTIZAL})"
)

# 1 ── Estable homogénea
pool_e_h = cands_hom[
    (cands_hom["max_stab_run"]    >= E_H_MIN_STAB_RUN)
    & (cands_hom["transition_pct"]<= E_H_MAX_TR_PCT)
    & (cands_hom["stable_yr_pct"] >= E_H_MIN_STAB_PCT)
    & (cands_hom["lulc_mode_pct"] >= E_H_MIN_MODE_PCT)
    & (cands_hom["shannon_idx"]   <= E_H_MAX_SHANNON)
].copy()
print(f"  1. estable_homogenea:      {len(pool_e_h):4d}  "
      f"(run>={E_H_MIN_STAB_RUN}  mode>={E_H_MIN_MODE_PCT}%  sh<={E_H_MAX_SHANNON})")

# 2 ── Estable simple-media
pool_e_s = cands_mix[
    (cands_mix["max_stab_run"]      >= E_S_MIN_STAB_RUN)
    & (cands_mix["transition_pct"]  <= E_S_MAX_TR_PCT)
    & (cands_mix["lulc_mode_pct"]   >= E_S_MIN_MODE_PCT)
    & (cands_mix["lulc_mode_pct"]   <  E_S_MAX_MODE_PCT)
    & (cands_mix["n_mode_classes"]  >= E_S_MIN_N_MODE)
    & (cands_mix["n_mode_classes"]  <= E_S_MAX_N_MODE)
].copy()
print(f"  2. estable_simple_media:   {len(pool_e_s):4d}  "
      f"(run>={E_S_MIN_STAB_RUN}  mode {E_S_MIN_MODE_PCT}-{E_S_MAX_MODE_PCT}%  n_mode {E_S_MIN_N_MODE}-{E_S_MAX_N_MODE})")

# 4 ── Anual homogénea
pool_a_h = cands_hom[
    cands_hom.apply(lambda r: get_best_period(r, A_H_MIN_STAB_YRS) is not None, axis=1)
    & cands_hom.apply(
        lambda r: max_mode_pct_in_qualifying(r, A_H_MIN_STAB_YRS) >= A_H_MIN_MODE_PCT,
        axis=1,
    )
].copy()
print(f"  4. anual_homogenea:        {len(pool_a_h):4d}  "
      f"(n_stb>={A_H_MIN_STAB_YRS}  mode>={A_H_MIN_MODE_PCT}%  cualquier P1-P4)")

# 5 ── Anual simple-media
pool_a_s = cands_mix[
    cands_mix.apply(lambda r: get_best_period(r, A_S_MIN_STAB_YRS) is not None, axis=1)
    & (cands_mix["lulc_mode_pct"] >= A_S_MIN_MODE_PCT)
    & (cands_mix["lulc_mode_pct"] <  A_S_MAX_MODE_PCT)
    & (cands_mix["n_mode_classes"]>= A_S_MIN_N_MODE)
    & (cands_mix["n_mode_classes"]<= A_S_MAX_N_MODE)
].copy()
print(f"  5. anual_simple_media:     {len(pool_a_s):4d}  "
      f"(n_stb>={A_S_MIN_STAB_YRS}  mode {A_S_MIN_MODE_PCT}-{A_S_MAX_MODE_PCT}%  cualquier P1-P4)")

# 7 ── Transición homogénea (relajada en E1-E5)
pool_t_h = cands_mix[
    arid_transition_mask(cands_mix, min_tr=T_H_MIN_TR_PCT, min_pure=T_H_MIN_PURE_PCT)
].copy()
print(f"  7. transicion_homogenea:   {len(pool_t_h):4d}  "
      f"(tr>={T_H_MIN_TR_PCT}%  aridas E1-E5 relajadas)")

# 8 ── Transición simple-media (relajada en E1-E5)
pool_t_s = cands_mix[
    arid_transition_mask(cands_mix, min_tr=T_S_MIN_TR_PCT, min_pure=T_H_MIN_PURE_PCT)
    & (cands_mix["n_mode_classes"]  >= T_S_MIN_N_MODE)
    & (cands_mix["n_mode_classes"]  <= T_S_MAX_N_MODE)
    & (cands_mix["lulc_mode_pct"]   >= T_S_MIN_MODE_PCT)
    & (cands_mix["lulc_mode_pct"]   <  T_S_MAX_MODE_PCT)
].copy()
print(f"  8. transicion_simple_media:{len(pool_t_s):4d}  "
      f"(tr>={T_S_MIN_TR_PCT}%  n_mode {T_S_MIN_N_MODE}-{T_S_MAX_N_MODE})")


# ══════════════════════════════════════════════════════════════
# 9. SELECCIÓN POR TIPO (EXCLUSIVA, TIPOS ESCASOS PRIMERO)
# ══════════════════════════════════════════════════════════════

used_ids: set = set()
spatial_tracker = SpatialSelectionTracker(gdf.crs, MAX_OVERLAP, OVERLAP_TOLERANCE_M2)
seed_spatial_tracker_from_files(spatial_tracker, overlap_files, gdf.crs)
parts: list[pd.DataFrame] = []

selection_specs = {
    "anual_simple_media": dict(
        pool_name="pool_a_s",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_A_S_PER_GROUP,
        sample_type="anual_simple_media",
        dim_t="anual", dim_s="simple_media",
        score_col="sc_a_s", tier=2, max_n=MAX_A_S,
        anual_min_stab_yrs=A_S_MIN_STAB_YRS,
    ),
    "transicion_simple_media": dict(
        pool_name="pool_t_s",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_T_S_PER_GROUP,
        sample_type="transicion_simple_media",
        dim_t="transicion", dim_s="simple_media",
        score_col="sc_t_s", tier=2, max_n=MAX_T_S,
    ),
    "transicion_homogenea": dict(
        pool_name="pool_t_h",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_T_H_PER_GROUP,
        sample_type="transicion_homogenea",
        dim_t="transicion", dim_s="homogenea",
        score_col="sc_t_h", tier=2, max_n=MAX_T_H,
    ),
    "anual_homogenea": dict(
        pool_name="pool_a_h",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_A_H_PER_GROUP,
        sample_type="anual_homogenea",
        dim_t="anual", dim_s="homogenea",
        score_col="sc_a_h", tier=1, max_n=MAX_A_H,
        anual_min_stab_yrs=A_H_MIN_STAB_YRS,
    ),
    "estable_simple_media": dict(
        pool_name="pool_e_s",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_E_S_PER_GROUP,
        sample_type="estable_simple_media",
        dim_t="estable", dim_s="simple_media",
        score_col="sc_e_s", tier=2, max_n=MAX_E_S,
    ),
    "estable_homogenea": dict(
        pool_name="pool_e_h",
        group_cols=["eco_dom_id", "lulc_mode_id"],
        n_per_group=N_E_H_PER_GROUP,
        sample_type="estable_homogenea",
        dim_t="estable", dim_s="homogenea",
        score_col="sc_e_h", tier=1, max_n=MAX_E_H,
        auto_tier_mask=lambda df: (
            (df["lulc_mode_pct"] >= (90 if UTM_ZONE == 18 else 95))
            & (df["max_stab_run"] >= (4 if UTM_ZONE == 18 else 5))
        ),
    ),
}

pool_lookup = {
    "pool_e_h": pool_e_h,
    "pool_e_s": pool_e_s,
    "pool_a_h": pool_a_h,
    "pool_a_s": pool_a_s,
    "pool_t_h": pool_t_h,
    "pool_t_s": pool_t_s,
}

rare_pool_lookup = {
    "presencia_arena_playa_duna": pool_arena,
    "presencia_salar": pool_salar,
    "presencia_achaparrado": pool_achap,
    "presencia_bosque_norte": pool_bosque_norte,
    "presencia_pastizal": pool_pastizal,
}

print("\n====== SELECCIÓN EXCLUSIVA ======")
anual_year_counts: dict[int, int] = defaultdict(int)
for type_name in SELECTION_ORDER:
    if type_name in RARE_CLASS_SPECS:
        spec = RARE_CLASS_SPECS[type_name]
        picked, used_ids = pick_rare_class(
            rare_pool_lookup[type_name],
            used_ids,
            class_id=spec["class_id"],
            class_name=spec["class_name"],
            score_col=spec["score_col"],
            n_per_group=spec["n_per_group"],
            max_n=spec["max_n"],
            min_period_pct=spec.get("min_period_pct", MIN_RARE_PERIOD_PCT),
            min_pct=spec.get("min_pct", MIN_RARE_PCT),
            review_tier=spec.get("review_tier", 1),
            year_counts=anual_year_counts,
            spatial_tracker=spatial_tracker,
        )
    else:
        spec = selection_specs[type_name]
        picked, used_ids = pick_type(
            pool_lookup[spec["pool_name"]],
            used_ids,
            group_cols=spec["group_cols"],
            n_per_group=spec["n_per_group"],
            sample_type=spec["sample_type"],
            dim_t=spec["dim_t"],
            dim_s=spec["dim_s"],
            score_col=spec["score_col"],
            tier=spec["tier"],
            max_n=spec["max_n"],
            anual_min_stab_yrs=spec.get("anual_min_stab_yrs"),
            auto_tier_mask=spec.get("auto_tier_mask"),
            year_counts=anual_year_counts,
            spatial_tracker=spatial_tracker,
        )
    parts.append(picked)
    print(f"  {type_name:24s}: {len(picked):4d}")


# ══════════════════════════════════════════════════════════════
# 10. ENSAMBLE FINAL
# ══════════════════════════════════════════════════════════════

selected = pd.concat([p for p in parts if not p.empty], ignore_index=True)
selected = selected.sort_values(["sample_type", "eco_dom_name"])

# Aplicar límite total manteniendo proporción por tipo (protege clases criticas dedicadas)
if len(selected) > MAX_TOTAL:
    rare_mask = (
        selected.get("target_rare_class", pd.Series("", index=selected.index))
        .astype(str)
        .str.strip()
        .ne("")
    )
    rare = selected[rare_mask].copy()
    rest = selected[~rare_mask].copy()
    budget_rest = max(0, MAX_TOTAL - len(rare))
    if len(rest) > budget_rest and budget_rest > 0:
        frac = budget_rest / len(rest)
        rest = (
            rest.groupby("sample_type", group_keys=False)
                .apply(lambda g: g.head(max(1, int(len(g) * frac))))
                .reset_index(drop=True)
        )
    elif budget_rest == 0:
        rest = rest.iloc[0:0]
    selected = pd.concat([rare, rest], ignore_index=True)

if USE_SCALE300_PROFILE and MAX_MODAL_OTRA < len(selected):
    before = len(selected)
    selected = apply_modal_class_cap(
        selected,
        OTRA_SIN_VEG_ID,
        MAX_MODAL_OTRA,
        exempt_fn=is_otra_sin_vegetacion_exempt,
    )
    print(f"\n  Cap Otra_sin_vegetacion (pre-fill): {before} -> {len(selected)}")

if USE_SCALE300_PROFILE and len(selected) < MAX_TOTAL:
    before = len(selected)
    selected, used_ids = fill_to_total_target(
        selected, cands, used_ids, target_n=MAX_TOTAL, score_col="sc_e_s",
        spatial_tracker=spatial_tracker,
    )
    print(f"  Relleno meta huso: {before} -> {len(selected)} (meta {MAX_TOTAL})")

if USE_SCALE300_PROFILE and ECO_FILL_MAX_ADD > 0:
    eco_budget = min(ECO_FILL_MAX_ADD, max(0, MAX_TOTAL + 25 - len(selected)))
    selected, used_ids = fill_ecoregion_quotas(
        selected,
        cands_all,
        used_ids,
        min_per_eco=MIN_PER_ECO,
        priority_ecos=PRIORITY_ECOS,
        max_add=eco_budget,
        score_col="sc_e_h",
        spatial_tracker=spatial_tracker,
    )
    print(f"  Relleno ecorregiones deficitarias (+{eco_budget} max): {len(selected)} total")

if USE_SCALE300_PROFILE and MAX_MODAL_OTRA < len(selected):
    before = len(selected)
    selected = apply_modal_class_cap(
        selected,
        OTRA_SIN_VEG_ID,
        MAX_MODAL_OTRA,
        exempt_fn=is_otra_sin_vegetacion_exempt,
    )
    print(f"  Cap Otra_sin_vegetacion (final): {before} -> {len(selected)}")

if USE_SCALE300_PROFILE:
    score_cols = [c for c in cands.columns if c.startswith("sc_")]
    if score_cols and "grid_id" in selected.columns:
        selected = selected.drop(columns=[c for c in score_cols if c in selected.columns], errors="ignore")
        selected = selected.merge(
            cands[["grid_id"] + score_cols].drop_duplicates("grid_id"),
            on="grid_id",
            how="left",
        )
    t_s_n = int((selected.get("sample_type", pd.Series(dtype=object)) == "transicion_simple_media").sum())
    if t_s_n > MAX_T_S_CAP:
        before = len(selected)
        selected = cap_sample_type(
            selected,
            "transicion_simple_media",
            MAX_T_S_CAP,
            score_col="sc_t_s",
        )
        print(f"  Cap transicion_simple_media: {before} -> {len(selected)} (max {MAX_T_S_CAP})")

if not selected.empty:
    before = len(selected)
    selected = finalize_temporal_labels(selected, anual_year_counts)
    print(f"  Reparacion anual/ref_year: {before} -> {len(selected)}")
    selected = annotate_selection_profile(selected)
    n_profile = selected["selection_profile"].iloc[0]
    n_est = int((selected["dim_temporal"] == "estable").sum())
    print(f"  Perfil temporal: {n_profile}  (estables={n_est})")

selected = gpd.GeoDataFrame(selected, geometry="geometry", crs=gdf.crs)

# Revisión: descripción del tier
tier_desc = {
    0: "auto_sin_revision",
    1: "revision_visual_rapida",
    2: "revision_imagen_ndvi",
    3: "revision_con_fuente_auxiliar",
}
selected["review_status"] = "pendiente"
selected["review_desc"]   = selected["review_tier"].map(tier_desc)


# ══════════════════════════════════════════════════════════════
# 11. SPLIT TRAIN / VAL / TEST
# ══════════════════════════════════════════════════════════════
# Split por grid_id único para evitar data leakage.

# Split estratificado por cluster espacial (vecinos comparten split).

selected["split"] = assign_cluster_aware_split(
    selected,
    seed=RANDOM_SEED,
    train_frac=0.70,
    val_frac=0.15,
    test_frac=0.15,
    rare_force_holdout=(
        BOSQUE_NORTE_CLASS_NAME,
        ARENA_CLASS_NAME,
        SALAR_CLASS_NAME,
        PASTIZAL_CLASS_NAME,
    ),
)
leak_stats = verify_cluster_split(selected, split_col="split")
print(
    f"\n  Verificacion clusters: pares_vecinos={leak_stats['neighbor_pairs']}  "
    f"fugas_split={leak_stats['leak_pairs']}"
)

reserves = pd.DataFrame()
if USE_SCALE300_PROFILE and RESERVE_PER_ECO > 0:
    reserves = build_ecoregion_reserves(
        selected,
        cands,
        used_ids,
        eco_ids=FRAGILE_ECOS,
        n_reserve=RESERVE_PER_ECO,
        score_col="sc_e_s",
    )
    if not reserves.empty:
        print(f"  Reservas E3/E6: {len(reserves)} candidatos suplentes")


# ══════════════════════════════════════════════════════════════
# 12. RESUMEN
# ══════════════════════════════════════════════════════════════

print("\n====== RESUMEN ======")
print(f"\nRectángulos seleccionados: {len(selected)}")
print(f"Rectángulos únicos:        {selected['grid_id'].nunique()}")

print("\n-- Por tipo de muestra --")
summary = (
    selected.groupby(["dim_temporal","dim_espacial","sample_type"])
    .agg(
        n         =("grid_id",     "count"),
        mode_pct  =("lulc_mode_pct","mean"),
        run_mean  =("max_stab_run", "mean"),
        shannon   =("shannon_idx",  "mean"),
    ).round(1)
)
print(summary.to_string())

print("\n-- Por tier de revision --")
tier_summary = selected.groupby("review_tier")["review_desc"].first()
tier_counts  = selected["review_tier"].value_counts().sort_index()
for tier, desc in tier_summary.items():
    print(f"  Tier {tier} ({desc}): {tier_counts.get(tier, 0)}")

print("\n-- Muestras anuales - ano de referencia --")
anuales = selected[selected["dim_temporal"] == "anual"]
if not anuales.empty:
    bad_ref = pd.to_numeric(anuales["ref_year"], errors="coerce").fillna(-9999) <= 0
    print(f"  Anuales sin ref_year valido: {int(bad_ref.sum())} / {len(anuales)}")
    print(anuales.groupby(["sample_type", "ref_period"])["ref_year"]
          .agg(["count", "min", "max"]).to_string())
    yr_counts = anuales["ref_year"].value_counts().sort_index()
    yr_pct = (yr_counts / len(anuales) * 100).round(1)
    print("\n  Distribucion ref_year (1999-2024):")
    for yr, n in yr_counts.items():
        print(f"    {int(yr)}: {n} ({yr_pct[yr]}%)")
    print("\n  Distribucion ref_period:")
    print(anuales["ref_period"].value_counts().sort_index().to_string())

print("\n-- Por ecorregion (top 10) --")
print(selected["eco_dom_name"].value_counts().head(10).to_string())
if "lulc_mode_id" in selected.columns:
    otra_n = int((pd.to_numeric(selected["lulc_mode_id"], errors="coerce") == OTRA_SIN_VEG_ID).sum())
    past_n = int((pd.to_numeric(selected["lulc_mode_id"], errors="coerce") == PASTIZAL_MODE_ID).sum())
    print(f"\n-- Clases modal clave --")
    print(f"  Otra_sin_vegetacion (25): {otra_n}")
    print(f"  Pastizal (15):            {past_n}")

print("\n-- Train / Val / Test --")
print(selected["split"].value_counts().to_string())
if "target_rare_class" in selected.columns:
    rare_split = selected[
        selected["target_rare_class"].astype(str).str.strip().ne("")
    ].groupby(["target_rare_class", "split"]).size().unstack(fill_value=0)
    if not rare_split.empty:
        print("\n-- Split clases criticas dedicadas --")
        print(rare_split.to_string())

if "target_rare_class" in selected.columns:
    print("\n-- Clases criticas dedicadas --")
    rare_sel = selected[
        selected["target_rare_class"].astype(str).str.strip().ne("")
    ]
    if rare_sel.empty:
        print("  (ninguna)")
    else:
        for class_name, group in rare_sel.groupby("target_rare_class"):
            print(f"  {class_name}: {len(group)}")
            pct_col = "rare_presence_pct"
            if class_name == ACHAP_CLASS_NAME and "achap_presence_pct" in group.columns:
                pct_col = "achap_presence_pct"
            elif (
                class_name == BOSQUE_NORTE_CLASS_NAME
                and "north_forest_presence_pct" in group.columns
            ):
                pct_col = "north_forest_presence_pct"
            if pct_col in group.columns:
                print(f"    presencia media: {group[pct_col].mean():.1f}%")
            print(group.groupby("sample_type")["grid_id"].count().to_string())

print("\n-- Calidad media por tipo --")
cols_q = ["valid_area_pct","lulc_mode_pct","max_stab_run",
          "shannon_idx","conf_risk_pct"]
for c in cols_q:
    if c in selected.columns:
        s = selected[c].describe()
        print(f"  {c:20s}: mean={s['mean']:.1f}  "
              f"min={s['min']:.1f}  max={s['max']:.1f}")


# ══════════════════════════════════════════════════════════════
# 13. EXPORTAR
# ══════════════════════════════════════════════════════════════

drop_sc = [c for c in selected.columns if c.startswith("sc_")]
export  = selected.drop(columns=drop_sc, errors="ignore")

export.to_file(output_gpkg,    layer="seleccion", driver="GPKG")
export.to_file(output_geojson, driver="GeoJSON")
try:
    export.to_file(output_shp, driver="ESRI Shapefile")
except Exception as exc:
    print(f"  Advertencia: no se pudo exportar SHP ({exc})")
export.drop(columns="geometry").to_csv(
    output_csv, index=False, encoding="utf-8-sig")

if not reserves.empty:
    reserve_export = reserves.drop(columns=[c for c in reserves.columns if c.startswith("sc_")], errors="ignore")
    reserve_export.drop(columns="geometry", errors="ignore").to_csv(
        output_reserve_csv, index=False, encoding="utf-8-sig"
    )

print("\n====== ARCHIVOS EXPORTADOS ======")
print(f"  {output_gpkg}")
print(f"  {output_geojson}")
print(f"  {output_shp}")
print(f"  {output_csv}")
if not reserves.empty:
    print(f"  {output_reserve_csv}")