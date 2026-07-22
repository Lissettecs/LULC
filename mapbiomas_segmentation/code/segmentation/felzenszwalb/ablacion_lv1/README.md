# FELZ-04 — Ablación Lv1 (RF_N)

Ablación dirigida sobre el stack 184B con bandas RF Lv1:

- **Fase A:** solo medianas (base robusta)
- **Fase B:** medianas + una feature "dura" a la vez

| | Ruta |
|---|---|
| Script | `seg_felzenszwalb_ablacion.py` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_ablacion/` |
| Visualizador | `../segmenters_labeling_viewer.py` |

```bash
python seg_felzenszwalb_ablacion.py --tile 18HYD --year 2010 --resume
```

Ver [EXPERIMENT.md](../EXPERIMENT.md).
