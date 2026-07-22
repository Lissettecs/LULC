# Pipeline B (Ruta B — activo)

Flujo unificado: **SLIC → RAG hierarchical → absorber_pequenos (min150)**.

## Código en este directorio

| Archivo | Rol |
|---------|-----|
| `seg_slic_pipeline_b.py` | Script principal (etapas 1–3 o solo etapa 3 con `--from-rag-dir`) |
| `seg_slic_grid.py` | Alias de compatibilidad → `seg_slic_pipeline_b.py` |
| `consolidar_pipeline_b_csv.py` | Une CSV parciales del array SLURM |
| `run_seg_slic_pipeline_b_from_rag.slurm` | SLURM recomendado (lee `pipeline_a/rag_hierarchical/`) |
| `run_seg_slic_pipeline_b.slurm` | SLURM flujo completo (lento, ≥128 GB RAM) |

## Salidas (cluster, no versionar)

```text
/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_b/
├── seg_*_hier_p*_min150.{tif,png}
├── resumen_pipeline_b_{tile}_{year}.csv
└── capas/
```

## Uso rápido

```bash
cd labeling/image_segmentation/seg_slic/pipeline_b

# Recomendado: solo etapa 3
python seg_slic_grid.py --tile 18HYD --year 2010 \
  --from-rag-dir /home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/rag_hierarchical \
  --combo-index 0 --resume

# SLURM (4 combos, uno a la vez)
sbatch --array=0-3%1 run_seg_slic_pipeline_b_from_rag.slurm
python consolidar_pipeline_b_csv.py --tile 18HYD --year 2010
```

Visualizador: panel **Pipeline B** en `segmenters_viewer.html`.
