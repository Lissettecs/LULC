#!/usr/bin/env python3
"""Deprecated alias — use plan_segmentation.py."""
import sys
from plan_segmentation import main

if __name__ == "__main__":
    sys.argv = [sys.argv[0].replace("planificar_segmentacion", "plan_segmentation")] + sys.argv[1:]
    raise SystemExit(main())
