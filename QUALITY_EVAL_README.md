# Quality Evaluation Pipeline - README

## Overview

This is an **independent training pipeline** designed to measure the quality of Markov chain models using rigorous statistical metrics. Unlike the production training pipeline (`02_train_model_pipeline.py`), this pipeline focuses on model evaluation using train/test split methodology.

## Key Features

### 🎯 **Fixed Train/Test Data**
- Uses pre-defined train.csv and test.csv from MinIO (`s3://models-quality-eval/data/`)
- Ensures reproducible comparisons across different drive cycle generation methods
- Same train/test split can be used by all methods for fair evaluation
- No random splitting - completely deterministic

### 📊 **Comprehensive Quality Metrics**

**Combined Traffic Metrics** - All metrics are aggregated across heavy and light traffic conditions using weighted averaging by sample size. This allows comparison with other drive cycle generation methods.

1. **Kinematic Comparisons**:
   - Average speed (real vs synthetic)
   - Average acceleration (real vs synthetic)
   - Standard deviation of speed
   - Standard deviation of acceleration
2. **VSP Distribution RMSE** - Metric for emission modeling validation
3. **Overall Validation Status** - Pass/Fail based on combined metrics

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
Step 1: Load Fixed Train/Test Data and Group by Traffic
    ↓
Step 2: Train Markov Models (on train set only)
    ↓
Step 3: Validate Quality (on test set)
```

### Step 1: Load Fixed Train/Test Data
**Notebook:** `01_load_fixed_train_test.ipynb`
- Loads fixed train.csv and test.csv from `s3://models-quality-eval/data/`
- Groups segments by traffic condition (Heavy/Light) using speed threshold
- No random splitting - uses pre-defined data splits
- **Different filtering for train vs test**:
  - Train: `MIN_DURATION_TRAIN = 5` seconds (quality over quantity)
  - Test: `MIN_DURATION_TEST = 0` seconds (accept all segments for comprehensive evaluation)
- Saves to versioned paths
- **CSV Format Expected**: Columns `speed_kmh`, `acceleration_ms2` (or `acc_forward`), and optionally `segment_id`

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

Applied to **combined metrics** across both heavy and light traffic conditions:

| Metric | Threshold | Description |
|--------|-----------|-------------|
| Speed Difference | < 5 km/h | Absolute difference in average speed (weighted average) |
| Acceleration Difference | < 0.5 m/s² | Absolute difference in average acceleration (weighted average) |
| VSP RMSE | < 0.15 | Root mean square error on VSP distributions (weighted average) |

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
✅ **Fixed data splits** - Reproducible comparisons with other methods  
✅ **Same schedule** - Can run in parallel without interference

## Data Preparation

Before running this pipeline, you need to prepare the fixed train/test data:

1. **Create the data folder** in MinIO bucket `models-quality-eval`:
   ```bash
   aws s3 mb s3://models-quality-eval/data/ --endpoint-url http://minio:9000
   ```

2. **Upload train.csv and test.csv**:
   ```bash
   aws s3 cp train.csv s3://models-quality-eval/data/train.csv --endpoint-url http://minio:9000
   aws s3 cp test.csv s3://models-quality-eval/data/test.csv --endpoint-url http://minio:9000
   ```

3. **CSV Format Requirements**:
   - Required columns: `speed_kmh`, and either `acceleration_ms2` or `acc_forward`
   - Optional column: `segment_id` (for grouping rows into segments)
   - Data should be preprocessed (1Hz sampling rate recommended)
   - The notebook automatically detects which acceleration column is present
   
4. **Why Fixed Data?**
   - Ensures all drive cycle generation methods use identical train/test data
   - Eliminates variability from random splitting
   - Makes comparisons fair and reproducible

## Output Files

### `quality_metrics.json`
New structure with combined overall metrics for cross-method comparison:
```json
{
  "overall": {
    "avg_speed_real_kmh": 18.8,
    "avg_speed_synthetic_kmh": 19.1,
    "speed_difference_kmh": 0.65,
    "avg_accel_real_ms2": 0.13,
    "avg_accel_synthetic_ms2": 0.14,
    "accel_difference_ms2": 0.025,
    "std_speed_real_kmh": 12.5,
    "std_speed_synthetic_kmh": 12.7,
    "std_accel_real_ms2": 0.85,
    "std_accel_synthetic_ms2": 0.87,
    "vsp_rmse": 0.089,
    "total_sample_size_sec": 24500,
    "validation_status": "PASSED",
    "failures": []
  },
  "heavy_traffic": { ... },  // For debugging
  "light_traffic": { ... }   // For debugging
}
```

**Key Feature**: The `overall` section contains weighted-average metrics suitable for comparing this Markov-based approach with other drive cycle generation methods.

### `comparison_plots.png`
Visual comparison with 12 subplots (3 rows x 4 columns):
- Row 1: Heavy Traffic (Speed dist, VSP dist, Speed stats, Accel stats)
- Row 2: Light Traffic (Speed dist, VSP dist, Speed stats, Accel stats)
- Row 3: Combined Overall (Speed dist, VSP dist, Speed stats, Accel stats)

**Note:** Row 3 shows the combined metrics by concatenating all data from both traffic conditions, providing a visual representation that matches the `overall` section in the JSON output.

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

**Issue:** Pipeline fails at Step 1 (load data)  
**Solution:** Verify train.csv and test.csv exist in `s3://models-quality-eval/data/` and have required columns

**Issue:** "Missing required column" error  
**Solution:** Ensure CSV files have `speed_kmh` and either `acceleration_ms2` or `acc_forward` columns

**Issue:** Pipeline fails at validation step  
**Solution:** Check if test set has sufficient data (min 100 segments per group)

**Issue:** Overall metrics exceed thresholds  
**Solution:** Model may be undertrained or data distribution has changed significantly. Review per-traffic metrics in `heavy_traffic` and `light_traffic` sections to identify which scenario is problematic.

**Issue:** Timestamp folders not created  
**Solution:** Verify XCom is working: check `generate_run_timestamp` task logs

## Comparing with Other Drive Cycle Generation Methods

The `overall` metrics section is designed for comparing the Markov-based approach with other generation methods:

1. **Extract overall metrics** from `quality_metrics.json`
2. **Compare key indicators:**
   - `speed_difference_kmh` - Lower is better (how well synthetic matches real average speed)
   - `accel_difference_kmh` - Lower is better (how well synthetic matches real acceleration)
   - `vsp_rmse` - Lower is better (VSP distribution similarity)
   - `validation_status` - Should be "PASSED"
3. **Use same test set** for fair comparison across methods
4. **Weight by sample size** when aggregating results from multiple runs

### Example Comparison Table

| Method | Speed Diff (km/h) | Accel Diff (m/s²) | VSP RMSE | Status |
|--------|-------------------|-------------------|----------|--------|
| Markov (this) | 0.65 | 0.025 | 0.089 | PASSED |
| Method B | 1.2 | 0.045 | 0.12 | PASSED |
| Method C | 0.8 | 0.035 | 0.095 | PASSED |

## Next Steps

1. **Automated Comparison:** Create script to compare overall metrics across multiple runs and methods
2. **Alerting:** Set up notifications when quality thresholds are exceeded
3. **Visualization Dashboard:** Build Grafana dashboard for metric trends
4. **Hyperparameter Tuning:** Use quality metrics to optimize V_RES and A_RES

## Related Files

- Production Training: `dags/02_train_model_pipeline.py`
- Inference Pipeline: `dags/03_inference_pipeline.py`
- Configuration: `dags/config.py`
