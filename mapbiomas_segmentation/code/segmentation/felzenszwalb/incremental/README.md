# FELZ-05 — Incremental (constructivo)

Prueba **constructiva**: parte de 3 medianas base y agrega **un incremento** a la vez (índices o bandas), midiendo si la granularidad se mantiene.

Opuesto a FELZ-04: sumar desde lo que funciona, no restar desde lo que fragmenta.

| | Ruta |
|---|---|
| Script | `seg_felzenszwalb_incremental.py` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_incremental/` |
| Visualizador | `../incremental_results_viewer.py` |

```bash
python seg_felzenszwalb_incremental.py --tile 18HYD --year 2010
python seg_felzenszwalb_incremental.py --resume --acumular
```

Ver [EXPERIMENT.md](../EXPERIMENT.md).
