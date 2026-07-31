#!/usr/bin/env python3
"""
Visualizador de segmentos etiquetados C2 con filtro de pureza.

Streamlit (interactivo):
  streamlit run visualizar_segmentos_etiquetados.py
  streamlit run visualizar_segmentos_etiquetados.py -- --gpkg /ruta/labeled_segments.gpkg

HTML estático (slider de pureza en el navegador):
  python visualizar_segmentos_etiquetados.py --export-html salida.html \\
      --gpkg /home/lserey/mapbiomas_land/prod/labeling_slic_rev2015/18GXA/.../labeled_segments.gpkg
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import pandas as pd

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from paleta_c2 import rgb_clase  # noqa: E402

DEFAULT_LABELING_ROOT = Path("/home/lserey/mapbiomas_land/prod/labeling_slic_rev2015")
DEFAULT_GPKG = (
    DEFAULT_LABELING_ROOT
    / "18GXA/18GXA_3x3_c003_r003/18GXA_3x3_c003_r003_labeled_segments.gpkg"
)


def listar_gpkg_disponibles(root: Path) -> list[Path]:
    if not root.is_dir():
        return []
    return sorted(root.rglob("*_labeled_segments.gpkg"))


def cargar_gpkg(path: Path) -> gpd.GeoDataFrame:
    gdf = gpd.read_file(path)
    for col in ("pureza", "pureza_2", "clase_moda", "clase_2", "area_px", "n_clases"):
        if col not in gdf.columns:
            raise ValueError(f"Falta columna {col!r} en {path}")
    gdf = gdf.copy()
    gdf["pureza"] = pd.to_numeric(gdf["pureza"], errors="coerce").fillna(0)
    gdf["pureza_2"] = pd.to_numeric(gdf["pureza_2"], errors="coerce").fillna(0)
    gdf["clase_moda"] = gdf["clase_moda"].astype(int)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    return gdf


def agregar_colores(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    out = gdf.copy()
    rgbs = out["clase_moda"].map(rgb_clase)
    out["fill_r"] = [c[0] for c in rgbs]
    out["fill_g"] = [c[1] for c in rgbs]
    out["fill_b"] = [c[2] for c in rgbs]
    return out


def filtrar_pureza(
    gdf: gpd.GeoDataFrame,
    pureza_min: float,
    solo_protegidas: bool = False,
) -> gpd.GeoDataFrame:
    m = gdf["pureza"] >= pureza_min
    if solo_protegidas and "tiene_protegida" in gdf.columns:
        m &= gdf["tiene_protegida"].astype(bool)
    return gdf.loc[m].copy()


def resumen_por_clase(
    gdf: gpd.GeoDataFrame,
    pureza_min: float = 0,
    solo_protegidas: bool = False,
) -> pd.DataFrame:
    """Segmentos y superficie (ha) por clase_moda presente en el rectángulo."""
    vis = filtrar_pureza(gdf, pureza_min, solo_protegidas)
    if vis.empty:
        return pd.DataFrame(
            columns=["clase_moda", "clase_moda_nombre", "n_segmentos", "area_ha", "fill_r", "fill_g", "fill_b"]
        )

    area_col = "area_ha" if "area_ha" in vis.columns else "area_px"
    nombre_col = "clase_moda_nombre" if "clase_moda_nombre" in vis.columns else None

    agg = {area_col: "sum", "segment_id": "count"}
    if nombre_col:
        agg[nombre_col] = "first"

    tbl = (
        vis.groupby("clase_moda", as_index=False)
        .agg(agg)
        .rename(columns={"segment_id": "n_segmentos", area_col: "area_ha"})
    )
    if not nombre_col:
        tbl["clase_moda_nombre"] = tbl["clase_moda"].astype(str)

    rgbs = tbl["clase_moda"].map(rgb_clase)
    tbl["fill_r"] = [c[0] for c in rgbs]
    tbl["fill_g"] = [c[1] for c in rgbs]
    tbl["fill_b"] = [c[2] for c in rgbs]
    return tbl.sort_values("area_ha", ascending=False).reset_index(drop=True)


def _feature_props(row: pd.Series) -> dict:
    return {
        "segment_id": int(row["segment_id"]),
        "clase_moda": int(row["clase_moda"]),
        "clase_moda_nombre": str(row.get("clase_moda_nombre", "")),
        "pureza": float(row["pureza"]),
        "clase_2": int(row.get("clase_2", 0) or 0),
        "pureza_2": float(row.get("pureza_2", 0) or 0),
        "n_clases": int(row.get("n_clases", 0) or 0),
        "area_px": int(row.get("area_px", 0) or 0),
        "area_ha": float(row.get("area_ha", 0) or 0),
        "distribucion_top3": str(row.get("distribucion_top3", "")),
        "tiene_protegida": bool(row.get("tiene_protegida", False)),
        "fill_r": int(row["fill_r"]),
        "fill_g": int(row["fill_g"]),
        "fill_b": int(row["fill_b"]),
    }


def gdf_a_feature_collection(gdf_wgs: gpd.GeoDataFrame, *, simplify: float = 1e-5) -> dict:
    gdf = gdf_wgs
    if simplify > 0:
        gdf = gdf_wgs.copy()
        gdf["geometry"] = gdf.geometry.simplify(simplify, preserve_topology=True)
    features = []
    for _, row in gdf.iterrows():
        features.append(
            {
                "type": "Feature",
                "geometry": row.geometry.__geo_interface__,
                "properties": _feature_props(row),
            }
        )
    return {"type": "FeatureCollection", "features": features}


def render_leaflet_html(
    gdf: gpd.GeoDataFrame,
    *,
    pureza_min: float = 0,
    solo_protegidas: bool = False,
    map_id: str = "map",
    interactive: bool = False,
    pureza_inicial: int = 30,
    titulo: str | None = None,
) -> str:
    """Mapa Leaflet: todos los segmentos visibles; resalta pureza ≥ umbral."""
    gdf_wgs = gdf.to_crs(epsg=4326)
    bounds = gdf_wgs.total_bounds
    center_lat = (bounds[1] + bounds[3]) / 2
    center_lon = (bounds[0] + bounds[2]) / 2
    fc = gdf_a_feature_collection(gdf_wgs)
    geojson_str = json.dumps(fc, ensure_ascii=False, separators=(",", ":"))
    clases_rect = resumen_por_clase(gdf, pureza_min=0, solo_protegidas=False)
    clases_meta = clases_rect[
        ["clase_moda", "clase_moda_nombre", "fill_r", "fill_g", "fill_b"]
    ].to_dict(orient="records")
    clases_meta_str = json.dumps(clases_meta, ensure_ascii=False, separators=(",", ":"))

    if interactive:
        bar_html = f"""
  <div id="bar">
    <div>
      <label>Pureza mínima (%): <span id="pureza-val">{pureza_inicial}</span></label><br/>
      <input type="range" id="pureza-slider" min="0" max="100" value="{pureza_inicial}" step="1" style="width:280px"/>
    </div>
    <label><input type="checkbox" id="solo-protegidas"/> Solo tier protegido</label>
    <div id="stats">—</div>
  </div>"""
        map_height = "100%"
        body_style = "body { margin: 0; font-family: system-ui, sans-serif; }"
        bar_style = """
    #bar {
      height: 88px; padding: 10px 16px; box-sizing: border-box;
      background: #1e1e1e; color: #eee; display: flex; flex-wrap: wrap;
      align-items: center; gap: 16px; flex-shrink: 0;
    }
    #pureza-val { font-weight: 700; min-width: 3em; }
    #stats { font-size: 13px; opacity: 0.9; }
    #layout { display: flex; flex-direction: column; height: 100vh; }
    #main { display: flex; flex: 1; min-height: 0; }
    #class-panel {
      width: 300px; flex-shrink: 0; overflow-y: auto;
      background: #fafafa; color: #222; border-left: 1px solid #ccc;
      padding: 10px 12px; box-sizing: border-box; font-size: 12px;
    }
    #class-panel h3 { margin: 0 0 8px; font-size: 13px; }
    #class-panel .hint { margin: 0 0 8px; color: #666; font-size: 11px; }
    #class-table { width: 100%; border-collapse: collapse; }
    #class-table th, #class-table td {
      padding: 4px 6px; border-bottom: 1px solid #e0e0e0; text-align: right;
    }
    #class-table th:first-child, #class-table td:first-child,
    #class-table th:nth-child(2), #class-table td:nth-child(2) { text-align: left; }
    #class-table tr.total td { font-weight: 700; border-top: 2px solid #bbb; }
    .swatch {
      display: inline-block; width: 12px; height: 12px;
      border: 1px solid #888; vertical-align: middle;
    }"""
        panel_html = """
  <div id="class-panel">
    <h3>Por clase (rectángulo)</h3>
    <p class="hint" id="class-hint">Segmentos con pureza ≥ umbral</p>
    <table id="class-table">
      <thead>
        <tr><th></th><th>Clase</th><th>N seg</th><th>Sup. (ha)</th></tr>
      </thead>
      <tbody id="class-tbody"></tbody>
    </table>
  </div>"""
        layout_wrap_open = '<div id="layout">'
        layout_wrap_close = "</div>"
        main_open = '<div id="main">'
        main_close = "</div>"
        filter_init = """
    let minPureza = +document.getElementById("pureza-slider").value;
    let soloProtegidas = document.getElementById("solo-protegidas").checked;
    const CLASES_RECT = """ + clases_meta_str + ";"
        filter_handlers = """
    function updateClassTable() {
      const byClass = new Map();
      for (const meta of CLASES_RECT) {
        byClass.set(meta.clase_moda, {
          ...meta, n: 0, ha: 0,
        });
      }
      for (const f of DATA.features) {
        const p = f.properties;
        if (!cumple(p)) continue;
        const row = byClass.get(p.clase_moda);
        if (!row) continue;
        row.n += 1;
        row.ha += p.area_ha || 0;
      }
      const rows = [...byClass.values()]
        .filter(r => r.n > 0)
        .sort((a, b) => b.ha - a.ha);
      let totN = 0, totHa = 0;
      const tbody = document.getElementById("class-tbody");
      tbody.innerHTML = rows.map(r => {
        totN += r.n;
        totHa += r.ha;
        const rgb = `rgb(${r.fill_r},${r.fill_g},${r.fill_b})`;
        const nombre = `${r.clase_moda_nombre} (${r.clase_moda})`;
        return `<tr>` +
          `<td><span class="swatch" style="background:${rgb}"></span></td>` +
          `<td>${nombre}</td><td>${r.n.toLocaleString()}</td>` +
          `<td>${r.ha.toLocaleString(undefined, {maximumFractionDigits: 1})}</td></tr>`;
      }).join("") +
        `<tr class="total"><td></td><td>Total</td>` +
        `<td>${totN.toLocaleString()}</td>` +
        `<td>${totHa.toLocaleString(undefined, {maximumFractionDigits: 1})}</td></tr>`;
    }

    function updateStats() {
      const n = DATA.features.filter(f => cumple(f.properties)).length;
      const pct = DATA.features.length ? (100 * n / DATA.features.length).toFixed(1) : 0;
      document.getElementById("pureza-val").textContent = minPureza;
      document.getElementById("stats").textContent =
        `Marcados ${n} / ${DATA.features.length} segmentos con pureza ≥ ${minPureza}% (${pct}%)`;
      updateClassTable();
    }

    function refresh() {
      minPureza = +document.getElementById("pureza-slider").value;
      soloProtegidas = document.getElementById("solo-protegidas").checked;
      geoLayer.eachLayer(layer => layer.setStyle(style(layer.feature)));
      updateStats();
    }

    document.getElementById("pureza-slider").addEventListener("input", refresh);
    document.getElementById("solo-protegidas").addEventListener("change", refresh);
    updateStats();"""
    else:
        bar_html = ""
        panel_html = ""
        layout_wrap_open = ""
        layout_wrap_close = ""
        main_open = ""
        main_close = ""
        map_height = "100%"
        body_style = ""
        bar_style = ""
        filter_init = f"""
    let minPureza = {pureza_min};
    let soloProtegidas = {"true" if solo_protegidas else "false"};"""
        filter_handlers = ""

    title_tag = f"<title>{titulo}</title>" if titulo else ""

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8"/>
  {title_tag}
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    {body_style}
    {bar_style}
    html, body {{ margin: 0; height: 100%; width: 100%; }}
    #{map_id} {{ margin: 0; height: {map_height}; width: 100%; flex: 1; min-width: 0; }}
  </style>
</head>
<body>
  {layout_wrap_open}
  {bar_html}
  {main_open}
  <div id="{map_id}"></div>
  {panel_html}
  {main_close}
  {layout_wrap_close}
  <script>
    const DATA = {geojson_str};
    const map = L.map("{map_id}").setView([{center_lat}, {center_lon}], 11);
    L.tileLayer("https://tile.openstreetmap.org/{{z}}/{{x}}/{{y}}.png", {{
      maxZoom: 19, attribution: "&copy; OpenStreetMap"
    }}).addTo(map);
    {filter_init}

    function cumple(p) {{
      if (p.pureza < minPureza) return false;
      if (soloProtegidas && !p.tiene_protegida) return false;
      return true;
    }}

    function style(f) {{
      const p = f.properties;
      if (!cumple(p)) {{
        return {{
          fillColor: "#d0d0d0",
          fillOpacity: 0.08,
          color: "#bbbbbb",
          weight: 0.25,
        }};
      }}
      return {{
        fillColor: `rgb(${{p.fill_r}},${{p.fill_g}},${{p.fill_b}})`,
        fillOpacity: 0.78,
        color: "#1a1a1a",
        weight: 1.2,
      }};
    }}

    function popup(f) {{
      const p = f.properties;
      const ok = cumple(p) ? "✓ cumple umbral" : "✗ bajo umbral";
      return `<b>Segmento ${{p.segment_id}}</b> · <span>${{ok}}</span><br/>` +
        `${{p.clase_moda_nombre}} (${{p.clase_moda}}) · <b>${{p.pureza.toFixed(1)}}%</b><br/>` +
        `2ª: ${{p.clase_2 || "—"}} (${{p.pureza_2.toFixed(1)}}%) · n=${{p.n_clases}}<br/>` +
        `Dist: ${{p.distribucion_top3}} · area_px=${{p.area_px}}` +
        (p.tiene_protegida ? '<br/><span style="color:#c00">Tier protegido</span>' : "");
    }}

    const geoLayer = L.geoJSON(DATA, {{
      style,
      onEachFeature: (f, layer) => layer.bindPopup(popup(f)),
    }}).addTo(map);
    map.fitBounds([[{bounds[1]}, {bounds[0]}], [{bounds[3]}, {bounds[2]}]]);
    {filter_handlers}
  </script>
</body>
</html>
"""


def export_html(
    gdf: gpd.GeoDataFrame,
    out_path: Path,
    titulo: str,
    pureza_inicial: int = 30,
) -> None:
    """HTML standalone con Leaflet + slider de pureza mínima."""
    html = render_leaflet_html(
        agregar_colores(gdf),
        interactive=True,
        pureza_inicial=pureza_inicial,
        titulo=titulo,
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")


def run_streamlit(gpkg_path: Path) -> None:
    import streamlit as st
    import streamlit.components.v1 as components

    st.set_page_config(page_title="Segmentos etiquetados C2", layout="wide")
    st.title("Segmentos etiquetados — MapBiomas C2")

    @st.cache_data
    def _load(p: str) -> gpd.GeoDataFrame:
        return agregar_colores(cargar_gpkg(Path(p)))

    gdf = _load(str(gpkg_path.resolve()))
    grid_id = str(gdf["grid_id"].iloc[0]) if "grid_id" in gdf.columns else gpkg_path.stem
    html_dir = REPO / "out"
    html_dir.mkdir(parents=True, exist_ok=True)
    html_path = html_dir / f"visualizador_{grid_id}.html"
    map_url = f"http://localhost:8765/{html_path.name}"

    @st.cache_data(show_spinner="Generando mapa HTML…")
    def _ensure_map_html(p: str, grid: str) -> str:
        out = html_dir / f"visualizador_{grid}.html"
        export_html(_load(p), out, titulo=grid)
        return f"http://localhost:8765/{out.name}"

    st.caption(f"`{gpkg_path}` · {len(gdf):,} segmentos · {grid_id}")

    with st.sidebar:
        st.header("Filtros")
        pureza_min = st.slider(
            "Pureza mínima (%)",
            min_value=0,
            max_value=100,
            value=30,
            step=1,
            help="Resalta segmentos con pureza ≥ umbral (clase moda). Los demás se atenúan.",
        )
        solo_protegidas = st.checkbox("Solo tier protegido", value=False)
        st.divider()
        st.markdown("**Leyenda**")
        st.markdown("Color = `clase_moda`")
        st.caption("Segmentos con pureza ≥ umbral: color pleno. Resto: gris tenue.")
        st.link_button("Abrir mapa en pestaña nueva", map_url)
        tbl_clases = resumen_por_clase(gdf, pureza_min, solo_protegidas)
        st.divider()
        st.markdown("**Por clase (≥ umbral)**")
        if tbl_clases.empty:
            st.caption("Ningún segmento cumple el filtro.")
        else:
            show = tbl_clases[
                ["clase_moda", "clase_moda_nombre", "n_segmentos", "area_ha"]
            ].copy()
            show.columns = ["ID", "Clase", "N seg", "Sup. (ha)"]
            show["Sup. (ha)"] = show["Sup. (ha)"].map(lambda x: f"{x:,.1f}")
            st.dataframe(show, hide_index=True, use_container_width=True)

    vis = filtrar_pureza(gdf, pureza_min, solo_protegidas)
    n_vis = len(vis)
    pct = 100.0 * n_vis / len(gdf) if len(gdf) else 0.0
    area_vis = vis["area_px"].sum() if n_vis else 0
    area_all = gdf["area_px"].sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Segmentos marcados", f"{n_vis:,}", f"{pct:.1f} % del total")
    c2.metric("Pureza media (visibles)", f"{vis['pureza'].mean():.1f} %" if n_vis else "—")
    c3.metric("Área px visible", f"{area_vis:,}", f"{100*area_vis/max(area_all,1):.1f} %")
    c4.metric("Con protegida (visibles)", int(vis["tiene_protegida"].sum()) if n_vis else 0)

    if n_vis == 0:
        st.warning("Ningún segmento cumple el umbral de pureza. Baja el slider.")
    else:
        st.caption(f"Marcados **{n_vis:,}** segmentos con pureza ≥ **{pureza_min}%**.")
        map_url = _ensure_map_html(str(gpkg_path.resolve()), grid_id)
        components.iframe(map_url, height=620, scrolling=True)

    with st.expander("Histograma de pureza (todos los segmentos)"):
        import plotly.express as px

        fig = px.histogram(
            gdf, x="pureza", nbins=50, title="Distribución de pureza",
            labels={"pureza": "Pureza (%)"},
        )
        fig.add_vline(x=pureza_min, line_dash="dash", line_color="red", annotation_text="umbral")
        st.plotly_chart(fig, use_container_width=True)

    with st.expander("Tabla segmentos visibles (primeros 500)"):
        cols = [
            "segment_id", "clase_moda_nombre", "pureza", "clase_2_nombre", "pureza_2",
            "distribucion_top3", "n_clases", "area_px", "tiene_protegida",
        ]
        cols = [c for c in cols if c in vis.columns]
        st.dataframe(vis[cols].head(500), use_container_width=True)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Visualizador segmentos etiquetados C2")
    p.add_argument("--gpkg", type=Path, default=DEFAULT_GPKG, help="GeoPackage etiquetado")
    p.add_argument("--labeling-root", type=Path, default=DEFAULT_LABELING_ROOT)
    p.add_argument("--export-html", type=Path, default=None, help="Exportar HTML estático")
    p.add_argument("--pureza-inicial", type=int, default=30, help="Pureza inicial en HTML export")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    gpkg = args.gpkg.resolve()
    if not gpkg.is_file():
        candidatos = listar_gpkg_disponibles(args.labeling_root)
        msg = f"No existe {gpkg}"
        if candidatos:
            msg += f"\nDisponibles:\n" + "\n".join(f"  {c}" for c in candidatos[:5])
        print(msg, file=sys.stderr)
        return 1

    gdf = agregar_colores(cargar_gpkg(gpkg))

    if args.export_html:
        export_html(
            gdf,
            args.export_html.resolve(),
            titulo=gpkg.stem,
            pureza_inicial=args.pureza_inicial,
        )
        print(f"HTML → {args.export_html}")
        return 0

    print("Indique --export-html o use Streamlit:", file=sys.stderr)
    print("  streamlit run visualizar_segmentos_etiquetados.py -- --gpkg RUTA.gpkg", file=sys.stderr)
    return 1


def _gpkg_desde_argv() -> Path:
    if "--gpkg" in sys.argv:
        i = sys.argv.index("--gpkg")
        if i + 1 < len(sys.argv):
            return Path(sys.argv[i + 1])
    return DEFAULT_GPKG


if __name__ == "__main__":
    if "--export-html" in sys.argv:
        raise SystemExit(main())
    run_streamlit(_gpkg_desde_argv().resolve())
