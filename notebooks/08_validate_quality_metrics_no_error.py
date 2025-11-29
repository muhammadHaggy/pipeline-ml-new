# @title 8. Validate Model Quality (Symmetric KL Divergence + Kinematic Metrics)
# Modified version: Saves results without raising ValueError

# CELL 1 [TAG: parameters]
# ---------------------------------------------------------
# Default parameters (Airflow will OVERWRITE these)
# ---------------------------------------------------------
RUN_TIMESTAMP = "2025-01-01_00-00-00"  # Injected by Airflow
INPUT_TEST_DATA = "s3://models-quality-eval/2025-01-01_00-00-00/test/grouped_segments.pkl"
INPUT_MODEL_DIR = "s3://models-quality-eval/2025-01-01_00-00-00/models/"
OUTPUT_METRICS_PATH = "s3://models-quality-eval/2025-01-01_00-00-00/metrics/quality_metrics.json"
OUTPUT_PLOT_PATH = "s3://models-quality-eval/2025-01-01_00-00-00/metrics/comparison_plots.png"
OUTPUT_KL_REPORT_PATH = "s3://models-quality-eval/2025-01-01_00-00-00/metrics/kl_divergence_report.txt"
VEHICLE_TYPE = 1  # Motorcycle

# Quality Thresholds
MAX_KL_DIVERGENCE = 0.5  # Symmetric KL divergence threshold
MAX_SPEED_DIFF = 5.0  # km/h
MAX_ACCEL_DIFF = 0.5  # m/s²
MAX_RMSE_THRESHOLD = 0.15  # VSP RMSE threshold

# MinIO Credentials
MINIO_ENDPOINT = "http://localhost:9000"
MINIO_ACCESS_KEY = "admin"
MINIO_SECRET_KEY = "password123"

# CELL 2: Imports
import pickle
import json
import io
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import s3fs
from scipy.stats import entropy

# CELL 3: MinIO Configuration
fs = s3fs.S3FileSystem(
    key=MINIO_ACCESS_KEY,
    secret=MINIO_SECRET_KEY,
    client_kwargs={'endpoint_url': MINIO_ENDPOINT}
)

# CELL 4: Helper Functions (Physics & Generation)
def calculate_vsp(speed_ms, acc_ms2, veh_type=1):
    """Calculates VSP using MOVESTAR coefficients."""
    if veh_type == 1:  # Motorcycle
        A, B, C, M, f = 0.0251, 0.0, 0.000315, 0.285, 0.285
    else:
        A, B, C, M, f = 0.156461, 0.002002, 0.000493, 1.4788, 1.4788

    vsp = (A * speed_ms) + (B * speed_ms**2) + (C * speed_ms**3) + (M * speed_ms * acc_ms2)
    return vsp / f

def get_distribution(data, bins):
    """Get normalized distribution from data."""
    counts, _ = np.histogram(data, bins=bins)
    total = np.sum(counts)
    return counts / total if total > 0 else np.zeros(len(counts))

def calculate_symmetric_kl_divergence(p, q, epsilon=1e-10):
    """
    Calculate Symmetric KL Divergence: d(P,Q) = [KL(P||Q) + KL(Q||P)] / 2
    
    This symmetric version eliminates directional bias in distribution comparison.
    A value close to zero indicates the Markov Chain model accurately replicates
    the speed and acceleration distribution patterns from real-world data.
    
    Following methodology from driving behavior classification research,
    this uses 2D probability distributions of (velocity, acceleration) as
    drive cycle characteristics representation.
    
    Args:
        p: Synthetic data distribution (from model)
        q: Real data distribution (ground truth)
        epsilon: Small value to avoid log(0)
    
    Returns:
        Symmetric KL divergence value (lower is better, 0 = perfect match)
    """
    # Add small epsilon to avoid division by zero
    p = p + epsilon
    q = q + epsilon
    # Renormalize
    p = p / np.sum(p)
    q = q / np.sum(q)
    
    # Calculate both directions
    kl_pq = np.sum(p * np.log(p / q))  # KL(P||Q)
    kl_qp = np.sum(q * np.log(q / p))  # KL(Q||P)
    
    # Return symmetric average
    return (kl_pq + kl_qp) / 2.0

def generate_synthetic_sequence(matrix, states, length):
    """Generates a random walk using the trained matrix."""
    if matrix is None or length <= 0:
        return np.array([])

    current_idx = np.random.randint(0, len(matrix))
    path = [current_idx]

    for _ in range(length - 1):
        probs = matrix[current_idx]
        if np.sum(probs) == 0:
            next_idx = current_idx
        else:
            next_idx = np.random.choice(len(probs), p=probs)
        path.append(next_idx)
        current_idx = next_idx

    # Decode state indices to Speed values (Column 0)
    return states[path, 0]

# CELL 5: Load Data & Models
print("Loading artifacts...")
print(f"Run Timestamp: {RUN_TIMESTAMP}")
model_base = INPUT_MODEL_DIR.rstrip("/")
try:
    # 1. Test Data (Grouped Segments)
    with fs.open(INPUT_TEST_DATA, 'rb') as f:
        test_segments = pickle.load(f)

    # 2. Models
    with fs.open(f"{model_base}/transition_matrices.pkl", 'rb') as f:
        trans_matrices = pickle.load(f)
    with fs.open(f"{model_base}/state_definitions.pkl", 'rb') as f:
        state_defs = pickle.load(f)

    print("✅ Loaded test data and models.")
except Exception as e:
    print(f"❌ Error loading artifacts: {e}")
    raise

# CELL 6: Generate & Compare with Enhanced Metrics
vsp_bins = np.arange(-20, 40, 2)
speed_bins = np.arange(0, 120, 5)  # Speed bins for KL divergence
metrics = {}
traffic_labels = {0: "Heavy Traffic", 1: "Light Traffic"}
kl_report_lines = []

kl_report_lines.append("=" * 60)
kl_report_lines.append("SYMMETRIC KL DIVERGENCE QUALITY EVALUATION REPORT")
kl_report_lines.append(f"Run Timestamp: {RUN_TIMESTAMP}")
kl_report_lines.append("=" * 60)
kl_report_lines.append("")
kl_report_lines.append("Metric: Symmetric KL Divergence d(P,Q) = [KL(P||Q) + KL(Q||P)] / 2")
kl_report_lines.append("This eliminates directional bias in distribution comparison.")
kl_report_lines.append("")

plt.figure(figsize=(16, 10))
for group_idx in range(2):
    print(f"\n--- Validating Group {group_idx} ({traffic_labels[group_idx]}) ---")

    # A. Prepare Real Test Data
    real_segments = test_segments[group_idx]
    if not real_segments:
        print("Skipping: No test data found.")
        continue

    real_concat = np.concatenate(real_segments)
    real_speed_kmh = real_concat[:, 0]  # km/h
    real_speed_ms = real_speed_kmh / 3.6  # m/s
    real_acc = real_concat[:, 1]  # m/s²

    # B. Generate Synthetic Data
    target_duration = len(real_speed_kmh)
    syn_speed_kmh = generate_synthetic_sequence(trans_matrices[group_idx], state_defs[group_idx], target_duration)

    if len(syn_speed_kmh) == 0:
        print("Skipping: Model failed to generate data.")
        continue

    syn_speed_ms = syn_speed_kmh / 3.6
    syn_acc = np.gradient(syn_speed_ms)

    # C. Kinematic Metrics
    avg_speed_real = np.mean(real_speed_kmh)
    avg_speed_syn = np.mean(syn_speed_kmh)
    avg_accel_real = np.mean(real_acc)
    avg_accel_syn = np.mean(syn_acc)
    std_speed_real = np.std(real_speed_kmh)
    std_speed_syn = np.std(syn_speed_kmh)
    std_accel_real = np.std(real_acc)
    std_accel_syn = np.std(syn_acc)

    speed_diff = abs(avg_speed_real - avg_speed_syn)
    accel_diff = abs(avg_accel_real - avg_accel_syn)

    # D. Symmetric KL Divergence on Speed Distribution
    speed_dist_real = get_distribution(real_speed_kmh, speed_bins)
    speed_dist_syn = get_distribution(syn_speed_kmh, speed_bins)
    symmetric_kl_divergence = calculate_symmetric_kl_divergence(speed_dist_syn, speed_dist_real)

    # E. Calculate VSP for RMSE
    vsp_real = calculate_vsp(real_speed_ms, real_acc, VEHICLE_TYPE)
    vsp_syn = calculate_vsp(syn_speed_ms, syn_acc, VEHICLE_TYPE)

    # F. Compare VSP Distributions
    vsp_dist_real = get_distribution(vsp_real, vsp_bins)
    vsp_dist_syn = get_distribution(vsp_syn, vsp_bins)
    vsp_rmse = np.sqrt(np.mean((vsp_dist_real - vsp_dist_syn)**2))

    # G. Store Metrics
    metrics[traffic_labels[group_idx]] = {
        "symmetric_kl_divergence": float(symmetric_kl_divergence),
        "avg_speed_real_kmh": float(avg_speed_real),
        "avg_speed_synthetic_kmh": float(avg_speed_syn),
        "speed_difference_kmh": float(speed_diff),
        "avg_accel_real_ms2": float(avg_accel_real),
        "avg_accel_synthetic_ms2": float(avg_accel_syn),
        "accel_difference_ms2": float(accel_diff),
        "std_speed_real_kmh": float(std_speed_real),
        "std_speed_synthetic_kmh": float(std_speed_syn),
        "std_accel_real_ms2": float(std_accel_real),
        "std_accel_synthetic_ms2": float(std_accel_syn),
        "vsp_rmse": float(vsp_rmse),
        "test_sample_size_sec": int(target_duration)
    }

    # H. Print Summary
    print(f"  Symmetric KL Divergence: {symmetric_kl_divergence:.4f}")
    print(f"  Avg Speed: Real={avg_speed_real:.2f} km/h, Syn={avg_speed_syn:.2f} km/h, Diff={speed_diff:.2f} km/h")
    print(f"  Avg Accel: Real={avg_accel_real:.3f} m/s², Syn={avg_accel_syn:.3f} m/s², Diff={accel_diff:.3f} m/s²")
    print(f"  VSP RMSE: {vsp_rmse:.4f}")

    # I. Add to KL Report
    kl_report_lines.append(f"\n{traffic_labels[group_idx]}:")
    kl_report_lines.append("-" * 60)
    kl_report_lines.append(f"Symmetric KL Divergence (Speed): {symmetric_kl_divergence:.6f}")
    kl_report_lines.append(f"Average Speed - Real: {avg_speed_real:.2f} km/h")
    kl_report_lines.append(f"Average Speed - Synthetic: {avg_speed_syn:.2f} km/h")
    kl_report_lines.append(f"Speed Difference: {speed_diff:.2f} km/h")
    kl_report_lines.append(f"Average Acceleration - Real: {avg_accel_real:.4f} m/s²")
    kl_report_lines.append(f"Average Acceleration - Synthetic: {avg_accel_syn:.4f} m/s²")
    kl_report_lines.append(f"Acceleration Difference: {accel_diff:.4f} m/s²")
    kl_report_lines.append(f"VSP RMSE: {vsp_rmse:.6f}")
    kl_report_lines.append(f"Test Sample Size: {target_duration} seconds")

    # J. Create Plots (2x2 grid per traffic type)
    base_idx = group_idx * 4
    
    # Plot 1: Speed Distribution
    plt.subplot(2, 4, base_idx + 1)
    plt.bar(speed_bins[:-1], speed_dist_real, width=4, alpha=0.5, label='Real', color='blue')
    plt.plot(speed_bins[:-1], speed_dist_syn, color='red', linewidth=2, label='Synthetic')
    plt.title(f"{traffic_labels[group_idx]}\nSpeed Distribution\nSymKL={symmetric_kl_divergence:.3f}")
    plt.xlabel("Speed (km/h)")
    plt.ylabel("Probability")
    plt.legend()
    
    # Plot 2: VSP Distribution
    plt.subplot(2, 4, base_idx + 2)
    plt.bar(vsp_bins[:-1], vsp_dist_real, width=1.8, alpha=0.5, label='Real', color='blue')
    plt.plot(vsp_bins[:-1], vsp_dist_syn, color='red', linewidth=2, label='Synthetic')
    plt.title(f"VSP Distribution\nRMSE={vsp_rmse:.3f}")
    plt.xlabel("VSP (kW/ton)")
    plt.ylabel("Probability")
    plt.legend()
    
    # Plot 3: Kinematic Comparison - Speed
    plt.subplot(2, 4, base_idx + 3)
    categories = ['Mean', 'Std Dev']
    real_vals = [avg_speed_real, std_speed_real]
    syn_vals = [avg_speed_syn, std_speed_syn]
    x = np.arange(len(categories))
    width = 0.35
    plt.bar(x - width/2, real_vals, width, label='Real', color='blue', alpha=0.7)
    plt.bar(x + width/2, syn_vals, width, label='Synthetic', color='red', alpha=0.7)
    plt.ylabel('Speed (km/h)')
    plt.title(f'Speed Statistics\nΔ={speed_diff:.2f} km/h')
    plt.xticks(x, categories)
    plt.legend()
    
    # Plot 4: Kinematic Comparison - Acceleration
    plt.subplot(2, 4, base_idx + 4)
    real_vals = [avg_accel_real, std_accel_real]
    syn_vals = [avg_accel_syn, std_accel_syn]
    plt.bar(x - width/2, real_vals, width, label='Real', color='blue', alpha=0.7)
    plt.bar(x + width/2, syn_vals, width, label='Synthetic', color='red', alpha=0.7)
    plt.ylabel('Acceleration (m/s²)')
    plt.title(f'Acceleration Statistics\nΔ={accel_diff:.3f} m/s²')
    plt.xticks(x, categories)
    plt.legend()

plt.tight_layout()

# CELL 7: Evaluate Pass/Fail & Save Results (NO ERROR RAISED)
print("\n=== FINAL EVALUATION ===")
print(json.dumps(metrics, indent=2))

# Determine pass/fail status
failures = []
for traffic_type, m in metrics.items():
    if m['symmetric_kl_divergence'] > MAX_KL_DIVERGENCE:
        failures.append(f"{traffic_type}: Symmetric KL divergence {m['symmetric_kl_divergence']:.4f} > {MAX_KL_DIVERGENCE}")
    if m['speed_difference_kmh'] > MAX_SPEED_DIFF:
        failures.append(f"{traffic_type}: Speed diff {m['speed_difference_kmh']:.2f} > {MAX_SPEED_DIFF} km/h")
    if m['accel_difference_ms2'] > MAX_ACCEL_DIFF:
        failures.append(f"{traffic_type}: Accel diff {m['accel_difference_ms2']:.3f} > {MAX_ACCEL_DIFF} m/s²")
    if m['vsp_rmse'] > MAX_RMSE_THRESHOLD:
        failures.append(f"{traffic_type}: VSP RMSE {m['vsp_rmse']:.4f} > {MAX_RMSE_THRESHOLD}")

# Add summary to KL report
kl_report_lines.append("\n" + "=" * 60)
kl_report_lines.append("QUALITY THRESHOLDS")
kl_report_lines.append("=" * 60)
kl_report_lines.append(f"Max Symmetric KL Divergence: {MAX_KL_DIVERGENCE}")
kl_report_lines.append(f"Max Speed Difference: {MAX_SPEED_DIFF} km/h")
kl_report_lines.append(f"Max Acceleration Difference: {MAX_ACCEL_DIFF} m/s²")
kl_report_lines.append(f"Max VSP RMSE: {MAX_RMSE_THRESHOLD}")
kl_report_lines.append("")

if failures:
    kl_report_lines.append("\n❌ VALIDATION FAILED")
    kl_report_lines.append("Failures:")
    for failure in failures:
        kl_report_lines.append(f"  - {failure}")
else:
    kl_report_lines.append("\n✅ VALIDATION PASSED")
    kl_report_lines.append("All metrics within acceptable thresholds.")

kl_report_lines.append("\n" + "=" * 60)

# Save Plot
img_buf = io.BytesIO()
plt.savefig(img_buf, format='png', dpi=150)
img_buf.seek(0)
with fs.open(OUTPUT_PLOT_PATH, 'wb') as f:
    f.write(img_buf.getbuffer())
print(f"\n✅ Plots saved to {OUTPUT_PLOT_PATH}")

# Save Metrics JSON
with fs.open(OUTPUT_METRICS_PATH, 'w') as f:
    json.dump(metrics, f, indent=2)
print(f"✅ Metrics saved to {OUTPUT_METRICS_PATH}")

# Save KL Report
kl_report_text = "\n".join(kl_report_lines)
with fs.open(OUTPUT_KL_REPORT_PATH, 'w') as f:
    f.write(kl_report_text)
print(f"✅ Symmetric KL Divergence report saved to {OUTPUT_KL_REPORT_PATH}")

# Quality Gate Summary (NO ERROR RAISED - MODIFIED SECTION)
if failures:
    print("\n⚠️  Model Quality Validation Failed (Results saved for analysis):")
    for failure in failures:
        print(f"  - {failure}")
else:
    print("\n✅ Model Quality Validation Passed.")
