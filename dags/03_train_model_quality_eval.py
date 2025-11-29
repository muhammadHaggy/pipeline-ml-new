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
    dag_id='03_train_model_quality_eval',
    schedule_interval='@weekly',
    start_date=days_ago(1),
    catchup=False,
    tags=['mlops', 'quality-evaluation', 'testing']
) as dag:

    # Generate timestamp from execution_date for versioning
    # Format: YYYY-MM-DD_HH-MM-SS
    # This will be passed to all notebooks to create versioned paths
    from airflow.operators.python import PythonOperator
    
    def generate_timestamp(**context):
        """Generate timestamp from execution_date for versioning."""
        exec_date = context['execution_date']
        timestamp = exec_date.strftime('%Y-%m-%d_%H-%M-%S')
        # Push to XCom for other tasks to use
        context['task_instance'].xcom_push(key='run_timestamp', value=timestamp)
        return timestamp
    
    get_timestamp = PythonOperator(
        task_id='generate_run_timestamp',
        python_callable=generate_timestamp,
        provide_context=True
    )

    # Step 1: Train/Test Split
    preprocess_split = PapermillOperator(
        task_id='step_01_train_test_split',
        input_nb=get_notebook_path('01_preprocess_train_test_split.ipynb'),
        output_nb=get_log_path('01_quality_eval_split.ipynb'),
        kernel_name="python3",
        parameters={
            'INPUT_FOLDER': 's3://processed-data/',
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'OUTPUT_TRAIN_DATA': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/train/grouped_segments.pkl",
            'OUTPUT_TEST_DATA': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/test/grouped_segments.pkl",
            'SPEED_THRESHOLD': 25.0,
            'MIN_DURATION': 15,
            'TRAIN_RATIO': 0.8,
            'RANDOM_SEED': 42,
            **COMMON_PARAMS
        }
    )

    # Step 2: Train Markov on Train Set
    train_markov = PapermillOperator(
        task_id='step_02_train_on_train_set',
        input_nb=get_notebook_path('03_train_markov_quality_eval.ipynb'),
        output_nb=get_log_path('03_quality_eval_training.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_GROUPED_DATA': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/train/grouped_segments.pkl",
            'OUTPUT_MODEL_DIR': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/models/",
            'V_RES': 2.5,
            'A_RES': 0.25,
            **COMMON_PARAMS
        }
    )

    # Step 3: Validate Quality with Enhanced Metrics
    validate_quality = PapermillOperator(
        task_id='step_03_validate_quality',
        input_nb=get_notebook_path('08_validate_quality_metrics.ipynb'),
        output_nb=get_log_path('08_quality_eval_validation.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_TEST_DATA': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/test/grouped_segments.pkl",
            'INPUT_MODEL_DIR': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/models/",
            'OUTPUT_METRICS_PATH': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/metrics/quality_metrics.json",
            'OUTPUT_PLOT_PATH': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/metrics/comparison_plots.png",
            'OUTPUT_KL_REPORT_PATH': "s3://models-quality-eval/{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}/metrics/kl_divergence_report.txt",
            'MAX_KL_DIVERGENCE': 0.5,
            'MAX_SPEED_DIFF': 5.0,
            'MAX_ACCEL_DIFF': 0.5,
            'MAX_RMSE_THRESHOLD': 0.15,
            **COMMON_PARAMS
        }
    )

    get_timestamp >> preprocess_split >> train_markov >> validate_quality
