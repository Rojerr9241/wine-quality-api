# Fase 2 — FastAPI App

## Objetivo

Construir la API que sirve predicciones del modelo entrenado en la fase anterior. Tres archivos con responsabilidades separadas: schemas de validación, lógica de modelo, y definición de endpoints.

## Estructura

```
app/
├── __init__.py
├── schemas.py    # Contratos de datos (Pydantic)
├── predictor.py  # Carga del modelo y lógica de predicción
└── main.py       # Instancia FastAPI y endpoints
```

### Por qué separar en tres archivos

Si todo estuviera en `main.py`, un cambio en el modelo obligaría a tocar el mismo archivo que define las rutas. La separación permite:
- Cambiar el modelo (sklearn → PyTorch) tocando solo `predictor.py`
- Cambiar el contrato de datos tocando solo `schemas.py`
- Los endpoints en `main.py` no saben cómo funciona sklearn — solo delegan

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Confirma que el servidor responde. Lo usan load balancers y health checks de Docker/AWS. |
| POST | `/predict` | Recibe las 11 features del vino, retorna calidad predicha y probabilidad. |
| GET | `/model-info` | Retorna metadata del modelo: accuracy, features, hiperparámetros, fecha de entrenamiento. |

### Por qué POST para `/predict`

GET solo acepta query params, lo que es incómodo con 11 campos y limita el tamaño del payload. POST con body JSON es la convención en APIs de ML.

## Conceptos clave

### Pydantic y validación automática

FastAPI usa Pydantic para validar el request body antes de que llegue al endpoint. Si el cliente manda `"alcohol": "mucho"` o falta un campo requerido, FastAPI rechaza la request con un 422 y un mensaje de error descriptivo — sin que el endpoint lo vea.

`Field()` cumple dos propósitos:
- **Restricciones de validación**: `ge=0, le=14` para pH, `ge=0, le=100` para alcohol
- **Metadata para `/docs`**: `description` y `example` aparecen en la UI interactiva de Swagger

Los response schemas (`PredictionResponse`, `ModelInfoResponse`) son menos críticos para validación porque los construye el propio código, no un usuario externo.

### `response_model`

```python
@app.get("/model-info", response_model=ModelInfoResponse)
def model_info():
    ...
```

Le dice a FastAPI qué schema usar para serializar y validar la respuesta. Si la función retorna campos extra o con tipos incorrectos, FastAPI los filtra o lanza un error antes de enviar al cliente.

### Imports relativos

Dentro de un paquete Python, los módulos se importan con punto `.`:

```python
from . import predictor          # importa el módulo completo
from .schemas import WineFeatures  # importa nombres específicos
```

El punto significa "del paquete actual (`app/`)". Sin el punto, Python busca el nombre como un paquete externo instalado.

En `main.py` se usa `from . import predictor` (módulo completo) en lugar de `from .predictor import predict` porque existe una función local llamada `predict` — importar el nombre directamente la pisaría.

### Carga del modelo al inicio del módulo

```python
_pipeline = joblib.load(MODELS_DIR / "pipeline.joblib")
_metadata = json.loads((MODELS_DIR / "metadata.json").read_text())
```

Estas líneas se ejecutan una sola vez cuando Python importa `predictor.py` — al arrancar la API. Si estuvieran dentro de `predict()`, cada request pagaría el costo de cargar el modelo desde disco (decenas de ms). El prefijo `_` indica que son variables internas del módulo, no parte de la API pública.

### Mapeo snake_case → nombres del dataset

`WineFeatures` usa snake_case (`fixed_acidity`, `ph`) por convención Python. El pipeline fue entrenado con los nombres originales del dataset (`"fixed acidity"`, `"pH"`). La reconciliación ocurre en `predictor.py`:

```python
values = list(features.model_dump().values())
input_df = pd.DataFrame([values], columns=FEATURE_NAMES)
```

`model_dump()` retorna un dict en el orden de definición de los campos. `FEATURE_NAMES` está en el mismo orden con los nombres correctos. Los valores se asignan columna por columna.

### `predict_proba` y la probabilidad reportada

`predict_proba` retorna la probabilidad de cada clase. Para una muestra con 6 clases posibles:

```
array([[0.02, 0.05, 0.15, 0.52, 0.22, 0.04]])
#       cl3   cl4   cl5   cl6   cl7   cl8
```

`[0].max()` extrae la fila de la única muestra y toma el valor máximo — la confianza del modelo en la clase predicha. El `[0]` es importante: `.max()` sobre el array 2D completo devolvería el max global, lo que sería incorrecto con múltiples muestras.

### `fastapi[standard]`

`fastapi` base no incluye la CLI (`fastapi dev`). El extra `[standard]` agrega las herramientas de desarrollo. En producción el servidor se levanta directamente con uvicorn:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

`--host 0.0.0.0` es necesario en contenedores: sin él, el servidor solo escucha dentro del contenedor y no es accesible desde afuera.

## Probar la API

Con la API corriendo (`uv run fastapi dev app/main.py`), la UI interactiva está en:

```
http://localhost:8000/docs
```

Ejemplo de request para `/predict`:

```json
{
  "fixed_acidity": 7.4,
  "volatile_acidity": 0.7,
  "citric_acid": 0.0,
  "residual_sugar": 1.9,
  "chlorides": 0.076,
  "free_sulfur_dioxide": 11.0,
  "total_sulfur_dioxide": 34.0,
  "density": 0.9978,
  "ph": 3.51,
  "sulphates": 0.56,
  "alcohol": 9.4
}
```

Respuesta esperada:

```json
{
  "quality": 5,
  "probability": 0.96
}
```

## Decisiones y tradeoffs

- **`fastapi[standard]` sobre `fastapi` + `uvicorn` separados**: el extra agrupa las dependencias de desarrollo necesarias. En el Dockerfile se usará uvicorn directamente.
- **`ModelInfoResponse(**_metadata)`**: el `**` desempaca el dict como kwargs para Pydantic. Equivale a pasar cada campo explícitamente pero sin hardcodear los nombres.
- **`get_params()` en metadata**: retorna todos los hiperparámetros del estimador, agnóstico al tipo de modelo. Si se cambia RandomForest por otro estimador, el metadata sigue siendo válido.