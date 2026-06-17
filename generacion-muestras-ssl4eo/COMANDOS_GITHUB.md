# Comandos para subir esta información a GitHub desde tu PC

Estos comandos asumen que trabajarás en tu computador local con Git instalado. No necesitas estar conectada al cluster.

Rama recomendada:

```bash
generacion-muestras-ssl4eo
```

## 1. Clonar el repositorio en tu PC

Abre Git Bash, PowerShell o la terminal de Cursor/VS Code en la carpeta donde quieras guardar el repositorio. Por ejemplo, en Windows:

```powershell
cd C:\Users\TU_USUARIO\Documents
mkdir GitHub
cd GitHub
```

Luego clona el repositorio:

```bash
git clone https://github.com/Lissettecs/LULC.git
cd LULC
```

## 2. Crear una rama distinta de main

```bash
git switch main
git pull origin main
git switch -c generacion-muestras-ssl4eo
```

Si Git indica que la rama ya existe localmente, usa:

```bash
git switch generacion-muestras-ssl4eo
```

Si la rama ya existe en GitHub, usa:

```bash
git fetch origin
git switch generacion-muestras-ssl4eo
```

## 3. Copiar los archivos del paquete

Descomprime `LULC_generacion_muestras_ssl4eo.zip` en una carpeta temporal de tu PC.

Luego copia el contenido del paquete dentro de la carpeta del repositorio `LULC`. La estructura final debería quedar así:

```text
LULC/
├── README.md
├── requirements.txt
├── environment.yml
├── .gitignore
├── COMANDOS_GITHUB.md
├── scripts/
├── docs/
├── data/
├── archivos_intermedios/
├── muestras_finales/
└── reportes_revision/
```

Puedes copiarlo desde el Explorador de Windows, desde Cursor/VS Code o con comandos.

Ejemplo desde PowerShell, ajustando las rutas a tu caso:

```powershell
Copy-Item -Path "C:\ruta\temporal\LULC_generacion_muestras_ssl4eo\*" `
  -Destination "C:\Users\TU_USUARIO\Documents\GitHub\LULC" `
  -Recurse -Force
```

## 4. Revisar qué se va a subir

Desde la carpeta `LULC`:

```bash
git status -sb
```

Debes revisar que aparezcan principalmente archivos `.py`, `.md`, `.yml`, `.txt` y carpetas vacías conservadas con `.gitkeep`.

No deberían subirse archivos pesados como `.tif`, `.shp`, `.gpkg`, `.geojson`, `.zip`, `.csv`, `.parquet` o resultados derivados grandes. Están excluidos en `.gitignore`, salvo excepciones internas como `.gitkeep`.

## 5. Agregar, confirmar y subir la rama

```bash
git add README.md requirements.txt environment.yml .gitignore COMANDOS_GITHUB.md scripts/ docs/ data/ archivos_intermedios/ muestras_finales/ reportes_revision/
git commit -m "Agregar flujo de generacion de muestras SSL4EO"
git push -u origin generacion-muestras-ssl4eo
```

## 6. Crear Pull Request en GitHub

Una vez subida la rama, entra al repositorio en GitHub y crea un Pull Request con:

```text
base: main
compare: generacion-muestras-ssl4eo
```

Título sugerido:

```text
Agregar flujo de generación de muestras SSL4EO
```

Descripción sugerida:

```markdown
## Cambios
- Agrega scripts para caracterización de grillas, descarga desde Drive, selección de rectángulos, revisión, auditoría, visualización y planificación temporal.
- Agrega módulos auxiliares de rutas, taxonomía, clases críticas y balanceo.
- Agrega README metodológico y estructura de carpetas para insumos, intermedios, muestras finales y reportes.
- Agrega archivos de dependencias para instalación con pip o conda/mamba.

## Alcance
Este PR incorpora el flujo de generación de muestras en una rama separada de main. No incorpora datos geoespaciales pesados ni productos derivados.

## Validación
- Revisión de estructura de archivos.
- Validación básica de sintaxis de los scripts Python.
- Archivos pesados excluidos por .gitignore.
```

## Comandos útiles si algo sale mal

Ver la rama actual:

```bash
git branch --show-current
```

Ver archivos pendientes:

```bash
git status
```

Quitar un archivo del área de commit sin borrarlo de tu PC:

```bash
git restore --staged ruta/del/archivo
```

Cancelar cambios locales de un archivo específico:

```bash
git restore ruta/del/archivo
```

Eliminar la rama local si necesitas empezar de nuevo:

```bash
git switch main
git branch -D generacion-muestras-ssl4eo
```
