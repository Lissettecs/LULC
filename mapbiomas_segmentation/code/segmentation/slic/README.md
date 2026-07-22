# SLIC — Pipeline A y Pipeline B

Segmentación SLIC para calibración visual MapBiomas.

## Estructura del repositorio

```text
seg_slic/
├── README.md
├── common.py                      ← utilidades compartidas (SLIC, RAG, absorber)
├── pipeline_a/                    ← Pipeline A (legado, 3 etapas)
│   ├── README.md
│   ├── seg_slic_pipeline_a.py
│   ├── consolidar_size_filter_csv.py
│   ├── run_etapa1.slurm
│   ├── run_etapa2.slurm
│   ├── run_etapa3.slurm
│   ├── run_etapa3_csv.slurm
│   └── legacy/                    ← SLURM históricos
└── pipeline_b/                    ← Pipeline B (Ruta B unificada)
    ├── README.md
    ├── seg_slic_pipeline_b.py     ← código principal
    ├── seg_slic_grid.py           ← alias compatibilidad
    ├── consolidar_pipeline_b_csv.py
    ├── run_seg_slic_pipeline_b_from_rag.slurm
    └── run_seg_slic_pipeline_b.slurm
```

## ¿Dónde está el código?

| Pipeline | Código Python | Estado |
|----------|---------------|--------|
| **A** | `pipeline_a/seg_slic_pipeline_a.py` | Activo, 3 etapas con flags |
| **B** | `pipeline_b/seg_slic_pipeline_b.py` | Activo, flujo unificado |

## Datos (cluster, fuera de Git)

```text
/home/lserey/mapbiomas_land/test/image_segmentation/seg_slic/
├── pipeline_a/          ← etapas 1–3 de Pipeline A
└── pipeline_b/          ← salidas finales Pipeline B
```

## Documentación

- [pipeline_a/README.md](pipeline_a/README.md) — legado, 3 etapas descompuestas
- [pipeline_b/README.md](pipeline_b/README.md) — Ruta B, uso y SLURM

## Visualizador

```bash
cd /home/lserey/mapbiomas_land/test/image_segmentation
python3 -m http.server 8765 --bind 0.0.0.0
# → segmenters_viewer.html
```

| Panel | Pipeline | Datos |
|-------|----------|-------|
| SLIC | A etapa 1 | `pipeline_a/` |
| SLIC + RAG hier | A etapa 2 | `pipeline_a/rag_hierarchical/` |
| SLIC + min150 | A etapa 3 | `pipeline_a/size_filter/` |
| Pipeline B | B | `pipeline_b/` |
