# ---- Builder stage: resolves and installs dependencies with uv ----
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# UV_COMPILE_BYTECODE: precompile .pyc at build time for faster startup.
# UV_LINK_MODE=copy: uv's default hardlinks don't survive being copied
# to another stage's filesystem, so force real file copies instead.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Install dependencies before copying app code, so Docker caches this
# (expensive) layer and skips it when only the code changes.
# --no-install-project: app/ doesn't exist yet, nothing to install.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Now copy the code and finish the sync — this installs the local
# project itself. Fast: the heavy dependencies are already on disk
# from the previous layer, only the project package gets added.
COPY app/ ./app/
RUN uv sync --frozen --no-dev

# Model artifact trained locally via training/train.py. Not tracked in
# git (see .gitignore), but present on disk — .dockerignore is what
# controls whether COPY can see it, independent of git.
COPY models/ ./models/


# ---- Runtime stage: lean image that actually serves the API ----
FROM python:3.12-slim-bookworm AS runtime

# Non-root user: if the app process is ever compromised, it doesn't
# run with root privileges inside the container.
RUN groupadd --system app && useradd --system --gid app app

WORKDIR /app

# Pull only the already-built venv and code from the builder — none of
# uv itself, its cache, or build tools end up in this final image.
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/app ./app
COPY --from=builder /app/models ./models

# Prepend the venv's bin/ to PATH so `uvicorn` resolves to the venv's
# copy (with all dependencies installed) without needing `source activate`.
ENV PATH="/app/.venv/bin:$PATH"

USER app
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]