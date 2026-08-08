# Mask CIM 184-band mosaics (water + glacier)

Replica of the workflow in `mapbiomas_land/tmp/mask_mosaic_2015/`, adapted to CIM mosaics downloaded into `mosaic_184bands/2015/` (6 GeoTIFF shards per tile).

## Inputs / outputs

| | Path |
|---|---|
| Mosaics (shards) | `/home/lserey/mapbiomas_land/mosaic_184bands/2015/` |
| Water ancillary | `ancillary_data/water_col1/{year}_water_water_surface.tif` |
| Glacier ancillary | `ancillary_data/glacier_col1/{year}_annual_glacier_surface.tif` |
| Output (1 GeoTIFF/tile) | `/home/lserey/mapbiomas_land/mosaic_184bands_mask_water/2015/` |
| Per-tile metadata | `mosaic_184bands_mask_water/work/{TILE}/mask_summary.json` |

Mask rule: `(glacier == 1) OR (water == 1)` → nodata `-9999` on all bands.

## Requirements

```bash
module load miniconda3/24.7.1-zen4-j
source "$(conda info --base)/etc/profile.d/conda.sh"
conda activate mb_coverage
```

## Single tile (test)

```bash
python mask_mosaic_cim_tile.py --tile SE-19-V-D --year 2015
```

## Local batch

```bash
./run_batch_2015.sh
```

## SLURM (124 tiles, 8 in parallel)

```bash
mkdir -p logs
sbatch mask_array_2015.slurm
```

## Monitoring

```bash
find /home/lserey/mapbiomas_land/mosaic_184bands_mask_water/2015 -name '*_masked.tif' | wc -l
find /home/lserey/mapbiomas_land/mosaic_184bands_mask_water/work -name mask_summary.json | wc -l
tail -f logs/slurm_<JOBID>_0.out
```
