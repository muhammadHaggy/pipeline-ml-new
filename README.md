# Data Engineering Stack

This stack provisions MinIO (object storage), OpenMaxIO (custom UI built from source), and an Apache Airflow deployment backed by Postgres. Everything runs on the `data-eng-network` bridge.

## Contents

- `Dockerfile.openmaxio`: multi-stage build that compiles the OpenMaxIO console with embedded frontend assets at version `v1.7.6`.
- `docker-compose.yml`: orchestrates MinIO, the custom OpenMaxIO console, Postgres, and the Airflow services (init, scheduler, webserver).

## How to Run

1. **Prepare directories** (used by Airflow volume mounts):
   ```bash
   mkdir -p ./dags ./logs ./plugins
   ```
2. **Build and start everything**:
   ```bash
   docker-compose up -d --build
   ```

## Access Credentials

| Service        | URL                      | Login | Password     |
| :------------- | :----------------------- | :---- | :----------- |
| Airflow UI     | http://localhost:8080    | admin | admin        |
| OpenMaxIO UI   | http://localhost:9090    | admin | password123  |
| MinIO API      | http://localhost:9000    | admin | password123  |

The OpenMaxIO container waits for the MinIO healthcheck before starting. Airflow initialization is handled by the `airflow-init` one-shot job that creates the metadata DB and admin account. Once the stack is up, you can add DAGs inside `./dags` and view task logs under `./logs`.

## Airflow ↔ MinIO Integration

### Python Requirements

Custom DAGs that talk to MinIO rely on `apache-airflow-providers-amazon` (for `S3Hook`) and the native `minio` SDK. These packages are listed in `requirements.txt` and mounted into each Airflow container at `/opt/airflow/requirements.txt`. The compose file runs `pip install --no-cache-dir -r /opt/airflow/requirements.txt` inside the `airflow-init`, `airflow-scheduler`, and `airflow-webserver` services during startup, so no manual install is needed.

### Create the Airflow Connection

1. Visit `http://localhost:8080` and log in as `admin/admin`.
2. Navigate to **Admin → Connections** and create a new connection with:
   - **Connection Id:** `minio_s3_conn`
   - **Connection Type:** `Amazon Web Services`
   - **AWS Access Key ID:** `admin`
   - **AWS Secret Access Key:** `password123`
   - **Extra:** `{"endpoint_url": "http://minio:9000"}`

This tells Airflow to route S3 traffic to the in-network `minio` service instead of AWS.

### Remote Logging (Optional but Recommended)

1. Use the OpenMaxIO UI (`http://localhost:9090`) to create a bucket named `airflow-logs`.
2. The compose file already injects the following variables into the scheduler and webserver to push logs to that bucket:
   ```
   AIRFLOW__LOGGING__REMOTE_LOGGING=True
   AIRFLOW__LOGGING__REMOTE_BASE_LOG_FOLDER=s3://airflow-logs
   AIRFLOW__LOGGING__REMOTE_LOG_CONN_ID=minio_s3_conn
   AIRFLOW__LOGGING__ENCRYPT_S3_LOGS=False
   ```

### Example DAG

`dags/minio_example.py` contains the `minio_integration_demo` DAG described in the blog post. It showcases:

- **Method 1:** Using `S3Hook` with the `minio_s3_conn` connection to create a bucket and upload a string.
- **Method 2:** Using the native `minio` Python client to create/upload JSON data manually (with `secure=False` because everything runs over the internal Docker network).

Trigger the DAG from the Airflow UI after configuring the connection to verify the integration.

