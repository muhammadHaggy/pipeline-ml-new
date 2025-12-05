from airflow import DAG
from airflow.providers.papermill.operators.papermill import PapermillOperator
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
import json
from config import get_notebook_path, get_log_path

# 1. Fetch Credentials from Airflow Connection
def get_minio_creds():
    try:
        conn = BaseHook.get_connection("minio_s3_conn")
        extra = json.loads(conn.extra) if conn.extra else {}
        return conn.login, conn.password, extra.get('endpoint_url', 'http://minio:9000')
    except:
        return "admin", "bismillahlulus", "http://minio:9000"

ACCESS_KEY, SECRET_KEY, ENDPOINT = get_minio_creds()

# 2. Prepare Common Parameters
# We pass these as standard notebook variables now, NOT env vars
COMMON_PARAMS = {
    "MINIO_ENDPOINT": ENDPOINT,
    "MINIO_ACCESS_KEY": ACCESS_KEY,
    "MINIO_SECRET_KEY": SECRET_KEY
}

with DAG(
    dag_id='02_train_ml_model_pipeline',
    schedule_interval='@weekly',
    start_date=days_ago(1),
    catchup=False,
    tags=['mlops', 'training']
) as dag:

    # Step 1: Group Segments
    preprocess_grouping = PapermillOperator(
        task_id='step_01_group_segments',
        input_nb=get_notebook_path('01_preprocess.ipynb'),
        output_nb=get_log_path('01_training_grouping.ipynb'),
        kernel_name="python3",
        parameters={
            'INPUT_FOLDER': 's3://processed-data/',
            'OUTPUT_GROUPED_DATA': 's3://models/grouped_segments.pkl',
            'SPEED_THRESHOLD': 25.0,
            'MIN_DURATION': 15,
            **COMMON_PARAMS  # <--- Merge creds here
        }
    )

    # Step 2: Train ML Model (Speed + Acceleration)
    train_ml_model = PapermillOperator(
        task_id='step_02_train_ml_model',
        input_nb=get_notebook_path('03_simplified_train_ml_speed_accel.ipynb'),
        output_nb=get_log_path('05_training_ml_model.ipynb'),
        kernel_name="python3",
        parameters={
            'INPUT_PROCESSED_FOLDER': 's3://processed-data/',
            'OUTPUT_ML_MODEL_PATH': 's3://models/ml/speed_accel_model.pkl',
            **COMMON_PARAMS
        }
    )


    preprocess_grouping >> train_ml_model
