# Fase 5 — CI con GitHub Actions

## Objetivo

Automatizar lo que hasta ahora se corría a mano: lint, formato, tests, y publicar la imagen Docker en un registry. Que cada `push` a `main` valide el código y, si pasa, publique una imagen lista para desplegar — sin intervención manual.

## Estructura

```
wine-quality-api/
├── .github/
│   └── workflows/
│       └── ci.yml
└── ...
```

Un solo workflow, dos jobs: `lint-test` (siempre) y `build-push` (solo en push a `main`, y solo si `lint-test` pasó).

## Conceptos clave

### Ruff: linter + formatter en uno

Reemplaza la combinación clásica flake8 + isort + black, pero como un solo binario en Rust — mucho más rápido. Se configura activando categorías de reglas por prefijo:

- `E`/`W` — pycodestyle (estilo PEP8 básico)
- `F` — pyflakes (errores reales: imports sin usar, variables no definidas)
- `I` — isort (orden de imports)
- `UP` — pyupgrade (sintaxis moderna de Python)
- `B` — flake8-bugbear (patrones propensos a bugs)

```toml
[tool.ruff]
target-version = "py312"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B"]
```

`line-length` arrancó en el default de Ruff (88, heredado de Black) y se subió a 100 porque los comentarios explicativos del proyecto —los que documentan el *porqué* de cada decisión— superaban ese límite seguido. Al cambiar el límite, el *formatter* también recalculó qué líneas necesitaban re-wrap, no solo el linter.

`ruff check .` (linter: señala violaciones de reglas) y `ruff format --check .` (formatter: solo *reporta* si algo necesitaría reformatearse, sin tocar nada — el flag `--check` es lo que lo hace apto para CI) son pasos separados y complementarios, no alternativos.

### Jobs, `needs`, y triggers condicionales

Un workflow puede tener varios `jobs:` que corren en paralelo por defecto. `needs: lint-test` fuerza que `build-push` espere a que `lint-test` termine (y solo corra si terminó bien) — así nunca se publica una imagen con tests rotos.

```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-test:
    ...
  build-push:
    needs: lint-test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
```

`lint-test` corre en cada push *y* cada PR (control de calidad temprano). `build-push` solo tiene sentido cuando el código ya se mergeó a `main` — publicar una imagen por cada PR abierto no aporta nada y gasta minutos de CI.

### El modelo no vive en el repo — hay que entrenarlo en CI

`models/` está en `.gitignore` a propósito (son artefactos binarios, no código). Localmente esto no se nota porque el modelo ya está en disco de haber corrido `train.py` antes. Pero el runner de GitHub Actions arranca desde una copia limpia del repo vía `git checkout` — solo tiene lo que está trackeado. Como `tests/conftest.py` importa `app.main`, que carga el `.joblib` al importarse, los tests fallaban con `FileNotFoundError` apenas arrancaba la collection de pytest.

La solución: como `training/train.py` descarga el dataset de una URL pública y fija `random_state=42`, es 100% reproducible — no hay motivo para *no* generarlo desde cero en cada run:

```yaml
- name: Train model
  run: uv run python -m training.train
```

Esto no escala a modelos grandes o caros de entrenar (retrainear en cada push sería un desperdicio de tiempo y cómputo). El patrón real para ese caso es un **model registry** versionado (MLflow y similares) del que el CI descarga el artefacto ya entrenado en vez de generarlo — la misma pieza que quedó pospuesta como extensión futura en la Fase 4.

### `python -m paquete.modulo` vs. `python ruta/al/archivo.py`

La diferencia está en qué carpeta se agrega a `sys.path[0]` (la lista de lugares donde Python busca al importar):

- `python training/train.py` (como *script*) → `sys.path[0]` es la carpeta del archivo (`training/`).
- `python -m training.train` (como *módulo*) → `sys.path[0]` es el directorio de trabajo actual (la raíz del repo), y Python resuelve `training.train` navegando esa ruta como un import.

Importa cuando el módulo necesita importar código de otra carpeta del proyecto (ej. `from app import algo`) — con `-m` funcionaría, con la ruta directa probablemente no. En este proyecto no hay tal dependencia, así que ambas formas funcionan igual; se usó `-m` por convención, no por necesidad puntual.

`training/` no tiene `__init__.py` (a diferencia de `app/`, que sí) y aun así `-m training.train` funciona: desde Python 3.3 (PEP 420) cualquier carpeta puede actuar como paquete implícito ("namespace package") sin necesitar ese archivo, siempre que Python la encuentre en el `sys.path`.

### GHCR (GitHub Container Registry) y autenticación

`ghcr.io` es el registry de contenedores integrado a GitHub — la ventaja frente a Docker Hub es que se autentica con el mismo `GITHUB_TOKEN` que el workflow ya tiene disponible automáticamente, sin generar ni guardar credenciales nuevas como secret.

```yaml
permissions:
  packages: write
```

Por defecto el `GITHUB_TOKEN` es de solo lectura para packages — hay que declarar el permiso de escritura explícitamente, si no el push a GHCR falla aunque el login haya sido exitoso.

### `$GITHUB_ENV`: pasar variables entre steps

Cada step de un job corre en su propio proceso de shell, aislado — una variable seteada en un step (`export X=5`) no sobrevive para el siguiente. GitHub Actions resuelve esto con un archivo temporal compartido por job, cuya ruta está en la variable `$GITHUB_ENV`:

```yaml
- name: Set lowercase image name
  run: echo "IMAGE_NAME=${GITHUB_REPOSITORY,,}" >> "$GITHUB_ENV"
```

`echo ... >> "$GITHUB_ENV"` no imprime en pantalla — el `>>` redirige esa salida para que se agregue como línea nueva a ese archivo, en vez de mostrarse en el log. Al terminar el step, el *runner* (no bash) lee el archivo y por cada línea `CLAVE=VALOR` inyecta una variable de entorno real para todos los steps siguientes del mismo job, accesible como `${{ env.IMAGE_NAME }}`.

`${GITHUB_REPOSITORY,,}` es sintaxis de bash: el sufijo `,,` convierte la variable a minúsculas. Hizo falta porque GHCR exige nombres de imagen todo en minúsculas, pero `github.repository`/`GITHUB_REPOSITORY` preserva las mayúsculas del usuario de GitHub (`Rojerr9241/...`) — sin este paso, el build fallaba con `repository name must be lowercase`.

## Decisiones y tradeoffs

- **Entrenar el modelo en cada run de CI en vez de commitear el artefacto o usar un registry**: simple y consistente con por qué `models/` está en `.gitignore`, a costa de no escalar si el entrenamiento se vuelve lento o costoso — para ese caso, ver la nota sobre model registry arriba.
- **`build-push` solo en push a `main`, no en PRs**: evita publicar imágenes de código todavía no revisado/mergeado; a costa de no poder probar la imagen Docker de un PR antes de mergearlo (aceptable en esta escala de proyecto).
- **GHCR en vez de Docker Hub**: cero configuración de credenciales extra (usa `GITHUB_TOKEN`), a costa de acoplar la publicación de imágenes a GitHub específicamente.
- **Tags `latest` + SHA completo del commit**: `latest` para conveniencia (siempre la versión más reciente de `main`), el SHA para trazabilidad exacta de qué commit generó cada imagen — dos etiquetas apuntando a la misma imagen, sin costo extra de build.

## Analogías que ayudaron

- **CI en general = un restaurante**: `lint-test` es el control de calidad en la cocina antes de que un plato salga; `build-push` es empaquetar el plato y llevarlo al mostrador de entrega (el registry) para que se pueda retirar y servir en cualquier lado.
- **GHCR = el mostrador pegado a tu propia cocina**: en vez de un mostrador público genérico (Docker Hub) que requeriría tramitar una llave nueva, usás el que ya está integrado a tu edificio (GitHub), con la credencial que ya tenés.
- **`push` a un PR vs. a `main` = receta en prueba vs. plato del menú oficial**: no tiene sentido empaquetar y publicar una receta que todavía se está probando en la cocina.
- **`needs: lint-test` = nadie empaqueta un plato que no pasó control de calidad primero.**
- **Los permisos de `packages: write` = el permiso explícito para dejar un paquete en el mostrador**, no solo mirarlo.
- **Las dos tags (`latest` + SHA) = "plato del día" + número de lote** — una es conveniente pero cambia todo el tiempo, la otra es un identificador único e inmutable para saber exactamente qué versión generó qué imagen.
- **`$GITHUB_ENV` = un corcho de notas compartido entre cocineros que no pueden hablarse directamente**: cada step es un cocinero que hace su turno y se va; para que el siguiente sepa algo, hay que dejarlo escrito en el corcho (el archivo), y es el gerente del restaurante (el runner) quien lee esas notas y se las comunica al próximo cocinero como si ya las supiera.

## Probar el workflow

Cualquier `push` a `main` lo dispara automáticamente — no requiere correr nada manualmente. Para validar los pasos de forma local antes de pushear:

```bash
uv run ruff check .
uv run ruff format --check .   # o sin --check para aplicar el reformateo
uv run python -m training.train
uv run pytest
```

Una vez publicada la imagen, se puede bajar y correr igual que en la Fase 4, apuntando a GHCR en vez de a la imagen local:

```bash
docker pull ghcr.io/rojerr9241/wine-quality-api:latest
docker run -p 8000:8000 ghcr.io/rojerr9241/wine-quality-api:latest
```
