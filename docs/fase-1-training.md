# Fase 1 — Script de Entrenamiento

## Objetivo

Crear `training/train.py`: un script que descarga el dataset Wine Quality, entrena un clasificador sklearn, evalúa su desempeño con cross-validation, y persiste los artefactos necesarios para que la API pueda servir predicciones.

## Artefactos generados

```
models/
├── pipeline.joblib   # Pipeline completo (scaler + clasificador)
└── metadata.json     # accuracy, feature_names, hiperparámetros, fecha
```

Solo `pipeline.joblib` es necesario para la API. `metadata.json` alimenta el endpoint `/model-info` sin necesidad de cargar ni re-entrenar el modelo.

## Conceptos clave

### Data leakage

El error más común en ML es "filtrar" información del set de validación al entrenamiento. Con un scaler manual esto ocurre si haces `scaler.fit(X_all)` antes de dividir, o si durante cross-validation el scaler ve los folds de validación.

La regla: **el scaler aprende μ y σ únicamente del set de entrenamiento** y aplica esos mismos valores al test. Nunca al revés.

```python
scaler.fit_transform(X_train)  # aprende μ, σ de train — y transforma train
scaler.transform(X_test)       # aplica el MISMO μ, σ aprendido de train
```

### sklearn Pipeline

`Pipeline` encadena pasos de transformación y un estimador final en un único objeto. Al llamar `pipeline.predict(X)`, internamente ejecuta `scaler.transform(X)` y luego `clf.predict(resultado)` — el escalado es invisible para el caller.

Ventajas sobre scaler + modelo separados:
- **Un solo artefacto** para serializar y cargar en la API
- **CV sin leakage garantizado**: en cada fold, el scaler se reajusta solo sobre los datos de train de ese fold
- **Menos superficie de error**: el endpoint no necesita recordar escalar antes de predecir

```python
pipeline = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", RandomForestClassifier(n_estimators=100, random_state=42)),
])
```

### Cross-validation vs un solo split

Un único `train_test_split` puede dar una estimación optimista o pesimista por azar del split. Cross-validation con `cv=5` divide `X_train` en 5 folds, entrena en 4 y valida en 1, rotando los roles. El resultado es un estimado más robusto del desempeño real.

```
CV accuracy: 0.668 ± 0.021   # ±2σ ≈ intervalo de confianza del 95%
```

### `cv=5` vs `KFold(shuffle=True)`

Pasar un entero activa `StratifiedKFold` automáticamente en clasificación: cada fold mantiene la misma proporción de clases que el dataset original. Esto es importante con datasets desbalanceados (pocas muestras de calidad 3 y 8).

`KFold` con `shuffle=True` aleatoriza el orden pero **no** garantiza proporciones de clase por fold. Para clasificación, `cv=5` es la opción correcta por defecto.

### Orden de imports — PEP 8

PEP 8 define tres grupos separados por una línea en blanco:

```python
# stdlib — módulos que vienen con Python
import json
from datetime import datetime

# third-party — instalados con pip/uv
import pandas as pd
from sklearn.pipeline import Pipeline

# local — módulos propios del proyecto
from app.schemas import WineFeatures
```

La herramienta `isort` aplica esta convención automáticamente.

### Serialización JSON

`json.dump(obj, f)` escribe a un file object abierto. `json.dumps(obj)` devuelve un string. Los objetos `datetime` no son serializables por JSON — deben convertirse con `.isoformat()` primero.

```python
# Correcto
with open(path, "w") as f:
    json.dump({"trained_at": datetime.now().isoformat()}, f, indent=2)
```

## Decisiones y tradeoffs

- **RandomForestClassifier**: funciona bien en datos tabulares sin tuning extenso, soporta multiclase nativamente, y expone `feature_importances_` para el endpoint `/model-info`. Tradeoff: más lento de entrenar e inferir que modelos lineales.
- **Pipeline sobre artefactos separados**: simplifica el serving — la API carga un solo objeto y llama `predict()`. Tradeoff: para inspeccionar el scaler hay que acceder vía `pipeline.named_steps["scaler"]`.
- **`model.get_params()` sobre `model.n_estimators`**: agnóstico al tipo de estimador. Si se cambia el modelo, el metadata sigue siendo válido.
- **`zero_division=0` en `classification_report`**: el dataset tiene clases muy subrepresentadas (calidad 3: 10 muestras, calidad 8: 18 muestras). El modelo no predice esas clases → precision indefinida. `zero_division=0` la reporta como 0 sin lanzar un warning.

## Desbalance de clases

El dataset tiene una distribución muy sesgada hacia calidades 5 y 6. Esto explica el accuracy de ~66% y los f1-score de 0.00 en clases extremas. Posibles mejoras futuras: `class_weight="balanced"`, oversampling con SMOTE, o reformular como clasificación binaria (bueno/malo).

## Correr el script

```bash
uv run python training/train.py
```

Esto descarga el dataset, entrena, imprime CV scores y el classification report, y escribe los artefactos en `models/`.