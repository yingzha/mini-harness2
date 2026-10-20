# mini-Harness²: one container for every lesson, test and demo.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/

# The venv lives outside /app so the bind-mounted source (and any host .venv)
# never shadows it. Use the image's Python; never download another.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home app \
 && mkdir -p /opt/venv /app \
 && chown app /opt/venv /app
USER app
WORKDIR /app

# Dependencies first, so editing lesson code doesn't invalidate this layer.
COPY --chown=app pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

COPY --chown=app . .

CMD ["uv", "run", "--frozen", "pytest", "-q"]
