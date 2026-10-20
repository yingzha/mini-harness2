# mini-Harness²: one image for every lesson, test and demo, and for the sandbox
# containers that model-written code runs in (so it holds no source and no secrets).
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /uvx /bin/
# The client only: our code starts sandbox containers through the host's Docker.
COPY --from=docker:29.8.1-cli /usr/local/bin/docker /usr/local/bin/docker

# The venv lives outside /app so the bind-mounted source (and any host .venv)
# never shadows it. Use the image's Python; never download another.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# /scratch becomes the scratch volume (compose.yaml); creating it here makes the
# volume start out owned by app.
RUN useradd --create-home app \
 && mkdir -p /opt/venv /app /scratch \
 && chown app /opt/venv /app /scratch
USER app
WORKDIR /app

# Only what installing the dependencies needs. The source is mounted at run time,
# never baked in: sandboxes run this image and must not find it here.
COPY --chown=app pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-install-project

CMD ["uv", "run", "--frozen", "pytest", "-q"]
