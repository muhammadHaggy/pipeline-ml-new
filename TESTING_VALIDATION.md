# Testing & Validation - Quality Metrics Update

## Changes Summary

### What Was Changed

1. **Removed KL Divergence Metric**
   - Deleted `calculate_symmetric_kl_divergence()` function from `08_validate_quality_metrics.ipynb`
   - Removed `MAX_KL_DIVERGENCE` parameter from DAG and notebook
   - Removed `OUTPUT_KL_REPORT_PATH` parameter from DAG
   - Removed all KL divergence computations and references

2. **Implemented Combined Traffic Metrics**
   - Added `aggregate_metrics()` function to compute weighted averages across heavy and light traffic
   - Weights are based on sample size (number of seconds in each traffic condition)
   - New JSON output structure with `overall`, `heavy_traffic`, and `light_traffic` sections

3. **Updated Validation Logic**
   - Pass/fail now based on **overall combined metrics** instead of per-traffic metrics
   - Validation status and failures list included in output JSON
   - Thresholds: `MAX_SPEED_DIFF` (5.0 km/h), `MAX_ACCEL_DIFF` (0.5 m/s²), `MAX_RMSE_THRESHOLD` (0.15)

4. **Updated Documentation**
   - Modified `QUALITY_EVAL_README.md` to reflect new metric philosophy
   - Added section on comparing with other drive cycle generation methods
   - Updated output file examples and troubleshooting

### Files Modified

- `notebooks/08_validate_quality_metrics.ipynb` - Main notebook with metrics computation
- `dags/03_train_model_quality_eval.py` - Airflow DAG parameter updates
- `QUALITY_EVAL_README.md` - Documentation updates

## New Metric Schema

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
  "heavy_traffic": { <per-traffic metrics for debugging> },
  "light_traffic": { <per-traffic metrics for debugging> }
}
```

## Testing Checklist

### ✅ Pre-Testing Verification

- [x] Removed all KL divergence references from notebook
- [x] Removed scipy.stats.entropy import (no longer needed)
- [x] Added aggregate_metrics() function
- [x] Updated pass/fail logic to use overall metrics
- [x] Updated JSON output structure
- [x] Removed OUTPUT_KL_REPORT_PATH from DAG
- [x] Removed MAX_KL_DIVERGENCE from DAG
- [x] Updated README documentation

### 🧪 Manual Testing Steps

#### 1. Verify Notebook Syntax

```bash
cd /home/Acer/pipeline-ml-new
jupyter nbconvert --to script notebooks/08_validate_quality_metrics.ipynb --stdout | python -m py_compile
```

#### 2. Test with Existing Data (if available)

Use a previous successful run's data to test the updated notebook:

```bash
# Set parameters based on a previous run
RUN_TIMESTAMP="2025-11-30_10-01-12"  # Adjust to match actual timestamp

# Run the notebook with papermill
papermill notebooks/08_validate_quality_metrics.ipynb \
  /tmp/test_output.ipynb \
  -p RUN_TIMESTAMP "$RUN_TIMESTAMP" \
  -p INPUT_TEST_DATA "s3://models-quality-eval/$RUN_TIMESTAMP/test/grouped_segments.pkl" \
  -p INPUT_MODEL_DIR "s3://models-quality-eval/$RUN_TIMESTAMP/models/" \
  -p OUTPUT_METRICS_PATH "/tmp/test_metrics.json" \
  -p OUTPUT_PLOT_PATH "/tmp/test_plots.png" \
  -p MINIO_ENDPOINT "http://localhost:9000" \
  -p MINIO_ACCESS_KEY "admin" \
  -p MINIO_SECRET_KEY "bismillahlulus"
```

#### 3. Verify Output Structure

```bash
# Check the output JSON structure
cat /tmp/test_metrics.json | jq .

# Should have three main keys: overall, heavy_traffic, light_traffic
# overall should contain validation_status and failures
```

#### 4. Trigger Full DAG Run

```bash
# Trigger the quality evaluation DAG
airflow dags trigger 03_train_model_quality_eval

# Monitor the run
airflow dags list-runs -d 03_train_model_quality_eval
```

#### 5. Verify DAG Success

```bash
# Check task status
airflow tasks states-for-dag-run 03_train_model_quality_eval <run_id>

# All tasks should show "success"
```

#### 6. Inspect MinIO Output

```bash
# List the latest run folder
aws s3 ls s3://models-quality-eval/ --endpoint-url http://minio:9000 --recursive | sort | tail -20

# Download and inspect the metrics
aws s3 cp s3://models-quality-eval/<timestamp>/metrics/quality_metrics.json /tmp/final_metrics.json --endpoint-url http://minio:9000

# Verify structure
cat /tmp/final_metrics.json | jq .overall
```

### 🔍 Validation Criteria

#### Output File Checks

- ✅ `quality_metrics.json` exists
- ✅ `comparison_plots.png` exists
- ❌ `kl_divergence_report.txt` should NOT exist (removed)

#### JSON Structure Checks

- ✅ Contains `overall` key with all expected metrics
- ✅ Contains `validation_status` field ("PASSED" or "FAILED")
- ✅ Contains `failures` field (array)
- ✅ Contains `heavy_traffic` key (for debugging)
- ✅ Contains `light_traffic` key (for debugging)
- ❌ Should NOT contain `symmetric_kl_divergence` in any section

#### Metric Value Checks

- ✅ `total_sample_size_sec` = sum of heavy and light sample sizes
- ✅ All weighted averages are between heavy and light traffic values
- ✅ Validation status matches pass/fail logic based on thresholds

### 📊 Comparison with Previous Runs

To verify backward compatibility and correctness:

1. **Compare test sample sizes:**
   - New `overall.total_sample_size_sec` should equal old `heavy + light sample sizes`

2. **Compare kinematic metrics:**
   - New `overall.speed_difference_kmh` should be weighted average of old per-traffic values
   - New `overall.vsp_rmse` should be weighted average of old per-traffic values

3. **Verify consistency:**
   - Heavy traffic metrics should match previous heavy traffic output
   - Light traffic metrics should match previous light traffic output

## Expected Results

### Success Criteria

1. ✅ Notebook executes without errors
2. ✅ No KL-related artifacts are created
3. ✅ JSON contains proper `overall` section with combined metrics
4. ✅ Validation status is set correctly based on thresholds
5. ✅ Plots are generated showing both traffic conditions
6. ✅ DAG completes successfully
7. ✅ No references to KL divergence in outputs or logs

### Known Issues / Notes

- **Sample size weighting**: The aggregation uses sample size (seconds) as weights. This is appropriate for time-series metrics.
- **Per-traffic metrics retained**: Heavy and light traffic metrics are still computed and saved for debugging purposes.
- **Threshold application**: Thresholds now apply to combined metrics, making the validation more holistic.
- **Plot saving fixed**: Plots are now saved immediately after creation (in Cell 5) using explicit figure reference to avoid blank images.

## Rollback Plan

If issues are found:

1. **Revert notebook:**
   ```bash
   git checkout HEAD~1 notebooks/08_validate_quality_metrics.ipynb
   ```

2. **Revert DAG:**
   ```bash
   git checkout HEAD~1 dags/03_train_model_quality_eval.py
   ```

3. **Revert README:**
   ```bash
   git checkout HEAD~1 QUALITY_EVAL_README.md
   ```

## Next Steps After Validation

1. ✅ Confirm all tests pass
2. ⏭️ Run comparison with alternative drive cycle generation methods
3. ⏭️ Document baseline metrics for future comparisons
4. ⏭️ Create automated comparison scripts using `overall` metrics
5. ⏭️ Set up monitoring/alerting based on `validation_status`

## Contact

For questions about these changes, refer to:
- Plan document: `/update.plan.md`
- Implementation discussion in PR/commit messages

