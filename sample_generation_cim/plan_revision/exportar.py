"""Escritura de salidas del plan de revisión."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import geopandas as gpd
import pandas as pd

from config import params_plan_revision as P
from plan_revision.derivar import enriquecer_dataframe
from plan_revision.reporte import expandir_pares, generar_reporte_md
from plan_revision.validar import validar_plan
from utilidades import git_hash, versiones_paquetes


def _resolver_sel_dir(tag_o_path: str | Path) -> Path:
    p = Path(tag_o_path)
    if p.is_dir():
        return p.resolve()
    cand = P.SEL_ROOT / str(tag_o_path)
    if cand.is_dir():
        return cand.resolve()
    raise FileNotFoundError(f"No se encontró corrida de selección: {tag_o_path}")


def _cargar_seleccion(sel_dir: Path) -> tuple[gpd.GeoDataFrame, pd.DataFrame]:
    path = sel_dir / "seleccion_nacional.gpkg"
    if not path.is_file():
        raise FileNotFoundError(f"Falta {path}")
    gdf = gpd.read_file(path)

    csv_path = sel_dir / "seleccion_nacional.csv"
    if csv_path.is_file():
        tabular = pd.read_csv(csv_path)
    else:
        tabular = gdf.drop(columns="geometry", errors="ignore")
    return gdf, tabular


def _out_dir(sel_dir: Path, timestamp: str | None = None) -> Path:
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M")
    return sel_dir / f"plan_revision_{ts}"


def ejecutar_plan_revision(
    seleccion: str | Path,
    *,
    timestamp: str | None = None,
    out_dir: Path | None = None,
) -> Path:
    """Deriva rev_years y escribe salidas sin modificar la selección original."""
    sel_dir = _resolver_sel_dir(seleccion)
    dest = out_dir or _out_dir(sel_dir, timestamp)
    dest.mkdir(parents=True, exist_ok=True)

    gdf, tabular = _cargar_seleccion(sel_dir)
    enriquecido = enriquecer_dataframe(tabular)
    validacion = validar_plan(enriquecido)
    expandido = expandir_pares(enriquecido)

    csv_out = dest / "seleccion_con_rev_years.csv"
    enriquecido.to_csv(csv_out, index=False)

    rev_cols = [c for c in enriquecido.columns if c.startswith("rev_")]
    merge = gdf.merge(
        enriquecido[["grid_id"] + rev_cols],
        on="grid_id",
        how="left",
        suffixes=("", "_dup"),
    )
    merge = merge[[c for c in merge.columns if not c.endswith("_dup")]]
    if merge.crs is None or merge.crs.to_epsg() != 4326:
        merge = merge.to_crs(4326)
    merge.to_file(dest / "seleccion_con_rev_years.gpkg", driver="GPKG")

    expandido.to_csv(dest / "plan_revision_expandido.csv", index=False)

    reporte = generar_reporte_md(
        enriquecido,
        expandido,
        validacion,
        sel_dir,
        dest,
    )
    (dest / "reporte_plan_revision.md").write_text(reporte, encoding="utf-8")

    summary = {
        "seleccion_base": str(sel_dir),
        "salida": str(dest),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "n_rectangulos": len(enriquecido),
        "n_pares_revision": len(expandido),
        "n_con_ref_year_previo": int(
            (pd.to_numeric(enriquecido.get("ref_year", P.SENTINEL), errors="coerce") > 0).sum()
        ),
        "dist_rev_n_years": enriquecido["rev_n_years"].value_counts().sort_index().astype(int).to_dict(),
        "dist_rev_role": expandido["rev_role"].value_counts().sort_index().astype(int).to_dict(),
        "dist_periodo": expandido["ref_period"].value_counts().reindex(
            P.ORDEN_PERIODOS, fill_value=0
        ).astype(int).to_dict(),
        "n_fallback_transicion": int((enriquecido["rev_metodo"] == "transicion_fallback_sin_cambio_periodo").sum()),
        "n_fallback_censo_refuerzo": int((enriquecido["rev_metodo"] == "censo_refuerzo_fallback").sum()),
        "validacion_ok": validacion.ok,
        "validacion_errores": validacion.errores,
        "versiones": versiones_paquetes(),
        "git_hash": git_hash(),
    }
    (dest / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"Plan de revisión escrito en {dest}")
    print(f"  Rectángulos: {len(enriquecido)}")
    print(f"  Pares (rect, año): {len(expandido)}")
    print(f"  Validación: {'OK' if validacion.ok else 'FALLA'}")
    if not validacion.ok:
        for err in validacion.errores[:10]:
            print(f"    - {err}")
    return dest
