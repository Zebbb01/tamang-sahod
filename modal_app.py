"""Deploy the FastAPI app to Modal (free Starter credits, no card):

    uv run modal deploy modal_app.py

The image installs the dependencies, copies the code and source data, then
downloads the embedding model and builds the search index once, at build time.
The app scales to zero; a visit after a quiet spell waits for a cold start.
"""

import modal

image = (
    modal.Image.debian_slim(python_version="3.13")
    .pip_install_from_pyproject("pyproject.toml")
    .add_local_dir("app", "/root/app", copy=True)
    .add_local_dir("data", "/root/data", copy=True, ignore=["index", "models"])
    .run_commands("cd /root && python -m app.search")
)

app = modal.App("tamang-sahod", image=image)


# About 1.1 GB in use once the model is loaded, so 2 GiB. Containers stay warm for
# 5 minutes after the last request, then scale to zero.
@app.function(memory=2048, cpu=1.0, scaledown_window=300)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from app.main import app as fastapi_app

    return fastapi_app
