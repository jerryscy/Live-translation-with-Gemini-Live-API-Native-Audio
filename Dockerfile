# ---------------------------------------------------------------------------
# Container image for Cloud Run (and local docker runs).
# Python 3.11 satisfies google-genai (>=3.10). Single lightweight process.
#
# Build & run locally:
#   docker build -t live-translation .
#   docker run --rm -p 8080:8080 \
#     -e GOOGLE_CLOUD_PROJECT=your-project -e GOOGLE_CLOUD_LOCATION=us-central1 \
#     -v $HOME/.config/gcloud:/root/.config/gcloud:ro \
#     live-translation
# ---------------------------------------------------------------------------
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8080 \
    HOST=0.0.0.0

WORKDIR /app

COPY requirements.txt ./
RUN pip install --index-url https://pypi.org/simple -r requirements.txt

COPY main.py liveapiworker.py languages.py ./
COPY static ./static

EXPOSE 8080

# Bind 0.0.0.0:$PORT so Cloud Run can route to it. `sh -c` expands $PORT.
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT}"]
