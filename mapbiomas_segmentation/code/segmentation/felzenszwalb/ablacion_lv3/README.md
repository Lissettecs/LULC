# FELZ-07 — Ablación Lv3

Ablación dirigida sobre las bandas Lv3 del REPORT:

- **Fase A:** solo medianas puras
- **Fase B:** medianas + una feature dura a la vez

Complementa FELZ-06 (stack completo de 34 bandas).

| | Ruta |
|---|---|
| Script | `seg_felzenszwalb_ablacion_lv3.py` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_ablacion_lv3/` |
| Visualizador | `../lv3_results_viewer.py` |

```bash
python seg_felzenszwalb_ablacion_lv3.py --dry-run
python seg_felzenszwalb_ablacion_lv3.py --tile 18HYD --year 2010 --resume
```

Ver [EXPERIMENT.md](../EXPERIMENT.md).
