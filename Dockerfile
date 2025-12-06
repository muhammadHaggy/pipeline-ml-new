# Use your current Airflow base image
FROM apache/airflow:2.9.0

# ---------------------------------------------------------
# Install OS-level dependencies needed by LightGBM
# ---------------------------------------------------------
USER root

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libgomp1 && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------
# Install Python dependencies (requirements.txt)
# ---------------------------------------------------------
USER airflow
COPY --chown=airflow:root requirements.txt /tmp/requirements.txt

RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && rm /tmp/requirements.txt

# ---------------------------------------------------------
# Copy DAGs, Plugins, Notebooks into image
# ---------------------------------------------------------
USER root
COPY dags/ /opt/airflow/dags/
COPY plugins/ /opt/airflow/plugins/
COPY notebooks/ /notebooks/

RUN mkdir -p /logs /opt/airflow/dags /opt/airflow/plugins /notebooks \
    && chown -R airflow:root /opt/airflow/dags /opt/airflow/plugins /notebooks /logs

# ---------------------------------------------------------
# Set ENV for notebook paths
# ---------------------------------------------------------
ENV NOTEBOOKS_ROOT=/notebooks \
    LOGS_ROOT=/logs

USER airflow
