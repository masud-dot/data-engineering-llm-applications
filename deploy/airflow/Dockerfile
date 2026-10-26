FROM apache/airflow:3.3.2-python3.12
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr procps \
 && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /opt/venv /opt/llmdata/models \
 && chown -R airflow:0 /opt/venv /opt/llmdata \
 && chmod -R g+rwX /opt/llmdata
USER airflow
COPY --chown=airflow:0 pyproject.toml uv.lock README.md /opt/llmdata/
RUN pip install --no-cache-dir uv==0.11.32 \
 && cd /opt/llmdata \
 && UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --no-dev --extra local --no-install-project \
    --no-cache --python 3.12
