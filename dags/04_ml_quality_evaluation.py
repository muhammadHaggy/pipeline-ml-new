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
COMMON_PARAMS = {
    "MINIO_ENDPOINT": ENDPOINT,
    "MINIO_ACCESS_KEY": ACCESS_KEY,
    "MINIO_SECRET_KEY": SECRET_KEY
}

with DAG(
    dag_id='04_ml_quality_evaluation',
    description='ML Quality Evaluation',
    schedule_interval='@weekly',
    start_date=days_ago(1),
    catchup=False,
    tags=['mlops', 'quality-evaluation', 'ml-testing', 'simplified']
) as dag:

    # Generate timestamp from execution_date for versioning
    from airflow.operators.python import PythonOperator
    
    def generate_timestamp(**context):
        """Generate timestamp from execution_date for versioning."""
        exec_date = context['execution_date']
        timestamp = exec_date.strftime('%Y-%m-%d_%H-%M-%S')
        context['task_instance'].xcom_push(key='run_timestamp', value=timestamp)
        return timestamp
    
    get_timestamp = PythonOperator(
        task_id='generate_run_timestamp',
        python_callable=generate_timestamp,
        provide_context=True
    )

    # Step 1: Intelligent Train/Test Split
    # Handles both single-file and multi-file scenarios
    ml_train_test_split = PapermillOperator(
        task_id='step_01_intelligent_split',
        input_nb=get_notebook_path('01_ml_train_test_split.ipynb'),
        output_nb=get_log_path('01_ml_quality_eval_split.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_FOLDER': 's3://processed-data',
            'OUTPUT_TRAIN_DATA': "s3://models-quality-eval-ml/train/train_data.pkl",
            'OUTPUT_TEST_DATA': "s3://models-quality-eval-ml/test/test_data.pkl",
            'TRAIN_RATIO': 0.8,
            'RANDOM_SEED': 42,
            'MIN_ROWS_FOR_SPLIT': 1000,
            **COMMON_PARAMS
        }
    )

    # Step 2: Train ML Model 
    # Uses fixed hyperparameters, optional CV
    ml_train_model = PapermillOperator(
        task_id='step_02_ml_train',
        input_nb=get_notebook_path('03_ml_train_quality_eval.ipynb'),
        output_nb=get_log_path('03_ml_quality_eval_training.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_TRAIN_DATA': "s3://models-quality-eval-ml/train/train_data.pkl",
            'OUTPUT_ML_MODEL_PATH': "s3://models-quality-eval-ml/models/speed_accel_model.pkl",
            'USE_CROSS_VALIDATION': False,  # Set True for extra robustness (slower)
            **COMMON_PARAMS
        }
    )

    # Step 3: Validate Quality on Test Set
    # Uses YOUR acceleration method: predicted_speed - speed_mps_prev1
    ml_validate_quality = PapermillOperator(
        task_id='step_03_ml_validate_quality',
        input_nb=get_notebook_path('08_ml_validate_quality.ipynb'),
        output_nb=get_log_path('08_ml_quality_eval_validation.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_TEST_DATA': "s3://models-quality-eval-ml/test/test_data.pkl",
            'INPUT_ML_MODEL_PATH': "s3://models-quality-eval-ml/models/speed_accel_model.pkl",
            'OUTPUT_METRICS_PATH': "s3://models-quality-eval-ml/metrics/quality_metrics.json",
            'OUTPUT_PLOT_PATH': "s3://models-quality-eval-ml/metrics/validation_plots.png",
            # Relaxed thresholds for single-file testing
            'MIN_R2_SCORE': 0.85,
            'MAX_SPEED_RMSE': 2.5,   # m/s
            'MAX_ACCEL_RMSE': 0.7,   # m/s²
            'MAX_SPEED_MAE': 2.0,    # m/s
            'MAX_ACCEL_MAE': 0.5,    # m/s²
            **COMMON_PARAMS
        }
    )

    ml_validate_quality_with_emissions = PapermillOperator(
        task_id='step_04_ml_validate_quality_with_emissions',
        input_nb=get_notebook_path('08_ml_validate_quality_with_emissions.ipynb'),
        output_nb=get_log_path('08_ml_quality_eval_validation_with_emissions.ipynb'),
        kernel_name="python3",
        parameters={
            'RUN_TIMESTAMP': "{{ task_instance.xcom_pull(task_ids='generate_run_timestamp', key='run_timestamp') }}",
            'INPUT_TEST_DATA': "s3://models-quality-eval-ml/test/test_data.pkl",
            'INPUT_ML_MODEL_PATH': "s3://models-quality-eval-ml/models/speed_accel_model.pkl",
            'OUTPUT_METRICS_PATH': "s3://models-quality-eval-ml/metrics/quality_metrics_with_emissions.json",
            'OUTPUT_PLOT_PATH': "s3://models-quality-eval-ml/metrics/validation_plots_with_emissions.png",
            # Relaxed thresholds for single-file testing
            'MIN_R2_SCORE': 0.85,
            'MAX_SPEED_RMSE': 2.5,   # m/s
            'MAX_ACCEL_RMSE': 0.7,   # m/s²
            'MAX_SPEED_MAE': 2.0,    # m/s
            'MAX_ACCEL_MAE': 0.5,    # m/s²
            **COMMON_PARAMS
        }
    )

    # Pipeline flow
    get_timestamp >> ml_train_test_split >> ml_train_model >> ml_validate_quality >> ml_validate_quality_with_emissions
