"""Desambiguar presupuesto no asignado (E) y estado de déficit (F)."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger("reauditoria")


def _cargar_pools(sel_dir: Path) -> pd.DataFrame:
    filas: list[pd.DataFrame] = []
    for p in sorted((sel_dir / "por_ecorregion").glob("**/pools_E*.csv")):
        df = pd.read_csv(p)
        # Extraer eco_id del nombre E02
        try:
            eco = int(p.stem.split("_E")[-1])
        except ValueError:
            eco = None
        df["ecorregion_id"] = eco
        filas.append(df)
    if not filas:
        return pd.DataFrame()
    return pd.concat(filas, ignore_index=True)


def desambiguar_presupuesto(sel_dir: Path) -> tuple[pd.DataFrame, dict]:
    """
    Cruza presupuesto_no_asignado.csv con pools_E**.csv → motivos concretos.

    Motivos:
      tope_relleno | sin_candidatos | bloqueo_solape | cuota_por_clase
    """
    path = sel_dir / "presupuesto_no_asignado.csv"
    if not path.is_file():
        return pd.DataFrame(), {"estado_archivo": "ausente", "n_ecos": 0, "total_rects": 0}

    base = pd.read_csv(path)
    if base.empty:
        return base.assign(motivo_desambiguado=[]), {
            "estado_archivo": "existente_vacio",
            "n_ecos": 0,
            "total_rects": 0,
        }

    pools = _cargar_pools(sel_dir)
    out_rows: list[dict] = []

    for _, row in base.iterrows():
        eco = int(row["ecorregion_id"])
        deficit = int(row.get("deficit_rects", 0) or 0)
        motivo_orig = str(row.get("motivo", ""))
        sub = pools[pools["ecorregion_id"] == eco] if not pools.empty else pd.DataFrame()

        motivo = _clasificar_motivo(sub, motivo_orig)
        detalle = _detalle_pools(sub)

        out_rows.append(
            {
                "ecorregion_id": eco,
                "deficit_rects": deficit,
                "motivo_original": motivo_orig,
                "motivo_desambiguado": motivo,
                "detalle_pools": detalle,
            }
        )

    out = pd.DataFrame(out_rows)
    meta = {
        "estado_archivo": "existente_con_filas",
        "n_ecos": int(out["ecorregion_id"].nunique()),
        "total_rects": int(out["deficit_rects"].sum()),
        "por_motivo": out.groupby("motivo_desambiguado")["deficit_rects"].sum().to_dict(),
    }
    return out, meta


def _clasificar_motivo(pools_eco: pd.DataFrame, motivo_orig: str) -> str:
    if "tope_relleno" in motivo_orig:
        return "tope_relleno"
    if pools_eco.empty:
        return "sin_candidatos"

    cierres = pools_eco.get("motivo_cierre", pd.Series(dtype=str)).astype(str)
    n_sel = pd.to_numeric(pools_eco.get("n_seleccionados", 0), errors="coerce").fillna(0)
    n_disp = pd.to_numeric(pools_eco.get("n_disponibles", 0), errors="coerce").fillna(0)
    n_tipo = pd.to_numeric(pools_eco.get("n_cumple_tipologia", 0), errors="coerce").fillna(0)

    # Pools de censo/presencia con candidatos tipológicos pero cuota agotada
    es_rara = pools_eco["pool"].astype(str).str.startswith(("censo_", "presencia_"))
    cuota_clase = (
        es_rara
        & cierres.isin(["presupuesto_agotado", "cobertura_alcanzada", "cuota_cumplida"])
        & (n_tipo > n_sel)
    )
    if cuota_clase.any() and "tope" in motivo_orig:
        # Había cupo de ecorregión sin usar y pools de clase cerraron por cuota
        return "cuota_por_clase"
    if cuota_clase.any() and (n_tipo > 0).any():
        return "cuota_por_clase"

    # Candidatos tipológicos > 0 pero seleccionados 0 y cierre por disponibles/solape
    bloqueo = (
        (n_tipo > 0)
        & (n_sel == 0)
        & cierres.isin(["sin_disponibles", "pool_agotado"])
    )
    if bloqueo.any() or (
        (n_disp > 0).any()
        and (n_sel.sum() < n_disp.sum())
        and cierres.isin(["sin_disponibles"]).any()
    ):
        # Si había tipología pero n_disponibles bajó a 0 por tracker
        if ((n_tipo > 0) & (n_disp == 0) & (n_sel == 0)).any():
            return "bloqueo_solape"

    if (n_tipo == 0).all() or cierres.isin(["pool_vacio"]).all():
        return "sin_candidatos"

    if "tope" in motivo_orig or "parcial" in motivo_orig:
        # Default: el tope de relleno cortó el déficit residual
        if (n_tipo > n_sel).any() and es_rara.any():
            return "cuota_por_clase"
        return "tope_relleno"

    return "tope_relleno"


def _detalle_pools(pools_eco: pd.DataFrame) -> str:
    if pools_eco.empty:
        return ""
    parts = []
    for _, r in pools_eco.iterrows():
        if not str(r.get("pool", "")).startswith(("censo_", "presencia_")):
            continue
        parts.append(
            f"{r['pool']}:{r.get('motivo_cierre','')}("
            f"sel={int(r.get('n_seleccionados',0) or 0)}/"
            f"tipo={int(r.get('n_cumple_tipologia',0) or 0)})"
        )
    return "; ".join(parts[:12])


def estado_deficit(sel_dir: Path) -> dict:
    """F: distinguir archivo vacío vs ausente."""
    path = sel_dir / "deficit_celdas.csv"
    if not path.is_file():
        return {
            "estado": "ausente",
            "mensaje": "El archivo deficit_celdas.csv no existe — el cálculo de déficit no se ejecutó o no se escribió.",
            "n_filas": None,
        }
    df = pd.read_csv(path)
    if df.empty:
        return {
            "estado": "existente_vacio",
            "mensaje": "deficit_celdas.csv existe y no tiene filas — no hubo déficit registrado.",
            "n_filas": 0,
        }
    return {
        "estado": "existente_con_filas",
        "mensaje": f"deficit_celdas.csv tiene {len(df)} filas de déficit.",
        "n_filas": int(len(df)),
    }
