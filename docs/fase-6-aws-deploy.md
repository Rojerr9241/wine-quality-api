# Fase 6 — Despliegue en AWS

> Doc en construcción — se va completando a medida que avanza la fase.

## Objetivo

Desplegar la API en AWS con el menor costo posible, priorizando la experiencia práctica de MLOps para portafolio por sobre la robustez de producción. Es un proyecto personal con tráfico esporádico (no una app con usuarios constantes), así que el criterio de decisión es costo mínimo primero, simplicidad después.

## Opciones evaluadas

### AWS App Runner

Servicio "fully managed": tomás una imagen de contenedor (puede venir de GHCR o ECR) y la ponés a correr detrás de una URL pública con HTTPS, autoscaling y health checks resueltos por AWS. Configurás CPU/memoria, puerto y variables de entorno, y listo.

Problema para este proyecto: **no hace scale-to-zero real**. Siempre mantiene al menos 1 instancia "provisioned", incluso sin tráfico. Para una config mínima (1 vCPU / 2GB) corriendo idle casi todo el tiempo, el costo típico ronda **$4-8 USD/mes**. Tiene un botón de "pause" para bajar a $0, pero es manual.

### ECS Fargate

Una capa más abajo que App Runner: hay que definir explícitamente un **Cluster**, una **Task Definition** (imagen, CPU/memoria, puertos), un **Service**, y normalmente un **Load Balancer (ALB)** delante para exponerlo. Más control (VPC, reglas de red, integraciones), pero más piezas que entender y mantener. Mismo problema de fondo que App Runner: no escala a cero sin intervención manual.

Para un solo servicio stateless como esta API, es complejidad que no se traduce en beneficio — ECS Fargate brilla orquestando múltiples servicios, no acá.

### AWS Lambda + contenedor (elegida)

Lambda es *pay-per-request* real: si nadie llama a la API, el costo es $0. Soporta imágenes de contenedor, así que reutiliza la misma imagen Docker de la Fase 4 sin tirar ese trabajo.

Tradeoff aceptado: **cold starts** (la primera request tras un rato sin tráfico tarda más mientras Lambda "levanta" el contenedor). Para un portafolio visitado esporádicamente, es un precio razonable a cambio de $0 de costo base.

## Costos: los dos tipos de free tier

Fuente de una confusión real durante la fase — vale la pena dejarlo explícito:

| Recurso | Tipo de free tier | ¿Cuándo se acaba? |
|---|---|---|
| **Lambda** (requests + tiempo de ejecución) | "Always free" — permanente | Nunca, aplica para siempre a cualquier cuenta AWS. 1M requests/mes + 400,000 GB-segundos/mes |
| **Lambda Function URL** | Sin costo, siempre | Nunca |
| **ECR** (donde vive la imagen del contenedor) | Free tier de **12 meses** — 500 MB gratis | Se acaba al año de creada la cuenta AWS. Después: $0.10/GB/mes |

Para el tráfico esperado de un proyecto de portafolio, el uso de Lambda (requests + compute) cae 100% dentro del free tier permanente → **$0 garantizado**. El único costo posible es el storage de la imagen en ECR si la cuenta ya pasó los 12 meses o la imagen pesa más de 500MB — y aun así son centavos al mes ($0.03-0.08 aprox.), no algo ligado al uso.

Para garantizar $0 absoluto: probar la Lambda y, si no se mantiene, borrar tanto la función Lambda **como** la imagen en ECR (borrar solo la función no alcanza — la imagen se queda guardada y esa es la que puede generar el cobro).

## Arquitectura: Lambda + Mangum + Function URL

Tres piezas que trabajan juntas, no alternativas entre sí:

```
Internet (tu navegador)
      │
      ▼
Lambda Function URL   ← la "puerta": una URL pública que Lambda da gratis
      │
      ▼
AWS Lambda             ← el servicio que ejecuta el código (esto es lo único que se cobra, por request+tiempo)
      │
      ▼
Mangum                 ← vive DENTRO del contenedor, traduce el evento de Lambda al formato que FastAPI entiende (ASGI)
      │
      ▼
Tu app FastAPI          ← el código de siempre (endpoints, Pydantic, modelo sklearn), sin cambios
```

## Analogías que ayudaron

- **App Runner / ECS Fargate sin scale-to-zero = dejar las luces de la oficina prendidas 24/7** aunque no haya nadie adentro, salvo que alguien se acuerde de apagarlas (pause manual).
- **Lambda = pagar luz solo cuando alguien enciende el interruptor**: si nadie entra al edificio, no se gasta nada.
- **Lambda como edificio de oficinas**:
  - **Lambda Function URL** = la dirección/puerta de entrada del edificio (gratis, cualquiera toca el timbre).
  - **AWS Lambda** = el edificio en sí, que "enciende las luces" cuando alguien entra y cobra por el tiempo que estuvieron encendidas.
  - **Mangum** = el recepcionista dentro del edificio que traduce lo que dice quien entra (formato Lambda) al idioma que entiende la oficina (formato que espera FastAPI).
  - **FastAPI** = la oficina en sí, sin cambios.

## Decisiones y tradeoffs

- **Lambda sobre App Runner/ECS Fargate**: prioridad explícita en costo mínimo para un proyecto de portafolio con tráfico esporádico. Se acepta cold start a cambio de $0 de costo base garantizado.
- **Lambda Function URL sobre API Gateway**: evita el único costo recurrente real de esta arquitectura (API Gateway cobra ~$1-3.5 por millón de requests; Function URL no cobra nada). No se pierden features necesarias para este caso (auth avanzado, throttling, dominios custom no hacen falta para una demo de portafolio).
