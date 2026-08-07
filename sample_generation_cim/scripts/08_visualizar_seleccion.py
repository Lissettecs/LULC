#!/usr/bin/env python3
"""
08 — Visualizador interactivo de selección SSL4EO v02.

Uso:
  streamlit run scripts/08_visualizar_seleccion.py
  python scripts/08_visualizar_seleccion.py --export-html dashboard_seleccion.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from config import params_seleccion as P
from config.diccionarios import CLASS_NAMES, CLASES_PROTEGIDAS
from seleccion.reportes import (
    calidad_por_tipo,
    clases_protegidas_detalle,
    clases_protegidas_resumen,
    grid_mode_por_tipo,
    pivot_clase_tipo,
    pivot_eco_clase,
    pivot_eco_tipo,
    por_tipo,
    preparar_dataframe,
    resumen_general,
    split_por_tipo,
)
from config.corridas_ref import SEL_RUN_REF, SEL_RUN_REF_DIR
from utilidades import ultima_corrida

DEFAULT_RUN = ultima_corrida(P.OUT_ROOT) or SEL_RUN_REF_DIR
DEFAULT_RUN_TAG = SEL_RUN_REF
MAP_COLOR_OPTIONS = [
    "sample_type",
    "split",
    "rect_side_label",
    "grid_mode",
    "lulc_mode_name",
    "eco_dom_name",
    "modo_tratamiento",
    "pool_origen",
]

HTML_STYLE = """
body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f4f6f8; color: #1f2933; }
.wrap { max-width: 1400px; margin: 0 auto; padding: 24px; }
.hero { background: linear-gradient(135deg, #0f4c75, #1b6ca8); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px; }
.hero h1 { margin: 0 0 8px; font-size: 1.8rem; }
.hero p { margin: 0; opacity: 0.9; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 12px; margin-bottom: 24px; }
.kpi { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.kpi .label { font-size: 0.85rem; color: #52606d; margin-bottom: 6px; }
.kpi .value { font-size: 1.5rem; font-weight: 700; color: #102a43; }
.section { background: #fff; border-radius: 12px; padding: 20px; margin-bottom: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.section h2 { margin: 0 0 16px; font-size: 1.15rem; color: #243b53; border-bottom: 2px solid #d9e2ec; padding-bottom: 8px; }
.grid-2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 20px; }
.chart { min-height: 420px; }
table.data { width: 100%; border-collapse: collapse; font-size: 0.92rem; }
table.data th, table.data td { border: 1px solid #d9e2ec; padding: 8px 10px; text-align: right; }
table.data th:first-child, table.data td:first-child { text-align: left; }
table.data thead th { background: #e6f0f8; color: #102a43; }
.note { color: #627d98; font-size: 0.9rem; margin-bottom: 12px; }
"""


def resolver_run_dir(run_dir: Path | None, run_tag: str | None = None) -> Path:
    if run_tag:
        candidate = P.OUT_ROOT / run_tag
        if candidate.is_dir():
            return candidate
        raise FileNotFoundError(f"No existe corrida {candidate}")
    if run_dir and run_dir.is_dir():
        return run_dir
    ult = ultima_corrida(P.OUT_ROOT)
    if ult and ult.is_dir():
        return ult
    raise FileNotFoundError(f"No hay corrida de selección en {P.OUT_ROOT}")


def _gpkg_por_huso(run_dir: Path) -> list[Path]:
    paths = sorted(run_dir.glob("seleccion_nacional_utm*.gpkg"))
    if paths:
        return paths
    legacy = run_dir / "seleccion_nacional.gpkg"
    return [legacy] if legacy.is_file() else []


def cargar_seleccion(run_dir: Path, utm: str):
    import geopandas as gpd

    gpkg_paths = _gpkg_por_huso(run_dir)
    if not gpkg_paths:
        raise FileNotFoundError(
            f"No hay capas de selección en {run_dir} "
            "(esperado seleccion_nacional_utm18/19.gpkg o seleccion_nacional.gpkg)"
        )

    frames = []
    for path in gpkg_paths:
        part = gpd.read_file(path)
        if part.crs is None:
            part = part.set_crs(4326)
        frames.append(part.to_crs(4326))
    gdf = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs="EPSG:4326")
    if utm != "TOTAL" and "utm_zone" in gdf.columns:
        zone = int(utm.replace("UTM", ""))
        gdf = gdf[pd.to_numeric(gdf["utm_zone"], errors="coerce") == zone].copy()
    if "rect_side" in gdf.columns:
        side = pd.to_numeric(gdf["rect_side"], errors="coerce").fillna(0).astype(int)
        gdf["rect_side_label"] = side.map({2: "2×2", 3: "3×3"}).fillna("otro")
    for col in MAP_COLOR_OPTIONS + ["grid_id", "pool_origen", "clase_objetivo_nombre"]:
        if col in gdf.columns:
            gdf[col] = gdf[col].astype(str)
    gdf["map_id"] = gdf["grid_id"].astype(str)
    return gdf


def heatmap_figure(matrix: pd.DataFrame, title: str, *, y_title: str = "", x_title: str = "") -> go.Figure:
    data = matrix.select_dtypes(include="number")
    if data.empty:
        data = matrix
    fig = px.imshow(
        data,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="Blues",
        labels=dict(x=x_title, y=y_title, color="n"),
    )
    fig.update_layout(title=title, margin=dict(l=10, r=10, t=50, b=10))
    fig.update_xaxes(tickangle=45, side="bottom")
    fig.update_yaxes(autorange="reversed")
    return fig


def bar_tipo_figure(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    order = df.sort_values("n_muestras", ascending=True)
    fig = px.bar(
        order,
        x="n_muestras",
        y="tipo_muestra",
        orientation="h",
        color="dim_temporal" if "dim_temporal" in order.columns else None,
        text="n_muestras",
        title="Muestras por tipo",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), yaxis_title="")
    return fig


def split_figure(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    fig = px.bar(
        df,
        x="tipo_muestra",
        y="n_muestras",
        color="split",
        barmode="stack",
        title="Distribución train / val / test por tipo",
        category_orders={"split": ["train", "val", "test"]},
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def grid_mode_figure(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    fig = px.bar(
        df,
        x="tipo_muestra",
        y="n_muestras",
        color="grid_mode",
        barmode="group",
        title="Homogéneo vs mixto por tipo",
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def calidad_figure(df: pd.DataFrame) -> go.Figure:
    if df.empty:
        return go.Figure()
    metrics = [c for c in df.columns if c != "tipo_muestra"]
    melted = df.melt(id_vars=["tipo_muestra"], value_vars=metrics, var_name="metrica", value_name="media")
    fig = px.bar(
        melted,
        x="tipo_muestra",
        y="media",
        color="metrica",
        barmode="group",
        title="Calidad media por tipo de muestra",
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def rect_side_figure(gdf) -> go.Figure:
    if "rect_side_label" not in gdf.columns:
        return go.Figure()
    counts = gdf["rect_side_label"].value_counts().reset_index()
    counts.columns = ["rect_side", "n"]
    order = ["2×2", "3×3", "otro"]
    counts["rect_side"] = pd.Categorical(counts["rect_side"], categories=order, ordered=True)
    counts = counts.sort_values("rect_side")
    fig = px.pie(
        counts,
        names="rect_side",
        values="n",
        title="Mix 2×2 / 3×3",
        color="rect_side",
        color_discrete_map={"2×2": "#1b6ca8", "3×3": "#e07a5f", "otro": "#adb5bd"},
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(margin=dict(l=10, r=10, t=50, b=10), showlegend=False)
    return fig


def pool_origen_figure(gdf) -> go.Figure:
    if "pool_origen" not in gdf.columns:
        return go.Figure()
    counts = gdf["pool_origen"].value_counts().reset_index()
    counts.columns = ["pool_origen", "n"]
    fig = px.bar(
        counts.sort_values("n"),
        x="n",
        y="pool_origen",
        orientation="h",
        text="n",
        title="Origen del pool",
        color="pool_origen",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(showlegend=False, margin=dict(l=10, r=10, t=50, b=10), yaxis_title="")
    return fig


def split_eco_figure(gdf) -> go.Figure:
    if "split" not in gdf.columns or "eco_dom_name" not in gdf.columns:
        return go.Figure()
    eco = gdf.copy()
    eco["ecorregion"] = eco.apply(
        lambda r: str(r["eco_dom_name"]).split("_")[0] if pd.notna(r.get("eco_dom_name")) else "?",
        axis=1,
    )
    pivot = (
        eco.groupby(["ecorregion", "split"], observed=True)
        .size()
        .reset_index(name="n")
    )
    fig = px.bar(
        pivot,
        x="ecorregion",
        y="n",
        color="split",
        barmode="stack",
        title="Split train / val / test por ecorregión",
        category_orders={"split": ["train", "val", "test"]},
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def protegidas_figure(resumen: pd.DataFrame) -> go.Figure:
    data = resumen[resumen["clase"] != "TOTAL (cualquier protegida)"].copy()
    if data.empty:
        return go.Figure()
    fig = px.bar(data, x="clase", y="n_muestras", text="n_muestras", title="Muestras con clases protegidas (≥5 %)")
    fig.update_traces(textposition="outside")
    fig.update_layout(xaxis_tickangle=45, showlegend=False, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def mapa_figure(gdf, color_by: str = "sample_type", title: str = "Rectángulos seleccionados") -> go.Figure:
    color_col = color_by if color_by in gdf.columns else "sample_type"
    geojson = json.loads(gdf.to_json())
    hover = {c: True for c in (
        "sample_type", "grid_mode", "eco_dom_name", "lulc_mode_name",
        "split", "utm_zone", "modo_tratamiento", "pool_origen", "rect_side_label",
    ) if c in gdf.columns}
    fig = px.choropleth_map(
        gdf,
        geojson=geojson,
        locations="map_id",
        featureidkey="properties.map_id",
        color=color_col,
        hover_name="grid_id",
        hover_data=hover,
        center={"lat": -38.5, "lon": -71.5},
        zoom=3.6,
        height=680,
        title=title,
        opacity=0.55,
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=50, b=0))
    return fig


def show_kpis(resumen: pd.DataFrame) -> None:
    import streamlit as st

    if resumen.empty:
        st.warning("Sin datos de resumen.")
        return
    r = resumen.iloc[0]
    cols = st.columns(6)
    labels = [
        ("Muestras", "n_muestras"),
        ("Ecorregiones", "n_ecorregiones"),
        ("Clases modales", "n_clases_modales"),
        ("Protegidas", "n_clases_protegidas"),
        ("Train / Val / Test", None),
        ("Hom / Mix", None),
    ]
    for col, (label, key) in zip(cols, labels):
        if key is None and label.startswith("Train"):
            col.metric(label, f"{int(r.get('n_train',0))}/{int(r.get('n_val',0))}/{int(r.get('n_test',0))}")
        elif key is None:
            col.metric(label, f"{int(r.get('n_homogeneo',0))} / {int(r.get('n_mixto',0))}")
        else:
            col.metric(label, int(r.get(key, 0) or 0))


def render_dashboard(run_dir: Path, utm: str) -> None:
    import streamlit as st

    gdf = cargar_seleccion(run_dir, utm)
    df = preparar_dataframe(gdf)
    res = resumen_general(df, utm)
    tipo_df = por_tipo(df, utm)
    split_df = split_por_tipo(df, utm)
    grid_df = grid_mode_por_tipo(df, utm)
    calidad_df = calidad_por_tipo(df, utm)
    eco_clase = pivot_eco_clase(df)
    eco_tipo = pivot_eco_tipo(df)
    clase_tipo = pivot_clase_tipo(df)
    prot_res = clases_protegidas_resumen(df)
    prot_det = clases_protegidas_detalle(df)

    st.title("Selección SSL4EO v02")
    st.caption(f"Corrida: `{run_dir.name}` · Vista: **{utm}** · {len(gdf)} rectángulos")
    show_kpis(res)

    tab_res, tab_eco, tab_tipo, tab_prot, tab_cal, tab_map, tab_inf = st.tabs([
        "Resumen", "Cobertura eco/clase", "Tipos y split", "Clases protegidas",
        "Calidad", "Mapa", "Informe / déficits",
    ])

    with tab_res:
        st.dataframe(res, use_container_width=True, hide_index=True)
        c1, c2, c3 = st.columns(3)
        with c1:
            st.plotly_chart(rect_side_figure(gdf), use_container_width=True)
        with c2:
            st.plotly_chart(pool_origen_figure(gdf), use_container_width=True)
        with c3:
            st.plotly_chart(split_eco_figure(gdf), use_container_width=True)
        st.plotly_chart(bar_tipo_figure(tipo_df), use_container_width=True)
        st.dataframe(tipo_df, use_container_width=True, hide_index=True)

    with tab_eco:
        c1, c2 = st.columns(2)
        with c1:
            if not eco_clase.empty:
                st.plotly_chart(
                    heatmap_figure(eco_clase, "Ecorregión × clase modal", y_title="Ecorregión", x_title="Clase"),
                    use_container_width=True,
                )
        with c2:
            if not eco_tipo.empty:
                st.plotly_chart(
                    heatmap_figure(eco_tipo, "Ecorregión × tipo", y_title="Ecorregión", x_title="Tipo"),
                    use_container_width=True,
                )
        if not clase_tipo.empty:
            st.plotly_chart(
                heatmap_figure(clase_tipo, "Clase modal × tipo", y_title="Clase", x_title="Tipo"),
                use_container_width=True,
            )

    with tab_tipo:
        if not split_df.empty:
            st.plotly_chart(split_figure(split_df), use_container_width=True)
        if not grid_df.empty:
            st.plotly_chart(grid_mode_figure(grid_df), use_container_width=True)

    with tab_prot:
        st.caption(
            "Clases protegidas v02: "
            + ", ".join(f"{i} {CLASS_NAMES.get(i, i)}" for i in CLASES_PROTEGIDAS)
        )
        c1, c2 = st.columns([1, 2])
        with c1:
            st.dataframe(prot_res, use_container_width=True, hide_index=True)
        with c2:
            st.plotly_chart(protegidas_figure(prot_res), use_container_width=True)
        if not prot_det.empty:
            st.dataframe(prot_det, use_container_width=True, hide_index=True)

    with tab_cal:
        if calidad_df.empty:
            st.warning("Sin métricas de calidad.")
        else:
            st.plotly_chart(calidad_figure(calidad_df), use_container_width=True)
            st.dataframe(calidad_df, use_container_width=True, hide_index=True)

    with tab_map:
        color_opts = [c for c in MAP_COLOR_OPTIONS if c in gdf.columns]
        color_by = st.selectbox("Color", color_opts or ["sample_type"], index=0)
        st.plotly_chart(
            mapa_figure(gdf, color_by, title=f"Selección nacional — {utm}"),
            use_container_width=True,
        )

    with tab_inf:
        informe = run_dir / "informe_seleccion.md"
        if informe.is_file():
            st.subheader("Informe de selección")
            st.markdown(informe.read_text(encoding="utf-8"))
        deficit = run_dir / "deficit_celdas.csv"
        if deficit.is_file():
            st.subheader("Déficits censo/refuerzo")
            st.dataframe(pd.read_csv(deficit), use_container_width=True, hide_index=True)


def export_html(output: Path, run_dir: Path, utm: str) -> None:
    gdf = cargar_seleccion(run_dir, utm)
    df = preparar_dataframe(gdf)
    res = resumen_general(df, utm)
    tipo_df = por_tipo(df, utm)
    split_df = split_por_tipo(df, utm)
    calidad_df = calidad_por_tipo(df, utm)
    eco_clase = pivot_eco_clase(df)
    eco_tipo = pivot_eco_tipo(df)
    prot_res = clases_protegidas_resumen(df)

    parts = [
        "<!DOCTYPE html><html lang='es'><head>",
        "<meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>",
        f"<title>Selección SSL4EO v02 — {run_dir.name}</title>",
        f"<style>{HTML_STYLE}</style></head><body><div class='wrap'>",
        "<header class='hero'>",
        "<h1>Selección SSL4EO v02</h1>",
        f"<p>Corrida: <strong>{run_dir.name}</strong> · Vista: <strong>{utm}</strong> · {len(gdf)} rectángulos</p>",
        "</header>",
    ]

    r = res.iloc[0]
    kpis = {
        "Muestras": int(r["n_muestras"]),
        "Ecorregiones": int(r["n_ecorregiones"]),
        "Train/Val/Test": f"{int(r['n_train'])}/{int(r['n_val'])}/{int(r['n_test'])}",
        "Hom/Mix": f"{int(r['n_homogeneo'])}/{int(r['n_mixto'])}",
    }
    cards = "".join(f"<div class='kpi'><div class='label'>{k}</div><div class='value'>{v}</div></div>" for k, v in kpis.items())
    parts.append(f"<div class='kpis'>{cards}</div>")

    plotly_js = False

    def chart(fig: go.Figure) -> str:
        nonlocal plotly_js
        html = fig.to_html(full_html=False, include_plotlyjs="cdn" if not plotly_js else False)
        plotly_js = True
        return f'<div class="chart">{html}</div>'

    caract = ""
    summary_path = run_dir / "summary.json"
    if summary_path.is_file():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            caract = str(summary.get("grid_run", "")).replace(str(P.DATA_ROOT) + "/", "")
        except json.JSONDecodeError:
            caract = ""
    if caract:
        parts.append(
            f"<p class='note'>Caracterización base: <strong>{caract}</strong></p>"
        )

    parts.append(f"<section class='section'><h2>Resumen</h2>{res.to_html(index=False, classes='data')}</section>")
    mix_row = "".join(
        chart(fig)
        for fig in (rect_side_figure(gdf), pool_origen_figure(gdf), split_eco_figure(gdf))
        if fig.data
    )
    if mix_row:
        parts.append(f"<section class='section'><h2>Mix y split</h2><div class='grid-2'>{mix_row}</div></section>")
    parts.append(f"<section class='section'><h2>Por tipo</h2>{chart(bar_tipo_figure(tipo_df))}</section>")

    heatmaps = ""
    if not eco_clase.empty:
        heatmaps += chart(heatmap_figure(eco_clase, "Ecorregión × clase modal", y_title="Eco", x_title="Clase"))
    if not eco_tipo.empty:
        heatmaps += chart(heatmap_figure(eco_tipo, "Ecorregión × tipo", y_title="Eco", x_title="Tipo"))
    if heatmaps:
        parts.append(f"<section class='section'><h2>Cobertura</h2><div class='grid-2'>{heatmaps}</div></section>")

    if not split_df.empty:
        parts.append(f"<section class='section'><h2>Split</h2>{chart(split_figure(split_df))}</section>")
    if not calidad_df.empty:
        parts.append(f"<section class='section'><h2>Calidad</h2>{chart(calidad_figure(calidad_df))}</section>")
    parts.append(f"<section class='section'><h2>Clases protegidas</h2>{chart(protegidas_figure(prot_res))}</section>")
    map_charts = []
    for color_col in ("sample_type", "split", "rect_side_label", "pool_origen"):
        if color_col in gdf.columns:
            map_charts.append(
                chart(mapa_figure(gdf, color_col, f"Mapa — color: {color_col}"))
            )
    parts.append(
        f"<section class='section'><h2>Mapa</h2>{''.join(map_charts)}</section>"
    )
    parts.append("</div></body></html>")

    output.write_text("\n".join(parts), encoding="utf-8")
    print(f"HTML exportado: {output}")


def run_streamlit() -> None:
    import streamlit as st

    st.set_page_config(page_title="Selección SSL4EO v02", page_icon="🗺️", layout="wide")
    with st.sidebar:
        st.header("Opciones")
        run_input = st.text_input("Carpeta de selección", str(DEFAULT_RUN))
        utm = st.radio("Huso UTM", ["TOTAL", "UTM18", "UTM19"], index=0)
        if st.button("Exportar HTML estático"):
            out = Path(run_input) / "dashboard_seleccion.html"
            try:
                export_html(out, Path(run_input), utm)
                st.success(f"Exportado: {out}")
            except Exception as exc:
                st.error(str(exc))
        informe = Path(run_input) / "informe_seleccion.md"
        if informe.is_file():
            st.caption(f"Informe: `{informe.name}`")

    try:
        run_dir = resolver_run_dir(Path(run_input) if run_input else None)
    except FileNotFoundError as exc:
        st.error(str(exc))
        return
    render_dashboard(run_dir, utm)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visualizador de selección SSL4EO v02")
    p.add_argument("--run-dir", type=Path, default=None, help="Carpeta 02_seleccion/{run_tag}")
    p.add_argument("--run-tag", default=None, help="Tag de corrida (p. ej. 20260727_1340)")
    p.add_argument("--utm", default="TOTAL", choices=["TOTAL", "UTM18", "UTM19"])
    p.add_argument("--export-html", type=Path, help="Exportar dashboard estático")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.export_html:
        run_dir = resolver_run_dir(args.run_dir, args.run_tag)
        export_html(args.export_html, run_dir, args.utm)
        return 0
    if "streamlit" not in sys.modules:
        print("Ejecuta: streamlit run scripts/08_visualizar_seleccion.py", file=sys.stderr)
        return 1
    run_streamlit()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and any(a.startswith("--") for a in sys.argv[1:]):
        sys.exit(main())
    run_streamlit()
