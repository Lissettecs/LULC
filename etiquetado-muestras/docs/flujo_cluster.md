# Flujo de etiquetado en cluster

## 1. Verificar entradas

```bash
cd /home/lserey/repositorios/LULC/etiquetado-muestras
bash cluster/run_check_inputs.sh
```

## 2. Ejecutar piloto

```bash
bash cluster/run_pilot_anuales.sh
```

Revisar en QGIS:

```text
/home/lserey/mapbiomas_land/prod/labels/anuales/subdivisiones_C2_anuales.gpkg
```

## 3. Ejecutar todo por grupo

```bash
bash cluster/run_all_by_group.sh
```

## 4. Si quieres parches individuales

Por defecto el script disuelve por clase dentro de cada rectángulo-año.

Para conservar cada parche continuo como entidad separada:

```bash
python scripts/02_generate_labels_c2_cluster.py \
  --samples-dir /home/lserey/mapbiomas_land/prod/samples \
  --landcover-dir /home/lserey/mapbiomas_land/landcover_col2 \
  --labels-dir /home/lserey/mapbiomas_land/prod/labels \
  --only-groups anuales \
  --patches \
  --overwrite
```
