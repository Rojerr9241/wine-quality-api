# Fase 3 — Testing con pytest

## Objetivo

Cubrir la API con dos niveles de tests: **integración** (los endpoints, vía HTTP) y **unitarios** (la lógica de `predictor.py`, en aislamiento). Usar fixtures compartidas para no duplicar el setup entre archivos.

## Estructura

```
tests/
├── __init__.py
├── conftest.py        # Fixtures compartidas: client, sample_payload
├── test_api.py         # Tests de integración (HTTP, vía TestClient)
└── test_predictor.py   # Tests unitarios (llamadas directas a predictor.py)
```

## Conceptos clave

### Unit tests vs. integration tests

- **Unitarios** (`test_predictor.py`): llaman a `predictor.predict()` / `predictor.get_metadata()` directamente, en el mismo proceso de Python. Sin red, sin JSON, sin routing de FastAPI de por medio.
- **Integración** (`test_api.py`): pasan por `TestClient`, ejercitando el stack completo — routing, validación de Pydantic, serialización de vuelta a JSON — tal como lo vería un cliente HTTP real.

Ambos validan garantías parecidas (tipo de `quality`, rango de `probability`) pero en capas distintas. Si un test unitario pasa y el de integración falla, el problema está en el routing o los schemas, no en la lógica del modelo.

### Fixtures (`@pytest.fixture`)

Una fixture es una función que prepara algo que los tests necesitan, y que pytest inyecta automáticamente por nombre de parámetro:

```python
def test_algo(client):   # pytest busca una fixture llamada "client"
    ...
```

Pytest la resuelve, la ejecuta, y pasa lo que produce como valor del parámetro — es inyección de dependencias. `conftest.py` es el lugar donde pytest busca fixtures automáticamente para todos los archivos de test en su mismo directorio (y subdirectorios), sin necesidad de import explícito.

Por defecto el scope es `function`: la fixture se re-ejecuta en cada test que la pide. No es una optimización de performance (no comparte instancias) — es principalmente una forma de evitar duplicar setup, y como bonus da aislamiento: cada test recibe su propia copia independiente, así que mutar el resultado de una fixture en un test no afecta a otros.

### `yield` vs. `return` en una fixture

Una fixture con `yield` separa el código en dos tiempos: lo que está *antes* corre como setup, lo que está *después* corre como teardown (cleanup), incluso si el test falla.

```python
@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
    # el "with" se cierra solo cuando el test termina y la ejecución vuelve acá
```

`sample_payload`, en cambio, usa `return` — es un dict plano, no hay ningún recurso que liberar después:

```python
@pytest.fixture
def sample_payload():
    return {...}
```

### `TestClient` y el lifespan de FastAPI

`with TestClient(app) as c:` dispara el protocolo ASGI de *lifespan*: el evento de startup al entrar al bloque, el de shutdown al salir. El proyecto todavía no define un lifespan explícito en `main.py` (el modelo se carga a nivel de módulo en `predictor.py`, no en un hook de startup), así que hoy esto no tiene efecto observable — pero es la forma idiomática recomendada por FastAPI, y queda preparado por si en el futuro se migra la carga del modelo a un lifespan real.

### De dónde viene `response.json()`

`TestClient` es una subclase de `httpx.Client`. `client.get(...)` / `client.post(...)` devuelven un objeto `httpx.Response` — el mismo tipo que tendrías con una petición HTTP real. `.status_code` y `.json()` son atributos/métodos de esa clase, no algo específico de FastAPI. `.json()` parsea el texto crudo del body (JSON) a un dict de Python.

### Reutilizar `sample_payload` entre HTTP y llamadas directas

Como las keys de `sample_payload` coinciden con los campos de `WineFeatures`, un test unitario puede construir la instancia con unpacking:

```python
features = WineFeatures(**sample_payload)
```

Evita duplicar los 11 valores en dos archivos distintos.

### Buenas prácticas de `assert` aplicadas

- **`status_code` primero**: si el endpoint falla, el mensaje de error es inmediato ("esperaba 200, recibí 422") en vez de un `KeyError` confuso al intentar leer el body de un error.
- **Comparaciones encadenadas**: `assert 0 <= x <= 1` en vez de `assert (0 <= x) and (x <= 1)`.
- **Nunca `isinstance(x, y) == True`**: `isinstance()` ya devuelve un `bool`; comparar contra `True` es ruido, no una verificación adicional.
- **No hardcodear valores que dependen del entrenamiento** (`accuracy` exacto, `quality` exacto, `trained_at`): eso rompería los tests en cada reentrenamiento sin que haya un bug real. En su lugar, se valida el **contrato de tipos** (`isinstance`) y los invariantes matemáticos estables (`0 <= probability <= 1`, `len(feature_names) == 11`).
- **No acoplarse al mensaje exacto de error 422 de Pydantic**: solo se valida el status code, porque el formato interno del mensaje puede cambiar entre versiones de Pydantic sin que sea un bug del proyecto.

### Arrange / Act / Assert (AAA)

Estructurar cada test en tres bloques, separados por líneas en blanco: preparar datos (Arrange), ejecutar la única acción bajo prueba (Act), verificar el resultado (Assert). Facilita leer un test de un vistazo sin necesidad de etiquetar cada línea con comentarios.

## Consideración en `pyproject.toml`

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

Sin esto, pytest recorre todo el árbol desde el rootdir buscando `test_*.py`, incluyendo `training/`, `models/`, etc. `testpaths` acota la búsqueda a `tests/`, haciendo que `uv run pytest` sea determinístico sin depender de desde dónde se corra.

Dependencias de desarrollo (grupo separado de las de producción, ya que no se necesitan en el contenedor final):

```toml
[dependency-groups]
dev = [
    "httpx>=0.28.1",
    "pytest>=9.1.1",
]
```

## Decisiones y tradeoffs

- **`httpx` explícito en `dev`**: `TestClient` lo requiere, y aunque podría venir como transitiva de `fastapi[standard]`, declararlo explícito deja claro en el lockfile por qué está ahí.
- **Tests unitarios contra el pipeline real** (no mockeado): da mayor confianza de que el modelo entrenado realmente funciona, al costo de que los tests dependan de que exista `models/pipeline.joblib` y sean un poco más lentos que con un mock. Si el pipeline creciera mucho, mockear `predictor._pipeline` sería la alternativa a evaluar.
- **`sample_payload` compartido vía `conftest.py`** en vez de definido por archivo: evita duplicar los 11 valores de features en `test_api.py` y `test_predictor.py`.

## Correr los tests

```bash
uv run pytest -v
```

`-v` (verbose) lista cada test por nombre completo con su resultado individual, en vez de un resumen compacto de puntos/letras.

### Warnings conocidos, no accionables

Al correr los tests aparecen dos grupos de warnings que no vienen del código del proyecto:

- `StarletteDeprecationWarning` sobre `httpx`/`httpx2` en `testclient.py` — interno de Starlette/FastAPI.
- `DeprecationWarning` de `joblib/numpy_pickle.py` al cargar `pipeline.joblib` — por diferencia de versión de NumPy entre el entorno de entrenamiento y el actual.

Ninguno afecta la validez de los tests. El único warning que sí era del proyecto (`PydanticDeprecatedSince20` por usar `example=` en vez de `examples=[...]` en `Field()`, en `schemas.py`) ya se corrigió.
