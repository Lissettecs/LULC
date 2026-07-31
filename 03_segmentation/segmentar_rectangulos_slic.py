#!/usr/bin/env python3
"""Deprecated alias — use run_slic_segmentation.py."""
import sys

if __name__ == "__main__":
    argv = sys.argv[:]
    for i, a in enumerate(argv):
        if a == "--solo-mosaico-disponible":
            argv[i] = "--require-mosaic"
        elif a == "--prueba-tile":
            argv[i] = "--test-tile"
    sys.argv = argv
    from run_slic_segmentation import main

    raise SystemExit(main())
