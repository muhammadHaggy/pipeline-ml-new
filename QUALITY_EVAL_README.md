# Quality Evaluation Pipeline - README

## Overview

This is an **independent training pipeline** designed to measure the quality of Markov chain models using rigorous statistical metrics. Unlike the production training pipeline (`02_train_model_pipeline.py`), this pipeline focuses on model evaluation using train/test split methodology.

## Key Features

### 🎯 **Train/Test Split (80:20)**
- Randomly splits data into 80% training and 20% testing
- Uses fixed random seed (42) for reproducibility
- Ensures no data leakage between train and test sets

### 📊 **Quality Metrics**

1. **Kinematic Comparisons**:
   - Average speed (real vs synthetic)
   - Average acceleration (real vs synthetic)
   - Standard deviation of speed
   - Standard deviation of acceleration
2. **VSP Distribution RMSE** - Metric for emission modeling validation

### 🗂️ **Versioned Storage**
Each pipeline run creates a timestamped folder in MinIO:
```
s3://models-quality-eval/
├── 2025-11-29_18-00-00/
│   ├── train/grouped_segments.pkl
│   ├── test/grouped_segments.pkl
│   ├── models/
│   │   ├── transition_matrices.pkl
│   │   └── state_definitions.pkl
│   └── metrics/
│       ├── quality_metrics.json
│       └── comparison_plots.png
└── 2025-12-06_18-00-00/
    └── ... (next run)
```

## Pipeline Architecture

```
Step 1: Train/Test Split
    ↓
Step 2: Train Markov Models (on train set only)
    ↓
Step 3: Validate Quality (on test set)
```

### Step 1: Train/Test Split
**Notebook:** `01_preprocess_train_test_split.ipynb`
- Loads processed data from `s3://processed-data/`
- Groups segments by traffic condition (Heavy/Light)
- Randomly splits each group 80:20
- Saves to versioned paths

### Step 2: Train Markov Models
**Notebook:** `03_train_markov_quality_eval.ipynb`
- Trains on **training set only**
- Uses same Markov chain logic as production pipeline
- Saves models to versioned path

### Step 3: Validate Quality
**Notebook:** `08_validate_quality_metrics.ipynb`
- Evaluates on **test set only** (unseen data)
- Generates synthetic data using trained models
- Calculates comprehensive metrics
- Creates visualizations (2x4 grid of plots)
- Saves detailed reports

## Quality Thresholds

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Speed Difference | < 5 km/h | Absolute difference in average speed |
| Acceleration Difference | < 0.5 m/s² | Absolute difference in average acceleration |
| VSP RMSE | < 0.15 | Root mean square error on VSP distributions |

## DAG Configuration

- **DAG ID:** `03_train_model_quality_eval`
- **Schedule:** `@weekly` (every Sunday at midnight)
- **Tags:** `['mlops', 'quality-evaluation', 'testing']`
- **Dependencies:** Same as production pipeline (MinIO, Papermill)

## Independence from Production Pipeline

✅ **Different DAG ID** - No naming conflicts  
✅ **Separate MinIO paths** - `s3://models-quality-eval/` vs `s3://models/`  
✅ **Different tags** - Easy to filter in Airflow UI  
✅ **Versioned outputs** - Multiple test runs preserved  
✅ **Same schedule** - Can run in parallel without interference

## Output Files

### `quality_metrics.json`
```json
{
  "Heavy Traffic": {
    "avg_speed_real_kmh": 18.5,
    "avg_speed_synthetic_kmh": 19.2,
    "speed_difference_kmh": 0.7,
    "avg_accel_real_ms2": 0.12,
    "avg_accel_synthetic_ms2": 0.15,
    "accel_difference_ms2": 0.03,
    "vsp_rmse": 0.089,
    "test_sample_size_sec": 12450
  },
  "Light Traffic": { ... }
}
```

### `comparison_plots.png`
Visual comparison with 8 subplots (2 rows x 4 columns):
- Row 1: Heavy Traffic (Speed dist, VSP dist, Speed stats, Accel stats)
- Row 2: Light Traffic (Speed dist, VSP dist, Speed stats, Accel stats)

## Usage

### Manual Trigger
```bash
airflow dags trigger 03_train_model_quality_eval
```

### View Results
1. Access MinIO UI
2. Navigate to `models-quality-eval/` bucket
3. Find latest timestamped folder
4. Download metrics and plots

### Compare Across Runs
```bash
# List all test runs
aws s3 ls s3://models-quality-eval/ --endpoint-url http://minio:9000

# Download specific run
aws s3 cp s3://models-quality-eval/2025-11-29_18-00-00/metrics/ ./results/ --recursive
```

## Troubleshooting

**Issue:** Pipeline fails at validation step  
**Solution:** Check if test set has sufficient data (min 100 segments per group)

**Issue:** KL divergence is very high  
**Solution:** Model may be undertrained or data distribution has changed significantly

**Issue:** Timestamp folders not created  
**Solution:** Verify XCom is working: check `generate_run_timestamp` task logs

## Next Steps

1. **Automated Comparison:** Create script to compare metrics across multiple runs
2. **Alerting:** Set up notifications when quality thresholds are exceeded
3. **Visualization Dashboard:** Build Grafana dashboard for metric trends
4. **Hyperparameter Tuning:** Use quality metrics to optimize V_RES and A_RES

## Related Files

- Production Training: `dags/02_train_model_pipeline.py`
- Inference Pipeline: `dags/03_inference_pipeline.py`
- Configuration: `dags/config.py`
