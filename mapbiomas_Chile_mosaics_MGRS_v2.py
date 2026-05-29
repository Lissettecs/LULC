"""
Google Earth Engine Landsat Mosaic Generator for Chile — MGRS version
======================================================================

Versión modificada del script original para generar mosaicos por tiles MGRS
en lugar de tiles CIM. Genera el mosaico de 184 bandas para Random Forest.

Cambios respecto al script original:
    - Lee input_params_mgrs.json (generado por generate_mgrs_params.py)
    - Usa grilla MGRS en vez de CIM
    - Exporta con CRS UTM explícito (EPSG:32718 o EPSG:32719 según tile)
    - Sin buffer ni tile mask (use_tile_mask=False para tiles MGRS)

Version: 1
"""

import ee
import sys
import os
import json
import traceback
from datetime import datetime

sys.path.append(os.path.abspath('.'))

from modules.CloudAndShadowMaskC2 import *
from modules.SpectralIndexes import *
from modules.Miscellaneous import *
from modules.SmaAndNdfi import *
from modules.Collection import *
from modules.BandNames import *
from modules.DataType import *
from modules.Mosaic import *

sys.dont_write_bytecode = True

ee.Initialize(project="mapbiomas-chile")

# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# JSON generado por generate_mgrs_params.py
paramsJsonPath = "input_params_mgrs.json"

# Sufijo para el nombre del asset exportado
# Usar "" para producción, "-TEST" para pruebas
exportAssetSuffix = "-TEST"

# Versión de máscaras Landsat
versionMasks = '2'

# Asset de la grilla MGRS
mgrsGridAsset = "projects/mapbiomas-chile/assets/LULC/COLLECTION-03/ANCILLARY_DATA/Tiles_Chile_Sentinel"

# Campo del nombre del tile en el asset MGRS
mgrsNameField = "Name"

# Asset de máscaras de tile Landsat (path/row)
assetMasks = "projects/mapbiomas-workspace/AUXILIAR/landsat-mask"

# Versión del mosaico
version = {'CHILE': '3'}

# Colecciones Landsat Collection 2
collectionIds = {
    'l4': 'LANDSAT/LT04/C02/T1_L2',
    'l5': 'LANDSAT/LT05/C02/T1_L2',
    'l7': 'LANDSAT/LE07/C02/T1_L2',
    'l8': 'LANDSAT/LC08/C02/T1_L2',
    'l9': 'LANDSAT/LC09/C02/T1_L2',
}

landsatIds = {
    'l4': 'landsat-4',
    'l5': 'landsat-5',
    'l7': 'landsat-7',
    'l8': 'landsat-8',
    'l9': 'landsat-9',
}

# Colección de salida — mosaico RF (184 bandas)
outputCollections = {
    'l4': 'projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF',
    'l5': 'projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF',
    'l7': 'projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF',
    'l8': 'projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF',
    'l9': 'projects/mapbiomas-chile/assets/MOSAICS/MGRS/RF',
}


# ============================================================================
# FUNCIONES AUXILIARES
# ============================================================================

def parse_iso_date(value, fallback):
    text = str(value or "").strip()
    if not text:
        return fallback
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return fallback


def normalize_satellite(value):
    text = str(value or "").strip().lower()
    if text in {"l4", "l5", "l7", "l8", "l9"}:
        return text
    if text in {"4", "5", "7", "8", "9"}:
        return f"l{text}"
    if text.startswith("l") and len(text) > 1 and text[1:].isdigit():
        return text
    raise ValueError(f"Código de satélite inválido: {value}")


def load_processing_params(json_path):
    """
    Lee input_params_mgrs.json y devuelve params organizados por territorio.
    Incluye el campo 'crs' para la exportación en UTM.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        records = json.load(f)

    params_by_territory = {}
    params_index = {}

    def to_bool(value, default=True):
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        s = str(value).strip().lower()
        if not s:
            return default
        return s not in {"false", "0", "no", "n", "off"}

    for item in records:
        territory = str(item.get("country", "CHILE")).strip().upper()
        grid_name = str(item.get("grid_name", "")).strip()
        year      = int(item.get("year"))
        satellite = normalize_satellite(item.get("satellite"))

        if not grid_name:
            continue

        default_start = f"{year}-01-01"
        default_end   = f"{year}-12-31"

        cloud_cover_raw = item.get("cloud_cover", 80)
        cloud_cover = int(cloud_cover_raw) if str(cloud_cover_raw).strip() else 80

        black_list_raw = item.get("black_list", [])
        if isinstance(black_list_raw, list):
            black_list = [str(x).strip() for x in black_list_raw if str(x).strip()]
        elif str(black_list_raw).strip():
            black_list = [str(black_list_raw).strip()]
        else:
            black_list = []

        use_tile_mask = to_bool(
            item.get("use_tile_mask", item.get("USETILEMASK", item.get("usetilemask"))),
            default=False,
        )

        crs = item.get("crs", None)

        param = {
            "territory":     territory,
            "grid_name":     grid_name,
            "year":          year,
            "satellite":     satellite,
            "date_start":    parse_iso_date(item.get("t0_s"), default_start),
            "date_end":      parse_iso_date(item.get("t1_s"), default_end),
            "cloud_cover":   cloud_cover,
            "black_list":    black_list,
            "use_tile_mask": use_tile_mask,
            "crs":           crs,
        }

        params_by_territory.setdefault(territory, []).append(param)
        params_index[(territory, grid_name, year, satellite)] = param

    return params_by_territory, params_index


def multiplyBy10000(image):
    bands = ['blue', 'red', 'green', 'nir', 'swir1', 'swir2',
             'cai', 'evi2', 'gcvi', 'hallcover', 'hallheigth',
             'ndvi', 'ndwi', 'pri', 'savi', 'ndbi', 'ndmi', 'ndsi', 'mbi']
    return image.addBands(
        srcImg=image.select(bands).multiply(10000),
        names=bands,
        overwrite=True
    )


def divideBy10000(image):
    bands = ['blue', 'red', 'green', 'nir', 'swir1', 'swir2']
    return image.addBands(
        srcImg=image.select(bands).divide(10000),
        names=bands,
        overwrite=True
    )


def applyCloudAndShadowMask(collection):
    collectionWithMasks = getMasks(
        collection,
        cloudThresh=10,
        cloudFlag=True,
        cloudScore=True,
        cloudShadowFlag=True,
        cloudShadowTdom=True,
        zScoreThresh=-1,
        shadowSumThresh=4000,
        dilatePixels=4,
        cloudHeights=[200, 700, 1200, 1700, 2200, 2700, 3200, 3700, 4200, 4700],
        cloudBand='cloudShadowFlagMask'
    )
    return collectionWithMasks.map(
        lambda image: image.mask(
            image.select(['cloudFlagMask', 'cloudShadowFlagMask'])
                 .reduce(ee.Reducer.anyNonZero()).eq(0)
        )
    )


def getTiles(collection):
    collection = collection.map(
        lambda image: image.set('tile', {
            'path': image.get('WRS_PATH'),
            'row':  image.get('WRS_ROW'),
            'id':   ee.Number(image.get('WRS_PATH'))
                       .multiply(1000).add(image.get('WRS_ROW')).int32()
        })
    )
    tiles = collection.distinct(['tile']) \
        .reduceColumns(ee.Reducer.toList(), ['tile']) \
        .get('list')
    return tiles.getInfo()


# ============================================================================
# CARGA DE PARÁMETROS
# ============================================================================

processingParamsByTerritory, processingParamsIndex = load_processing_params(paramsJsonPath)

territoryNames = sorted(processingParamsByTerritory.keys())
gridNames = {
    territory: sorted({p["grid_name"] for p in params})
    for territory, params in processingParamsByTerritory.items()
}

print(f"Parámetros cargados: {sum(len(v) for v in processingParamsByTerritory.values())} filas")
print(f"Territorios: {territoryNames}")
print(f"Tiles MGRS:  {sum(len(v) for v in gridNames.values())}")
print(f"Jobs totales: {sum(len(v) for v in processingParamsByTerritory.values())}")

# ── FILTRO: 6 tiles, años 2010-2016 ─────────────────────────────
YEARS_RANGE = list(range(2010, 2017))  # 2010, 2011, ..., 2016

for territory in processingParamsByTerritory:
    processingParamsByTerritory[territory] = [
        p for p in processingParamsByTerritory[territory]
        if p["year"] in YEARS_RANGE
    ]

print(f"Jobs filtrados: {sum(len(v) for v in processingParamsByTerritory.values())}")
# ────────────────────────────────────────────────────────────────
# ============================================================================
# CARGA DE ASSETS GEE
# ============================================================================

mgrsGrid = ee.FeatureCollection(mgrsGridAsset)

collectionTiles = ee.ImageCollection(assetMasks)
allTiles = collectionTiles.reduceColumns(
    ee.Reducer.toList(), ['tile']).get('list').getInfo()

# ============================================================================
# LOOP PRINCIPAL
# ============================================================================

for territoryName in territoryNames:

    for param in processingParamsByTerritory[territoryName]:
        gridName  = param["grid_name"]
        year      = param["year"]
        satellite = param["satellite"]
        exportCRS = param["crs"]

        print(f"\n{'='*60}")
        print(f"Procesando: {gridName} | {year} | {satellite.upper()} | {exportCRS}")

        dateStart  = param["date_start"]
        dateEnd    = param["date_end"]
        cloudCover = param["cloud_cover"]

        outputName = (
            f"TMP-{territoryName}-{gridName}-{year}"
            f"-{satellite.upper()}-{version[territoryName]}{exportAssetSuffix}"
        )

        try:
            # ── Verificar si el mosaico ya existe ─────────────────────────
            alreadyInCollection = ee.ImageCollection(outputCollections[satellite]) \
                .filterMetadata('grid_name', 'equals', gridName) \
                .filterMetadata('year', 'equals', year) \
                .reduceColumns(ee.Reducer.toList(), ['system:index']) \
                .get('list').getInfo()

            if outputName in alreadyInCollection:
                print(f"  Ya existe, saltando...")
                continue

            # ── Geometría del tile MGRS ────────────────────────────────────
            grid = mgrsGrid.filter(ee.Filter.eq(mgrsNameField, gridName))
            grid = ee.Feature(grid.first()).geometry()

            # ── Colección Landsat ──────────────────────────────────────────
            excluded = param["black_list"]

            collection = getCollection(
                collectionIds[satellite],
                dateStart=dateStart,
                dateEnd=dateEnd,
                cloudCover=cloudCover,
                geometry=grid,
                trashList=excluded if excluded else None
            )

            # ── Tiles path/row intersectantes ──────────────────────────────
            tiles = getTiles(collection)
            use_tile_mask = bool(param.get("use_tile_mask", False))

            if use_tile_mask:
                tiles = [t for t in tiles if t['id'] in allTiles]

            if len(tiles) == 0:
                print(f"  Sin tiles disponibles, saltando...")
                continue

            # ── Procesar por path/row ──────────────────────────────────────
            subcollectionList = []
            for tile in tiles:
                print(f"  Path: {tile['path']}  Row: {tile['row']}")

                subcollection = collection \
                    .filterMetadata('WRS_PATH', 'equals', tile['path']) \
                    .filterMetadata('WRS_ROW',  'equals', tile['row'])

                if use_tile_mask:
                    tileMask = ee.Image(f"{assetMasks}/{tile['id']}-{versionMasks}")
                    subcollection = subcollection.map(
                        lambda image: image.mask(tileMask).selfMask()
                    )

                subcollectionList.append(subcollection)

            # ── Fusionar subcollections ────────────────────────────────────
            collection = ee.ImageCollection(
                ee.List(subcollectionList).iterate(
                    lambda sub, col: ee.ImageCollection(col).merge(sub),
                    ee.ImageCollection([])
                )
            )

            # ── Renombrar bandas ───────────────────────────────────────────
            bands = getBandNames(satellite + 'c2')
            collection = collection.select(bands['bandNames'], bands['newNames'])

            # ── Máscara de nubes y sombras ─────────────────────────────────
            collection = applyCloudAndShadowMask(collection)

            # ── SMA ────────────────────────────────────────────────────────
            endmember  = ENDMEMBERS[landsatIds[satellite]]
            collection = collection.map(
                lambda image: image.addBands(getFractions(image, endmember))
            )

            # ── Índices SMA ────────────────────────────────────────────────
            collection = collection \
                .map(getNDFI) \
                .map(getSEFI) \
                .map(getWEFI) \
                .map(getFNS)

            # ── Índices espectrales ────────────────────────────────────────
            collection = (collection
                .map(divideBy10000)
                .map(getCAI)
                .map(getEVI2)
                .map(getGCVI)
                .map(getHallCover)
                .map(getHallHeigth)
                .map(getNDVI)
                .map(getNDWI)
                .map(getPRI)
                .map(getSAVI)
                .map(getNDBI)
                .map(getNDMI)
                .map(getNDSI)
                .map(getMBI)
                .map(multiplyBy10000)
            )

            # ── Mosaico anual ──────────────────────────────────────────────
            mosaic = getMosaic(
                collection,
                percentileDry=25,
                percentileWet=75,
                percentileBand='ndvi',
                dateStart=dateStart,
                dateEnd=dateEnd
            )

            mosaic = promoteMedianToBaseName(mosaic, ['mbi', 'ndbi', 'ndmi', 'ndsi'])

            # ── Topografía y textura ───────────────────────────────────────
            mosaic = getEntropyG(mosaic)
            mosaic = getAspect(mosaic)
            mosaic = getElevation(mosaic)
            mosaic = getSlope(mosaic)
            mosaic = getTpi(mosaic)

            mosaic = setBandTypes(mosaic, mtype="chile")

            # ── Reproyectar al CRS UTM del tile MGRS ──────────────────────
            mosaic = mosaic.reproject(crs=exportCRS, scale=30)

            # ── Metadata ───────────────────────────────────────────────────
            mosaic = mosaic \
                .set('year',       year) \
                .set('collection', 1.0) \
                .set('grid_name',  gridName) \
                .set('grid_type',  'MGRS') \
                .set('crs',        exportCRS) \
                .set('version',    str(version[territoryName])) \
                .set('territory',  territoryName) \
                .set('satellite',  satellite)

            # ── Exportación ────────────────────────────────────────────────
            print(f"  Exportando: {outputName}")
            task = ee.batch.Export.image.toAsset(
                image=mosaic,
                description=outputName,
                assetId=outputCollections[satellite] + '/' + outputName,
                region=grid.coordinates().getInfo(),
                crs=exportCRS,
                scale=30,
                maxPixels=int(1e13)
            )
            task.start()
            print(f"  Tarea iniciada OK")

        except Exception as e:
            msg = 'Too many tasks already in the queue (3000). Please wait for some of them to complete.'
            if str(e) == msg:
                raise Exception(e)
            else:
                print(f"  ERROR en {gridName} {year}: {e}")
                traceback.print_exc()
