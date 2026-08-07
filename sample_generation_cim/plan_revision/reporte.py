"""Generación de reporte_plan_revision.md."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from config import params_plan_revision as P
from plan_revision.derivar import periodo_de_anio
from plan_revision.validar import ResultadoValidacion


def _periodo_label(anio: int) -> str:
    p = periodo_de_anio(anio)
    return p if p else "?"


def _df_a_markdown(df: pd.DataFrame, floatfmt: str = ".2f") -> str:
    if df.empty:
        return "_Sin datos._"
    view = df.copy()
    for col in view.select_dtypes(include="float").columns:
        view[col] = view[col].map(lambda x: format(x, floatfmt) if pd.notna(x) else "")
    headers = list(view.columns)
    rows = view.astype(str).values.tolist()
    sep = "| " + " | ".join(headers) + " |"
    bar = "| " + " | ".join("---" for _ in headers) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([sep, bar, *body])


def expandir_pares(df: pd.DataFrame) -> pd.DataFrame:
    filas: list[dict] = []
    for _, row in df.iterrows():
        base = {
            "grid_id": row.get("grid_id"),
            "sample_type": row.get("sample_type"),
            "eco_dom_id": row.get("eco_dom_id"),
            "eco_dom_name": row.get("eco_dom_name"),
            "clase_objetivo": row.get("clase_objetivo"),
            "clase_objetivo_nombre": row.get("clase_objetivo_nombre"),
            "modo_tratamiento": row.get("modo_tratamiento"),
            "rev_metodo": row.get("rev_metodo"),
            "rev_n_years": row.get("rev_n_years"),
        }
        for i in (1, 2, 3):
            y = int(row.get(f"rev_year{i}", P.SENTINEL))
            if y == P.SENTINEL:
                continue
            filas.append({
                **base,
                "rev_orden": i,
                "rev_year": y,
                "rev_role": row.get(f"rev_role{i}", ""),
                "ref_period": _periodo_label(y),
            })
    return pd.DataFrame(filas)


def generar_reporte_md(
    df: pd.DataFrame,
    expandido: pd.DataFrame,
    validacion: ResultadoValidacion,
    sel_dir: Path,
    out_dir: Path,
    *,
    expectativa: dict | None = None,
) -> str:
    expectativa = expectativa or {}
    n_rects = len(df)
    n_pares = len(expandido)
    n_con_ref = int((pd.to_numeric(df.get("ref_year", P.SENTINEL), errors="coerce") > 0).sum())
    n_con_rev = int((df["rev_year1"] != P.SENTINEL).sum())

    dist_n = df["rev_n_years"].value_counts().sort_index()
    dist_roles = expandido["rev_role"].value_counts().sort_index()
    dist_periodo = expandido["ref_period"].value_counts().reindex(
        P.ORDEN_PERIODOS, fill_value=0
    )

    fb_trans = df[df["rev_metodo"] == "transicion_fallback_sin_cambio_periodo"]
    fb_censo = df[df["rev_metodo"] == "censo_refuerzo_fallback"]
    fb_criticos = fb_trans.copy()

    refuerzo = df[df["sample_type"] == "presencia_refuerzo"].copy()
    estabilidad_refuerzo = pd.DataFrame()
    if not refuerzo.empty and "clase_objetivo_nombre" in refuerzo.columns:
        estabilidad_refuerzo = (
            refuerzo.groupby("clase_objetivo_nombre", dropna=False)
            .agg(
                n=("grid_id", "count"),
                max_stab_run_medio=("max_stab_run", "mean"),
                transition_pct_medio=("transition_pct", "mean"),
            )
            .reset_index()
            .sort_values("max_stab_run_medio")
        )

    ts = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        "# Reporte — plan de años de revisión",
        "",
        f"**Selección base:** `{sel_dir}`  ",
        f"**Salida:** `{out_dir}`  ",
        f"**Generado:** {ts}  ",
        f"**Rectángulos:** {n_rects}  ",
        f"**Pares (rectángulo, año):** {n_pares}  ",
        "",
        "---",
        "",
        "## 1. Resumen",
        "",
        "| Indicador | Valor |",
        "|-----------|------:|",
        f"| Rectángulos con `ref_year` > 0 (antes) | {n_con_ref} |",
        f"| Rectángulos con `rev_year1` asignado | {n_con_rev} |",
        f"| Pares totales | {n_pares} |",
        f"| Validación automática | {'OK' if validacion.ok else 'FALLA'} |",
        "",
        "### Expectativa vs resultado",
        "",
        "| Indicador | Esperado | Resultado |",
        "|-----------|----------|----------:|",
        f"| Rectángulos con año | 341 / 341 | {n_con_rev} / {n_rects} |",
        f"| Pares totales | ~450–600 | {n_pares} |",
        f"| Rectángulos fallback transición | pocos | {len(fb_trans)} |",
        f"| Rectángulos fallback censo/refuerzo | esperado en clases minoritarias | {len(fb_censo)} |",
        "",
        "---",
        "",
        "## 2. Distribución de `rev_n_years`",
        "",
        "| Años por rectángulo | N | % |",
        "|--------------------:|--:|--:|",
    ]

    for n_years, cnt in dist_n.items():
        pct = 100.0 * cnt / n_rects if n_rects else 0
        lines.append(f"| {int(n_years)} | {int(cnt)} | {pct:.1f} |")

    lines.extend([
        "",
        "---",
        "",
        "## 3. Distribución de `rev_role`",
        "",
        "| Rol | Pares |",
        "|-----|------:|",
    ])
    for rol, cnt in dist_roles.items():
        lines.append(f"| {rol} | {int(cnt)} |")

    lines.extend([
        "",
        "---",
        "",
        "## 4. Balance por periodo Landsat",
        "",
        "| Periodo | Pares | % |",
        "|---------|------:|--:|",
    ])
    for periodo, cnt in dist_periodo.items():
        pct = 100.0 * cnt / n_pares if n_pares else 0
        lines.append(f"| {periodo} | {int(cnt)} | {pct:.1f} |")

    lines.extend([
        "",
        "---",
        "",
        "## 5. Transiciones sin cambio de moda entre periodos (revisión manual sugerida)",
        "",
        f"Total: **{len(fb_criticos)}**",
        "",
    ])
    if fb_criticos.empty:
        lines.append("_Ninguno._")
    else:
        cols = [
            "grid_id", "sample_type", "rev_metodo", "rev_year1",
            "rev_role1", "transition_pct", "max_stab_run",
            "md_id_P1", "md_id_P2", "md_id_P3", "md_id_P4",
        ]
        cols = [c for c in cols if c in fb_criticos.columns]
        lines.append(_df_a_markdown(fb_criticos[cols]))

    lines.extend([
        "",
        "---",
        "",
        "## 6. Censo/refuerzo con fallback de periodo",
        "",
        "Ocurre cuando la clase objetivo no es moda en ningún periodo Landsat "
        "(habitual en refuerzo). Se asigna igual un año representativo; "
        "no implica error automático.",
        "",
        f"Total: **{len(fb_censo)}**",
        "",
    ])
    if fb_censo.empty:
        lines.append("_Ninguno._")
    else:
        cols = [
            "grid_id", "sample_type", "clase_objetivo_nombre",
            "rev_year1", "rev_metodo", "max_stab_run",
        ]
        cols = [c for c in cols if c in fb_censo.columns]
        lines.append(_df_a_markdown(fb_censo[cols].head(20)))

    lines.extend([
        "",
        "---",
        "",
        "## 7. Estabilidad temporal en refuerzo (decisión visible)",
        "",
        "Para censo/refuerzo se asigna **un solo año**. Si alguna clase rara tiene "
        "`max_stab_run` bajo, un año podría no representarla.",
        "",
    ])
    if estabilidad_refuerzo.empty:
        lines.append("_Sin muestras de refuerzo._")
    else:
        lines.append(_df_a_markdown(estabilidad_refuerzo, floatfmt=".1f"))

    if fb_censo.empty is False:
        lines.extend([
            "",
            f"Rectángulos con `censo_refuerzo_fallback`: **{len(fb_censo)}**",
        ])

    if validacion.errores:
        lines.extend(["", "---", "", "## 8. Errores de validación", ""])
        for err in validacion.errores[:50]:
            lines.append(f"- {err}")
    if validacion.advertencias:
        lines.extend(["", "## Advertencias", ""])
        for adv in validacion.advertencias[:30]:
            lines.append(f"- {adv}")

    lines.extend([
        "",
        "---",
        "",
        f"*Generado automáticamente el {ts}.*",
    ])
    return "\n".join(lines) + "\n"
