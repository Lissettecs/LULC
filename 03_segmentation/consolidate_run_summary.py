#!/usr/bin/env python3
"""Consolida run_summary_rev{year}.json a partir de los summary.json por rectángulo."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.paths import output_dir  # noqa: E402
from rectangles import construir_plan, guardar_plan  # noqa: E402


def parsear_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Consolida el resumen de una corrida de segmentación")
    p.add_argument("--rev-year", type=int, default=2015, help="Año de revisión")
    p.add_argument("--year", type=int, default=None, help="Año del mosaico (default: = rev-year)")
    p.add_argument("--output-dir", type=Path, default=None, help="Directorio de salida de segmentación")
    p.add_argument("--mosaic-root", type=Path, default=None, help="Raíz de mosaicos enmascarados")
    p.add_argument(
        "--errors-file",
        type=Path,
        default=None,
        help="JSONL opcional con errores adicionales",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parsear_args(argv)
    year = args.year if args.year is not None else args.rev_year
    out = args.output_dir or output_dir(args.rev_year)
    from config.paths import mosaic_root as mosaic_root_fn

    mroot = args.mosaic_root or mosaic_root_fn(year)

    plan = construir_plan(rev_year=args.rev_year, year=year, mosaic_root_dir=mroot, output_root=out)
    guardar_plan(plan, out / f"plan_rev{args.rev_year}.json")

    results = []
    errors = []
    for rect in plan.rects:
        if not rect.mosaic_ok:
            continue
        summ_year = out / rect.tile / rect.grid_id / f"{rect.grid_id}_{year}_summary.json"
        summ_legacy = out / rect.tile / rect.grid_id / f"{rect.grid_id}_summary.json"
        summ_path = summ_year if summ_year.is_file() else summ_legacy
        if summ_path.is_file():
            results.append(json.loads(summ_path.read_text(encoding="utf-8")))
        elif rect.already_processed:
            pass
        else:
            errors.append({"grid_id": rect.grid_id, "error": "falta summary.json"})

    if args.errors_file and args.errors_file.is_file():
        for line in args.errors_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                errors.append(json.loads(line))

    run_summary = {
        "rev_year": args.rev_year,
        "year": year,
        "n_ok": len(results),
        "n_error": len(errors),
        "mosaic_root": str(mroot),
        "output_dir": str(out),
        "plan_path": str(out / f"plan_rev{args.rev_year}.json"),
        "mode": "slurm_array",
        "results": results,
        "errors": errors,
        "finished_at": datetime.now(timezone.utc).isoformat(),
    }
    run_path = out / f"run_summary_rev{args.rev_year}.json"
    run_path.write_text(json.dumps(run_summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Consolidado: {len(results)} OK · {len(errors)} errores → {run_path}")
    return 1 if errors else 0


parse_args = parsear_args


if __name__ == "__main__":
    raise SystemExit(main())
