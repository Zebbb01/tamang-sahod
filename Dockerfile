# Google Cloud Run: serves on $PORT (8080 by default). Needs about 1.1 GB of memory
# once the embedding model is loaded, so give the service 2 GiB.
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

EXPOSE 8080
CMD ["sh", "-c", "exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
