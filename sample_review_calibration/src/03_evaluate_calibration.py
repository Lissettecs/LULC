#!/usr/bin/env python3
"""Fase 3 — Scoring de calibración (correr DESPUÉS de la revisión humana).

Construye la clave: reference_class = supervisor_class.
Puntúa cada revisor contra esa clave. NO valida C2 (salvo subproducto QA).
"""

from __future__ import annotations

# ═══════════════════════════════════════════════════════════════
# PARÁMETROS
# ═══════════════════════════════════════════════════════════════
DIR_RESULTADOS = "/home/lserey/mapbiomas_land/prod/sample_review_calibration"

# AJUSTAR a las rutas de la corrida de Fase 2 (archivos ya llenados)
SUPERVISOR_FILE = (
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "EDITAR_CON_RUN_FASE2/sample/supervisor_review.gpkg"
)
REVIEWER_FILES = [
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "EDITAR_CON_RUN_FASE2/sample/per_reviewer/review_rev_A.gpkg",
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "EDITAR_CON_RUN_FASE2/sample/per_reviewer/review_rev_B.gpkg",
    "/home/lserey/mapbiomas_land/prod/sample_review_calibration/"
    "EDITAR_CON_RUN_FASE2/sample/per_reviewer/review_rev_C.gpkg",
]
# ═══════════════════════════════════════════════════════════════

import importlib.util
from itertools import combinations
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

_SRC = Path(__file__).resolve().parent
_SPEC = importlib.util.spec_from_file_location(
    "analyze_proportion", _SRC / "01_analyze_proportion.py"
)
_AP = importlib.util.module_from_spec(_SPEC)
assert _SPEC.loader is not None
_SPEC.loader.exec_module(_AP)

crear_dir_run = _AP.crear_dir_run


def _leer_atributos(path: str | Path) -> pd.DataFrame:
    gdf = gpd.read_file(path)
    return pd.DataFrame(gdf.drop(columns=[gdf.geometry.name], errors="ignore"))


def _clave_union(df: pd.DataFrame) -> str:
    if "review_id" in df.columns:
        return "review_id"
    if "segment_uid" in df.columns:
        return "segment_uid"
    raise ValueError("Se requiere review_id o segment_uid para unir.")


def cohen_kappa(y1: np.ndarray, y2: np.ndarray) -> float:
    """Cohen's kappa entre dos etiquetados categóricos."""
    y1 = np.asarray(y1)
    y2 = np.asarray(y2)
    mask = (~pd.isna(y1)) & (~pd.isna(y2))
    y1, y2 = y1[mask], y2[mask]
    if len(y1) == 0:
        return float("nan")
    classes = np.unique(np.concatenate([y1, y2]))
    n = len(y1)
    # Matriz de confusión
    idx = {c: i for i, c in enumerate(classes)}
    cm = np.zeros((len(classes), len(classes)), dtype=float)
    for a, b in zip(y1, y2):
        cm[idx[a], idx[b]] += 1
    po = np.trace(cm) / n
    pe = np.sum(cm.sum(axis=0) * cm.sum(axis=1)) / (n * n)
    if pe >= 1.0 - 1e-15:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def accuracy_overall(ref: pd.Series, pred: pd.Series) -> dict:
    mask = ref.notna() & pred.notna()
    r, p = ref[mask], pred[mask]
    n = int(mask.sum())
    correct = int((r.astype(int) == p.astype(int)).sum()) if n else 0
    return {
        "n_scored": n,
        "n_correct": correct,
        "accuracy": (correct / n) if n else float("nan"),
    }


def accuracy_per_class(ref: pd.Series, pred: pd.Series) -> pd.DataFrame:
    mask = ref.notna() & pred.notna()
    r = ref[mask].astype(int)
    p = pred[mask].astype(int)
    rows = []
    for code in sorted(r.unique()):
        m = r == code
        n = int(m.sum())
        correct = int((p[m] == code).sum())
        rows.append(
            {
                "reference_class": int(code),
                "n": n,
                "n_correct": correct,
                "accuracy": (correct / n) if n else float("nan"),
            }
        )
    return pd.DataFrame(rows)


def confusion_matrix(ref: pd.Series, pred: pd.Series, reviewer: str) -> pd.DataFrame:
    mask = ref.notna() & pred.notna()
    r = ref[mask].astype(int)
    p = pred[mask].astype(int)
    ct = pd.crosstab(r, p, dropna=False)
    ct.index.name = "reference_class"
    ct.columns.name = "reviewer_class"
    long = ct.stack().reset_index(name="count")
    long.insert(0, "reviewer", reviewer)
    return long


def main() -> None:
    print("═" * 60)
    print("FASE 3 — Evaluación de calibración")
    print("═" * 60)
    print("Parámetros:")
    print(f"  SUPERVISOR_FILE = {SUPERVISOR_FILE}")
    print(f"  REVIEWER_FILES  = {REVIEWER_FILES}")

    sup_path = Path(SUPERVISOR_FILE)
    if not sup_path.is_file():
        print(f"ERROR: no existe SUPERVISOR_FILE: {sup_path}")
        raise SystemExit(1)

    for rf in REVIEWER_FILES:
        if not Path(rf).is_file():
            print(f"ERROR: no existe archivo de revisor: {rf}")
            raise SystemExit(1)

    sup = _leer_atributos(sup_path)
    if "supervisor_class" not in sup.columns:
        print("ERROR: supervisor_review debe tener columna supervisor_class")
        raise SystemExit(1)

    key_col = _clave_union(sup)
    ref = sup[[key_col, "supervisor_class"]].copy()
    if "proposed_class" in sup.columns:
        ref["proposed_class"] = pd.to_numeric(sup["proposed_class"], errors="coerce")
    ref["supervisor_class"] = pd.to_numeric(ref["supervisor_class"], errors="coerce")

    n_empty = int(ref["supervisor_class"].isna().sum())
    ref_ok = ref.dropna(subset=["supervisor_class"]).copy()
    ref_ok["reference_class"] = ref_ok["supervisor_class"].astype(int)
    print(
        f"Clave: {len(ref_ok)} segmentos con supervisor_class; "
        f"{n_empty} excluidos (vacíos)"
    )

    run_dir = crear_dir_run(DIR_RESULTADOS)
    out_dir = run_dir / "results"
    out_dir.mkdir(parents=True, exist_ok=True)

    overall_rows = []
    per_class_frames = []
    conf_frames = []
    reviewer_labels: dict[str, pd.Series] = {}

    for rf in REVIEWER_FILES:
        rdf = _leer_atributos(rf)
        rev_name = (
            str(rdf["reviewer_id"].iloc[0])
            if "reviewer_id" in rdf.columns and rdf["reviewer_id"].notna().any()
            else Path(rf).stem
        )
        if "reviewer_class" not in rdf.columns:
            print(f"ERROR: falta reviewer_class en {rf}")
            raise SystemExit(1)

        k = _clave_union(rdf)
        sub = rdf[[k, "reviewer_class"]].copy()
        sub["reviewer_class"] = pd.to_numeric(sub["reviewer_class"], errors="coerce")
        merged = ref_ok.merge(sub, left_on=key_col, right_on=k, how="left")
        if k != key_col and k in merged.columns:
            # ya unido
            pass

        ov = accuracy_overall(merged["reference_class"], merged["reviewer_class"])
        ov["reviewer"] = rev_name
        ov["n_excluded_empty_supervisor"] = n_empty
        overall_rows.append(ov)
        print(
            f"  {rev_name}: accuracy={ov['accuracy']:.4f} "
            f"({ov['n_correct']}/{ov['n_scored']})"
        )

        pc = accuracy_per_class(merged["reference_class"], merged["reviewer_class"])
        pc.insert(0, "reviewer", rev_name)
        per_class_frames.append(pc)

        cm = confusion_matrix(merged["reference_class"], merged["reviewer_class"], rev_name)
        conf_frames.append(cm)

        # Para kappa inter-revisor: indexar por clave
        serie = merged.set_index(key_col)["reviewer_class"]
        reviewer_labels[rev_name] = serie

    overall_df = pd.DataFrame(overall_rows)
    overall_df.to_csv(out_dir / "accuracy_overall.csv", index=False)
    pd.concat(per_class_frames, ignore_index=True).to_csv(
        out_dir / "accuracy_per_class.csv", index=False
    )
    pd.concat(conf_frames, ignore_index=True).to_csv(
        out_dir / "confusion_matrix.csv", index=False
    )

    if len(REVIEWER_FILES) > 1:
        agr_rows = []
        names = list(reviewer_labels.keys())
        # Alinear índices
        common_idx = None
        for s in reviewer_labels.values():
            common_idx = s.index if common_idx is None else common_idx.intersection(s.index)
        for a, b in combinations(names, 2):
            s1 = reviewer_labels[a].loc[common_idx]
            s2 = reviewer_labels[b].loc[common_idx]
            mask = s1.notna() & s2.notna()
            agree = (
                float((s1[mask].astype(int) == s2[mask].astype(int)).mean())
                if mask.any()
                else float("nan")
            )
            kappa = cohen_kappa(s1[mask].to_numpy(), s2[mask].to_numpy())
            agr_rows.append(
                {
                    "reviewer_a": a,
                    "reviewer_b": b,
                    "n_paired": int(mask.sum()),
                    "pct_agreement": agree,
                    "cohen_kappa": kappa,
                }
            )
        agr_df = pd.DataFrame(agr_rows)
        agr_df.to_csv(out_dir / "agreement.csv", index=False)
        print("\nAcuerdo inter-revisor:")
        print(agr_df.to_string(index=False))

    # QA C2 vs supervisora (solo modo confirmar)
    if "proposed_class" in ref_ok.columns:
        prop = ref_ok.dropna(subset=["proposed_class"]).copy()
        prop["proposed_class"] = prop["proposed_class"].astype(int)
        prop["corrected"] = prop["proposed_class"] != prop["reference_class"]
        qa = (
            prop.groupby("proposed_class")
            .agg(
                n=("corrected", "size"),
                n_corrected=("corrected", "sum"),
            )
            .reset_index()
            .rename(columns={"proposed_class": "proposed_class"})
        )
        qa["correction_rate"] = qa["n_corrected"] / qa["n"]
        # También por reference_class (clase confirmada)
        qa_ref = (
            prop.groupby("reference_class")
            .agg(
                n=("corrected", "size"),
                n_corrected_from_c2=("corrected", "sum"),
            )
            .reset_index()
        )
        qa_ref["correction_rate"] = qa_ref["n_corrected_from_c2"] / qa_ref["n"]
        # Entregar tabla por clase propuesta (error de etiqueta C2)
        qa.to_csv(out_dir / "c2_vs_supervisor_corrections.csv", index=False)
        print("\nQA C2 vs supervisora (proposed_class ≠ supervisor_class):")
        print(qa.to_string(index=False))
        print(f"  tasa global = {prop['corrected'].mean():.4f} "
              f"({int(prop['corrected'].sum())}/{len(prop)})")

    print(f"\nSalidas en: {out_dir}")
    print(overall_df.to_string(index=False))


if __name__ == "__main__":
    main()
