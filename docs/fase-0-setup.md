# Fase 0 — Setup del Repositorio

## Objetivo

Establecer la estructura base del proyecto: control de versiones, entorno virtual reproducible, y organización de carpetas que soporte el crecimiento hacia un proyecto de producción.

## Conceptos clave

### Separación training / serving

El entrenamiento del modelo y el servicio de predicciones son procesos distintos con ciclos de vida distintos. Mezclarlos en una sola carpeta genera acoplamiento innecesario: un cambio en el training puede romper la API y viceversa.

- `training/` — scripts que se corren periódicamente para generar el modelo
- `app/` — la API que se despliega y sirve predicciones en tiempo real

### Artefactos vs código fuente

El modelo entrenado (`.pkl`, `.joblib`) es un artefacto generado, no código fuente. No va en git porque:
- Puede pesar cientos de MB
- Cambia cada vez que se reentrena
- Es binario (el diff es inútil)

En producción, los artefactos van en un registro de modelos (MLflow, S3, etc.). En este proyecto, van en `models/` (en `.gitignore`) y se regeneran corriendo `train.py`.

### uv vs pip + venv

| | pip + venv | uv |
|---|---|---|
| Velocidad | Lenta | 10-100x más rápida |
| Lockfile | `requirements.txt` (solo dependencias directas) | `uv.lock` (árbol completo, determinístico) |
| Reproducibilidad | Parcial | Total |
| `pyproject.toml` | Necesita pip-tools o Poetry | Nativo |

`uv.lock` garantiza que cualquier máquina (incluyendo CI/CD y el contenedor de Docker) instale exactamente las mismas versiones. Por eso el lockfile **sí va en git**, aunque el `.venv` no.

### Creación lazy del entorno

`uv` no crea el `.venv` al hacer `uv init`. Lo crea la primera vez que se necesita (por ejemplo, al correr `uv run python --version`). Esto es comportamiento intencional.

## Estructura creada

```
wine-quality-api/
├── app/                    # API FastAPI (lo que se despliega)
│   ├── __init__.py
│   ├── main.py             # Punto de entrada FastAPI 
│   ├── schemas.py          # Model Pydantic (request/response)
│   └── predictor.py        # Lógica de carga del modelo y predicción
├── training/               # Scripts de entrenamiento (no va en el contenedor)
│   └── train.py
├── models/                 # Artefactos generados (.gitignore, no van en git)
│   └── .gitkeep
├── tests/                  # Tests con pytest
│   ├── __init__.py
│   ├── test_api.py
│   └── test_predictor.py
├── docs/                   # Documentación de fases y decisiones
├── .github/
│   └── workflows/          # CI/CD (Fase 5)
├── pyproject.toml          # Metadata y dependencias del proyecto
├── uv.lock                 # Lockfile determinístico (sí va en git)
├── Dockerfile
├── .dockerignore
├── .gitignore
└── README.md
```

## Comandos usados

```bash
git init
uv init --name wine-quality-api --python 3.12
mkdir -p app training models tests .github/workflows docs
touch app/__init__.py app/main.py app/schemas.py app/predictor.py
touch training/train.py
touch models/.gitkeep
touch tests/__init__.py tests/test_api.py tests/test_predictor.py
```

> **Nota:** `uv init` genera un `main.py` de ejemplo en la raíz del proyecto. Como nuestro punto de entrada real está en `app/main.py`, ese archivo no se necesita y hay que eliminarlo:
>
> ```bash
> rm main.py
> ```

## GitHub setup y primer commit

### 1. Crear el repositorio en GitHub

En [github.com/new](https://github.com/new):
- **Repository name:** `wine-quality-api`
- **Visibility:** Public (es un proyecto de portafolio)
- **No** inicializar con README, .gitignore ni licencia (ya los tenemos)

### 2. Conectar el repo local y hacer el primer push

```bash
# Staging de todos los archivos iniciales
git add .

# Primer commit
git commit -m "chore: initial project structure (fase 0)"

# Conectar con el repo remoto (reemplazar <usuario> con tu GitHub username)
git remote add origin https://github.com/<usuario>/wine-quality-api.git

# Push
git push -u origin main
```

La flag `-u` en el push establece el upstream: a partir de ahí, `git push` y `git pull` sin argumentos saben a qué rama apuntar.

> **Nota sobre el mensaje de commit:** La convención `chore: ...` viene de [Conventional Commits](https://www.conventionalcommits.org/). Los prefijos más usados son `feat:` (nueva funcionalidad), `fix:` (corrección de bug), `chore:` (tareas de mantenimiento sin cambio de lógica), `docs:` (documentación). GitHub Actions y herramientas de changelog leen estos prefijos para automatizar releases.

## Verificación

```bash
git status          # .venv/ y models/ NO deben aparecer (están en .gitignore)
uv run python --version  # debe devolver Python 3.12.x
```

## Decisiones y tradeoffs

- **uv sobre pip**: elegido por velocidad y lockfile determinístico. Tradeoff: herramienta más nueva, menor documentación externa que pip.
- **`models/` en .gitignore**: los artefactos no son código. En un proyecto más maduro, irían a S3 o un registro de modelos con versionado propio.
- **`.gitkeep` en `models/`**: git no trackea carpetas vacías, solo archivos. El `.gitkeep` es un archivo vacío convencional para forzar que git registre la carpeta.
