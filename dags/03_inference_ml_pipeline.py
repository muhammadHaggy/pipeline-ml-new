from airflow import DAG
from airflow.providers.papermill.operators.papermill import PapermillOperator
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
import json
from config import get_notebook_path, get_log_path
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowException
from airflow.models.param import Param

def get_minio_creds():
    try:
        conn = BaseHook.get_connection("minio_s3_conn")
        extra = json.loads(conn.extra) if conn.extra else {}
        return conn.login, conn.password, extra.get('endpoint_url', 'http://minio:9000')
    except:
        return "admin", "bismillahlulus", "http://minio:9000"


ACCESS_KEY, SECRET_KEY, ENDPOINT = get_minio_creds()

COMMON_PARAMS = {
    "MINIO_ENDPOINT": ENDPOINT,
    "MINIO_ACCESS_KEY": ACCESS_KEY,
    "MINIO_SECRET_KEY": SECRET_KEY
}

MODELS_DIR = "s3://models/ml"
RUNS_DIR = "s3://runs/{{ run_id }}"

with DAG(
    dag_id='03_inference_ml_pipeline',
    schedule_interval=None,
    start_date=days_ago(1),
    catchup=False,
    tags=['mlops', 'inference', 'ml']
) as dag:

    # 1. Fetch topology from Google Maps APIs
    fetch_topology_ml = PapermillOperator(
        task_id='step_04_fetch_topology_ml',
        input_nb=get_notebook_path('04_fetch_topology_ml.ipynb'),
        output_nb=get_log_path('04_ml_inf_{{ run_id }}.ipynb'),
        kernel_name="python3",
        parameters={
            'ORIGIN_ADDRESS': '{{ dag_run.conf["origin"] }}',
            'DESTINATION_ADDRESS': '{{ dag_run.conf["dest"] }}',
            'GOOGLE_API_KEY': '{{ var.value.google_maps_key }}',
            'OUTPUT_TOPOLOGY_PATH': f"{RUNS_DIR}/topology_ml.csv",
            **COMMON_PARAMS
        }
    )



    # 2. ML inference (speed + acceleration)
    predict_speed_accel = PapermillOperator(
    task_id='step_05_predict_speed_accel',
    input_nb=get_notebook_path('05_predict_speed_accel.ipynb'),
    output_nb=get_log_path(f'05_ml_inf_{{{{ run_id }}}}.ipynb'),
    kernel_name="python3",
    parameters={
        'INPUT_TOPOLOGY_PATH': f"{RUNS_DIR}/topology_ml.csv",
        'MODEL_FILE_PATH': f"{MODELS_DIR}/speed_accel_model.pkl",
        'OUTPUT_PREDICTIONS_PATH': f"{RUNS_DIR}/pred_speed_accel.csv",
        **COMMON_PARAMS
    }
    )

    # 3. Emission calculation from predicted speed (VSP)
    predict_emissions = PapermillOperator(
        task_id='step_06_movestar',
        input_nb=get_notebook_path('06_movestar.ipynb'),
        output_nb=get_log_path(f'06_ml_inf_{{{{ run_id }}}}.ipynb'),
        kernel_name="python3",
        parameters={
            'INPUT_CYCLE_PATH': f"{RUNS_DIR}/pred_speed_accel.csv",
            'VEHICLE_TYPE': 1,
            'OUTPUT_REPORT_PATH': f"{RUNS_DIR}/emissions.json",
            **COMMON_PARAMS
        }
    )

    


    fetch_topology_ml >> predict_speed_accel >> predict_emissions