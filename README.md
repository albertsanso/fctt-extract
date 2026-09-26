# Descarga de actas FCTT

`src/actas-html/download_actas.py` recorre las jornadas 1 a 22 de los grupos
`G1`, `G2` y `G3` y guarda directamente el HTML de cada página
`fctt.cat/lligues/.../?jornada=N` en:

```text
resources/{temporada}/tercera nacional/{grup}/jornada_{N}.html
```

El script no necesita paquetes externos: usa únicamente la biblioteca estándar
de Python. No solicita los enlaces `control.fctt.cat/partido/.../acta`, porque
esos enlaces pueden devolver PDF. Prueba primero la URL indicada en el prompt
(`/lligues/G1/`) y, si la web responde 404, usa la ruta actual
(`/lligues/grup-1/`).

## Uso

Desde la raíz del repositorio:

```powershell
python src/actas-html/download_actas.py --verbose
```

Para una descarga parcial o una simulación:

```powershell
python src/actas-html/download_actas.py --groups G1 G2 --jornadas 1 2 3
python src/actas-html/download_actas.py --groups G1 --jornadas 1 --dry-run --verbose
python src/actas-html/download_actas.py --output D:\datos\fctt --overwrite
```

Los archivos existentes se conservan por defecto. `--overwrite` permite
actualizarlos. `--retries` y `--timeout` controlan la tolerancia de red.

El descargador reutiliza una sesión HTTP, deja por defecto cinco segundos entre
peticiones y aplica *backoff* exponencial con *jitter* ante errores temporales.
Respeta `Retry-After` cuando el servidor limita la velocidad. No intenta
eludir controles de acceso —no usa proxies ni rota el `User-Agent`—: una respuesta `403` o una página de bloqueo se
registra como error y se continúa con la jornada siguiente. Los fallos quedan
en `resources/download_failures.jsonl` para facilitar una ejecución posterior.

Cuando FCTT responde `No s'han trobat resultats.`, el script vuelve a comprobar
la jornada una sola vez tras 30 segundos de forma predeterminada. Si en una
actualización posterior aparecen datos, sustituye automáticamente el HTML vacío
existente. Puede ajustarse con `--empty-retries` y `--empty-retry-delay`.

```powershell
python src/actas-html/download_actas.py --request-delay 5 --retries 5 --verbose
python src/actas-html/download_actas.py --empty-retries 2 --empty-retry-delay 60 --verbose
python src/actas-html/download_actas.py --failure-log resources/download_failures.jsonl --verbose
```

## Parsear HTML a JSON

`src/actas-html/parse_actas.py` recorre los HTML descargados y genera un JSON
por encuentro en:

```text
resources/actas-json/{temporada}/{categoria}/{grup}/jornada_{N}_partido_{id}.json
```

Cada JSON sigue el modelo de `resources/actas-json/model-definition.json` e
incluye equipos, alineaciones, partidos individuales, dobles, sets, resultado,
fecha, hora, lugar y árbitro cuando están disponibles.
Si una página HTML masculina contiene `No s'han trobat resultats.` o no tiene
ningún partido, no se crea un JSON; el parser lo informa mediante un warning.
En cambio, para `female` se genera igualmente
`jornada-{N}-partido-pendiente.json` con la información mínima exigida por el
modelo (`acta_publicada: false`, temporada, género, competición, fase, grupo y
jornada; el resto a `null` o vacío). Se sustituye automáticamente en cuanto la
jornada publica sus encuentros.

Para procesar todos los HTML:

```powershell
python src/actas-html/parse_actas.py --verbose
```

Para procesar una carpeta o un único HTML en otra ubicación:

```powershell
python src/actas-html/parse_actas.py --input src/actas-html/resources --output resources/actas-json
python src/actas-html/parse_actas.py --input src/actas-html/resources/2025-2026/tercera nacional/G1/jornada_1.html --output resources/actas-json
```

## Empaquetar JSON

`src/packager/package_actas.py` crea `actas-json.zip` con todos los JSON de
`resources/actas-json/`, bajo el prefijo `actas-json/` y conservando su jerarquía.
También incluye un `manifest.json` con `source: "FCTT"`, las temporadas
detectadas y las rutas de los archivos dentro de `assets.ACTAS.files`.

```powershell
python src/packager/package_actas.py
python src/packager/package_actas.py --input-dir D:\datos\actas-json --output-file D:\datos\actas-json.zip --force
python src/packager/package_actas.py --season 2023-2024,2024-2025 --force
python src/packager/package_actas.py --input-dir D:\datos\actas-json --season "2023-2024, 2024-2025" --output-file D:\datos\seleccion.zip --force
```

`--season` es opcional. Si se indica, acepta una o varias temporadas separadas
por comas (`YYYY-YYYY`) y el ZIP solo incluye esas carpetas, además de
`manifest.json`. La salida puede contener cualquier número de temporadas
seleccionadas; el nombre automático incluye las temporadas normalizadas.

La salida existente se conserva por defecto; usa `--force` para reemplazarla.

## Pruebas

Las pruebas son offline y no descargan datos:

```powershell
python -m unittest discover -s src/actas-html -p "test_*.py"
```
