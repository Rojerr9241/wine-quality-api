# Fase 4 — Dockerfile multi-stage con uv

## Objetivo

Empaquetar la API en una imagen Docker reproducible y liviana: sin herramientas de build, sin cache de `uv`, sin dependencias de desarrollo (`pytest`, `httpx`) — solo lo necesario para correr `uvicorn app.main:app` en producción.

## Estructura

```
wine-quality-api/
├── Dockerfile         # raíz del repo — mismo nivel que pyproject.toml
├── .dockerignore       # raíz del repo
└── ...
```

Ambos van en la raíz porque el *build context* de `docker build .` es el directorio desde el que se corre el comando — todo lo que el `Dockerfile` copia (`app/`, `models/`, `pyproject.toml`, `uv.lock`) tiene que estar dentro de ese contexto.

## Conceptos clave

### Imagen vs. contenedor

Una **imagen** es una plantilla de solo lectura: capas de filesystem apiladas (una por cada `COPY`/`RUN`) más metadata (`CMD`, variables de entorno, puerto expuesto). Es un molde, no algo en ejecución — análogo a una clase en OOP. Un **contenedor** es una instancia en ejecución de esa imagen (análogo a un objeto instanciado de esa clase); pueden correr varios contenedores del mismo `wine-quality-api:latest` en simultáneo, cada uno aislado, todos compartiendo el mismo molde de solo lectura de base.

### Por qué multi-stage

Un build de una sola etapa dejaría en la imagen final el binario de `uv`, su cache de descargas, y cualquier herramienta de compilación usada durante la instalación — peso muerto que nunca se usa en runtime. La solución: dos etapas (`FROM ... AS builder` y `FROM ... AS runtime`), donde la segunda es una imagen **completamente nueva y separada**. Nada de `builder` pasa automáticamente a `runtime` — solo lo que se copia explícitamente con `COPY --from=builder`. El resultado final (lo que se tagea y se corre) es únicamente lo que arma la etapa `runtime`; `builder` queda descartado (aunque Docker lo mantiene cacheado localmente para acelerar builds futuros).

### El truco de los dos `uv sync`

```dockerfile
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app/ ./app/
RUN uv sync --frozen --no-dev
```

- **Primer `uv sync`**: corre cuando en la imagen solo existen `pyproject.toml` y `uv.lock` (`app/` todavía no fue copiado). Instala todas las dependencias externas declaradas (`pandas`, `scikit-learn`, `fastapi`, etc.). `--no-install-project` le dice que no intente instalar el paquete local, porque su código fuente ni siquiera está copiado todavía.
- **Segundo `uv sync`**: corre después de `COPY app/ ./app/`, y ahora sí instala el paquete local también (sin el flag). Es rápido porque las dependencias pesadas ya están en disco desde la capa anterior — solo agrega el paquete propio.

La separación en dos pasos no la decide `uv`, la decide el **orden de los `COPY`**, combinado con el cacheo de capas de Docker: si `pyproject.toml`/`uv.lock` no cambian entre builds, Docker reutiliza la capa completa del primer `uv sync` sin re-ejecutarlo. Si solo cambia código en `app/`, se invalida `COPY app/` en adelante, pero la capa de dependencias ya instaladas se mantiene como punto de partida — evita reinstalar `pandas`/`scikit-learn` en cada build por un cambio de una línea en un endpoint.

- `--frozen`: falla si `uv.lock` no está sincronizado con `pyproject.toml`, en vez de resolver algo distinto silenciosamente — es lo que da reproducibilidad real.
- `--no-dev`: excluye el grupo `dev` (`pytest`, `httpx`) — no hacen falta en producción.
- `UV_LINK_MODE=copy`: por defecto `uv` usa hardlinks desde su cache para instalar rápido, pero esos enlaces no sobreviven al copiarse a otra etapa (`COPY --from=builder`). `copy` fuerza archivos reales.
- `UV_COMPILE_BYTECODE=1`: precompila `.pyc` durante el build en vez de en el primer arranque — arranques más rápidos en producción.

### Rutas relativas y `WORKDIR`

`predictor.py` calcula la ruta al modelo así:

```python
MODELS_DIR = Path(__file__).parent.parent / "models"
```

Esto asume que `app/` y `models/` son carpetas hermanas bajo una raíz común — tal como están en el repo local. Por eso `WORKDIR /app` y `COPY models/ ./models/` (ruta relativa al `WORKDIR`, no absoluta) son importantes: replican esa misma estructura relativa dentro del contenedor, para que el código funcione sin cambios entre entorno local y Docker. Si el modelo se copiara a una ruta distinta (por ejemplo `/models` absoluto, en vez de `./models` relativo a `/app`), `MODELS_DIR` apuntaría a un lugar inexistente y la API fallaría al arrancar con `FileNotFoundError`.

### Usuario no-root

```dockerfile
RUN groupadd --system app && useradd --system --gid app app
...
USER app
```

Sin `USER`, un contenedor corre como `root` por defecto — no es un error de Docker, pero es mala práctica de seguridad: si el proceso de la app es comprometido (por una vulnerabilidad propia o de una dependencia), correr como `root` le da privilegios totales dentro del contenedor. Crear un usuario sin privilegios limita ese radio de daño. No es obligatorio técnicamente, pero es un ítem estándar de checklist en cualquier imagen pensada para producción.

### `ENV PATH="/app/.venv/bin:$PATH"`

`PATH` es una lista de directorios separados por `:`, heredada de la imagen base. El sistema busca ejecutables recorriéndola de izquierda a derecha y se detiene en la primera coincidencia. Al anteponer `/app/.venv/bin`, cualquier comando (`uvicorn`, en el `CMD`) resuelve primero al binario del `.venv/` — el que tiene todas las dependencias instaladas — antes que cualquier cosa del sistema operativo. Es el mismo efecto que la parte relevante de `source .venv/bin/activate`, sin necesitar una sesión de shell interactiva.

### `CMD` y `uvicorn`

```dockerfile
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

FastAPI es un framework, no un servidor — necesita un servidor ASGI (`uvicorn`) para abrir un socket y despachar requests HTTP a la app. `app.main:app` apunta al módulo `app/main.py` y al objeto `app` dentro de él. `--host 0.0.0.0` (no `127.0.0.1`) es necesario para que el servidor sea alcanzable desde fuera del contenedor. La forma de lista (`CMD ["..."]`, *exec form*) evita que Docker envuelva el comando en un shell intermedio, para que señales como `SIGTERM` lleguen directo al proceso de `uvicorn`.

### `.dockerignore`

Análogo a `.gitignore`, pero controla qué entra al *build context* de Docker (independiente de qué está trackeado en git). Excluye `.venv/`, `.git/`, `tests/`, `docs/`, caches — nada de eso hace falta para correr la API. Deliberadamente **no** excluye `models/`, `pyproject.toml` ni `uv.lock`, que sí se necesitan.

## Decisiones y tradeoffs

- **Modelo copiado desde disco local (`COPY models/`) en vez de entrenado en el build o descargado de un registry**: build rápido y simple, a costa de requerir que el modelo ya esté entrenado localmente (`uv run python training/train.py`) antes de buildear la imagen. Alternativas consideradas:
  - Entrenar el modelo dentro del `builder` (`RUN uv run python training/train.py`): 100% reproducible desde cero, pero build más lento y requiere red durante el build.
  - Descargar el artefacto desde un registry externo (S3, MLflow Model Registry): el patrón más robusto para equipos reales, pero es infraestructura adicional que corresponde más a una fase futura (ver abajo).
- **Imágenes base con el mismo tag de Debian (`bookworm`) en ambas etapas**: evita incompatibilidades de librerías del sistema (glibc, etc.) entre lo instalado en `builder` y lo que corre en `runtime`.
- **MLflow (Tracking / Model Registry) queda fuera de esta fase**: se consideró como alternativa a la opción 2 para gestionar el artefacto del modelo, pero se decidió posponerlo — agregaría experiment tracking y versionado de modelos, conectando naturalmente con una futura fase de gestión de modelos en AWS, pero no es necesario para tener el Dockerfile funcionando.

## Probar la imagen

```bash
docker build -t wine-quality-api:latest .
docker run -p 8000:8000 wine-quality-api:latest
```

Con el contenedor corriendo:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/model-info

curl -X POST http://localhost:8000/predict \
  -H "Content-Type: application/json" \
  -d '{
    "fixed_acidity": 7.4, "volatile_acidity": 0.7, "citric_acid": 0.0,
    "residual_sugar": 1.9, "chlorides": 0.076, "free_sulfur_dioxide": 11.0,
    "total_sulfur_dioxide": 34.0, "density": 0.9978, "ph": 3.51,
    "sulphates": 0.56, "alcohol": 9.4
  }'
```

`curl` no necesita `uv run` — es un binario del sistema operativo, ajeno al entorno virtual de Python; solo hace una petición HTTP normal contra el puerto mapeado por `docker run -p`.

## Nota sobre `docker compose`

No se usa en esta fase: el proyecto tiene un solo servicio (la API), sin base de datos ni otros contenedores que orquestar, así que `docker build`/`docker run` alcanza. `docker compose` tendría sentido si en el futuro se agregara, por ejemplo, una base de datos para loguear predicciones — permite declarar varios servicios en un YAML, con red compartida automática (los contenedores se resuelven entre sí por nombre de servicio) y un solo comando (`docker compose up`) para levantarlos todos juntos.