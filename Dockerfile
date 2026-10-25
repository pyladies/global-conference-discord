FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy

WORKDIR /app

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

ENV PATH="/app/.venv/bin:$PATH"

# prod-config.toml, livestreams.toml and any other runtime .toml (test-*.toml are
# excluded by .dockerignore)
COPY *.toml ./

# Cabotage's release image layers its own entrypoint over this one and runs
# the Procfile command as `nobody`, with only /tmp writable; every runtime
# state path in prod-config.toml therefore points at /tmp. USER and CMD here
# only matter for running the image locally, where they mirror that environment.
USER nobody
CMD ["run-bot", "--config-file", "prod-config.toml"]
