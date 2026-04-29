# ── Stage 1 : build du venv ──────────────────────────────────────────────────
FROM python:3.12-slim-bookworm AS builder

WORKDIR /home/app

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
        libpq-dev gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN python -m venv /home/app/venv

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    /home/app/venv/bin/pip install --upgrade pip && \
    /home/app/venv/bin/pip install -r requirements.txt

# ── Stage 2 : image finale avec NGINX Unit ───────────────────────────────────
FROM unit:python3.12

WORKDIR /home/app/application_api

# Dépendances système pour psycopg2 et Pillow
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt,sharing=locked \
    apt-get update -y && \
    apt-get install -y --no-install-recommends \
        libpq5 libjpeg62-turbo libwebp7 && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /home/app/venv /home/app/venv

ENV PATH="/home/app/venv/bin:$PATH" \
    DJANGO_SETTINGS_MODULE="config.settings_prod" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY --chown=unit:unit . .

RUN chmod +x docker_entrypoint.sh scheduler_entrypoint.sh

EXPOSE 80

ENTRYPOINT ["/home/app/application_api/docker_entrypoint.sh"]
CMD ["unitd", "--no-daemon", "--control", "unix:/var/run/control.unit.sock"]
