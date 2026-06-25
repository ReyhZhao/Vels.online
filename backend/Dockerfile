FROM python:3.12-slim

WORKDIR /app

# Native libraries required by WeasyPrint (incident report PDF rendering, ADR-0029).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        libharfbuzz0b \
        libffi8 \
        libjpeg62-turbo \
        libcairo2 \
        fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# The uvicorn worker class handles async views (streaming endpoint) while sync DRF
# views continue to run in Django's threadpool unchanged. A long streaming response
# on a uvicorn worker never triggers gunicorn's sync --timeout kill because the worker
# heartbeats on the event loop while the sync research loop runs in a thread.
CMD ["gunicorn", "config.asgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--worker-class", "uvicorn.workers.UvicornWorker", "--timeout", "240"]
