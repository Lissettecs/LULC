#!/usr/bin/env python
"""01 — Genera las grillas de celdas sobre las cartas CIM y las exporta a GeoPackage.

Todo en EPSG:4326: un solo CRS, sin husos. Cada carta se subdivide desde su
esquina noroeste y ninguna celda cruza a la carta vecina. Se genera un
GeoPackage por tamaño de celda.

Uso:
    python scripts/01_generar_grilla.py
    python scripts/01_generar_grilla.py --escala 2x2
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import geopandas as gpd  # noqa: E402
from pyproj import Geod  # noqa: E402

from config import params_grilla as P  # noqa: E402
from grilla.construir import (  # noqa: E402
    ancla_carta,
    cargar_cartas_cim,
    construir_grilla,
    lado_deg,
)

GEOD = Geod(ellps="WGS84")


def _area_km2(geom) -> float:
    return abs(GEOD.geometry_area_perimeter(geom)[0]) / 1e6


def validar(gdf: gpd.GeoDataFrame, celda_px: int, ref: dict) -> dict:
    """Unicidad, alineación a píxel, contención en la carta, solapes y cobertura."""
    lado = lado_deg(celda_px, ref)
    informe: dict = {
        "escala": P.etiqueta(celda_px),
        "celda_px": celda_px,
        "n_chips": celda_px // P.CHIP_PX,
        "lado_deg": lado,
        "n_celdas": int(len(gdf)),
        "n_cartas": int(gdf["cim_name"].nunique()),
        "grid_id_unicos": bool(gdf["grid_id"].is_unique),
        "crs": str(gdf.crs),
    }

    dev = max(
        float(((gdf["lon_max"] - gdf["lon_min"]) - lado).abs().max()),
        float(((gdf["lat_max"] - gdf["lat_min"]) - lado).abs().max()),
    )
    informe["lado_desvio_max_mm"] = round(dev * 111_320 * 1000, 6)

    paso_ok = True
    for _, sub in gdf.groupby("cim_name"):
        cols = sorted(sub["px_col_off"].unique())
        filas = sorted(sub["px_row_off"].unique())
        paso_ok &= all((b - a) == celda_px for a, b in zip(cols, cols[1:]))
        paso_ok &= all((b - a) == celda_px for a, b in zip(filas, filas[1:]))
    informe["paso_regular_por_carta"] = bool(paso_ok)

    informe["celdas_duplicadas"] = int(
        len(gdf) - len(gdf[["px_col_off", "px_row_off"]].drop_duplicates())
    )

    sj = gpd.sjoin(
        gdf[["grid_id", "geometry"]], gdf[["grid_id", "geometry"]],
        how="inner", predicate="overlaps",
    )
    informe["pares_celdas_solapadas"] = int(
        len(sj[sj["grid_id_left"] != sj["grid_id_right"]]) // 2
    )

    cartas = cargar_cartas_cim()
    idx = cartas.set_index("cim_name")

    fuera, peor = 0, 1.0
    for nombre, sub in gdf.groupby("cim_name"):
        carta = idx.loc[nombre, "geometry"]
        for geom in sub.geometry:
            frac = geom.intersection(carta).area / geom.area
            peor = min(peor, frac)
            if frac < 1 - 1e-9:
                fuera += 1
    informe["celdas_fuera_de_su_carta"] = int(fuera)
    informe["frac_en_carta_minima"] = round(peor, 9)

    desfases = []
    for nombre in gdf["cim_name"].unique():
        carta = idx.loc[nombre, "geometry"]
        lon_w, _, _, lat_n = carta.bounds
        col0, fil0 = ancla_carta(carta, ref)
        desfases.append(max(
            abs(ref["lon_origen"] + col0 * ref["res"] - lon_w),
            abs(ref["lat_origen"] - fil0 * ref["res"] - lat_n),
        ))
    informe["desfase_ancla_max_px"] = round(max(desfases) / ref["res"], 6)
    informe["desfase_ancla_max_m"] = round(max(desfases) * 111_320, 2)

    conteo = gdf["cim_name"].value_counts()
    informe["celdas_por_carta"] = {
        "min": int(conteo.min()), "max": int(conteo.max()),
        "valores": sorted(int(v) for v in conteo.unique()),
    }
    informe["cuadricula_por_carta"] = {
        "columnas": int(gdf["col_idx"].max()) + 1,
        "filas": int(gdf["row_idx"].max()) + 1,
    }

    union_cartas = cartas.geometry.union_all()
    a_cartas = _area_km2(union_cartas)
    a_cub = _area_km2(union_cartas.intersection(gdf.geometry.union_all()))
    informe["area_cartas_km2"] = round(a_cartas, 1)
    informe["area_cubierta_km2"] = round(a_cub, 1)
    informe["cobertura_global_pct"] = round(100 * a_cub / a_cartas, 4)

    # Franja de la carta que queda sin cubrir por no caber una celda entera
    informe["sobra_este_deg"] = round(1.5 - informe["cuadricula_por_carta"]["columnas"] * lado, 9)
    informe["sobra_sur_deg"] = round(1.0 - informe["cuadricula_por_carta"]["filas"] * lado, 9)

    sin_celdas = sorted(set(cartas["cim_name"]) - set(gdf["cim_name"]))
    informe["n_cartas_sin_celdas"] = len(sin_celdas)
    informe["cartas_sin_celdas"] = sin_celdas

    for campo in ("area_km2", "ancho_km", "alto_km", "razon_ancho_alto"):
        informe[campo] = {
            "min": float(gdf[campo].min()),
            "max": float(gdf[campo].max()),
            "media": round(float(gdf[campo].mean()), 4),
        }
    return informe


def generar(celda_px: int) -> dict:
    gdf, ref = construir_grilla(celda_px)
    salida = P.gpkg(celda_px)
    salida.parent.mkdir(parents=True, exist_ok=True)

    lado = lado_deg(celda_px, ref)
    print(f"\n=== Grilla {P.etiqueta(celda_px)}: {celda_px} px "
          f"({celda_px // P.CHIP_PX} chips de {P.CHIP_PX} px) ===")
    print(f"  lado    : {lado:.9f}° ({lado * 60:.4f} arcmin)")
    print(f"  celdas  : {len(gdf)}")

    informe = validar(gdf, celda_px, ref)
    informe.update({
        "generado": datetime.now().isoformat(timespec="seconds"),
        "cim_vector": str(P.CIM_VECTOR),
        "raster_referencia": ref["ruta"],
        "raster_res_deg": ref["res"],
        "anclaje": "carta_noroeste",
        "snap_a_pixel": P.SNAP_A_PIXEL,
        "crs_salida": P.CRS_SALIDA,
        "salida": str(salida),
    })

    gdf.to_file(salida, layer=P.capa(celda_px), driver="GPKG")
    verif = gpd.read_file(salida, rows=1)
    if verif.crs is None or verif.crs.to_epsg() != 4326:
        raise RuntimeError(f"CRS escrito incorrecto: {verif.crs}")

    gdf.drop(columns=["geometry"]).to_csv(salida.with_suffix(".csv"), index=False)
    (salida.parent / f"{salida.stem}_resumen.json").write_text(
        json.dumps(informe, indent=2, ensure_ascii=False) + "\n"
    )

    cua = informe["cuadricula_por_carta"]
    print(f"  cuadrícula por carta : {cua['columnas']} columnas x {cua['filas']} filas "
          f"= {cua['columnas'] * cua['filas']} celdas")
    for k in ("grid_id_unicos", "paso_regular_por_carta", "celdas_duplicadas",
              "pares_celdas_solapadas", "celdas_fuera_de_su_carta",
              "desfase_ancla_max_m", "cobertura_global_pct"):
        print(f"  {k}: {informe[k]}")
    print(f"  sobra al este: {informe['sobra_este_deg']:.6f}°  "
          f"al sur: {informe['sobra_sur_deg']:.6f}°")
    print(f"  área celda (km2): {informe['area_km2']}")
    print(f"  razón ancho/alto: {informe['razon_ancho_alto']}")
    print(f"  -> {salida}")
    return informe


def main() -> None:
    ap = argparse.ArgumentParser(description="Genera las grillas CIM en EPSG:4326")
    ap.add_argument("--escala", action="append", dest="escalas",
                    help="'2x2', '3x3' o el lado en píxeles; repetible")
    args = ap.parse_args()
    celdas = [P.desde_etiqueta(e) for e in args.escalas] if args.escalas else P.CELDAS_PX

    todas = cargar_cartas_cim(solo_con_datos=False)
    usadas = cargar_cartas_cim()
    print(f"Vector CIM : {P.CIM_VECTOR}")
    print(f"  cartas totales        : {len(todas)}")
    print(f"  cartas con landcover  : {len(usadas)}")
    fuera = sorted(set(todas["cim_name"]) - set(usadas["cim_name"]))
    if fuera:
        print(f"  sin datos (excluidas) : {', '.join(fuera)}")
    print(f"\nAnclaje : esquina noroeste de cada carta"
          f"{' (ajustada al borde de píxel)' if P.SNAP_A_PIXEL else ''}")

    for celda_px in celdas:
        generar(celda_px)


if __name__ == "__main__":
    main()
