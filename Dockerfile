FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"
WORKDIR /app
COPY --from=ghcr.io/astral-sh/uv:0.10.8 /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
COPY packages/ packages/
COPY src/ src/
COPY config/teams.json config/
COPY alembic.ini ./
RUN uv sync --frozen --no-dev --no-editable \
    && mkdir -p /app/out \
    && chgrp -R 0 /app \
    && chmod -R g=u /app
USER 1001
EXPOSE 8000
CMD ["alerts-bi-runs", "serve"]
