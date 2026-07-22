# Pipeline A (legado, descompuesto)

Pipeline A fue el flujo **incremental** usado en julio 2026: cada etapa escribía en un directorio distinto sin sobrescribir resultados previos.

## Etapas y salidas (tile 18HYD 2010 — completas en cluster)

| Etapa | Descripción | Directorio de datos | Panel en visualizador |
|-------|-------------|---------------------|------------------------|
| 1 | SLIC + RAG threshold/percentile | `pipeline_a/` | **SLIC** |
| 2 | SLIC + RAG hierarchical (p10/p20) | `pipeline_a/rag_hierarchical/` | **SLIC + RAG hier** |
| 3 | Filtro tamaño min150 sobre RAG threshold | `pipeline_a/size_filter/` | **SLIC + min150** |

Raíz de datos:

```text
/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/
├── seg_{tile}_{year}_s{scale}_sig{sigma}.tif          # superpíxeles
├── seg_{tile}_{year}_s{scale}_sig{sigma}_ragp{p}.tif  # post-RAG percentile
├── rag_hierarchical/seg_*_hier_p{p}.tif               # post-RAG hierarchical
└── size_filter/seg_*_ragp{p}_min150.tif               # post-filtro tamaño
```

## Grid Pipeline A

| Sub-pipeline | scales | sigmas | RAG | Combos |
|--------------|--------|--------|-----|--------|
| Base SLIC + RAG | 25, 50, 100, 150, 200 | 0.1, 0.5, 0.8 | threshold + p10/20/30 | 60 TIFs base |
| RAG hierarchical | 100, 150 | 0.1 | p10, p20 | 4 TIFs |
| Size filter | 25–200 | 0.1, 0.5, 0.8 | p10, p20, p30 | 44 TIFs |

## Scripts SLURM archivados

Los scripts en `slurm/` corresponden al código **anterior** a la consolidación en Pipeline B (`pipeline_b/seg_slic_grid.py` ya no expone `--solo-rag-hierarchical` ni `--solo-size-filter`).

Se conservan como referencia histórica. **No ejecutar** sin restaurar el código legado.

| Script | Propósito original |
|--------|-------------------|
| `run_seg_slic_grid.slurm` | Etapa 1: SLIC + RAG |
| `run_seg_slic_rag_hierarchical.slurm` | Etapa 2: RAG hierarchical |
| `run_seg_slic_size_filter.slurm` | Etapa 3: filtro tamaño (array 0–44) |
| `run_seg_slic_size_filter_csv.slurm` | Consolidar CSV size_filter |

## Regenerar Pipeline A

Los artefactos en disco están completos y visibles en `segmenters_viewer.html`. Para **reproducir** desde cero habría que restaurar el script multi-modo previo a julio 2026 o reimplementar etapas separadas.

Pipeline B reutiliza la etapa 2 de Pipeline A (`pipeline_a/rag_hierarchical/`) para la etapa 3 unificada.
