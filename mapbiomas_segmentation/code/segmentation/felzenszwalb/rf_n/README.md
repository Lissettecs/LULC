# Pipeline Felzenszwalb RF_N

Segmentación Felzenszwalb con **bandas seleccionadas por Random Forest** (`importance_gated_clusters`).

Pipeline **independiente** de `seg_felzenszwalb/` (mosaico 3 bandas nir/swir1/red).

## Código

| Archivo | Rol |
|---------|-----|
| `seg_felzenszwalb_rf_n_grid.py` | Script principal |
| `rf_selected_bands.py` | Índices per-tile Lv1/Lv3 (desde `random_forest/REPORT/REPORT.md`) |
| `run_seg_felzenszwalb_rf_n.slurm` | Job array SLURM |

Reutiliza utilidades I/O de `../seg_felzenszwalb/seg_felzenszwalb_grid.py` (import `base`), sin modificar ese script.

## Entrada / salida

| | Ruta |
|---|---|
| Mosaico 184B | `/home/lserey/mapbiomas_land/test/mosaics/mosaics_184bands/{tile}/TMP-CHILE-*-SBAND-184B.tif` |
| Salidas | `/home/lserey/mapbiomas_land/test/image_segmentation/seg_felzenszwalb_rf_n/` |

Nombres: `seg_{tile}_{year}_lv1_rfn_s{scale}_sig{sigma}.tif`

**No sobrescribe** `seg_felzenszwalb/`.

## Uso

```bash
cd labeling/image_segmentation/seg_felzenszwalb_rf_n

python seg_felzenszwalb_rf_n_grid.py --tile 18HYD --year 2010
python seg_felzenszwalb_rf_n_grid.py --rf-level 3 --combo-index 0 --resume

sbatch --array=0-14%3 run_seg_felzenszwalb_rf_n.slurm
```

## Selección de bandas

- Fuente: [random_forest/REPORT/REPORT.md](../../../random_forest/REPORT/REPORT.md)
- `--rf-level 1` (default): selección per-tile Level 1 (ej. 18HYD → 39 bandas)
- `--rf-level 3`: selección per-tile Level 3
- `--selected-bands-json`: override con `selected_bands.json` del pipeline RF

Las bandas se resuelven **por nombre** en las descriptions del GeoTIFF (el orden del TIF ≠ índice del catálogo RF).

## Preprocesamiento

Z-score por banda seleccionada antes de Felzenszwalb (escalas heterogéneas: elevation, NDVI, slope, etc.).
