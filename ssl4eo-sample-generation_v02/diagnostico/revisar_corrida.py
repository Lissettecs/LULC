#!/usr/bin/env python3
"""
Diagnóstico previo sobre parquet y GeoPackage existentes (sin cluster).

Uso:
  python diagnostico/revisar_corrida.py \\
      --caracterizacion 20260727_1004 --seleccion 20260727_1340
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import geopandas as gpd
import numpy as np
import pandas as pd
from shapely.geometry import box

from config import params_caracterizacion as PC
from config import params_seleccion as PS
from config.diccionarios import BBOX_CLASE, CLASS_NAMES, CLASES_MODELO_GENERAL, ECO_NAMES

DATA_ROOT = PC.DATA_ROOT


def _pct_cols(df: pd.DataFrame) -> list[str]:
    return sorted(c for c in df.columns if c.startswith("pct_") and c[4:].isdigit())


def _cargar_caracterizacion(tag: str) -> pd.DataFrame:
    run_dir = DATA_ROOT / "01_caracterizacion" / tag
    por_tile = run_dir / "por_tile"
    if not por_tile.is_dir():
        raise FileNotFoundError(f"No existe {por_tile}")
    partes = [pd.read_parquet(p) for p in sorted(por_tile.glob("*.parquet"))]
    if not partes:
        raise FileNotFoundError(f"Sin parquet en {por_tile}")
    return pd.concat(partes, ignore_index=True)


def _cargar_consolidado(tag: str) -> pd.DataFrame:
    run_dir = DATA_ROOT / "01_caracterizacion" / tag / "consolidado"
    partes = []
    for p in sorted(run_dir.glob("grilla_utm*.gpkg")):
        if "inspeccion" in p.name:
            continue
        g = gpd.read_file(p)
        g["_archivo"] = p.name
        partes.append(g)
    if not partes:
        raise FileNotFoundError(f"Sin GPKG en {run_dir}")
    return pd.concat(partes, ignore_index=True)


def _cargar_seleccion(tag: str) -> tuple[pd.DataFrame, Path]:
    run_dir = DATA_ROOT / "02_seleccion" / tag
    csv = run_dir / "seleccion_nacional.csv"
    if csv.is_file():
        return pd.read_csv(csv), run_dir
    gpkg = run_dir / "seleccion_nacional.gpkg"
    if gpkg.is_file():
        return pd.DataFrame(gpd.read_file(gpkg).drop(columns="geometry", errors="ignore")), run_dir
    raise FileNotFoundError(f"Sin selección en {run_dir}")


def _diagnostico_clase0(df: pd.DataFrame, lineas: list[str]) -> bool:
    lineas.append("## A.1 — Clase 0 (nodata raster)")
    pct_cols = _pct_cols(df)
    tiene_pct0 = "pct_0" in df.columns
    lineas.append(f"1. ¿Existe columna `pct_0`? **{'Sí' if tiene_pct0 else 'No'}**")

    if pct_cols:
        suma_con = df[pct_cols].sum(axis=1)
        sin0 = [c for c in pct_cols if c != "pct_0"]
        suma_sin = df[sin0].sum(axis=1) if sin0 else suma_con
        lineas.append(
            f"2. Suma `pct_{{id}}`: con pct_0 media={suma_con.mean():.2f}% · "
            f"sin pct_0 media={suma_sin.mean():.2f}% · "
            f"filas fuera 99.9–100.1: {((suma_sin < 99.9) | (suma_sin > 100.1)).sum()}"
        )
    else:
        lineas.append("2. Sin columnas pct_{id} numéricas.")

    n_modo0 = int((df["lulc_mode_id"] == 0).sum()) if "lulc_mode_id" in df.columns else 0
    media_valid = float(df.loc[df["lulc_mode_id"] == 0, "valid_area_pct"].mean()) if n_modo0 else float("nan")
    lineas.append(
        f"3. Rectángulos con `lulc_mode_id == 0`: **{n_modo0}** · "
        f"`valid_area_pct` medio en ellos: {media_valid:.2f}%"
    )

    if tiene_pct0:
        p0 = pd.to_numeric(df["pct_0"], errors="coerce").fillna(0)
        lineas.append(
            f"4. Distribución `pct_0`: mediana={p0.median():.2f}% · p90={p0.quantile(0.9):.2f}% · "
            f"máx={p0.max():.2f}% · >10%: {(p0 > 10).sum()}"
        )
        recaracterizar = bool((p0 > 1).any())
    else:
        lineas.append("4. Sin columna `pct_0` — no hay vector de composición para nodata.")
        recaracterizar = False

    lineas.append(
        "5. **`valid_area_pct` actual:** excluye ecorregión nodata (`eco!=0`) y clase 27; "
        "**no excluye clase 0** del denominador de composición ni de métricas temporales."
    )
    lineas.append("")
    return recaracterizar


def _diagnostico_tamarugo(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("## A.2 — Clase 3 (tamarugo)")
    if "pct_3" not in df.columns:
        lineas.append("Sin columna `pct_3` en caracterización.")
        lineas.append("")
        return

    mask = (pd.to_numeric(df["pct_3"], errors="coerce").fillna(0) > 0) & (
        df.get("en_bbox_3", False).astype(bool)
    )
    n = int(mask.sum())
    lineas.append(f"6. Candidatos con `pct_3 > 0` y `en_bbox_3`: **{n}**")
    if n:
        desglose = df.loc[mask].groupby("eco_dom_id").size()
        for eco_id, cnt in desglose.items():
            nombre = ECO_NAMES.get(int(eco_id), f"E{eco_id}")
            lineas.append(f"   - E{int(eco_id)} ({nombre}): {cnt}")
    else:
        lineas.append("   Sin candidatos — revisar reproyección de bbox.")

    bbox = BBOX_CLASE[3]
    lineas.append(
        f"7. Bbox definida en EPSG:{bbox['epsg']} · "
        f"x=[{bbox['xmin']}, {bbox['xmax']}] y=[{bbox['ymin']}, {bbox['ymax']}]"
    )
    for huso, epsg in ((18, 32718), (19, 32719)):
        g = gpd.GeoSeries([box(bbox["xmin"], bbox["ymin"], bbox["xmax"], bbox["ymax"])], crs=f"EPSG:{bbox['epsg']}")
        g2 = g.to_crs(epsg)
        b = g2.total_bounds
        lineas.append(f"   Huso {huso} (EPSG:{epsg}): xmin={b[0]:.1f} xmax={b[2]:.1f} ymin={b[1]:.1f} ymax={b[3]:.1f}")

    lineas.append("8. Modo clase 3 en universo (matriz presencia + EXCEPCIONES_MODO):")
    if PS.MATRIZ_PRESENCIA.is_file():
        matriz = pd.read_csv(PS.MATRIZ_PRESENCIA)
        for eco_id in (1, 2, 5):
            sub = matriz[(matriz["ecorregion_id"] == eco_id) & (matriz["clase_id"] == 3)]
            if sub.empty:
                lineas.append(f"   - E{eco_id}: sin fila en matriz")
                continue
            area = float(sub.iloc[0]["area_ha"])
            pct = float(sub.iloc[0]["pct_de_ecorregion"])
            modo_exc = PS.EXCEPCIONES_MODO.get((eco_id, 3))
            if modo_exc:
                modo = modo_exc
            elif area * PS.SEGMENTOS_POR_1000HA / 1000 <= PS.UMBRAL_CENSO_SEGMENTOS:
                modo = "censo"
            elif pct < PS.UMBRAL_RAREZA_PCT_ECO:
                modo = "refuerzo"
            else:
                modo = "estandar/techo"
            lineas.append(f"   - E{eco_id}: modo esperado **{modo}** (area={area:.0f} ha, {pct:.2f}% eco)")
    lineas.append("")


def _diagnostico_pools_seleccion(sel_dir: Path, lineas: list[str]) -> None:
    lineas.append("## A.3 — Pools (corrida de selección)")
    por_eco = sel_dir / "por_ecorregion"
    if not por_eco.is_dir():
        lineas.append("Sin directorio por_ecorregion.")
        lineas.append("")
        return

    for eco_dir in sorted(por_eco.glob("E*")):
        pools_csv = list(eco_dir.glob("pools_E*.csv"))
        if not pools_csv:
            continue
        pl = pd.read_csv(pools_csv[0])
        lineas.append(f"### {eco_dir.name}")
        for _, row in pl.iterrows():
            lineas.append(
                f"- {row.get('pool', '?')}: n_candidatos={row.get('n_candidatos', '?')} · "
                f"max_n={row.get('max_n', '?')}"
            )
    lineas.append("")
    lineas.append(
        "**Nota:** la corrida anterior no registraba `motivo_cierre` ni conteos intermedios; "
        "no se distingue pool vacío de agotado."
    )
    lineas.append("")


def _diagnostico_estable_simple(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("## A.3b — Desglose `estable_simple_media` (proxy sobre candidatos E02 hom+mix)")
    th = PS.TIPOLOGIA_DEFAULT
    eco = df[df["eco_dom_id"].astype(int) == 2].copy()
    if eco.empty:
        lineas.append("Sin candidatos E02.")
        lineas.append("")
        return

    condiciones = {
        "E_S_MIN_STAB_RUN": eco["max_stab_run"] >= th["E_S_MIN_STAB_RUN"],
        "E_S_MAX_TR_PCT": eco["transition_pct"] <= th["E_S_MAX_TR_PCT"],
        "E_S_MIN_MODE_PCT": eco["lulc_mode_pct"] >= th["E_S_MIN_MODE_PCT"],
        "E_S_MAX_MODE_PCT": eco["lulc_mode_pct"] < th["E_S_MAX_MODE_PCT"],
        "E_S_MIN_N_MODE": eco["n_mode_classes"] >= th["E_S_MIN_N_MODE"],
        "E_S_MAX_N_MODE": eco["n_mode_classes"] <= th["E_S_MAX_N_MODE"],
    }
    filtro_base = (
        (eco["valid_area_pct"] >= PS.FILTRO_BASE["valid_area_pct"])
        & (eco["eco_dom_pct"] >= PS.FILTRO_BASE["eco_dom_pct"])
        & (eco["noobs_pct"] <= PS.FILTRO_BASE["noobs_pct"])
    )
    lineas.append(f"- Tras FILTRO_BASE: {int(filtro_base.sum())} / {len(eco)}")
    eco_f = eco[filtro_base]
    todas = pd.Series(True, index=eco_f.index)
    for nombre, m in condiciones.items():
        mf = m.reindex(eco_f.index, fill_value=False)
        lineas.append(f"- `{nombre}`: {int(mf.sum())} cumplen · {int((todas & mf).sum())} acumulado")
        todas &= mf
    lineas.append(f"- **Todas las condiciones:** {int(todas.sum())}")
    lineas.append("")


def _diagnostico_e03(df: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("## A.4 — Ecorregión E03")
    eco = df[df["eco_dom_id"].astype(int) == 3]
    if eco.empty:
        lineas.append("Sin candidatos con eco_dom_id=3.")
    else:
        v = pd.to_numeric(eco["valid_area_pct"], errors="coerce")
        lineas.append(f"- Candidatos: {len(eco)} · `valid_area_pct` medio: {v.mean():.1f}%")
        lineas.append(f"- Superan 40% valid_area: {(v >= 40).sum()} · superan 30%: {(v >= 30).sum()}")
    lineas.append("")


def _diagnostico_seleccion(sel: pd.DataFrame, lineas: list[str]) -> None:
    lineas.append("## Problemas confirmados en selección")
    if "modo_tratamiento" in sel.columns and "clase_objetivo" in sel.columns:
        cr = sel[sel["modo_tratamiento"].isin(["censo", "refuerzo"])]
        fuera = cr[~cr["clase_objetivo"].isin(CLASES_MODELO_GENERAL)]
        lineas.append(
            f"- Censo/refuerzo fuera de CLASES_MODELO_GENERAL: **{len(fuera)}** rectángulos"
        )
        if not fuera.empty:
            top = fuera["clase_objetivo"].value_counts().head(10)
            for cid, n in top.items():
                nombre = CLASS_NAMES.get(int(cid), f"DESCONOCIDO_{cid}")
                lineas.append(f"  - clase {int(cid)} ({nombre}): {n}")

        c0 = cr[cr["clase_objetivo"] == 0]
        lineas.append(f"- Censo/refuerzo clase 0: **{len(c0)}**")

        c3 = cr[cr["clase_objetivo"] == 3]
        lineas.append(f"- Censo/refuerzo clase 3 (tamarugo): **{len(c3)}**")

    if "split" in sel.columns:
        lineas.append(
            f"- Split nacional: train={( sel['split']=='train').sum()} · "
            f"val={(sel['split']=='val').sum()} · test={(sel['split']=='test').sum()}"
        )
        if "eco_dom_id" in sel.columns:
            sin_test = []
            for eco_id, grp in sel.groupby("eco_dom_id"):
                if (grp["split"] == "test").sum() == 0:
                    sin_test.append(int(eco_id))
            lineas.append(f"- Ecorregiones sin test: {sin_test}")
    lineas.append("")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnóstico de corrida caracterización + selección")
    parser.add_argument("--caracterizacion", required=True, help="run_tag caracterización")
    parser.add_argument("--seleccion", required=True, help="run_tag selección")
    parser.add_argument("--salida", type=Path, default=None, help="Markdown de salida")
    args = parser.parse_args()

    salida = args.salida or (
        REPO / "diagnostico" / f"diagnostico_{args.caracterizacion}_{args.seleccion}.md"
    )
    salida.parent.mkdir(parents=True, exist_ok=True)
    lineas: list[str] = [
        f"# Diagnóstico — caracterización `{args.caracterizacion}` · selección `{args.seleccion}`",
        "",
    ]

    print(f"Cargando caracterización {args.caracterizacion}…")
    df = _cargar_caracterizacion(args.caracterizacion)
    print(f"  {len(df)} rectángulos en parquet por_tile")

    recaracterizar = _diagnostico_clase0(df, lineas)
    _diagnostico_tamarugo(df, lineas)
    _diagnostico_estable_simple(df, lineas)

    print(f"Cargando selección {args.seleccion}…")
    sel, sel_dir = _cargar_seleccion(args.seleccion)
    _diagnostico_pools_seleccion(sel_dir, lineas)
    _diagnostico_e03(df, lineas)
    _diagnostico_seleccion(sel, lineas)

    lineas.append("## A.5 — Criterio de decisión")
    if recaracterizar:
        lineas.append("**→ RECARACTERIZAR (Etapa B completa)** — existe `pct_0` con valores > 1%.")
        decision = "RECARACTERIZAR"
    else:
        lineas.append(
            "**→ Saltar Etapa B** — no hay columna `pct_0` con valores > 1%. "
            "Ir directo a Etapa C (corrección de selección)."
        )
        lineas.append("")
        lineas.append(
            "*Nota:* persisten otros hallazgos (clase 0 como `lulc_mode_id`, suma pct < 100, "
            "CRS consolidado en WGS84). Las correcciones B quedan en código para la próxima caracterización."
        )
        decision = "SALTAR_ETAPA_B"

    texto = "\n".join(lineas) + "\n"
    salida.write_text(texto, encoding="utf-8")

    print("\n" + "=" * 60)
    print(texto)
    print("=" * 60)
    print(f"Decisión A.5: {decision}")
    print(f"Informe guardado en {salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
