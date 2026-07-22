# FELZ-06 — Felzenszwalb Lv3 (REPORT)

Felzenszwalb sobre las **34 bandas Lv3** parseadas desde `random_forest/REPORT/reports/lv3_multitile.md`.

Resuelve bandas por **nombre** en el GeoTIFF 184B (no por índice del catálogo RF).

| | Ruta |
|---|---|
| Scripts | `seg_felzenszwalb_rf_lv3.py`, `parse_lv3_report.py` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_lv3/` |
| Visualizador | `../lv3_results_viewer.py` |

```bash
python seg_felzenszwalb_rf_lv3.py --dry-run
python seg_felzenszwalb_rf_lv3.py --tile 18HYD --year 2010 --resume
```

Ver [EXPERIMENT.md](../EXPERIMENT.md).
