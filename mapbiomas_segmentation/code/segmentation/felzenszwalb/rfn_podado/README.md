# FELZ-03 — Felzenszwalb RF_N podado

Segmentación con **subconjunto espectral podado** (~10 bandas) del stack RF_N, estandarizado por banda.

Compara geometría vs FELZ-01 (3 bandas) y FELZ-02 (39 bandas RF_N completas) al mismo `scale=200`, `sigma=0.1`.

| | Ruta |
|---|---|
| Script | `seg_felzenszwalb_rfn_podado.py` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rfn/` |
| Visualizador | `../segmenters_labeling_viewer.py` |

```bash
python seg_felzenszwalb_rfn_podado.py --tile 18HYD --year 2010 --resume
```

Ver [EXPERIMENT.md](../EXPERIMENT.md).
