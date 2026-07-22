# Pipeline A (legado)

Pipeline A es un flujo **descompuesto en 3 etapas**; cada etapa escribe en un subdirectorio de `pipeline_a/` en el cluster.

## Código activo

| Archivo | Etapa |
|---------|-------|
| `seg_slic_pipeline_a.py` | 1 (default), 2 (`--solo-rag-hierarchical`), 3 (`--solo-size-filter`) |
| `consolidar_size_filter_csv.py` | Post-proceso CSV etapa 3 |
| `run_etapa1.slurm` | SLURM etapa 1 |
| `run_etapa2.slurm` | SLURM etapa 2 (array 0–3) |
| `run_etapa3.slurm` | SLURM etapa 3 (array 0–44) |
| `run_etapa3_csv.slurm` | Consolidar CSV etapa 3 |

Utilidades compartidas con Pipeline B: `../common.py`.

## Uso local

```bash
cd labeling/image_segmentation/seg_slic/pipeline_a

# Etapa 1: SLIC + RAG threshold (p10/p20/p30)
python seg_slic_pipeline_a.py --tile 18HYD --year 2010 --resume

# Etapa 2: RAG hierarchical (reutiliza SLIC de pipeline_a/)
python seg_slic_pipeline_a.py --solo-rag-hierarchical --combo-index 0 --resume

# Etapa 3: min150 sobre RAG threshold
python seg_slic_pipeline_a.py --solo-size-filter --combo-index 0 --resume
```

## Grid

| Etapa | scales | sigmas | RAG |
|-------|--------|--------|-----|
| 1 | 25, 50, 100, 150, 200 | 0.1, 0.5, 0.8 | threshold p10/p20/p30 |
| 2 | 100, 150 | 0.1 | hierarchical p10/p20 |
| 3 | 25–200 | 0.1, 0.5, 0.8 | min150 sobre ragp* |

## Etapas y salidas (cluster)

| Etapa | Subdirectorio datos | Visualizador |
|-------|---------------------|--------------|
| 1 SLIC + RAG threshold | `pipeline_a/` (raíz) | SLIC |
| 2 RAG hierarchical | `pipeline_a/rag_hierarchical/` | SLIC + RAG hier |
| 3 min150 | `pipeline_a/size_filter/` | SLIC + min150 |

Ruta datos:

```text
/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/pipeline_a/
```

## Scripts SLURM archivados

Ver [legacy/README.md](legacy/README.md) — referencia histórica del script monolítico `seg_slic_grid.py`.
