#!/usr/bin/env python3
"""Build run_summary_rev{year}.json from per-rectangle summary.json files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))

from config.paths import output_dir  # noqa: E402
from rectangles import build_plan, save_plan  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Consolidate segmentation run summary")
    p.add_argument("--rev-year", type=int, default=2015)
    p.add_argument("--year", type=int, default=None)
    p.add_argument("--output-dir", type=Path, default=None)
    p.add_argument("--mosaic-root", type=Path, default=None)
    p.add_argument("--errors-file", type=Path, default=None, help="Optional JSONL of errors")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    year = args.year if args.year is not None else args.rev_year
    out = args.output_dir or output_dir(args.rev_year)
    from config.paths import mosaic_root as mosaic_root_fn

    mroot = args.mosaic_root or mosaic_root_fn(year)

    plan = build_plan(rev_year=args.rev_year, year=year, mosaic_root_dir=mroot, output_root=out)
    save_plan(plan, out / f"plan_rev{args.rev_year}.json")

    results = []
    errors = []
    for rect in plan.rects:
        if not rect.mosaic_ok:
            continue
        summ_path = out / rect.tile / rect.grid_id / f"{rect.grid_id}_summary.json"
        if summ_path.is_file():
            results.append(json.loads(summ_path.read_text(encoding="utf-8")))
        elif rect.already_processed:
            pass
        else:
            errors.append({"grid_id": rect.grid_id, "error": "missing summary.json"})

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
    print(f"Consolidated {len(results)} OK · {len(errors)} errors → {run_path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
