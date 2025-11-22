"""Example DAG showcasing two strategies for working with MinIO from Airflow."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from airflow import DAG
from airflow.decorators import task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from minio import Minio

DEFAULT_ARGS = {
    "owner": "airflow",
}


with DAG(
    dag_id="minio_integration_demo",
    default_args=DEFAULT_ARGS,
    schedule=None,
    start_date=datetime(2023, 1, 1),
    catchup=False,
    tags=["minio"],
) as dag:

    @task
    def upload_text_file_s3hook() -> None:
        """Use the S3Hook and the minio_s3_conn connection to upload a payload."""
        hook = S3Hook(aws_conn_id="minio_s3_conn")
        bucket_name = "test-bucket"

        if not hook.check_for_bucket(bucket_name):
            hook.create_bucket(bucket_name)

        hook.load_string(
            string_data="Hello from Airflow S3Hook!",
            key="airflow_hook_test.txt",
            bucket_name=bucket_name,
            replace=True,
        )

    @task
    def upload_via_minio_client() -> None:
        """Demonstrate using the MinIO Python SDK directly."""
        client = Minio(
            "minio:9000",
            access_key="admin",
            secret_key="password123",
            secure=False,
        )

        bucket_name = "processed"
        object_name = "blog_style_upload.json"
        payload = {"message": "Hello from the MinIO Python Client!"}
        file_path = Path(object_name)

        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        file_path.write_text(json.dumps(payload), encoding="utf-8")
        try:
            client.fput_object(bucket_name, object_name, str(file_path))
        finally:
            if file_path.exists():
                file_path.unlink()

    upload_text_file_s3hook()
    upload_via_minio_client()

