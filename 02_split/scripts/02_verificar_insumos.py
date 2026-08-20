#!/usr/bin/env python
"""02 — Verifica los insumos antes de caracterizar.

Comprueba lo que el resto del pipeline da por supuesto:
  - la serie de landcover está completa y todos los años comparten la grilla;
  - el ráster de ecorregiones está alineado píxel a píxel con el landcover;
  - las grillas están generadas y sus ventanas caen dentro del ráster;
  - la fórmula de área por latitud coincide con el cálculo geodésico de pyproj.

Uso:
    python scripts/02_verificar_insumos.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from shapely.geometry import Polygon  # noqa: E402

import geodesia  # noqa: E402
from caracterizacion.leer import anios, perfil_referencia, ruta_lulc  # noqa: E402
from config import params_caracterizacion as PC  # noqa: E402
from config import params_grilla as PG  # noqa: E402
from grilla.construir import cargar_grilla  # noqa: E402

OK, FALLA = "OK  ", "FALLA"


def _print(cond: bool, texto: str) -> bool:
    print(f"  [{OK if cond else FALLA}] {texto}")
    return cond


def verificar_landcover(informe: dict) -> bool:
    print("\nSerie de landcover")
    ref = perfil_referencia()
    lista = anios()
    todo = _print(
        all(ruta_lulc(a).is_file() for a in lista),
        f"{len(lista)} años presentes ({lista[0]}–{lista[-1]})",
    )
    misma = True
    for a in lista:
        with rasterio.open(ruta_lulc(a)) as src:
            misma &= (
                src.crs.to_epsg() == 4326
                and (src.width, src.height) == (ref["width"], ref["height"])
                and max(abs(x - y) for x, y in zip(src.transform, ref["transform"])) < 1e-12
            )
    todo &= _print(misma, "todos los años comparten CRS, tamaño y transform")
    print(f"         resolución {ref['res']:.17f}° ({ref['res'] * 111_320:.3f} m en latitud)")
    informe["landcover"] = {
        "anios": lista, "res_deg": ref["res"],
        "width": ref["width"], "height": ref["height"],
        "grilla_consistente": bool(misma),
    }
    return todo


def verificar_eco(informe: dict) -> bool:
    print("\nRáster de ecorregiones")
    ref = perfil_referencia()
    existe = _print(PC.ECO_RASTER.is_file(), f"existe {PC.ECO_RASTER.name}")
    if not existe:
        informe["eco"] = {"existe": False}
        return False
    with rasterio.open(PC.ECO_RASTER) as src:
        alineado = (
            src.crs.to_epsg() == 4326
            and (src.width, src.height) == (ref["width"], ref["height"])
            and max(abs(x - y) for x, y in zip(src.transform, ref["transform"])) < 1e-12
        )
        informe["eco"] = {
            "existe": True, "alineado": bool(alineado),
            "width": int(src.width), "height": int(src.height),
        }
    return _print(alineado, "alineado píxel a píxel con el landcover (no requiere remuestreo)")


def verificar_grillas(informe: dict) -> bool:
    print("\nGrillas")
    ref = perfil_referencia()
    todo = True
    informe["grillas"] = {}
    for celda_px in PC.CELDAS_PX:
        escala = PG.etiqueta(celda_px)
        ruta = PG.gpkg(celda_px)
        if not _print(ruta.is_file(), f"{escala}: existe {ruta.name}"):
            todo = False
            continue
        gdf = cargar_grilla(celda_px)
        dentro = int(
            (
                (gdf["px_col_off"] >= 0)
                & (gdf["px_row_off"] >= 0)
                & (gdf["px_col_off"] + celda_px <= ref["width"])
                & (gdf["px_row_off"] + celda_px <= ref["height"])
            ).sum()
        )
        divide = celda_px % PC.STATS_BLOQUE_PX == 0
        todo &= _print(
            divide,
            f"{escala}: sus {celda_px} px son divisibles por el bloque de "
            f"{PC.STATS_BLOQUE_PX} px ({celda_px // PC.STATS_BLOQUE_PX} bloques por lado, "
            f"sin píxeles descartados)",
        )
        print(f"         {len(gdf)} celdas, {gdf['cim_name'].nunique()} cartas, "
              f"{dentro} con la ventana íntegra dentro del ráster")
        informe["grillas"][escala] = {
            "celda_px": celda_px,
            "n_celdas": int(len(gdf)), "n_cartas": int(gdf["cim_name"].nunique()),
            "ventanas_dentro_del_raster": dentro,
            "divisible_por_bloque": bool(divide),
        }
    return todo


def _cuadrangulo_denso(lat_norte: float, lado: float, n_vertices: int) -> Polygon:
    """Caja lat/lon con los bordes este-oeste densificados.

    pyproj.Geod une los vértices con geodésicas, y una geodésica entre dos puntos
    del mismo paralelo no sigue el paralelo. Sin densificar, el polígono que mide
    Geod no es el mismo cuadrángulo y la comparación arroja un desvío espurio de
    ~2 ppm.
    """
    lons = np.linspace(0.0, lado, n_vertices)
    borde_norte = [(x, lat_norte) for x in lons]
    borde_sur = [(x, lat_norte - lado) for x in lons[::-1]]
    return Polygon(borde_norte + borde_sur)


def verificar_areas(informe: dict) -> bool:
    print("\nÁrea de píxel por latitud")
    res = perfil_referencia()["res"]
    peor = 0.0
    for celda_px in PC.CELDAS_PX:
        for lat in (-17.5, -30.0, -40.0, -50.0, -56.0):
            a_formula = geodesia.area_celda_m2(lat, res, celda_px)
            a_geod = abs(
                geodesia.GEOD.geometry_area_perimeter(
                    _cuadrangulo_denso(lat, res * celda_px, 4000)
                )[0]
            )
            peor = max(peor, abs(a_formula - a_geod) / a_geod)
    ok = _print(
        peor < 1e-9,
        f"coincide con pyproj.Geod sobre bordes densificados (error relativo máx. {peor:.2e})",
    )

    ha_norte = float(geodesia.areas_pixel_ha(-17.5, res, 1)[0, 0])
    ha_sur = float(geodesia.areas_pixel_ha(-55.9, res, 1)[0, 0])
    print(f"         un píxel mide {ha_norte:.4f} ha en el norte y {ha_sur:.4f} ha en el sur "
          f"({(1 - ha_sur / ha_norte) * 100:.1f}% menos)")
    print("         por eso los porcentajes se ponderan por área y no por conteo")
    informe["areas"] = {
        "error_relativo_max": peor,
        "ha_pixel_norte": round(ha_norte, 6),
        "ha_pixel_sur": round(ha_sur, 6),
        "radio_autalico_m": round(geodesia.RADIO_AUTALICO_M, 4),
    }
    return ok


def main() -> int:
    print("=== Verificación de insumos ===")
    informe: dict = {"verificado": datetime.now().isoformat(timespec="seconds")}
    todo = all([
        verificar_landcover(informe),
        verificar_eco(informe),
        verificar_grillas(informe),
        verificar_areas(informe),
    ])
    informe["todo_ok"] = todo

    PC.OUT_ROOT.mkdir(parents=True, exist_ok=True)
    destino = PC.OUT_ROOT / "_verificacion_insumos.json"
    destino.write_text(json.dumps(informe, indent=2, ensure_ascii=False, default=str) + "\n")
    print(f"\n{'Todo en orden.' if todo else 'HAY FALLAS.'}  Informe: {destino}")
    return 0 if todo else 1


if __name__ == "__main__":
    raise SystemExit(main())
