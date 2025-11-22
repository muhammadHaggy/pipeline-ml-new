from airflow import DAG
from airflow.providers.papermill.operators.papermill import PapermillOperator
from airflow.utils.dates import days_ago
from airflow.hooks.base import BaseHook
import json

# 1. Get Creds
def get_minio_creds():
    try:
        conn = BaseHook.get_connection("minio_s3_conn")
        extra = json.loads(conn.extra) if conn.extra else {}
        return conn.login, conn.password, extra.get('endpoint_url', 'http://minio:9000')
    except:
        return "admin", "password123", "http://minio:9000"

ACCESS_KEY, SECRET_KEY, ENDPOINT = get_minio_creds()

# Common Env Vars for Notebooks
COMMON_PARAMS = {
    "MINIO_ENDPOINT": ENDPOINT,
    "MINIO_ACCESS_KEY": ACCESS_KEY,
    "MINIO_SECRET_KEY": SECRET_KEY
}

# S3 Paths
MODELS_DIR = "s3://models/prod"
RUNS_DIR = "s3://runs/{{ run_id }}" # Unique folder per request

with DAG(
    dag_id='03_inference_pipeline',
    schedule_interval=None, # Triggered manually via API
    start_date=days_ago(1),
    catchup=False,
    tags=['mlops', 'inference']
) as dag:

    # Task 1: Fetch Topology
    fetch_topology = PapermillOperator(
        task_id='step_04_fetch_topology',
        input_nb='/notebooks/04_fetch_topology.ipynb',
        output_nb=f'/logs/04_inf_{{{{ run_id }}}}.ipynb',
        kernel_name="python3",
        parameters={
            'ORIGIN_ADDRESS': '{{ dag_run.conf["origin"] }}',
            'DESTINATION_ADDRESS': '{{ dag_run.conf["dest"] }}',
            'GOOGLE_API_KEY': '{{ var.value.google_maps_key }}',
            'OUTPUT_TOPOLOGY_PATH': f"{RUNS_DIR}/topology.json",
            **COMMON_PARAMS
        }
    )

    # Task 2: Generate Cycle
    generate_cycle = PapermillOperator(
        task_id='step_05_generate_cycle',
        input_nb='/notebooks/05_generate_cycle.ipynb',
        output_nb=f'/logs/05_inf_{{{{ run_id }}}}.ipynb',
        kernel_name="python3",
        parameters={
            'INPUT_TOPOLOGY_PATH': f"{RUNS_DIR}/topology.json",
            'MODEL_MATRIX_PATH': f"{MODELS_DIR}/transition_matrices.pkl",
            'MODEL_STATES_PATH': f"{MODELS_DIR}/state_definitions.pkl",
            'REF_SEGMENTS_PATH': f"s3://models/reference_segments.pkl",
            'OUTPUT_CYCLE_PATH': f"{RUNS_DIR}/cycle.csv",
            **COMMON_PARAMS
        }
    )

    # Task 3: Predict Emissions
    predict_emissions = PapermillOperator(
        task_id='step_06_movestar',
        input_nb='/notebooks/06_movestar.ipynb',
        output_nb=f'/logs/06_inf_{{{{ run_id }}}}.ipynb',
        kernel_name="python3",
        parameters={
            'INPUT_CYCLE_PATH': f"{RUNS_DIR}/cycle.csv",
            'VEHICLE_TYPE': 1,
            'OUTPUT_REPORT_PATH': f"{RUNS_DIR}/emissions.json",
            **COMMON_PARAMS
        }
    )

    fetch_topology >> generate_cycle >> predict_emissions