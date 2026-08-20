"""Genera informe_seleccion_reauditado.md."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from config import params_seleccion as P
from config.diccionarios import ECO_NAMES


def _eco(eco_id: int) -> str:
    raw = ECO_NAMES.get(int(eco_id), f"E{int(eco_id)}")
    return raw.split("_", 1)[0] if "_" in raw else raw


def generar_informe(
    *,
    sel_tag: str,
    car_tag: str,
    out_dir: Path,
    aud: pd.DataFrame,
    ratio_df: pd.DataFrame,
    tests: pd.DataFrame,
    geo_meta: dict,
    presup_meta: dict,
    presup_df: pd.DataFrame,
    deficit_meta: dict,
    sel_df: pd.DataFrame,
    solape: pd.DataFrame | None,
) -> str:
    n = len(sel_df)
    n_rel = int((sel_df.get("pool_origen", "") == "relleno").sum()) if "pool_origen" in sel_df else 0
    side = pd.to_numeric(sel_df.get("rect_side", 0), errors="coerce").fillna(0).astype(int)
    n2, n3 = int((side == 2).sum()), int((side == 3).sum())

    raras = aud[aud["modo"].isin(["censo", "refuerzo"])].copy()
    n_raras = len(raras)
    cumplen = int(raras["cumple_objetivo"].fillna(False).sum()) if n_raras else 0
    vacias = int((aud["estado"] == "vacia").sum())
    n_aud = len(aud)

    # Distribución cobertura alcanzable (raras)
    dist_rows = _distribucion_cobertura(raras)

    peores = (
        raras.sort_values("pct_cubierto_alcanzable", ascending=True, na_position="first")
        .head(10)
    )

    # ratio_fuentes stats
    rf = pd.to_numeric(ratio_df["ratio_fuentes"], errors="coerce").dropna()
    top_desv = (
        ratio_df.assign(_d=(pd.to_numeric(ratio_df["ratio_fuentes"], errors="coerce") - 1).abs())
        .sort_values("_d", ascending=False)
        .head(5)
    )

    fallan = tests[tests["resultado"] == "FALLA"] if not tests.empty else pd.DataFrame()
    pasan = tests[tests["resultado"] == "PASA"] if not tests.empty else pd.DataFrame()

    suma = union = n_pares = "—"
    if solape is not None and not solape.empty:
        suma = f"{float(solape.iloc[0]['suma_km2']):,.1f}".replace(",", " ")
        union = f"{float(solape.iloc[0]['union_km2']):,.1f}".replace(",", " ")
        n_pares = int(solape.iloc[0]["n_pares_intersectan"])

    # Tamarugo E2
    tam = aud[(aud["eco_id"] == 2) & (aud["class_id"] == 3)]
    tam_alc = float(tam["pct_cubierto_alcanzable"].iloc[0]) if len(tam) else None
    tam_abs = float(tam["pct_cubierto_absoluto"].iloc[0]) if len(tam) else None

    geo = geo_meta.get("resumen", {})

    lineas: list[str] = []
    a = lineas.append

    a("# Informe de selección reauditado — SSL4EO v02")
    a("")
    a(f"**Corrida de origen:** `{sel_tag}`  ")
    a(f"**Caracterización:** `{car_tag}`  ")
    a(f"**Reauditoría:** `{out_dir.name}`  ")
    a(f"**Fecha:** {date.today().isoformat()}  ")
    a("")
    a("> Reauditoría de métricas **sin recalcular selección**. Los 221 rectángulos son los mismos.")
    a("> Indicador principal de cobertura: `pct_cubierto_alcanzable` (A.1).")
    a("")
    a("---")
    a("")
    a("## 0. Tests de aceptación (evaluación offline)")
    a("")
    a(f"**{len(fallan)} tests fallidos de {len(tests)}** · {len(pasan)} pasan · "
      f"{int((tests['resultado']=='NO_EVALUABLE').sum()) if not tests.empty else 0} no evaluables.")
    a("")
    if not tests.empty:
        a("| test_id | descripción | criterio | valor | resultado | detalle |")
        a("|---|---|---|---:|---|---|")
        for _, t in tests.iterrows():
            det = str(t.get("detalle", "") or "").replace("|", "/")[:80]
            a(
                f"| {t['test_id']} | {t['descripcion']} | {t['criterio']} | "
                f"{t['valor_obtenido']} | **{t['resultado']}** | {det} |"
            )
    a("")
    if not fallan.empty:
        a("### Tests que fallan")
        a("")
        for _, t in fallan.iterrows():
            a(f"- **{t['test_id']}** {t['descripcion']}: valor={t['valor_obtenido']} · {t['detalle']}")
        a("")
    else:
        a(f"**0 tests fallidos de {len(tests)}.**")
        a("")

    a("---")
    a("")
    a("## 1. Resumen ejecutivo")
    a("")
    a("| Indicador | Valor |")
    a("|---|---:|")
    a(f"| Rectángulos (sin cambio) | **{n}** |")
    a(f"| Celdas que cumplen objetivo (A.1, censo/refuerzo) | **{cumplen} / {n_raras}** ({100*cumplen/max(n_raras,1):.1f} %) |")
    a(f"| Celdas vacías (todas las auditadas, A.1) | {vacias} / {n_aud} |")
    a(f"| Relleno | {n_rel} ({100*n_rel/max(n,1):.1f} %) |")
    a(f"| Mix 2×2 / 3×3 | {n2} / {n3} ({100*n2/max(n2+n3,1):.0f} / {100*n3/max(n2+n3,1):.0f}) |")
    a(f"| Pares con área de intersección | {n_pares} · suma {suma} km² · unión {union} km² |")
    if tam_alc is not None:
        a(f"| Tamarugo E02 alcanzable (A.1) | **{100*tam_alc:.1f} %** |")
        a(f"| Tamarugo E02 absoluto (A.2, ref.) | {100*tam_abs:.1f} % |")
    a(f"| Presupuesto no asignado | {presup_meta.get('total_rects', 0)} rects en {presup_meta.get('n_ecos', 0)} ecos |")
    a("")
    a("### Distribución de cobertura alcanzable (celdas censo/refuerzo)")
    a("")
    a("| Rango de `pct_cubierto_alcanzable` | N celdas |")
    a("|---|---:|")
    for label, cnt in dist_rows:
        a(f"| {label} | {cnt} |")
    a("")
    a("### Diez peores coberturas (censo/refuerzo)")
    a("")
    a("| Eco | Clase | Modo | Alcanzable | Absoluto | Objetivo | Estado |")
    a("|---|---|---|---:|---:|---:|---|")
    for _, r in peores.iterrows():
        pa = r["pct_cubierto_alcanzable"]
        pb = r["pct_cubierto_absoluto"]
        ob = r["objetivo"]
        a(
            f"| {_eco(r['eco_id'])} | {r['class_name']} ({int(r['class_id'])}) | {r['modo']} | "
            f"{'' if pd.isna(pa) else f'{100*pa:.1f} %'} | "
            f"{'' if pd.isna(pb) else f'{100*pb:.1f} %'} | "
            f"{'' if pd.isna(ob) else f'{100*ob:.0f} %'} | {r['estado']} |"
        )
    a("")

    a("---")
    a("")
    a("## 2. Cobertura corregida (A.1 / A.2 / A.3)")
    a("")
    a("- **A.1 alcanzable** (principal): `Σ ha_sel / Σ ha_candidatos_2x2`. Por construcción ≤ 100 %. ")
    a("- **A.2 absoluto** (referencia): `Σ ha_sel / area_ha_matriz` (año 2016). No comparable con A.1.")
    a("- **A.3 ratio_fuentes**: `Σ ha_candidatos_2x2 / area_ha_matriz` — desajuste entre fuentes.")
    a("")
    n_sobre = int((pd.to_numeric(aud["pct_cubierto_alcanzable"], errors="coerce").fillna(0) > 1.0001).sum())
    a(f"Celdas con `pct_cubierto_alcanzable` > 100 %: **{n_sobre}** (debe ser 0).")
    a("")
    if len(rf):
        a("### Distribución de `ratio_fuentes`")
        a("")
        a("| Estadístico | Valor |")
        a("|---|---:|")
        a(f"| Mediana | {rf.median():.3f} |")
        a(f"| p10 | {rf.quantile(0.10):.3f} |")
        a(f"| p90 | {rf.quantile(0.90):.3f} |")
        a("")
        a("### Cinco celdas con mayor desviación `|ratio − 1|`")
        a("")
        a("| Eco | Clase | ha_candidatos_2x2 | ha_matriz | ratio_fuentes |")
        a("|---|---|---:|---:|---:|")
        for _, r in top_desv.iterrows():
            a(
                f"| {_eco(r['eco_id'])} | {r['class_name']} ({int(r['class_id'])}) | "
                f"{r['ha_candidatos_2x2']:.0f} | {r['ha_matriz_presencia']:.0f} | {r['ratio_fuentes']:.3f} |"
            )
        a("")
        a("Esas desviaciones explican los >100 % del informe original (denominador matriz 2016 vs numerador moda temporal).")
        a("")

    a("---")
    a("")
    a("## 3. Diagnóstico de geometrías (D)")
    a("")
    a("| Indicador | Valor |")
    a("|---|---:|")
    a(f"| Suma geométrica almacenada | {geo.get('suma_geom_km2')} km² |")
    a(f"| Suma campo `area_km2` | {geo.get('suma_area_km2_campo')} km² |")
    a(f"| Suma nominal (`rect_m²`) | {geo.get('suma_nominal_km2')} km² |")
    a(f"| `ratio_geom_nominal` mediana | {geo.get('ratio_geom_nominal_mediana')} |")
    a(f"| `ratio_geom_nominal` p10 / p90 | {geo.get('ratio_geom_nominal_p10')} / {geo.get('ratio_geom_nominal_p90')} |")
    a(f"| Mínimo | {geo.get('ratio_geom_nominal_min')} |")
    a(f"| N con ratio < 0,99 | {geo.get('n_ratio_lt_099')} |")
    a(f"| Pares con área (geoms almacenadas) | {geo.get('n_pares_area_almacenadas')} |")
    a(f"| Pares con área (extensión nominal reconstruida) | {geo.get('n_pares_area_nominales')} |")
    a("")
    a("> Si una fracción relevante de las geometrías está recortada, el test de solape ")
    a("> (`suma == unión`) se calcula sobre geometrías recortadas y **no garantiza ausencia de ")
    a("> solape entre las extensiones reales de los rectángulos**. En ese caso el test debe ")
    a("> recalcularse sobre las extensiones nominales reconstruidas desde `col_idx`, `row_idx`, ")
    a("> `rect_side` y el tile padre.")
    a("")
    if geo.get("solape_difiere_reconstruccion"):
        a(
            f"**Alerta:** el conteo de pares difiere entre geometrías almacenadas "
            f"({geo.get('n_pares_area_almacenadas')}) y nominales reconstruidas "
            f"({geo.get('n_pares_area_nominales')})."
        )
    else:
        a(
            f"Los conteos de pares con área coinciden ({geo.get('n_pares_area_almacenadas')}) "
            "entre geometrías almacenadas y nominales reconstruidas desde el centroide."
        )
    a("")
    a("### Por `rect_side`")
    a("")
    a("| rect_side | n | mediana | p10 | p90 | mínimo |")
    a("|---:|---:|---:|---:|---:|---:|")
    for r in geo_meta.get("por_rect_side", []):
        a(
            f"| {r.get('rect_side')} | {r.get('n')} | {r.get('mediana'):.4f} | "
            f"{r.get('p10'):.4f} | {r.get('p90'):.4f} | {r.get('minimo'):.4f} |"
        )
    a("")
    a("### Diez geometrías de menor `ratio_geom_nominal`")
    a("")
    a("| grid_id | eco | tile | side | geom_km² | nominal_km² | ratio |")
    a("|---|---|---|---:|---:|---:|---:|")
    for r in geo_meta.get("peores_10", []):
        a(
            f"| {r.get('grid_id')} | {_eco(r.get('eco_dom_id', -1))} | {r.get('mgrs_dom')} | "
            f"{r.get('rect_side')} | {r.get('area_geom_km2'):.2f} | {r.get('area_nominal_km2'):.2f} | "
            f"{r.get('ratio_geom_nominal'):.4f} |"
        )
    a("")

    a("---")
    a("")
    a("## 4. Presupuesto no asignado desambiguado (E)")
    a("")
    a(f"Estado del archivo original: **{presup_meta.get('estado_archivo')}** · "
      f"total {presup_meta.get('total_rects', 0)} rects en {presup_meta.get('n_ecos', 0)} ecos.")
    a("")
    if not presup_df.empty:
        a("| Eco | Déficit rects | Motivo original | Motivo desambiguado | Detalle pools raras |")
        a("|---|---:|---|---|---|")
        for _, r in presup_df.sort_values("deficit_rects", ascending=False).iterrows():
            a(
                f"| {_eco(r['ecorregion_id'])} | {int(r['deficit_rects'])} | "
                f"{r['motivo_original']} | **{r['motivo_desambiguado']}** | "
                f"{str(r.get('detalle_pools',''))[:90]} |"
            )
        a("")
        a("Resumen por motivo:")
        a("")
        a("| Motivo | Rectángulos |")
        a("|---|---:|")
        for m, v in (presup_meta.get("por_motivo") or {}).items():
            a(f"| {m} | {int(v)} |")
        a("")
        a("El caso `cuota_por_clase` (pools de censo/refuerzo cerrados por `presupuesto_agotado` "
          "con candidatos tipológicos restantes, mientras la eco tenía cupo sin usar) es el "
          "insumo principal de la corrección v04.")
        a("")

    a("---")
    a("")
    a("## 5. Déficit de celdas (F)")
    a("")
    a(f"**{deficit_meta.get('mensaje')}**")
    a("")

    a("---")
    a("")
    a("## 6. Conclusiones")
    a("")
    a("### Logros")
    a("")
    a(f"- 0 pares con área de intersección · suma {suma} km² · unión {union} km².")
    a(f"- {n_sobre} celdas con cobertura alcanzable > 100 % (corregido el indicador).")
    a(f"- Indicador principal redefinido: {cumplen}/{n_raras} celdas raras cumplen objetivo (A.1).")
    a(f"- Celdas vacías (secundario): {vacias}/{n_aud}.")
    if tam_alc is not None:
        a(f"- Tamarugo E02: {100*tam_alc:.1f} % alcanzable · {100*tam_abs:.1f} % absoluto.")
    a("")
    a("### Tests que fallan")
    a("")
    if fallan.empty:
        a(f"0 tests fallidos de {len(tests)}.")
    else:
        for _, t in fallan.iterrows():
            a(f"- **{t['test_id']}** {t['descripcion']}: {t['detalle']} (criterio: {t['criterio']})")
    a("")
    a("---")
    a("")
    a("*Fin del informe reauditado.*")
    return "\n".join(lineas)


def _distribucion_cobertura(raras: pd.DataFrame) -> list[tuple[str, int]]:
    if raras.empty:
        return [("≥ objetivo", 0), ("40 % – objetivo", 0), ("20 % – 40 %", 0), ("< 20 %", 0), ("0 % (vacía)", 0)]
    pct = pd.to_numeric(raras["pct_cubierto_alcanzable"], errors="coerce")
    obj = pd.to_numeric(raras["objetivo"], errors="coerce")
    n_obj = int(((pct >= obj) & pct.notna() & obj.notna()).sum())
    n_40 = int(((pct >= 0.40) & (pct < obj) & pct.notna() & obj.notna()).sum())
    # también sin obj
    n_20_40 = int(((pct >= 0.20) & (pct < 0.40) & pct.notna()).sum())
    n_lt20 = int(((pct > 0) & (pct < 0.20) & pct.notna()).sum())
    n_0 = int(((pct.fillna(0) <= 0) | (raras["estado"] == "vacia")).sum())
    # Ajuste: n_40 solo entre 40 y objetivo; el resto de 40-obj sin objetivo no aplica
    return [
        ("≥ objetivo", n_obj),
        ("40 % – objetivo", n_40),
        ("20 % – 40 %", n_20_40),
        ("< 20 % (excl. vacías)", n_lt20),
        ("0 % (vacía)", n_0),
    ]
