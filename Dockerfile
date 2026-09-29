# Hugging Face Spaces (Docker SDK): runs as uid 1000 and serves on port 7860.
FROM python:3.13-slim

RUN pip install --no-cache-dir uv && useradd -m -u 1000 user
USER user
ENV HOME=/home/user PYTHONUNBUFFERED=1
WORKDIR /home/user/app

COPY --chown=user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=user . .
# Downloads the embedding model and builds the search index into the image.
RUN .venv/bin/python -m app.search

EXPOSE 7860
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--no-access-log"]
