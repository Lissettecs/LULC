#!/usr/bin/env python3
"""
09 — Genera informe_seleccion.md para una corrida de selección.

Compara contra la baseline de producción (por defecto 20260724_1357) e incluye
la tabla de expectativa vs resultado.

Uso:
  python scripts/09_generar_informe_seleccion.py --seleccion TAG
  python scripts/09_generar_informe_seleccion.py --seleccion 20260727_1340 \\
      --baseline 20260724_1357 --caracterizacion 20260727_1004
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_seleccion as P
from config.corridas_ref import CARACT_RUN_REF, SEL_BASELINE_REF
from config.diccionarios import CLASS_NAMES, ECO_NAMES

BASELINE_DEFAULT = SEL_BASELINE_REF
CARACT_DEFAULT = CARACT_RUN_REF

# Expectativa de resultado — corrección v03 (anotada antes de correr)
EXPECTATIVA_V03 = {
    "n_rects": "180–240",
    "pct_relleno": "≤ 30 %",
    "celdas_vacias": "Menos de 15",
    "ecos_train_lt_50": "0",
    "ecos_train_0": "0",
    "mix_2x2_3x3": "3×3 bastante por encima de 74",
    "n_pares": "0",
    "suma_vs_union": "Iguales dentro de 0,1 %",
    "tamarugo_e2": "≥ 60 %",
}


def _eco_label(eco_id: int) -> str:
    raw = ECO_NAMES.get(int(eco_id), f"E{int(eco_id)}")
    # E1_Nombre → Nombre legible
    if "_" in raw:
        parts = raw.split("_", 1)
        return parts[1].replace("_", " ")
    return raw


def _eco_code(eco_id: int) -> str:
    return f"E{int(eco_id):02d}"


def resolver_run_dir(tag_o_path: str, root: Path) -> Path:
    """Acepta TAG o path absoluto/relativo a un directorio de corrida."""
    p = Path(tag_o_path)
    if p.is_dir():
        return p.resolve()
    cand = root / str(tag_o_path)
    if cand.is_dir():
        return cand.resolve()
    raise FileNotFoundError(
        f"No se encontró corrida de selección '{tag_o_path}' "
        f"(ni como path ni bajo {root})"
    )


def _leer_csv(path: Path) -> pd.DataFrame | None:
    if not path.is_file():
        return None
    return pd.read_csv(path)


def _leer_json(path: Path) -> dict:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _fmt_n(n: float | int | None, dec: int = 0) -> str:
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    if dec == 0:
        return f"{int(round(n)):,}".replace(",", " ")
    return f"{n:,.{dec}f}".replace(",", " ")


def _fmt_pct(frac: float | None, dec: int = 1) -> str:
    if frac is None or (isinstance(frac, float) and pd.isna(frac)):
        return "—"
    return f"{100 * frac:.{dec}f} %"


def _delta(a, b, as_int: bool = True) -> str:
    if a is None or b is None:
        return "—"
    try:
        d = float(b) - float(a)
    except (TypeError, ValueError):
        return "—"
    if as_int:
        d = int(round(d))
        return f"+{d}" if d > 0 else str(d)
    return f"{d:+.1f}"


def _col_estado(celdas: pd.DataFrame) -> pd.Series:
    if "estado" in celdas.columns:
        return celdas["estado"].astype(str).str.lower()
    if "cobertura" in celdas.columns:
        return celdas["cobertura"].astype(str).str.lower()
    return pd.Series(["desconocido"] * len(celdas), index=celdas.index)


def indicadores(run_dir: Path) -> dict:
    """Calcula indicadores clave de una corrida de selección."""
    sel = _leer_csv(run_dir / "seleccion_nacional.csv")
    if sel is None or sel.empty:
        raise FileNotFoundError(f"Falta seleccion_nacional.csv en {run_dir}")

    n = len(sel)
    n_relleno = int((sel.get("pool_origen", pd.Series(dtype=str)) == "relleno").sum())
    pct_relleno = n_relleno / max(n, 1)

    side = pd.to_numeric(sel.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    n2 = int((side == 2).sum())
    n3 = int((side == 3).sum())
    tot_side = n2 + n3
    pct2 = n2 / tot_side if tot_side else None
    pct3 = n3 / tot_side if tot_side else None

    # Split por eco
    ecos_train_lt_50 = 0
    ecos_train_0 = 0
    split_inviable = []
    por_eco = []
    if "eco_dom_id" in sel.columns and "split" in sel.columns:
        for eco_id, grp in sel.groupby(sel["eco_dom_id"].astype(int)):
            n_eco = len(grp)
            n_tr = int((grp["split"] == "train").sum())
            n_va = int((grp["split"] == "val").sum())
            n_te = int((grp["split"] == "test").sum())
            pct_tr = n_tr / max(n_eco, 1)
            invi = False
            if "split_inviable" in grp.columns:
                invi = bool(grp["split_inviable"].astype(str).str.lower().isin(["true", "1"]).any())
            if not invi and pct_tr < float(getattr(P, "SPLIT_MIN_PCT_TRAIN", 0.50)):
                ecos_train_lt_50 += 1
            if n_tr == 0:
                ecos_train_0 += 1
            if invi:
                split_inviable.append(_eco_code(eco_id))
            por_eco.append(
                {
                    "eco_id": int(eco_id),
                    "n": n_eco,
                    "train": n_tr,
                    "val": n_va,
                    "test": n_te,
                    "pct_train": pct_tr,
                    "pct_val": n_va / max(n_eco, 1),
                    "pct_test": n_te / max(n_eco, 1),
                    "inviable": invi,
                    "valid_area": float(pd.to_numeric(grp.get("valid_area_pct"), errors="coerce").mean())
                    if "valid_area_pct" in grp.columns
                    else None,
                    "mode_pct": float(pd.to_numeric(grp.get("lulc_mode_pct"), errors="coerce").mean())
                    if "lulc_mode_pct" in grp.columns
                    else None,
                }
            )

    # Celdas
    celdas = _leer_csv(run_dir / "auditoria_cobertura_celdas.csv")
    n_vacias = n_parcial = n_cubiertas = n_celdas = None
    if celdas is not None and not celdas.empty:
        est = _col_estado(celdas)
        n_celdas = len(celdas)
        n_vacias = int((est == "vacia").sum())
        n_parcial = int((est == "parcial").sum())
        n_cubiertas = int(est.isin(["cubierta", "cubierto"]).sum())

    marg = _leer_csv(run_dir / "auditoria_cobertura_celdas_marginales.csv")
    n_marginales = len(marg) if marg is not None else 0

    # Solape
    solape = _leer_csv(run_dir / "auditoria_solape.csv")
    suma_km2 = union_km2 = n_pares = diff_rel = None
    if solape is not None and not solape.empty:
        row = solape.iloc[0]
        suma_km2 = float(row.get("suma_km2", float("nan")))
        union_km2 = float(row.get("union_km2", float("nan")))
        n_pares = int(row.get("n_pares_intersectan", -1))
        if pd.notna(suma_km2) and suma_km2 > 0 and pd.notna(union_km2):
            diff_rel = abs(suma_km2 - union_km2) / suma_km2

    # Tamarugo E2
    tamarugo_e2_pct = None
    tamarugo_e2_rects = None
    tamarugo_e2_estado = None
    if celdas is not None and not celdas.empty:
        eco_col = "eco_id" if "eco_id" in celdas.columns else "ecorregion_id"
        cid_col = "class_id" if "class_id" in celdas.columns else "clase_id"
        sub = celdas[(celdas[eco_col].astype(int) == 2) & (celdas[cid_col].astype(int) == 3)]
        if not sub.empty:
            r = sub.iloc[0]
            tamarugo_e2_rects = int(r.get("n_rects_con_clase", 0) or 0)
            tamarugo_e2_estado = str(r.get("estado", r.get("cobertura", "")))
            if "pct_clase_cubierto" in sub.columns and pd.notna(r.get("pct_clase_cubierto")):
                tamarugo_e2_pct = float(r["pct_clase_cubierto"])

    # Split nacional
    n_train = int((sel.get("split", "") == "train").sum()) if "split" in sel.columns else 0
    n_val = int((sel.get("split", "") == "val").sum()) if "split" in sel.columns else 0
    n_test = int((sel.get("split", "") == "test").sum()) if "split" in sel.columns else 0

    n_censo = int((sel.get("modo_tratamiento", "") == "censo").sum()) if "modo_tratamiento" in sel.columns else 0
    n_refuerzo = int((sel.get("modo_tratamiento", "") == "refuerzo").sum()) if "modo_tratamiento" in sel.columns else 0

    area_km2 = float(pd.to_numeric(sel.get("area_km2"), errors="coerce").sum()) if "area_km2" in sel.columns else None

    summary = _leer_json(run_dir / "summary.json")
    deficit = _leer_csv(run_dir / "deficit_celdas.csv")
    no_asig = _leer_csv(run_dir / "presupuesto_no_asignado.csv")

    return {
        "tag": run_dir.name,
        "run_dir": run_dir,
        "sel": sel,
        "celdas": celdas,
        "marginales": marg,
        "deficit": deficit,
        "no_asignado": no_asig,
        "summary": summary,
        "n": n,
        "n_unicos": int(sel["grid_id"].nunique()) if "grid_id" in sel.columns else n,
        "n_ecos": int(sel["eco_dom_id"].nunique()) if "eco_dom_id" in sel.columns else 0,
        "n_relleno": n_relleno,
        "pct_relleno": pct_relleno,
        "n2": n2,
        "n3": n3,
        "pct2": pct2,
        "pct3": pct3,
        "ecos_train_lt_50": ecos_train_lt_50,
        "ecos_train_0": ecos_train_0,
        "split_inviable": split_inviable,
        "por_eco": sorted(por_eco, key=lambda x: x["eco_id"]),
        "n_vacias": n_vacias,
        "n_parcial": n_parcial,
        "n_cubiertas": n_cubiertas,
        "n_celdas": n_celdas,
        "n_marginales": n_marginales,
        "suma_km2": suma_km2,
        "union_km2": union_km2,
        "n_pares": n_pares,
        "diff_rel": diff_rel,
        "tamarugo_e2_pct": tamarugo_e2_pct,
        "tamarugo_e2_rects": tamarugo_e2_rects,
        "tamarugo_e2_estado": tamarugo_e2_estado,
        "n_train": n_train,
        "n_val": n_val,
        "n_test": n_test,
        "n_censo": n_censo,
        "n_refuerzo": n_refuerzo,
        "area_km2": area_km2,
    }


def _fmt_tamarugo(ind: dict) -> str:
    if ind["tamarugo_e2_pct"] is not None:
        return _fmt_pct(ind["tamarugo_e2_pct"])
    if ind["tamarugo_e2_rects"] is not None:
        est = ind["tamarugo_e2_estado"] or "?"
        return f"{ind['tamarugo_e2_rects']} rects ({est})"
    return "—"


def _fmt_celdas(ind: dict) -> str:
    if ind["n_vacias"] is None:
        return "—"
    return f"{ind['n_vacias']} / {ind['n_celdas']}"


def _fmt_mix(ind: dict) -> str:
    if ind["pct2"] is None:
        return "—"
    return (
        f"{ind['n2']} / {ind['n3']} "
        f"({100 * ind['pct2']:.0f} / {100 * ind['pct3']:.0f})"
    )


def _fmt_suma_union(ind: dict) -> str:
    if ind["suma_km2"] is None:
        return "Sin reportar"
    d = ind["diff_rel"]
    d_txt = f"{100 * d:.1f} %" if d is not None else "—"
    return (
        f"suma {_fmt_n(ind['suma_km2'], 1)} · "
        f"unión {_fmt_n(ind['union_km2'], 1)} · "
        f"Δ {d_txt}"
    )


def _tabla_comparacion(base: dict, cur: dict) -> list[str]:
    filas = [
        ("Rectángulos totales", base["n"], cur["n"], True),
        ("Relleno (n)", base["n_relleno"], cur["n_relleno"], True),
        ("Relleno (%)", round(100 * base["pct_relleno"], 1), round(100 * cur["pct_relleno"], 1), False),
        ("Celdas vacías", base["n_vacias"], cur["n_vacias"], True),
        ("Celdas auditadas", base["n_celdas"], cur["n_celdas"], True),
        ("Ecos train < 50 %", base["ecos_train_lt_50"], cur["ecos_train_lt_50"], True),
        ("Ecos train = 0", base["ecos_train_0"], cur["ecos_train_0"], True),
        ("2×2", base["n2"], cur["n2"], True),
        ("3×3", base["n3"], cur["n3"], True),
        ("Pares que intersectan", base["n_pares"], cur["n_pares"], True),
        ("Censo", base["n_censo"], cur["n_censo"], True),
        ("Refuerzo", base["n_refuerzo"], cur["n_refuerzo"], True),
        ("Split train", base["n_train"], cur["n_train"], True),
        ("Split val", base["n_val"], cur["n_val"], True),
        ("Split test", base["n_test"], cur["n_test"], True),
    ]
    lines = [
        f"| Indicador | `{base['tag']}` | `{cur['tag']}` | Δ |",
        "|-----------|--------------:|--------------:|--:|",
    ]
    for nombre, a, b, as_int in filas:
        av = "—" if a is None else (_fmt_n(a) if as_int else f"{a}")
        bv = "—" if b is None else (_fmt_n(b) if as_int else f"{b}")
        lines.append(f"| {nombre} | {av} | {bv} | {_delta(a, b, as_int)} |")
    # Tamarugo y solape como texto
    lines.append(
        f"| Cobertura tamarugo E02 | {_fmt_tamarugo(base)} | {_fmt_tamarugo(cur)} | — |"
    )
    lines.append(
        f"| Suma vs unión | {_fmt_suma_union(base)} | {_fmt_suma_union(cur)} | — |"
    )
    return lines


def _tabla_expectativa(base: dict, cur: dict) -> list[str]:
    filas = [
        ("Rectángulos totales", _fmt_n(base["n"]), _fmt_n(cur["n"]), EXPECTATIVA_V03["n_rects"]),
        (
            "Relleno",
            f"{base['n_relleno']} ({_fmt_pct(base['pct_relleno'])})",
            f"{cur['n_relleno']} ({_fmt_pct(cur['pct_relleno'])})",
            EXPECTATIVA_V03["pct_relleno"],
        ),
        ("Celdas vacías", _fmt_celdas(base), _fmt_celdas(cur), EXPECTATIVA_V03["celdas_vacias"]),
        (
            "Ecorregiones con train < 50 %",
            str(base["ecos_train_lt_50"]),
            str(cur["ecos_train_lt_50"]),
            EXPECTATIVA_V03["ecos_train_lt_50"],
        ),
        (
            "Ecorregiones con train = 0",
            str(base["ecos_train_0"]),
            str(cur["ecos_train_0"]),
            EXPECTATIVA_V03["ecos_train_0"],
        ),
        ("Mix 2×2 / 3×3", _fmt_mix(base), _fmt_mix(cur), EXPECTATIVA_V03["mix_2x2_3x3"]),
        (
            "Pares que se intersectan",
            "Sin reportar" if base["n_pares"] is None else str(base["n_pares"]),
            "Sin reportar" if cur["n_pares"] is None else str(cur["n_pares"]),
            EXPECTATIVA_V03["n_pares"],
        ),
        (
            "Suma de áreas vs. unión",
            _fmt_suma_union(base),
            _fmt_suma_union(cur),
            EXPECTATIVA_V03["suma_vs_union"],
        ),
        (
            "Cobertura de tamarugo en E02",
            _fmt_tamarugo(base) if base["tamarugo_e2_pct"] is not None else "~40 % (ref. v03)",
            _fmt_tamarugo(cur),
            EXPECTATIVA_V03["tamarugo_e2"],
        ),
    ]
    lines = [
        "| Indicador | Baseline | Resultado | Esperado (v03) |",
        "|-----------|--------:|----------:|---------------:|",
    ]
    for nom, b, c, exp in filas:
        lines.append(f"| {nom} | {b} | {c} | {exp} |")
    return lines


def generar_markdown(
    cur: dict,
    base: dict,
    caract_tag: str | None,
) -> str:
    tag = cur["tag"]
    base_tag = base["tag"]
    hoy = date.today().isoformat()
    summary = cur["summary"]
    grid_run = summary.get("grid_run", "")
    if caract_tag:
        caract_txt = f"01_caracterizacion/{caract_tag}"
    elif grid_run:
        caract_txt = str(grid_run).replace(str(P.DATA_ROOT) + "/", "")
    else:
        caract_txt = "—"

    mismo = cur["run_dir"] == base["run_dir"]
    sel = cur["sel"]
    n = cur["n"]

    lines: list[str] = []
    lines.append("# Informe de selección de rectángulos SSL4EO v02")
    lines.append("")
    lines.append(f"**Corrida:** `{tag}`  ")
    lines.append(f"**Fecha de generación:** {hoy}  ")
    lines.append(f"**Caracterización base:** `{caract_txt}`  ")
    lines.append(f"**Directorio:** `{cur['run_dir']}/`  ")
    lines.append(f"**Corrida de referencia (comparación):** `{base_tag}`")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 1. Resumen ejecutivo ──
    lines.append("## 1. Resumen ejecutivo")
    lines.append("")
    lines.append("| Indicador | Valor |")
    lines.append("|-----------|------:|")
    lines.append(f"| Rectángulos seleccionados | **{_fmt_n(n)}** |")
    lines.append(f"| `grid_id` únicos | {_fmt_n(cur['n_unicos'])} |")
    lines.append(f"| Ecorregiones cubiertas | {cur['n_ecos']} / 15 |")
    if cur["area_km2"] is not None:
        lines.append(f"| Superficie total aprox. (`area_km2`) | {_fmt_n(cur['area_km2'], 0)} km² |")
    if cur["suma_km2"] is not None:
        lines.append(f"| Suma geométrica de áreas | {_fmt_n(cur['suma_km2'], 1)} km² |")
        lines.append(f"| Unión geométrica de áreas | {_fmt_n(cur['union_km2'], 1)} km² |")
    lines.append(f"| Presupuesto nacional de segmentos | {_fmt_n(P.PRESUPUESTO_SEGMENTOS_TOTAL)} |")
    lines.append(f"| Censo + refuerzo | {cur['n_censo'] + cur['n_refuerzo']} |")
    lines.append(f"| Rectángulos relleno | {cur['n_relleno']} ({_fmt_pct(cur['pct_relleno'])}) |")
    lines.append(f"| Celdas clase×eco vacías | {_fmt_celdas(cur)} |")
    lines.append(f"| Ecorregiones con `split_inviable` | {len(cur['split_inviable'])} |")
    lines.append(
        f"| Pares que se intersectan | "
        f"{'Sin reportar' if cur['n_pares'] is None else cur['n_pares']} |"
    )
    lines.append(f"| Ecos con train < 50 % | {cur['ecos_train_lt_50']} |")
    lines.append(f"| Ecos con train = 0 | {cur['ecos_train_0']} |")
    lines.append(f"| Mix 2×2 / 3×3 | {_fmt_mix(cur)} |")
    lines.append(f"| Cobertura tamarugo E02 | {_fmt_tamarugo(cur)} |")
    lines.append("")
    if mismo:
        lines.append(
            "Informe de la **baseline** de referencia para la corrección v03 "
            "(cobertura de clases raras, split y tope de relleno)."
        )
    else:
        lines.append(
            f"Corrida comparada contra la baseline `{base_tag}` "
            "(corrección v03: piso de presencia por ha, techo de split, tope de relleno, "
            "tracker de solape y cobertura de clases raras)."
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 2. Comparación + expectativa ──
    lines.append(f"## 2. Comparación contra `{base_tag}`")
    lines.append("")
    lines.append("### 2.1 Indicadores globales")
    lines.append("")
    lines.extend(_tabla_comparacion(base, cur))
    lines.append("")
    lines.append("### 2.2 Expectativa vs resultado (corrección v03)")
    lines.append("")
    lines.append(
        "Valores esperados anotados **antes** de la corrida v03, para contrastar "
        "el efecto del piso de presencia, el orden 3×3→2×2, el tope de relleno "
        "y el tracker de solape."
    )
    lines.append("")
    lines.extend(_tabla_expectativa(base, cur))
    lines.append("")
    lines.append(
        "> **Nota:** el total de rectángulos debe bajar respecto de la baseline. "
        "Con los 3×3 seleccionados primero y el tracker activo, cada 3×3 ocupa el "
        "equivalente a ~2,25 rectángulos 2×2. Menos rectángulos con más contexto "
        "espacial es el resultado buscado."
    )
    lines.append("")

    # Por ecorregión (conteos)
    lines.append("### 2.3 Rectángulos por ecorregión")
    lines.append("")
    lines.append(f"| Eco | Nombre | `{base_tag}` | `{tag}` | Δ |")
    lines.append("|-----|--------|--------------:|--------------:|--:|")
    base_eco = {e["eco_id"]: e["n"] for e in base["por_eco"]}
    cur_eco = {e["eco_id"]: e["n"] for e in cur["por_eco"]}
    for eid in range(1, 16):
        a = base_eco.get(eid, 0)
        b = cur_eco.get(eid, 0)
        lines.append(
            f"| {_eco_code(eid)} | {_eco_label(eid)} | {a} | {b} | {_delta(a, b)} |"
        )
    lines.append("")

    # Modo / pool
    lines.append("### 2.4 Por modo de tratamiento")
    lines.append("")
    modes = sorted(
        set(base["sel"].get("modo_tratamiento", pd.Series(dtype=str)).dropna().astype(str))
        | set(cur["sel"].get("modo_tratamiento", pd.Series(dtype=str)).dropna().astype(str))
    )
    lines.append(f"| Modo | `{base_tag}` | `{tag}` |")
    lines.append("|------|--------------:|--------------:|")
    for m in modes:
        a = int((base["sel"].get("modo_tratamiento", "") == m).sum())
        b = int((cur["sel"].get("modo_tratamiento", "") == m).sum())
        lines.append(f"| {m} | {a} | {b} |")
    # relleno como pool
    a_rel = base["n_relleno"]
    b_rel = cur["n_relleno"]
    lines.append(f"| relleno (pool) | {a_rel} | {b_rel} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 3. Solape ──
    lines.append("## 3. Solape geométrico")
    lines.append("")
    lines.append(
        "Tres cifras obligatorias (auditoría al cierre). "
        "No basta con afirmar que no hay solapes."
    )
    lines.append("")
    lines.append("| Cifra | Valor |")
    lines.append("|-------|------:|")
    if cur["suma_km2"] is None:
        lines.append("| Suma de áreas (km²) | *Sin `auditoria_solape.csv`* |")
        lines.append("| Unión de áreas (km²) | — |")
        lines.append("| Pares que se intersectan | — |")
        lines.append("")
        lines.append(
            "> Archivo `auditoria_solape.csv` ausente. "
            "Regenerar la selección con el cierre B.10 para obtener las tres cifras."
        )
    else:
        lines.append(f"| Suma de áreas (km²) | **{_fmt_n(cur['suma_km2'], 4)}** |")
        lines.append(f"| Unión de áreas (km²) | **{_fmt_n(cur['union_km2'], 4)}** |")
        lines.append(f"| Pares que se intersectan | **{cur['n_pares']}** |")
        if cur["diff_rel"] is not None:
            ok = cur["n_pares"] == 0 and cur["diff_rel"] <= 0.001
            lines.append(
                f"| Diff relativa \|suma−unión\|/suma | "
                f"{100 * cur['diff_rel']:.4f} % "
                f"({'OK' if ok else 'FALLA'}) |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 4. Parámetros ──
    lines.append("## 4. Insumos y parámetros")
    lines.append("")
    lines.append("| Parámetro | Valor |")
    lines.append("|-----------|-------|")
    lines.append(f"| Presupuesto total segmentos | {_fmt_n(P.PRESUPUESTO_SEGMENTOS_TOTAL)} |")
    lines.append(f"| `PISO_PRESENCIA_HA` | {getattr(P, 'PISO_PRESENCIA_HA', '—')} |")
    lines.append(f"| `COBERTURA_OBJETIVO_RARAS` | {getattr(P, 'COBERTURA_OBJETIVO_RARAS', '—')} |")
    lines.append(f"| `COBERTURA_OBJETIVO_CENSO` | {getattr(P, 'COBERTURA_OBJETIVO_CENSO', '—')} |")
    lines.append(f"| `SPLIT_MIN_PCT_TRAIN` | {getattr(P, 'SPLIT_MIN_PCT_TRAIN', '—')} |")
    lines.append(f"| `SPLIT_MARGEN_TECHO` | {getattr(P, 'SPLIT_MARGEN_TECHO', '—')} |")
    lines.append(f"| `TOPE_RELLENO_PCT` | {getattr(P, 'TOPE_RELLENO_PCT', '—')} |")
    lines.append(f"| `ORDEN_TAMANOS` / `RELLENO_ORDEN_TAMANOS` | {getattr(P, 'ORDEN_TAMANOS', '—')} |")
    lines.append(f"| `CENSO_PARTICIPA_SPLIT` | {P.CENSO_PARTICIPA_SPLIT} |")
    lines.append(f"| `SPLIT_MIN_CLUSTERS` | {P.SPLIT_MIN_CLUSTERS} |")
    lines.append(
        f"| Filtro base | valid_area ≥ {P.FILTRO_BASE['valid_area_pct']} %, "
        f"eco_dom ≥ {P.FILTRO_BASE['eco_dom_pct']} %, "
        f"noobs ≤ {P.FILTRO_BASE['noobs_pct']} % |"
    )
    lines.append(
        f"| Split objetivo | train {100 * P.SPLIT_PROPORCIONES['train']:.0f} % · "
        f"val {100 * P.SPLIT_PROPORCIONES['val']:.0f} % · "
        f"test {100 * P.SPLIT_PROPORCIONES['test']:.0f} % |"
    )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 5. Composición ──
    lines.append("## 5. Composición de la selección")
    lines.append("")
    lines.append("### 5.1 Por tipo de muestra")
    lines.append("")
    if "sample_type" in sel.columns:
        lines.append("| Tipo | N | % |")
        lines.append("|------|--:|--:|")
        vc = sel["sample_type"].fillna("?").astype(str).value_counts()
        for tipo, cnt in vc.items():
            lines.append(f"| {tipo} | {cnt} | {100 * cnt / n:.1f} |")
    else:
        lines.append("*Sin columna `sample_type`.*")
    lines.append("")
    lines.append("### 5.2 Por tamaño de rectángulo")
    lines.append("")
    lines.append(f"- **2×2:** {cur['n2']} ({_fmt_pct(cur['pct2'])})")
    lines.append(f"- **3×3:** {cur['n3']} ({_fmt_pct(cur['pct3'])})")
    lines.append("")
    if "utm_zone" in sel.columns:
        lines.append("### 5.3 Por huso UTM")
        lines.append("")
        for z, cnt in sel["utm_zone"].value_counts().sort_index().items():
            lines.append(f"- **UTM {int(z)}:** {cnt} ({100 * cnt / n:.1f} %)")
        lines.append("")
    lines.append("---")
    lines.append("")

    # ── 6. Split ──
    lines.append("## 6. Split train / validation / test")
    lines.append("")
    lines.append("### 6.1 Nacional")
    lines.append("")
    lines.append("| Split | N | % |")
    lines.append("|-------|--:|--:|")
    for nombre, cnt in (("train", cur["n_train"]), ("val", cur["n_val"]), ("test", cur["n_test"])):
        lines.append(f"| {nombre} | {cnt} | {100 * cnt / max(n, 1):.1f} |")
    lines.append("")
    invi = ", ".join(cur["split_inviable"]) if cur["split_inviable"] else "ninguna"
    lines.append(f"**Ecorregiones `split_inviable`:** {invi}.")
    lines.append("")
    lines.append("### 6.2 Por ecorregión")
    lines.append("")
    lines.append(
        "| Eco | Nombre | N | Train | Val | Test | "
        "Train % | Val % | Test % | Inviable |"
    )
    lines.append(
        "|-----|--------|--:|------:|----:|-----:|"
        "-------:|------:|-------:|:--------:|"
    )
    for e in cur["por_eco"]:
        lines.append(
            f"| {_eco_code(e['eco_id'])} | {_eco_label(e['eco_id'])} | "
            f"{e['n']} | {e['train']} | {e['val']} | {e['test']} | "
            f"{100 * e['pct_train']:.1f} | {100 * e['pct_val']:.1f} | "
            f"{100 * e['pct_test']:.1f} | "
            f"{'Sí' if e['inviable'] else 'No'} |"
        )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 7. Cobertura ──
    lines.append("## 7. Cobertura de celdas clase × ecorregión")
    lines.append("")
    celdas = cur["celdas"]
    if celdas is None or celdas.empty:
        lines.append("*Sin `auditoria_cobertura_celdas.csv`.*")
    else:
        est = _col_estado(celdas)
        lines.append("| Estado | N | % |")
        lines.append("|--------|--:|--:|")
        for estado in ("cubierta", "parcial", "vacia"):
            cnt = int((est == estado).sum())
            label = f"**{estado}**" if estado == "vacia" else estado
            lines.append(f"| {label} | {cnt} | {100 * cnt / len(celdas):.1f} |")
        lines.append(f"| Total auditadas | {len(celdas)} | 100 |")
        if cur["n_marginales"]:
            lines.append(
                f"| Marginales (archivo aparte) | {cur['n_marginales']} | — |"
            )
        lines.append("")

        # Clases raras / censo-refuerzo con pct_clase_cubierto
        lines.append("### 7.1 Cobertura de clases raras (`pct_clase_cubierto`)")
        lines.append("")
        if "pct_clase_cubierto" not in celdas.columns:
            lines.append(
                "*Columna `pct_clase_cubierto` ausente (corrida anterior a B.6). "
                "Regenerar selección para obtener cobertura de superficie.*"
            )
        else:
            sub = celdas[celdas["modo"].isin(["censo", "refuerzo"])].copy()
            if sub.empty:
                lines.append("*Sin celdas en modo censo/refuerzo.*")
            else:
                lines.append(
                    "| Eco | Clase | Modo | Rects | "
                    "`pct_clase_cubierto` | Objetivo | Cumple | Estado |"
                )
                lines.append(
                    "|-----|-------|------|------:|"
                    "--------------------:|---------:|:------:|--------|"
                )
                eco_c = "eco_id" if "eco_id" in sub.columns else "ecorregion_id"
                cid_c = "class_id" if "class_id" in sub.columns else "clase_id"
                sub = sub.sort_values([eco_c, cid_c])
                for _, r in sub.iterrows():
                    pct = r.get("pct_clase_cubierto")
                    pct_txt = f"{100 * float(pct):.1f} %" if pd.notna(pct) else "—"
                    obj = r.get("cobertura_objetivo")
                    obj_txt = f"{100 * float(obj):.0f} %" if pd.notna(obj) else "—"
                    cumple = r.get("cumple_objetivo")
                    if pd.isna(cumple):
                        cumple_txt = "—"
                    else:
                        cumple_txt = "Sí" if bool(cumple) else "No"
                    estado = str(r.get("estado", r.get("cobertura", "")))
                    lines.append(
                        f"| {_eco_code(int(r[eco_c]))} | "
                        f"{r.get('clase', CLASS_NAMES.get(int(r[cid_c]), r[cid_c]))} "
                        f"({int(r[cid_c])}) | {r['modo']} | "
                        f"{int(r.get('n_rects_con_clase', 0))} | "
                        f"{pct_txt} | {obj_txt} | {cumple_txt} | {estado} |"
                    )
        lines.append("")

        # Vacías
        vacias = celdas[est == "vacia"]
        if not vacias.empty:
            lines.append("### 7.2 Celdas vacías")
            lines.append("")
            lines.append("| Eco | Clase | Modo | Cuota |")
            lines.append("|-----|-------|------|------:|")
            eco_c = "eco_id" if "eco_id" in vacias.columns else "ecorregion_id"
            cid_c = "class_id" if "class_id" in vacias.columns else "clase_id"
            for _, r in vacias.head(25).iterrows():
                lines.append(
                    f"| {_eco_code(int(r[eco_c]))} | "
                    f"{r.get('clase', '?')} ({int(r[cid_c])}) | "
                    f"{r.get('modo', '?')} | {int(r.get('cuota_rects', 0) or 0)} |"
                )
            if len(vacias) > 25:
                lines.append(f"| … | +{len(vacias) - 25} celdas | | |")
            lines.append("")

        # Tamarugo
        lines.append("### 7.3 Tamarugo (clase 3)")
        lines.append("")
        eco_c = "eco_id" if "eco_id" in celdas.columns else "ecorregion_id"
        cid_c = "class_id" if "class_id" in celdas.columns else "clase_id"
        tam = celdas[celdas[cid_c].astype(int) == 3].sort_values(eco_c)
        if tam.empty:
            lines.append("*Sin celdas de clase 3 en la auditoría.*")
        else:
            for _, r in tam.iterrows():
                pct = r.get("pct_clase_cubierto")
                pct_txt = (
                    f", cobertura superficie **{_fmt_pct(float(pct))}**"
                    if pd.notna(pct)
                    else ""
                )
                lines.append(
                    f"- **{_eco_code(int(r[eco_c]))}:** "
                    f"{int(r.get('n_rects_con_clase', 0))} rects, "
                    f"estado **{r.get('estado', r.get('cobertura', '?'))}**, "
                    f"modo {r.get('modo', '?')}{pct_txt}"
                )
            lines.append("")
            lines.append(
                "> Si E01 permanece vacía incluso con piso de 50 ha, no es un problema "
                "de umbral: el área de clase está muy dispersa. Registrar como hallazgo, "
                "no como déficit corregible."
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 8. Censo/refuerzo ──
    lines.append("## 8. Censo y refuerzo (solo modelo general)")
    lines.append("")
    lines.append(f"Censo: **{cur['n_censo']}** · Refuerzo: **{cur['n_refuerzo']}**")
    lines.append("")
    if "modo_tratamiento" in sel.columns and "clase_objetivo" in sel.columns:
        sub = sel[sel["modo_tratamiento"].isin(["censo", "refuerzo"])]
        if not sub.empty:
            lines.append("| Clase | Nombre | N | Modo |")
            lines.append("|------:|--------|--:|------|")
            grp = (
                sub.groupby(["clase_objetivo", "modo_tratamiento"], dropna=False)
                .size()
                .reset_index(name="n")
                .sort_values("n", ascending=False)
            )
            for _, r in grp.iterrows():
                cid = int(r["clase_objetivo"])
                lines.append(
                    f"| {cid} | {CLASS_NAMES.get(cid, str(cid))} | "
                    f"{int(r['n'])} | {r['modo_tratamiento']} |"
                )
            lines.append("")
    lines.append("---")
    lines.append("")

    # ── 9. Déficits ──
    lines.append("## 9. Déficits censo/refuerzo")
    lines.append("")
    defi = cur["deficit"]
    if defi is None or defi.empty:
        lines.append("Sin déficits registrados (`deficit_celdas.csv` vacío o ausente).")
    else:
        lines.append("| Eco | Clase | Modo | Cuota | Sel. | Déficit |")
        lines.append("|-----|-------|------|------:|-----:|--------:|")
        for _, r in defi.iterrows():
            eid = int(r.get("ecorregion_id", r.get("eco_id", 0)))
            cid = int(r.get("clase_id", r.get("class_id", 0)))
            lines.append(
                f"| {_eco_code(eid)} | {r.get('clase', CLASS_NAMES.get(cid, cid))} | "
                f"{r.get('modo', '?')} | "
                f"{int(r.get('cuota_rectangulos', r.get('cuota_rects', 0)) or 0)} | "
                f"{int(r.get('n_seleccionados', 0) or 0)} | "
                f"{int(r.get('deficit', 0) or 0)} |"
            )
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 10. Presupuesto no asignado ──
    lines.append("## 10. Presupuesto no asignado")
    lines.append("")
    na = cur["no_asignado"]
    if na is None or na.empty:
        lines.append(
            "Sin `presupuesto_no_asignado.csv` (todo el presupuesto de relleno "
            "asignado, o corrida sin pasada de relleno)."
        )
    else:
        lines.append(f"Registros: **{len(na)}**")
        lines.append("")
        cols = [c for c in na.columns if c in na.columns][:8]
        lines.append("| " + " | ".join(cols) + " |")
        lines.append("|" + "|".join(["---"] * len(cols)) + "|")
        for _, r in na.head(30).iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
        if len(na) > 30:
            lines.append(f"| … | +{len(na) - 30} filas |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 11. Pools E02 ──
    lines.append("## 11. Diagnóstico de pools (E02)")
    lines.append("")
    pools_path = cur["run_dir"] / "por_ecorregion" / "E02" / "pools_E02.csv"
    if not pools_path.is_file():
        # buscar glob
        encontrados = list((cur["run_dir"] / "por_ecorregion").glob("**/pools_E02.csv"))
        pools_path = encontrados[0] if encontrados else None
    if pools_path is None or not Path(pools_path).is_file():
        lines.append("*Sin `pools_E02.csv`.*")
    else:
        pools = pd.read_csv(pools_path)
        interes = pools[
            pools["pool"].astype(str).str.contains("presencia_3|estable_simple|relleno|censo_3", regex=True)
            | (pools.get("n_seleccionados", 0) > 0)
        ]
        if interes.empty:
            interes = pools.head(8)
        for _, r in interes.head(12).iterrows():
            lines.append(f"### `{r['pool']}`")
            lines.append("| Campo | Valor |")
            lines.append("|-------|------:|")
            for col in (
                "n_candidatos_universo",
                "n_pasa_filtro_calidad",
                "n_cumple_tipologia",
                "n_disponibles",
                "n_seleccionados",
                "n_falla_valid_area",
                "n_falla_eco_dom",
                "n_falla_noobs",
                "motivo_cierre",
            ):
                if col in pools.columns:
                    lines.append(f"| {col} | {r.get(col, '—')} |")
            lines.append("")
    lines.append("---")
    lines.append("")

    # ── 12. Archivos ──
    lines.append("## 12. Archivos generados")
    lines.append("")
    lines.append("```")
    lines.append(f"02_seleccion/{tag}/")
    lines.append("├── seleccion_nacional_utm18.gpkg")
    lines.append("├── seleccion_nacional_utm19.gpkg")
    lines.append("├── seleccion_nacional.csv")
    lines.append("├── auditoria_cobertura_celdas.csv")
    if cur["n_marginales"]:
        lines.append("├── auditoria_cobertura_celdas_marginales.csv")
    lines.append("├── auditoria_nacional.csv")
    if cur["suma_km2"] is not None:
        lines.append("├── auditoria_solape.csv")
    if na is not None and not na.empty:
        lines.append("├── presupuesto_no_asignado.csv")
    lines.append("├── deficit_celdas.csv")
    lines.append("├── informe_seleccion.md")
    lines.append("└── por_ecorregion/E**/{seleccion,pools,auditoria}_E**.*")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 13. Conclusiones ──
    lines.append("## 13. Conclusiones")
    lines.append("")
    if mismo:
        lines.append(f"### Baseline `{tag}` (pre-v03)")
        lines.append("1. Referencia para medir la corrección v03.")
        lines.append(
            f"2. Problemas conocidos: relleno {_fmt_pct(cur['pct_relleno'])}, "
            f"{cur['ecos_train_lt_50']} ecos con train < 50 %, "
            f"{cur['ecos_train_0']} con train = 0, "
            f"celdas vacías {_fmt_celdas(cur)}, mix 3×3 estancado en {cur['n3']}."
        )
        lines.append(
            "3. Solape: la baseline no reportaba las tres cifras; "
            "la discrepancia suma vs unión se estimó en ~20,6 %."
        )
    else:
        lines.append(f"### Logros vs `{base_tag}`")
        checks = []
        if cur["n"] < base["n"]:
            checks.append(
                f"Total de rectángulos bajó ({base['n']} → {cur['n']}), "
                "coherente con prioridad 3×3 + tracker."
            )
        if cur["pct_relleno"] <= float(getattr(P, "TOPE_RELLENO_PCT", 0.30)) + 1e-6:
            checks.append(
                f"Relleno dentro del tope ({_fmt_pct(cur['pct_relleno'])} ≤ "
                f"{_fmt_pct(float(getattr(P, 'TOPE_RELLENO_PCT', 0.30)))})."
            )
        else:
            checks.append(
                f"Relleno aún sobre el tope: {_fmt_pct(cur['pct_relleno'])}."
            )
        if cur["ecos_train_0"] == 0:
            checks.append("Ninguna ecorregión con train = 0.")
        else:
            checks.append(f"Aún {cur['ecos_train_0']} ecos con train = 0.")
        if cur["ecos_train_lt_50"] == 0:
            checks.append("Ninguna eco viable con train < 50 %.")
        else:
            checks.append(f"Aún {cur['ecos_train_lt_50']} ecos con train < 50 %.")
        if cur["n_pares"] == 0:
            checks.append("0 pares que se intersectan.")
        elif cur["n_pares"] is not None:
            checks.append(f"{cur['n_pares']} pares que se intersectan (revisar tracker).")
        if cur["diff_rel"] is not None and cur["diff_rel"] <= 0.001:
            checks.append("Suma ≈ unión (Δ ≤ 0,1 %).")
        if cur["tamarugo_e2_pct"] is not None and cur["tamarugo_e2_pct"] >= 0.60:
            checks.append(f"Tamarugo E02 ≥ 60 % ({_fmt_pct(cur['tamarugo_e2_pct'])}).")
        elif cur["tamarugo_e2_pct"] is not None:
            checks.append(
                f"Tamarugo E02 bajo objetivo: {_fmt_pct(cur['tamarugo_e2_pct'])} "
                "(esperado ≥ 60 %)."
            )
        if cur["n3"] > base["n3"]:
            checks.append(f"3×3 subió de {base['n3']} a {cur['n3']}.")
        for i, c in enumerate(checks, 1):
            lines.append(f"{i}. {c}")
        lines.append("")
        lines.append("### Pendiente")
        pend = []
        if cur["n_vacias"] and cur["n_vacias"] >= 15:
            pend.append(f"{cur['n_vacias']} celdas vacías (objetivo < 15).")
        if cur["split_inviable"]:
            pend.append(f"split_inviable: {', '.join(cur['split_inviable'])}.")
        if not pend:
            pend.append("Revisar hallazgos puntuales (p. ej. tamarugo E01) y FASE 2.")
        for i, p in enumerate(pend, 1):
            lines.append(f"{i}. {p}")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        f"*Generado el {hoy} a partir de la corrida `{tag}` "
        f"con comparación contra `{base_tag}` "
        f"(expectativa corrección v03).*"
    )
    lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Genera informe_seleccion.md comparando una corrida "
            f"contra la baseline (default {BASELINE_DEFAULT})."
        )
    )
    parser.add_argument(
        "--seleccion",
        required=True,
        help="TAG de corrida bajo 02_seleccion/ o path al directorio",
    )
    parser.add_argument(
        "--baseline",
        default=BASELINE_DEFAULT,
        help=f"TAG o path de la corrida de referencia (default: {BASELINE_DEFAULT})",
    )
    parser.add_argument(
        "--caracterizacion",
        default=CARACT_DEFAULT,
        help=f"TAG de caracterización (default: {CARACT_DEFAULT})",
    )
    parser.add_argument(
        "--salida",
        type=Path,
        default=None,
        help="Ruta del md de salida (default: <seleccion>/informe_seleccion.md)",
    )
    args = parser.parse_args()

    run_dir = resolver_run_dir(args.seleccion, P.OUT_ROOT)
    base_dir = resolver_run_dir(args.baseline, P.OUT_ROOT)
    out = args.salida or (run_dir / "informe_seleccion.md")

    # No sobrescribir el informe de una corrida de referencia al regenerarla
    # contra sí misma (salvo que se pase --salida explícita).
    if args.salida is None and run_dir.resolve() == base_dir.resolve():
        print(
            f"ERROR: --seleccion y --baseline apuntan al mismo directorio ({run_dir}). "
            "Pase --salida para forzar, o use otra baseline.",
            file=sys.stderr,
        )
        return 2

    cur = indicadores(run_dir)
    base = indicadores(base_dir)

    md = generar_markdown(cur, base, args.caracterizacion)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"Informe escrito en {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
