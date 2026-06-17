#!/usr/bin/env python3
"""
Visualizador interactivo de reportes de revision (05_revision_seleccion_rectangulos.py).

Uso (desde grillas/):
  streamlit run scripts/07_visualizar_reportes.py
  python scripts/07_visualizar_reportes.py --export-html revision_dashboard.html
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from clases_criticas import (
    CRITICAL_CLASS_NAMES,
    annotate_critical_classes,
    critical_summary,
    presence_pct_column,
)
from rutas_proyecto import FINALES_DIR, GRILLAS_ROOT, REVISION_DIR, SCRIPTS_DIR

ROOT = GRILLAS_ROOT
REVISION_SCRIPT = SCRIPTS_DIR / "05_revision_seleccion_rectangulos.py"
DEFAULT_REVISION = REVISION_DIR
DEFAULT_GEOJSON_GLOB = "muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"
DEFAULT_SELECTION_GLOB = "muestras_finales/seleccion_grilla_ssl4eo_muestras_UTM*_scale300.csv"
DEFAULT_CHIPS_GLOB = "archivos_intermedios/chips_1x1/seleccion/seleccion_chips_1x1_*.geojson"
# Alias retrocompatible con el nombre anterior del parametro
DEFAULT_GPKG_GLOB = DEFAULT_GEOJSON_GLOB
MAP_COLOR_OPTIONS = ["sample_type", "split", "grid_mode", "lulc_mode_name", "eco_dom_name"]

REPORT_STEMS = {
    "resumen": "01_resumen_general",
    "tipo": "02_por_tipo_muestra",
    "eco_clase_pivot": "03_eco_x_clase_pivot",
    "eco_clase_long": "03_eco_x_clase_long",
    "eco_tipo_pivot": "04_eco_x_tipo_pivot",
    "eco_tipo_long": "04_eco_x_tipo_long",
    "clase_tipo_pivot": "05_clase_x_tipo_pivot",
    "clase_tipo_long": "05_clase_x_tipo_long",
    "grid_mode": "06_grid_mode_x_tipo",
    "split": "07_split_x_tipo",
    "criticas_resumen": "08_clases_criticas_resumen",
    "criticas_detalle": "08_clases_criticas_detalle",
    "achaparrado": "08_achaparrado_detalle",
    "calidad": "09_calidad_por_tipo",
}

CRITICAL_DISPLAY_COLS = [
    "grid_id",
    "utm",
    "ecorregion",
    "clase_modal",
    "clase_ultimo",
    "clases_criticas",
    "tipo_muestra",
    "grid_mode",
    "critical_pct",
    "achap_presence_pct",
    "achaparrado_pct",
    "target_rare_class",
    "split",
    "review_tier",
    "valid_area_pct",
    "transition_pct",
]

CALIDAD_METRICS = [
    "valid_area_pct",
    "eco_dom_pct",
    "lulc_mode_pct",
    "transition_pct",
    "shannon_idx",
    "conf_risk_pct",
    "critical_pct",
    "achap_presence_pct",
    "achaparrado_pct",
]


def resolve_glob(pattern: str) -> list[Path]:
    """Resuelve un patron con comodines relativo a grillas/ o absoluto."""
    pat = Path(pattern)
    if pat.is_absolute():
        return sorted(pat.parent.glob(pat.name))
    return sorted(GRILLAS_ROOT.glob(pattern))


def revision_subprocess_cmd(*extra: str) -> list[str]:
    return [sys.executable, str(REVISION_SCRIPT), *extra]


def report_path(revision_dir: Path, stem: str, utm: str) -> Path:
    if utm == "TOTAL":
        return revision_dir / f"{stem}.csv"
    return revision_dir / f"{stem}_{utm}.csv"


def text_report_path(revision_dir: Path, utm: str) -> Path:
    if utm == "TOTAL":
        return revision_dir / "REVISION_COMPLETA.txt"
    return revision_dir / f"REVISION_COMPLETA_{utm}.txt"


def load_csv(revision_dir: Path, stem: str, utm: str) -> pd.DataFrame | None:
    path = report_path(revision_dir, stem, utm)
    if path.exists():
        return pd.read_csv(path, encoding="utf-8-sig")
    fallback = report_path(revision_dir, stem, "TOTAL")
    if not fallback.exists():
        return None
    df = pd.read_csv(fallback, encoding="utf-8-sig")
    if utm != "TOTAL" and "utm" in df.columns:
        return df[df["utm"] == utm].copy()
    return df


def load_pivot(revision_dir: Path, stem: str, utm: str) -> pd.DataFrame | None:
    path = report_path(revision_dir, stem, utm)
    if not path.exists():
        path = report_path(revision_dir, stem, "TOTAL")
        if not path.exists():
            return None
    df = pd.read_csv(path, index_col=0, encoding="utf-8-sig")
    if "TOTAL" in df.columns:
        df = df.drop(columns=["TOTAL"])
    if utm != "TOTAL" and "utm" in df.columns:
        df = df[df["utm"] == utm].drop(columns=["utm"], errors="ignore")
    return df


def load_calidad_means(revision_dir: Path, utm: str) -> pd.DataFrame | None:
    path = report_path(revision_dir, "09_calidad_por_tipo", utm)
    if not path.exists():
        return None
    raw = pd.read_csv(path, header=None, encoding="utf-8-sig")
    metrics = raw.iloc[0].ffill()
    stats = raw.iloc[1]
    names = ["utm", "tipo_muestra"]
    for i in range(2, len(metrics)):
        names.append(f"{metrics.iloc[i]}_{stats.iloc[i]}")
    df = raw.iloc[3:].copy()
    df.columns = names[: len(df.columns)]
    if utm != "TOTAL" and "utm" in df.columns:
        df = df[df["utm"] == utm]
    mean_cols = [c for c in df.columns if c.endswith("_mean")]
    out = df[["utm", "tipo_muestra"] + mean_cols].copy()
    out.columns = ["utm", "tipo_muestra"] + [c[: -len("_mean")] for c in mean_cols]
    for col in out.columns:
        if col not in ("utm", "tipo_muestra"):
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.reset_index(drop=True)


def heatmap_figure(matrix: pd.DataFrame, title: str) -> go.Figure:
    data = matrix.select_dtypes(include="number")
    if data.empty:
        data = matrix
    fig = px.imshow(
        data,
        text_auto=True,
        aspect="auto",
        color_continuous_scale="Blues",
        labels=dict(color="n"),
    )
    fig.update_layout(
        title=title,
        xaxis_title="",
        yaxis_title="",
        margin=dict(l=10, r=10, t=50, b=10),
    )
    fig.update_xaxes(tickangle=45)
    return fig


def bar_tipo_figure(df: pd.DataFrame, utm: str) -> go.Figure:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    if "tipo_muestra" not in data.columns or "n_muestras" not in data.columns:
        return go.Figure()
    order = data.sort_values("n_muestras", ascending=True)
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


def split_figure(df: pd.DataFrame, utm: str) -> go.Figure:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    fig = px.bar(
        data,
        x="tipo_muestra",
        y="n_muestras",
        color="split",
        barmode="stack",
        title="Distribucion train / val / test por tipo",
        category_orders={"split": ["train", "val", "test"]},
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def calidad_figure(df: pd.DataFrame) -> go.Figure:
    if df is None or df.empty:
        return go.Figure()
    metrics = [c for c in CALIDAD_METRICS if c in df.columns]
    melted = df.melt(
        id_vars=["tipo_muestra"],
        value_vars=metrics,
        var_name="metrica",
        value_name="media",
    )
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


@st.cache_data(show_spinner=False)
def load_critical_data(
    revision_dir: Path,
    selection_glob: str,
    utm: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    detalle = load_csv(revision_dir, REPORT_STEMS["criticas_detalle"], utm)
    resumen = load_csv(revision_dir, REPORT_STEMS["criticas_resumen"], utm)

    if detalle is None or detalle.empty:
        detalle = load_csv(revision_dir, REPORT_STEMS["achaparrado"], utm)

    if detalle is None or "clases_criticas" not in detalle.columns:
        paths = resolve_glob(selection_glob)
        frames = []
        for path in paths:
            df = pd.read_csv(path, encoding="utf-8-sig")
            if "utm" not in df.columns:
                name = path.stem.upper()
                if "UTM18" in name:
                    df["utm"] = "UTM18"
                elif "UTM19" in name:
                    df["utm"] = "UTM19"
            frames.append(df)
        if frames:
            detalle = annotate_critical_classes(pd.concat(frames, ignore_index=True))
            if "ecorregion" not in detalle.columns and "eco_dom_name" in detalle.columns:
                detalle["ecorregion"] = detalle["eco_dom_name"]
            if "clase_modal" not in detalle.columns and "lulc_mode_name" in detalle.columns:
                detalle["clase_modal"] = detalle["lulc_mode_name"]
            if "clase_ultimo" not in detalle.columns and "lulc_last_name" in detalle.columns:
                detalle["clase_ultimo"] = detalle["lulc_last_name"]
            if "tipo_muestra" not in detalle.columns and "sample_type" in detalle.columns:
                detalle["tipo_muestra"] = detalle["sample_type"]

    if detalle is None:
        detalle = pd.DataFrame()
    else:
        if "clases_criticas" not in detalle.columns:
            detalle = annotate_critical_classes(detalle)
        if utm != "TOTAL" and "utm" in detalle.columns:
            detalle = detalle[detalle["utm"] == utm].copy()

    if detalle.empty:
        crit = detalle
    else:
        crit = detalle[detalle["tiene_clase_critica"]].copy()

    if resumen is None or resumen.empty:
        resumen = critical_summary(crit) if not crit.empty else critical_summary(detalle)

    return crit, resumen


def critical_summary_figure(resumen: pd.DataFrame) -> go.Figure:
    data = resumen[resumen["clase"] != "TOTAL (cualquier critica)"].copy()
    fig = px.bar(
        data,
        x="clase",
        y="n_muestras",
        text="n_muestras",
        title="Muestras por clase critica",
        color="clase",
    )
    fig.update_traces(textposition="outside")
    fig.update_layout(
        xaxis_tickangle=45,
        showlegend=False,
        margin=dict(l=10, r=10, t=50, b=10),
    )
    return fig


def grid_mode_figure(df: pd.DataFrame, utm: str) -> go.Figure:
    data = df.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        data = data[data["utm"] == utm]
    fig = px.bar(
        data,
        x="tipo_muestra",
        y="n_muestras",
        color="grid_mode",
        barmode="group",
        title="Homogeneo vs mixto por tipo",
    )
    fig.update_layout(xaxis_tickangle=45, margin=dict(l=10, r=10, t=50, b=10))
    return fig


def _utm_zone_from_view(utm: str) -> int | None:
    if utm == "TOTAL":
        return None
    return int(utm.replace("UTM", ""))


def _filter_gdf_by_utm(gdf, utm: str, path: Path | None = None):
    if utm == "TOTAL":
        return gdf
    zone = _utm_zone_from_view(utm)
    if "utm_zone" in gdf.columns:
        return gdf[pd.to_numeric(gdf["utm_zone"], errors="coerce") == zone]
    if path and f"UTM{zone}" in path.name.upper():
        return gdf
    return gdf.iloc[0:0]


def _prepare_map_columns(gdf) -> None:
    if "sample_type" in gdf.columns:
        gdf["sample_type"] = gdf["sample_type"].astype(str)
    elif "sample_type_gee" in gdf.columns:
        gdf["sample_type"] = gdf["sample_type_gee"].astype(str)
    else:
        gdf["sample_type"] = "sin_tipo"
    for col, default in (
        ("grid_mode", ""),
        ("eco_dom_name", ""),
        ("lulc_mode_name", ""),
        ("split", ""),
        ("clases_criticas", ""),
        ("target_rare_class", ""),
        ("parent_grid_id", ""),
    ):
        gdf[col] = gdf[col].astype(str) if col in gdf.columns else default
    if "utm_zone" in gdf.columns:
        gdf["utm"] = "UTM" + pd.to_numeric(gdf["utm_zone"], errors="coerce").fillna(0).astype(int).astype(str)


@st.cache_data(show_spinner=False)
def load_selection_geometries(gpkg_glob: str, utm: str):
    try:
        import geopandas as gpd
    except ImportError:
        return None
    paths = resolve_glob(gpkg_glob)
    if not paths:
        return None
    frames = []
    for path in paths:
        gdf = gpd.read_file(path)
        gdf = _filter_gdf_by_utm(gdf, utm, path)
        if gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(32700 + int(gdf["utm_zone"].iloc[0]))
        gdf = gdf.to_crs(4326)
        _prepare_map_columns(gdf)
        gdf["map_id"] = gdf["grid_id"].astype(str)
        frames.append(gdf)
    if not frames:
        return None
    import geopandas as gpd
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")


@st.cache_data(show_spinner=False)
def load_chips_geometries(chips_glob: str, utm: str):
    try:
        import geopandas as gpd
    except ImportError:
        return None
    paths = resolve_glob(chips_glob)
    if not paths:
        return None
    frames = []
    for path in paths:
        gdf = gpd.read_file(path)
        if utm != "TOTAL" and f"UTM{_utm_zone_from_view(utm)}" not in path.name.upper():
            if "utm_zone" in gdf.columns:
                gdf = _filter_gdf_by_utm(gdf, utm)
            elif utm != "TOTAL":
                continue
        if gdf.empty:
            continue
        if gdf.crs is None:
            gdf = gdf.set_crs(4326)
        gdf = gdf.to_crs(4326)
        _prepare_map_columns(gdf)
        if "parent_grid_id" not in gdf.columns and "parent_gri" in gdf.columns:
            gdf["parent_grid_id"] = gdf["parent_gri"]
        gdf["map_id"] = "chip_" + gdf["grid_id"].astype(str)
        gdf["_layer"] = "chip_1x1"
        frames.append(gdf)
    if not frames:
        return None
    import geopandas as gpd
    return gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), geometry="geometry", crs="EPSG:4326")


def selection_map_figure(
    gdf,
    color_by: str = "sample_type",
    chips_gdf=None,
    *,
    title: str = "Rectangulos seleccionados (2x2 / 3x3)",
) -> go.Figure:
    color_col = color_by if color_by in gdf.columns else "sample_type"
    geojson = json.loads(gdf.to_json())
    fig = px.choropleth_map(
        gdf,
        geojson=geojson,
        locations="map_id",
        featureidkey="properties.map_id",
        color=color_col,
        hover_name="grid_id",
        hover_data={
            c: True
            for c in ("sample_type", "grid_mode", "eco_dom_name", "lulc_mode_name", "split", "utm")
            if c in gdf.columns
        },
        center={"lat": -38.5, "lon": -71.5},
        zoom=3.6,
        height=680,
        title=title,
        opacity=0.55,
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=50, b=0))

    if chips_gdf is not None and not chips_gdf.empty:
        chip_geojson = json.loads(chips_gdf.to_json())
        chip_fig = px.choropleth_map(
            chips_gdf,
            geojson=chip_geojson,
            locations="map_id",
            featureidkey="properties.map_id",
            color="_layer",
            color_discrete_map={"chip_1x1": "#d64545"},
            hover_name="grid_id",
            hover_data={
                c: True
                for c in ("parent_grid_id", "target_rare_class", "lulc_mode_name", "clases_criticas")
                if c in chips_gdf.columns
            },
            opacity=0.85,
        )
        for trace in chip_fig.data:
            trace.name = "Chip 1x1 (clase critica)"
            trace.showlegend = True
            fig.add_trace(trace)
    return fig


def map_figure(df: pd.DataFrame, color_by: str) -> go.Figure:
    """Compatibilidad: mapa de centroides si solo hay tabla puntual."""
    fig = px.scatter_map(
        df,
        lat="lat",
        lon="lon",
        color=color_by,
        hover_name="grid_id",
        hover_data=["ecorregion", "clase_modal", "achap_pct", "split"],
        zoom=3.5,
        height=600,
        title="Ubicacion de muestras seleccionadas",
    )
    fig.update_layout(map_style="open-street-map", margin=dict(l=0, r=0, t=40, b=0))
    return fig


def show_kpis(resumen: pd.DataFrame, utm: str) -> None:
    if resumen is None or resumen.empty:
        st.warning("No hay resumen general.")
        return
    data = resumen.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        row = data[data["utm"] == utm]
        if row.empty:
            row = data[data["utm"] == "TOTAL"]
    else:
        row = data[data["utm"] == "TOTAL"] if "utm" in data.columns else data.head(1)
    if row.empty:
        row = data.head(1)
    r = row.iloc[0]
    cols = st.columns(5)
    metrics = [
        ("Muestras", "n_muestras"),
        ("Ecorregiones", "n_ecorregiones"),
        ("Clases modales", "n_clases_modales"),
        ("Clases criticas", "n_clases_criticas"),
        ("Homogeneo / Mixto", None),
    ]
    for col, (label, key) in zip(cols, metrics):
        if key is None:
            hom = int(r.get("n_homogeneo", 0))
            mix = int(r.get("n_mixto", 0))
            col.metric(label, f"{hom} / {mix}")
        else:
            value = r.get(key)
            if pd.isna(value) and key == "n_clases_criticas":
                value = r.get("n_achaparrado", 0)
            col.metric(label, int(value or 0))


def render_critical_tab(
    revision_dir: Path,
    selection_glob: str,
    utm: str,
) -> None:
    crit, resumen = load_critical_data(revision_dir, selection_glob, utm)
    class_options = ["Todas"] + list(CRITICAL_CLASS_NAMES.values())

    st.caption(
        "Clases criticas definidas en `caracterizacion_grillas_gee.py`: "
        + ", ".join(f"{i} {n}" for i, n in CRITICAL_CLASS_NAMES.items())
    )

    if crit.empty:
        st.info("No hay muestras con clases criticas en esta vista.")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        st.dataframe(resumen, use_container_width=True, hide_index=True)
    with c2:
        st.plotly_chart(critical_summary_figure(resumen), use_container_width=True)

    selected = st.selectbox("Filtrar por clase", class_options, index=0)
    view = crit.copy()
    if selected != "Todas":
        view = view[view["clases_criticas"].str.contains(selected, regex=False, na=False)]

    st.metric("Muestras en filtro", len(view))

    pct_col = presence_pct_column(selected) if selected != "Todas" else "critical_pct"
    if pct_col and pct_col in view.columns and not view.empty:
        st.plotly_chart(
            px.histogram(
                view,
                x=pct_col,
                color="utm" if utm == "TOTAL" and "utm" in view.columns else None,
                nbins=20,
                title=f"Distribucion de {pct_col} (%)",
            ),
            use_container_width=True,
        )

    cols = [c for c in CRITICAL_DISPLAY_COLS if c in view.columns]
    st.dataframe(view[cols], use_container_width=True, hide_index=True)


def render_dashboard(
    revision_dir: Path,
    utm: str,
    gpkg_glob: str,
    selection_glob: str,
    chips_glob: str,
) -> None:
    st.title("Revision de seleccion SSL4EO — scale300")
    st.caption(f"Carpeta: `{revision_dir}` · Vista: **{utm}**")

    resumen = load_csv(revision_dir, REPORT_STEMS["resumen"], utm)
    show_kpis(resumen, utm)

    tab_resumen, tab_eco, tab_tipo, tab_crit, tab_calidad, tab_mapa, tab_txt = st.tabs(
        [
            "Resumen",
            "Cobertura eco/clase",
            "Tipos y split",
            "Clases criticas",
            "Calidad",
            "Mapa",
            "Informe texto",
        ]
    )

    with tab_resumen:
        if resumen is not None:
            st.subheader("Indicadores generales")
            st.dataframe(resumen, use_container_width=True, hide_index=True)
        por_tipo = load_csv(revision_dir, REPORT_STEMS["tipo"], utm)
        if por_tipo is not None:
            st.plotly_chart(bar_tipo_figure(por_tipo, utm), use_container_width=True)

    with tab_eco:
        c1, c2 = st.columns(2)
        eco_clase = load_pivot(revision_dir, REPORT_STEMS["eco_clase_pivot"], utm)
        eco_tipo = load_pivot(revision_dir, REPORT_STEMS["eco_tipo_pivot"], utm)
        clase_tipo = load_pivot(revision_dir, REPORT_STEMS["clase_tipo_pivot"], utm)
        with c1:
            if eco_clase is not None:
                st.plotly_chart(
                    heatmap_figure(eco_clase, "Ecorregion x clase modal"),
                    use_container_width=True,
                )
        with c2:
            if eco_tipo is not None:
                st.plotly_chart(
                    heatmap_figure(eco_tipo, "Ecorregion x tipo de muestra"),
                    use_container_width=True,
                )
        if clase_tipo is not None:
            st.plotly_chart(
                heatmap_figure(clase_tipo, "Clase modal x tipo de muestra"),
                use_container_width=True,
            )

    with tab_tipo:
        split_df = load_csv(revision_dir, REPORT_STEMS["split"], utm)
        grid_df = load_csv(revision_dir, REPORT_STEMS["grid_mode"], utm)
        if split_df is not None:
            st.plotly_chart(split_figure(split_df, utm), use_container_width=True)
        if grid_df is not None:
            st.plotly_chart(grid_mode_figure(grid_df, utm), use_container_width=True)
        if por_tipo is not None:
            st.dataframe(por_tipo, use_container_width=True, hide_index=True)

    with tab_crit:
        render_critical_tab(revision_dir, selection_glob, utm)

    with tab_calidad:
        calidad = load_calidad_means(revision_dir, utm)
        if calidad is None or calidad.empty:
            st.warning("No se encontro 09_calidad_por_tipo.csv")
        else:
            st.plotly_chart(calidad_figure(calidad), use_container_width=True)
            st.dataframe(calidad, use_container_width=True, hide_index=True)

    with tab_mapa:
        sel_gdf = load_selection_geometries(gpkg_glob, utm)
        chips_gdf = load_chips_geometries(chips_glob, utm)
        if sel_gdf is None or sel_gdf.empty:
            st.info(
                "No hay archivos GPKG de seleccion. "
                f"Se buscan en: `{GRILLAS_ROOT / gpkg_glob}`"
            )
        else:
            color_opts = [c for c in MAP_COLOR_OPTIONS if c in sel_gdf.columns]
            color_by = st.selectbox("Color", color_opts or ["sample_type"], index=0)
            show_chips = st.checkbox(
                "Superponer chips 1x1 (intermedio, opcional)",
                value=False,
                disabled=chips_gdf is None or chips_gdf.empty,
            )
            n2 = len(sel_gdf)
            n1 = len(chips_gdf) if chips_gdf is not None else 0
            st.caption(f"Rectangulos seleccionados: **{n2}**" + (f" · Chips 1x1: **{n1}**" if n1 else ""))
            st.plotly_chart(
                selection_map_figure(
                    sel_gdf,
                    color_by,
                    chips_gdf if show_chips else None,
                ),
                use_container_width=True,
            )

    with tab_txt:
        txt_path = text_report_path(revision_dir, utm)
        if txt_path.exists():
            st.code(txt_path.read_text(encoding="utf-8"), language=None)
        else:
            st.warning(f"No existe {txt_path.name}")


def ensure_revision_reports(revision_dir: Path) -> tuple[bool, str]:
    """Genera reportes CSV si la carpeta revision aun no existe."""
    if revision_dir.exists() and any(revision_dir.glob("*.csv")):
        return True, ""
    geojsons = sorted(FINALES_DIR.glob("seleccion_grilla_ssl4eo_muestras_UTM*_scale300.geojson"))
    if not geojsons:
        return False, (
            "No hay reportes de revision ni selecciones .geojson en muestras_finales/. "
            "Ejecuta primero scripts/03_seleccion_rectangulos.py y scripts/05_revision_seleccion_rectangulos.py."
        )
    revision_dir.mkdir(parents=True, exist_ok=True)
    cmd = revision_subprocess_cmd(
        "--input",
        *[str(p.relative_to(GRILLAS_ROOT)) for p in geojsons],
    )
    result = subprocess.run(cmd, cwd=GRILLAS_ROOT, capture_output=True, text=True)
    if result.returncode != 0:
        return False, result.stderr or result.stdout or "Error desconocido."
    return True, ""


def run_streamlit() -> None:
    st.set_page_config(
        page_title="Revision SSL4EO scale300",
        page_icon="🗺️",
        layout="wide",
    )

    with st.sidebar:
        st.header("Opciones")
        revision_dir = Path(
            st.text_input("Carpeta de reportes", str(DEFAULT_REVISION))
        )
        utm = st.radio("Huso UTM", ["TOTAL", "UTM18", "UTM19"], index=0)
        gpkg_glob = st.text_input("Patron GeoJSON (mapa)", DEFAULT_GEOJSON_GLOB)
        selection_glob = st.text_input(
            "Patron CSV seleccion (clases criticas)", DEFAULT_SELECTION_GLOB
        )
        chips_glob = st.text_input("Patron GeoJSON chips 1x1 (opcional)", DEFAULT_CHIPS_GLOB)
        if st.button("Regenerar reportes"):
            with st.spinner("Ejecutando 05_revision_seleccion_rectangulos.py..."):
                result = subprocess.run(
                    revision_subprocess_cmd("--utm", "18", "19"),
                    cwd=GRILLAS_ROOT,
                    capture_output=True,
                    text=True,
                )
            if result.returncode == 0:
                st.success("Reportes actualizados.")
                st.cache_data.clear()
            else:
                st.error(result.stderr or result.stdout)

        if not revision_dir.exists():
            ok, msg = ensure_revision_reports(revision_dir)
            if ok:
                st.info("Reportes generados automaticamente desde las selecciones .geojson.")
                st.cache_data.clear()
            else:
                st.error(msg or "La carpeta de reportes no existe.")
                st.caption(
                    "Generala manualmente:\n"
                    "`python scripts/05_revision_seleccion_rectangulos.py --utm 18 19`"
                )

    if revision_dir.exists():
        render_dashboard(revision_dir, utm, gpkg_glob, selection_glob, chips_glob)


HTML_STYLE = """
body { font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f4f6f8; color: #1f2933; }
.wrap { max-width: 1400px; margin: 0 auto; padding: 24px; }
.hero { background: linear-gradient(135deg, #0f4c75, #1b6ca8); color: #fff; padding: 28px 32px; border-radius: 12px; margin-bottom: 24px; }
.hero h1 { margin: 0 0 8px; font-size: 1.8rem; }
.hero p { margin: 0; opacity: 0.9; }
.kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
.kpi { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 3px rgba(0,0,0,.08); }
.kpi .label { font-size: 0.85rem; color: #52606d; margin-bottom: 6px; }
.kpi .value { font-size: 1.6rem; font-weight: 700; color: #102a43; }
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


def kpi_row(resumen: pd.DataFrame | None, utm: str) -> dict[str, str]:
    if resumen is None or resumen.empty:
        return {}
    data = resumen.copy()
    if utm != "TOTAL" and "utm" in data.columns:
        row = data[data["utm"] == utm]
        if row.empty:
            row = data[data["utm"] == "TOTAL"]
    else:
        row = data[data["utm"] == "TOTAL"] if "utm" in data.columns else data.head(1)
    if row.empty:
        row = data.head(1)
    r = row.iloc[0]
    crit = r.get("n_clases_criticas")
    if pd.isna(crit):
        crit = r.get("n_achaparrado", 0)
    return {
        "Muestras": str(int(r.get("n_muestras", 0) or 0)),
        "Ecorregiones": str(int(r.get("n_ecorregiones", 0) or 0)),
        "Clases modales": str(int(r.get("n_clases_modales", 0) or 0)),
        "Clases criticas": str(int(crit or 0)),
        "Homogeneo / Mixto": f"{int(r.get('n_homogeneo', 0) or 0)} / {int(r.get('n_mixto', 0) or 0)}",
    }


def styled_table(df: pd.DataFrame) -> str:
    return df.to_html(index=False, classes="data", border=0)


def html_section(title: str, body: str) -> str:
    return f'<section class="section"><h2>{title}</h2>{body}</section>'


def html_chart(fig: go.Figure, *, include_js: bool = False) -> str:
    return (
        f'<div class="chart">{fig.to_html(full_html=False, include_plotlyjs="cdn" if include_js else False)}</div>'
    )


def export_html(
    output: Path,
    revision_dir: Path,
    utm: str,
    *,
    gpkg_glob: str = DEFAULT_GPKG_GLOB,
    chips_glob: str = DEFAULT_CHIPS_GLOB,
) -> None:
    """Genera un HTML estatico con el mismo contenido principal del dashboard."""
    resumen = load_csv(revision_dir, REPORT_STEMS["resumen"], utm)
    por_tipo = load_csv(revision_dir, REPORT_STEMS["tipo"], utm)
    eco_clase = load_pivot(revision_dir, REPORT_STEMS["eco_clase_pivot"], utm)
    eco_tipo = load_pivot(revision_dir, REPORT_STEMS["eco_tipo_pivot"], utm)
    clase_tipo = load_pivot(revision_dir, REPORT_STEMS["clase_tipo_pivot"], utm)
    split_df = load_csv(revision_dir, REPORT_STEMS["split"], utm)
    calidad = load_calidad_means(revision_dir, utm)
    crit, crit_resumen = load_critical_data(revision_dir, DEFAULT_SELECTION_GLOB, utm)

    parts = [
        "<!DOCTYPE html>",
        "<html lang='es'><head>",
        "<meta charset='utf-8'>",
        "<meta name='viewport' content='width=device-width, initial-scale=1'>",
        "<title>Revision SSL4EO scale300</title>",
        f"<style>{HTML_STYLE}</style>",
        "</head><body><div class='wrap'>",
        "<header class='hero'>",
        "<h1>Revision de seleccion SSL4EO — scale300</h1>",
        f"<p>Vista: <strong>{utm}</strong> · Carpeta: <code>{revision_dir}</code></p>",
        "</header>",
    ]

    kpis = kpi_row(resumen, utm)
    if kpis:
        cards = "".join(
            f"<div class='kpi'><div class='label'>{label}</div><div class='value'>{value}</div></div>"
            for label, value in kpis.items()
        )
        parts.append(f"<div class='kpis'>{cards}</div>")

    if resumen is not None:
        parts.append(html_section("Resumen general", styled_table(resumen)))

    plotly_added = False
    if por_tipo is not None:
        parts.append(
            html_section(
                "Muestras por tipo",
                html_chart(bar_tipo_figure(por_tipo, utm), include_js=not plotly_added),
            )
        )
        plotly_added = True

    heatmaps = []
    if eco_clase is not None:
        heatmaps.append(html_chart(heatmap_figure(eco_clase, "Ecorregion x clase modal"), include_js=not plotly_added))
        plotly_added = True
    if eco_tipo is not None:
        heatmaps.append(html_chart(heatmap_figure(eco_tipo, "Ecorregion x tipo de muestra"), include_js=not plotly_added))
        plotly_added = True
    if heatmaps:
        parts.append(html_section("Cobertura eco / clase", f"<div class='grid-2'>{''.join(heatmaps)}</div>"))

    if clase_tipo is not None:
        parts.append(
            html_section(
                "Clase modal x tipo de muestra",
                html_chart(heatmap_figure(clase_tipo, "Clase modal x tipo de muestra"), include_js=not plotly_added),
            )
        )
        plotly_added = True

    if split_df is not None:
        parts.append(
            html_section(
                "Tipos y split",
                html_chart(split_figure(split_df, utm), include_js=not plotly_added),
            )
        )
        plotly_added = True

    if not crit.empty:
        crit_body = (
            "<p class='note'>Clases criticas segun <code>caracterizacion_grillas_gee.py</code>: "
            + ", ".join(f"{i} {n}" for i, n in CRITICAL_CLASS_NAMES.items())
            + "</p>"
            + f"<div class='grid-2'>{styled_table(crit_resumen)}"
            + html_chart(critical_summary_figure(crit_resumen), include_js=not plotly_added)
            + "</div>"
        )
        plotly_added = True
        cols = [c for c in CRITICAL_DISPLAY_COLS if c in crit.columns]
        crit_body += styled_table(crit[cols].head(50))
        if len(crit) > 50:
            crit_body += f"<p class='note'>Mostrando 50 de {len(crit)} filas.</p>"
        parts.append(html_section("Clases criticas", crit_body))
    else:
        parts.append(html_section("Clases criticas", "<p class='note'>No hay muestras con clases criticas en esta vista.</p>"))

    if calidad is not None:
        parts.append(
            html_section(
                "Calidad por tipo",
                html_chart(calidad_figure(calidad), include_js=not plotly_added),
            )
        )
        plotly_added = True

    sel_gdf = load_selection_geometries(gpkg_glob, utm)
    chips_gdf = load_chips_geometries(chips_glob, utm)
    if sel_gdf is not None and not sel_gdf.empty:
        n2 = len(sel_gdf)
        n1 = len(chips_gdf) if chips_gdf is not None else 0
        map_note = (
            f"<p class='note'>Mapa interactivo: <strong>{n2}</strong> rectangulos seleccionados"
            + (f" y <strong>{n1}</strong> chips 1x1 (rojo) de clases criticas." if n1 else ".")
            + " Color por tipo de muestra.</p>"
        )
        map_body = map_note + html_chart(
            selection_map_figure(
                sel_gdf,
                "sample_type",
                chips_gdf,
                title=f"Todos los rectangulos seleccionados — {utm}",
            ),
            include_js=not plotly_added,
        )
        plotly_added = True
        parts.append(html_section("Mapa de muestras", map_body))

    txt_path = text_report_path(revision_dir, utm)
    if txt_path.exists():
        txt = txt_path.read_text(encoding="utf-8")
        parts.append(
            html_section(
                "Informe texto",
                f"<pre style='white-space:pre-wrap;background:#f8fafc;padding:12px;border-radius:8px;'>{txt}</pre>",
            )
        )

    parts.extend(["</div></body></html>"])
    output.write_text("\n".join(parts), encoding="utf-8")
    print(f"HTML exportado: {output}")


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visualizador de reportes de revision.")
    p.add_argument("--revision-dir", type=Path, default=DEFAULT_REVISION)
    p.add_argument("--utm", default="TOTAL", choices=["TOTAL", "UTM18", "UTM19"])
    p.add_argument("--gpkg-glob", default=DEFAULT_GPKG_GLOB)
    p.add_argument("--chips-glob", default=DEFAULT_CHIPS_GLOB)
    p.add_argument("--export-html", type=Path, help="Exportar dashboard estatico a HTML.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.export_html:
        export_html(
            args.export_html,
            args.revision_dir,
            args.utm,
            gpkg_glob=args.gpkg_glob,
            chips_glob=args.chips_glob,
        )
        return 0
    if "streamlit" not in sys.modules:
        print(
            "Ejecuta con: streamlit run scripts/07_visualizar_reportes.py",
            file=sys.stderr,
        )
        return 1
    run_streamlit()
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and any(arg.startswith("--") for arg in sys.argv[1:]):
        sys.exit(main())
    run_streamlit()
