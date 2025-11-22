from airflow import DAG
from airflow.decorators import task
from airflow.providers.papermill.operators.papermill import PapermillOperator
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook  # <--- Import this
import s3fs
import os
import json

# Helper function to load creds from the Connection we just made
def get_s3fs_options():
    try:
        # Fetch the connection object by ID
        conn = BaseHook.get_connection("minio_s3_conn")
        extra = json.loads(conn.extra) if conn.extra else {}
        
        return {
            'key': conn.login,           # 'admin'
            'secret': conn.password,     # 'password123'
            'client_kwargs': {
                'endpoint_url': extra.get('endpoint_url', 'http://minio:9000')
            }
        }
    except Exception as e:
        print(f"⚠️ Connection 'minio_s3_conn' not found or invalid: {e}")
        # Fallback for local testing if connection is missing
        return {
            'key': 'admin', 
            'secret': 'password123', 
            'client_kwargs': {'endpoint_url': 'http://minio:9000'}
        }

with DAG(
    dag_id='01_ingest_new_zips',
    schedule_interval='@hourly',
    start_date=days_ago(1),
    catchup=False
) as dag:

    @task
    def get_new_trips():
        # 1. Load Options dynamically
        s3_opts = get_s3fs_options()
        print(f"Connecting to S3 Endpoint: {s3_opts['client_kwargs']['endpoint_url']}")

        # 2. Initialize File System with these options
        fs = s3fs.S3FileSystem(**s3_opts)
        
        # 3. List Files (Debug prints added)
        try:
            raw_files = fs.glob("s3://raw-gps/*.zip")
            print(f"Raw files found: {raw_files}")
            
            proc_files = fs.glob("s3://processed-data/*.csv")
            print(f"Processed files found: {proc_files}")
        except Exception as e:
            print(f"Error listing files: {e}")
            return []

        # 4. Calculate Delta
        raw_ids = {os.path.splitext(os.path.basename(f))[0] for f in raw_files}
        proc_ids = {os.path.basename(f).replace("_1hz.csv", "") for f in proc_files}
        
        new_ids = list(raw_ids - proc_ids)
        print(f"Found {len(new_ids)} new trips to process: {new_ids}")
        
        return new_ids

    new_trips = get_new_trips()

    process_trips = PapermillOperator.partial(
        task_id="process_trip",
        input_nb="/notebooks/00_ingest_raw_trip.ipynb",
        kernel_name="python3"
    ).expand(
        output_nb=new_trips.map(lambda x: f"/logs/00_{x}.ipynb"),
        
        # ALL parameters (static + dynamic) must be defined here
        parameters=new_trips.map(lambda x: {
            'INPUT_ZIP_PATH': f"s3://raw-gps/{x}.zip",
            'OUTPUT_PROCESSED_PATH': f"s3://processed-data/{x}_1hz.csv",
            'GOOGLE_ROADS_API_KEY': '{{ var.value.google_maps_key }}' # Moved here
        })
    )