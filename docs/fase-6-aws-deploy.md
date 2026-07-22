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

## De GHCR a ECR

Lambda con imagen de contenedor **no acepta GHCR** como origen — solo ECR (o Docker Hub con restricciones). Como la Fase 5 ya dejó el pipeline publicando en GHCR, hubo que reemplazar ese job por uno que publique en ECR. El conocimiento de cómo se hizo con GHCR no se pierde: queda documentado en `docs/fase-5-github-actions.md` y en el git history — no hace falta mantener ambos publicando en paralelo.

## Autenticación: OIDC + IAM Role, no access keys

Para que GitHub Actions pueda hacer push a ECR, la opción "fácil" sería crear un usuario IAM con access keys y guardarlas como secret de GitHub. Se descartó a propósito: son credenciales de **larga duración** — si se filtran, quedan válidas hasta que alguien las rote manualmente. El estándar de industria actual es **OIDC (OpenID Connect)**: GitHub Actions le presenta a AWS un token firmado y de corta duración (minutos) en cada ejecución, y AWS lo intercambia por credenciales temporales — sin ningún secreto de larga duración guardado en ningún lado.

Dos piezas necesarias en AWS, con responsabilidades distintas:

- **OIDC provider**: registra a GitHub como emisor de identidad confiable ("recepción del edificio que acepta visitantes con credencial de GitHub").
- **IAM Role** (`github-actions-ecr-push`): la identidad temporal que GitHub Actions puede pedir prestada. Tiene dos documentos separados:
  - **Trust policy** — quién puede asumir el role. Scoped con dos condiciones sobre el token OIDC: `aud` (audience, tiene que ser `sts.amazonaws.com`) y `sub` (subject, tiene que ser exactamente `repo:Rojerr9241/wine-quality-api:ref:refs/heads/main`). Esto último es clave: ni un fork, ni un PR desde otra rama, ni otro repo pueden asumir este role — solo pushes a `main` de este repo puntual.
  - **Permissions policy** — qué puede hacer una vez asumido el role. Scoped al ARN exacto del repo ECR `wine-quality-api` (least privilege: nada de `Resource: "*"` salvo en las dos acciones que IAM no permite scopear por resource, `ecr:GetAuthorizationToken` y `iam:ListOpenIDConnectProviders`).

Mismo principio se aplicó al usuario `aws-cli-developer` (el que corre los comandos de setup manual): en vez de darle permisos amplios "por las dudas", recibió dos policies inline nuevas, cada una scoped a los ARNs exactos de los recursos que tenía que crear (el repo ECR, el OIDC provider, el role). Los ARNs de recursos que todavía no existen se pueden anticipar porque siguen un patrón fijo (`arn:aws:iam::<account-id>:role/<nombre-elegido>`) — el "número de casa" lo elegimos nosotros al planificar, no lo genera AWS al azar.

## Setup ejecutado (cheatsheet de comandos)

Cuenta AWS `897081433974`, región `us-east-1`, repo GitHub `Rojerr9241/wine-quality-api`.

**1. Repo ECR**

```bash
aws ecr create-repository \
  --repository-name wine-quality-api \
  --region us-east-1 \
  --image-scanning-configuration scanOnPush=true \
  --image-tag-mutability MUTABLE
```

`MUTABLE` porque el CI resube el tag `latest` en cada push (con `IMMUTABLE` el segundo push al mismo tag fallaría). `scanOnPush` es gratis y no bloquea ni alarga el push — corre async después.

**2. OIDC provider**

```bash
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

Ojo al copiar el thumbprint: son 40 caracteres, fácil perder uno al transcribir.

**3. IAM Role con trust policy scoped**

```bash
cat > /tmp/trust-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::897081433974:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:Rojerr9241/wine-quality-api:ref:refs/heads/main"
        }
      }
    }
  ]
}
EOF

aws iam create-role \
  --role-name github-actions-ecr-push \
  --assume-role-policy-document file:///tmp/trust-policy.json \
  --description "Allows GitHub Actions to push wine-quality-api images to ECR"
```

**4. Permissions policy del role**

```bash
cat > /tmp/ecr-push-policy.json << 'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRAuth",
      "Effect": "Allow",
      "Action": "ecr:GetAuthorizationToken",
      "Resource": "*"
    },
    {
      "Sid": "ECRPushPull",
      "Effect": "Allow",
      "Action": [
        "ecr:BatchCheckLayerAvailability",
        "ecr:PutImage",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload"
      ],
      "Resource": "arn:aws:ecr:us-east-1:897081433974:repository/wine-quality-api"
    }
  ]
}
EOF

aws iam put-role-policy \
  --role-name github-actions-ecr-push \
  --policy-name ecr-push-pull \
  --policy-document file:///tmp/ecr-push-policy.json
```

**5. Job `build-push` migrado a ECR/OIDC**

El job `build-push` de `.github/workflows/ci.yml` (antes autenticaba contra GHCR con `docker/login-action` + `secrets.GITHUB_TOKEN`) quedó así:

```yaml
    permissions:
      contents: read
      id-token: write
    steps:
      - uses: actions/checkout@v4

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::897081433974:role/github-actions-ecr-push
          aws-region: us-east-1

      - name: Log in to ECR
        uses: aws-actions/amazon-ecr-login@v2

      - name: Build and push image
        uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            897081433974.dkr.ecr.us-east-1.amazonaws.com/wine-quality-api:latest
            897081433974.dkr.ecr.us-east-1.amazonaws.com/wine-quality-api:${{ github.sha }}
```

Puntos clave:

- `packages: write` (permiso que necesitaba GHCR) se reemplaza por `id-token: write` — el permiso que le permite al job **emitir** un token OIDC. Solo acepta `write` o `none`; no existe `read`, porque pedir el token es generar una credencial nueva y firmada para esa ejecución puntual, no leer algo que ya existía.
- La autenticación pasa a ser un flujo de **dos pasos**: primero `configure-aws-credentials` (intercambia el token OIDC por credenciales temporales de AWS vía el role `github-actions-ecr-push`), después `amazon-ecr-login` (usa esas credenciales para loguear el Docker daemon contra ECR). Es el mismo patrón de siempre para cualquier acción de `aws-actions` con OIDC: obtener identidad → usarla contra el servicio puntual.
- El paso "Set lowercase image name" desaparece — existía porque GHCR arma el nombre de imagen a partir de `github.repository` (`Rojerr9241/...`, con mayúscula) y Docker exige minúsculas. El repo ECR (`wine-quality-api`) es un nombre fijo elegido a mano, ya en minúsculas, así que el workaround ya no aplica.
- Los tags pasan de `ghcr.io/${{ env.IMAGE_NAME }}` a la URI completa de ECR (`897081433974.dkr.ecr.us-east-1.amazonaws.com/wine-quality-api`), hardcodeada porque —a diferencia de GHCR— el registry de ECR no se deriva de ningún dato de contexto de GitHub; incluye el account ID y la región, fijos para esta cuenta.

La versión anterior (GHCR completa) queda conservada como referencia en `docs/examples/ci-ghcr.yml`.

**Pendiente**: adaptar el Dockerfile a una base image compatible con Lambda (`python:3.12-slim-bookworm` no sirve tal cual — Lambda con contenedor necesita una imagen base que implemente el Runtime API, típicamente `public.ecr.aws/lambda/python` o la técnica de runtime interface client sobre una imagen genérica).
