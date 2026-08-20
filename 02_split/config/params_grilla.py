"""Parámetros de la grilla de caracterización sobre las cartas CIM 1:250.000.

La grilla vive íntegramente en EPSG:4326, igual que las cartas CIM y que el
ráster de landcover. No hay husos ni zonas UTM: un solo CRS.
"""

from pathlib import Path

# --- Rutas -------------------------------------------------------------------
ANCILLARY = Path("/home/lserey/mapbiomas_land/ancillary_data")
DATA_ROOT = Path("/home/lserey/mapbiomas_land/prod/samples_cim")
OUT_ROOT = DATA_ROOT / "00_grilla"

CIM_VECTOR = ANCILLARY / "cim_world-1-250000.gpkg"
CIM_CAMPO_NOMBRE = "name"

LULC_DIR = ANCILLARY / "landcover_col2"
LULC_PATRON = "classification_{year}.tif"
LULC_ANIO_REF = 1999  # ráster que fija la resolución y la grilla de píxeles

# --- Geometría de la celda ---------------------------------------------------
# Cada celda son N x N píxeles de la grilla nativa del ráster. Se generan las
# dos escalas, análogas a los rectángulos 2x2 y 3x3 de ssl4eo v02:
#   528 px = 2 chips de 264 px
#   792 px = 3 chips de 264 px
CHIP_PX = 264
CELDAS_PX = [528, 792]

# --- Anclaje -----------------------------------------------------------------
# La malla arranca en la esquina NOROESTE de cada carta y avanza hacia el este y
# hacia el sur. Cada carta se subdivide de forma independiente y ninguna celda
# cruza a la carta vecina.
#
# Con SNAP_A_PIXEL el ancla se corre al primer borde de píxel del ráster que
# queda dentro de la carta (a lo más un píxel, 30 m, de la esquina). Así cada
# celda sigue siendo una ventana de píxeles enteros y se lee sin remuestrear.
SNAP_A_PIXEL = True

# --- Alcance -----------------------------------------------------------------
# Solo cartas que intersectan el ráster de landcover: descarta Isla de Pascua
# (SG-12-Z-D) y las cartas oceánicas (SI-17-X-C/D), que no tienen datos.
SOLO_CARTAS_CON_DATOS = True

# --- Salida ------------------------------------------------------------------
CRS_SALIDA = "EPSG:4326"


def etiqueta(celda_px: int) -> str:
    """Nombre corto de la escala: 528 -> '2x2', 792 -> '3x3'.

    Es la forma en que se nombran los archivos y los grid_id, porque el número de
    chips dice más que el lado en píxeles.
    """
    if celda_px % CHIP_PX:
        raise ValueError(
            f"celda_px={celda_px} no es múltiplo del chip de {CHIP_PX} px"
        )
    n = celda_px // CHIP_PX
    return f"{n}x{n}"


def desde_etiqueta(texto: str) -> int:
    """Inversa de etiqueta(): admite '2x2', '3x3' o directamente el lado en píxeles."""
    txt = str(texto).strip().lower()
    if "x" in txt:
        a, _, b = txt.partition("x")
        if not (a.isdigit() and b.isdigit() and a == b):
            raise ValueError(f"Escala no reconocida: {texto!r} (se espera '2x2' o '3x3')")
        return int(a) * CHIP_PX
    if not txt.isdigit():
        raise ValueError(f"Escala no reconocida: {texto!r}")
    return int(txt)


def capa(celda_px: int) -> str:
    return f"grilla_cim_{etiqueta(celda_px)}"


def gpkg(celda_px: int) -> Path:
    return OUT_ROOT / f"{capa(celda_px)}.gpkg"
