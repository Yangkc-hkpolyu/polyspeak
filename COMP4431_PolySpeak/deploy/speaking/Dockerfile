FROM python:3.11-slim-bookworm

ARG TORCH_VERSION=2.6.0
ARG TORCH_INDEX_URL=https://download.pytorch.org/whl/cu126
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1 \
    LT_MEL_USE_GPU=0 \
    TEMP=/app/speaking-runtime/temp TMP=/app/speaking-runtime/temp \
    NUMBA_CACHE_DIR=/app/speaking-runtime/numba-cache \
    MPLCONFIGDIR=/app/speaking-runtime/matplotlib \
    TORCH_HOME=/app/speaking-runtime/torch-cache \
    CUDA_CACHE_PATH=/app/speaking-runtime/cuda-cache
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates libgl1 libglib2.0-0 libgomp1 libasound2 libssl3 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-speaking.txt ./
RUN python -m pip install --no-cache-dir "torch==${TORCH_VERSION}" --index-url "${TORCH_INDEX_URL}" \
    && python -m pip install --no-cache-dir -r requirements-speaking.txt
COPY backend/speaking/ backend/speaking/
COPY frontend/dist-speaking/ frontend/dist-speaking/
COPY deploy/speaking/start.sh /usr/local/bin/start-speaking-cloud
RUN useradd --create-home --uid 10001 speaking \
    && mkdir -p speaking-runtime/temp speaking-models speaking-resources/official \
    && chown -R speaking:speaking /app \
    && chmod 755 /usr/local/bin/start-speaking-cloud
USER speaking
EXPOSE 8008
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8008/api/speaking/status',timeout=3)"
ENTRYPOINT ["/usr/local/bin/start-speaking-cloud"]
