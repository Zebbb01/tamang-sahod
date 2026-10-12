"""Deploy the FastAPI app to Modal:

    uv run modal token new                 # once: approve in the browser
    uv run modal deploy modal_app.py

The image installs the locked dependencies, copies the code and source data, then
downloads the embedding model and builds the search index once, at build time.

Sized for the Starter plan without a card ($1 of compute a month): half a CPU, and
containers scale to zero two minutes after the last request. A visit after a quiet
spell waits for a cold start while the model loads.
"""

import modal

image = (
    modal.Image.debian_slim(python_version="3.13")
    .uv_sync()
    .add_local_dir("app", "/root/app", copy=True)
    .add_local_dir("data", "/root/data", copy=True, ignore=["index", "models"])
    .run_commands("cd /root && python -m app.search")
)

app = modal.App("tamang-sahod", image=image)


# About 1.1 GB in use once the model is loaded; memory is billed on actual use.
@app.function(cpu=0.5, memory=1024, scaledown_window=120, timeout=60)
@modal.concurrent(max_inputs=20)
@modal.asgi_app()
def web():
    from app.main import app as fastapi_app

    return fastapi_app
