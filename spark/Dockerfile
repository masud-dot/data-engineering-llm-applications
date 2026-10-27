# region: spark-image
# The Airflow image, with Java and PySpark added for the spark profile.
ARG BASE=llmdata-airflow:local
FROM ${BASE}
USER root
RUN apt-get update \
 && apt-get install -y --no-install-recommends openjdk-17-jre-headless \
 && rm -rf /var/lib/apt/lists/*
USER airflow
RUN cd /opt/llmdata \
 && UV_PROJECT_ENVIRONMENT=/opt/venv UV_PYTHON_DOWNLOADS=never \
    uv sync --frozen --no-dev --extra local --extra spark \
    --no-install-project --no-cache --python 3.12
# endregion
