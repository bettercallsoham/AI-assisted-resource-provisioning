# Phase 3 data and model evaluation

## Scope and status

The [protocol](PROTOCOL.md) was written before the final held-out slice was scored. This phase audited existing CSV files, evaluated the saved LSTM and Random Forest (RF) artifacts, and ran a separate leakage-safe version of the same LSTM-to-RF architecture. No original dataset or saved model was changed. No XGBoost or other replacement model was installed or evaluated. These results are **exploratory**, because the original source measurements and Claude preprocessing steps for `final_dataset.csv` are unavailable.

## Data reliability and provenance

The user reports that a teammate measured a laptop and that Claude assisted with preprocessing. The repository contains neither the original measurements nor the transformation instructions or script, so it is impossible to verify whether the final values, timestamps, units, missing-value handling, and labels faithfully represent those measurements. Git history records the processed dataset but no source-to-final lineage. The root and ML-service copies of `final_dataset.csv` are byte-identical (SHA-256 `d91fdb6eaaa61a139b49466e48d953b852ec4650e5a2ee7fd14c5c94273b975b`).

The final CSV has 5,000 rows from 2026-09-01 00:00:00 through 06:56:35 UTC, exactly 5 seconds apart, with no missing/nonfinite cells, duplicate timestamps, out-of-order rows, or negative values. Each numeric column has 5,000 distinct values. This is internally clean but does not prove the observations are genuine or that the preprocessing preserved them. CPU and memory values are within 0–100%, and network throughput is positive; original units and measurement scope remain unverified. See [data_audit.json](data_audit.json) for reproducible details.

All five numeric columns are strongly correlated in the final CSV: request rate correlates 0.951 with CPU, 0.956 with memory, 0.929 with network, and 0.892 with latency. Real workloads can be correlated, but without the raw source and transformation steps we cannot tell whether these relationships were measured, smoothed, or generated during preprocessing. They make model scores particularly dependent on this dataset's construction.

The available live `data/raw/metrics.csv` is 40 rows covering about 3 minutes 19 seconds on 2026-09-26. It cannot validate the 5,000-row file's origin. Its median request rate is 1.76 req/s versus 25.33 in training, CPU 4.2% versus 42.03%, and network 2,013 B/s versus 195,477 B/s. Its memory values are approximately `5.5e-10%`, which is implausible for a process/container percentage. The live metric in `workload-generator/app.py` divides process RSS by `memory_limit()`; the fallback accepts a potentially huge cgroup limit value. The network gauge uses host-wide `psutil.net_io_counters()` rather than per-workload traffic, so its scope is also different from a VM network reservation. These are code-supported instrumentation concerns, not proof of the final CSV's origin. The 12-row sample CSV has 60-second spacing and fractional CPU/memory values; it is not suitable as a compatible test set.

Even within the final CSV, the last 750 rows contain only 15 request-rate, 13 CPU, 23 memory, and 28 network observations above their respective training 75th-percentile thresholds. High-load safety behavior is therefore inconclusive under the predeclared minimum of 30 observations. The final slice has a lower median for each target than the training slice. A five-second next-row forecast also cannot establish useful long-range capacity decisions by itself.

## Leakage analysis and correction

`training/train_lstm.py` uses chronological train/validation/test segments and fits its scaler on training request rates. The earlier claim that it trained on RF test rows was incorrect. `training/train_random_forest.py::build_supervised_data`, however, generates *all* RF features using one saved LSTM before the RF split. For RF training rows, the upstream LSTM has already seen those request targets during its own training. For RF test rows, it has not. This creates an in-sample/out-of-sample feature mismatch and invalidates the old RF evaluation as a clean assessment of stacked forecasting. It is not direct leakage of the final RF test labels into the LSTM. The existing `models/rf_metrics.json` and `/train/random-forest` output remain **legacy metrics**, not reliable model-selection evidence.

`corrected_pipeline.py` uses expanding, past-only LSTM fits to generate out-of-fold request forecasts for RF training targets 980–3499. It fits the final LSTM on request targets before row 3500, uses rows 3500–4249 for early stopping, and evaluates rows 4250–4999 once. RF scaling and fitting use training features only. RF features for target row `t+1` include the predicted request rate for that row and actual resource observations no later than row `t`. The RF models in this evaluation are temporary in-memory models with the existing architecture and hyperparameters; the saved operational RF artifacts are unchanged. The first 980 targets are excluded from RF fitting to provide a causal warm-up period. Thus the corrected experiment estimates the architecture's performance, while the saved-artifact run describes the current deployment. It does not certify the deployed artifacts as leakage-safe.

The reported RF validation MAE is only a diagnostic: the upstream final LSTM used that same validation period for early stopping. Only the untouched final-test rows support the table below. This is one fixed chronological split from one processed session, so it does not measure variability across machines or collection runs.

## Held-out results

All values below are mean absolute error on the same 750 target rows (4250–4999) within the corrected experiment. The trailing-12 baseline is the better simple baseline for every target. Persistence, RMSE, WAPE, bias, and high-load errors are recorded in [corrected_results.json](corrected_results.json). The saved-artifact run covers 749 common rows because of its original RF indexing; its separate results are in [legacy_results.json](legacy_results.json).

| Target | Unit | Persistence | Trailing 12 mean | Existing architecture, leakage-safe fit | Improvement over best baseline |
| --- | --- | ---: | ---: | ---: | ---: |
| Next request rate (LSTM alone) | req/s | 2.6733 | 2.0644 | 2.0416 | 1.1% |
| Next CPU utilization (LSTM → RF) | percentage points | 4.3099 | 3.2578 | 3.3727 | -3.5% |
| Next memory utilization (LSTM → RF) | percentage points | 3.8058 | 2.9139 | 2.9505 | -1.3% |
| Next network throughput (LSTM → RF) | B/s | 22,899 | 16,768 | 17,054 | -1.7% |

The LSTM is slightly better than the request-rate moving average, but misses the predeclared 5% improvement gate. Each RF resource result is worse than its moving-average baseline by MAE and RMSE. The saved operational artifacts show the same qualitative pattern on their 749-row slice. These are observations on this CSV only. The high-load gate cannot be judged because every high-load test subset has fewer than 30 rows. We cannot claim that the existing pipeline reliably predicts laptop or VM demand, nor that another algorithm would perform better.

An RF-only result conditioned on an *actual future request rate* would use unavailable information and would not measure deployable performance. This phase therefore reports the LSTM request forecast separately and each RF target with the causally generated LSTM forecast, which is also the complete pipeline result. The simple per-resource baselines are independent of the LSTM. A future ablation may test whether the predicted-request feature adds value, without introducing a new model family.

## Reproduction

The run used Python 3.11, TensorFlow 2.18.0, Keras 3.15.1, NumPy 2.0.2, pandas 2.2.3, and scikit-learn 1.6.1 from an isolated copy of the existing `ml-service/requirements.txt`. The ambient TensorFlow 2.16.1 could not load the saved Keras model. The saved artifact hashes are:

| Artifact | SHA-256 |
| --- | --- |
| `lstm_model.keras` | `cc28f26f04dfd7abebda38e0ec167060bf80d96bdb554d1cb89c31d3e46fcae3` |
| `lstm_scaler.joblib` | `854440ae9e649be7e2ef68752710aadd00068992403b73aab5a3f5d7b1d4234` |
| `rf_cpu.joblib` | `3d1d3e8bf03688c40c3fc4c03555085719e631df156025015ca6e27295702a40` |
| `rf_memory.joblib` | `dc36e05abf247a406c37c3ecd77bc98be4f8fb9c8897a6b791e43b6162be23b0` |
| `rf_network.joblib` | `1894614a0e8290c2b6c8adce12a25d9e23bf94ce413f6d4caca9864f24f0e095` |
| `rf_scaler.joblib` | `7c98011f6cb49dd71ced46bb0a98e1ce9dc45b296c50417c9bf717186a43589a` |

From the repository root, with the ML-service requirements already available in the Python environment:

```powershell
py -3.11 -s -B ml-service/evaluation/audit_data.py final_dataset.csv ml-service/data/final_dataset.csv data/raw/metrics.csv ml-service/data/sample_metrics.csv
py -3.11 -s -B ml-service/evaluation/evaluate.py
py -3.11 -s -B ml-service/evaluation/evaluate.py --legacy-models
py -3.11 -s -B ml-service/evaluation/corrected_pipeline.py --epochs 30
py -3.11 -s -B -m unittest discover -s ml-service/evaluation -p 'test_*.py' -v
```

The checked-in JSON files contain the actual output of those commands. The corrected training is seeded but TensorFlow and parallel RF execution are not guaranteed bitwise identical on every machine. No tuning was performed against the final slice.

Validation performed here: the three new `unittest` checks passed; the two existing plain-function tests in `ml-service/tests/test_preprocessing.py` passed when called directly; the leakage-safe evaluation completed and wrote `corrected_results.json`. A `pytest` invocation could not run because `pytest` is not installed in the isolated Python environment; no additional dependency was installed for this phase. Python compilation of the evaluation scripts passed. No live model API or provisioning workflow was changed or exercised in Phase 3.

## Minimum evidence needed next

Collect new, unchanged Prometheus exports from the actual intended workload and host, retaining query definitions, timestamps, collection script revision, workload scenario, machine/container limits, and SHA-256 hashes. Before collecting, fix the live memory percentage and decide whether network demand means workload traffic, host traffic, or a VM limit. Measure at the same five-second cadence and record idle, steady, ramp-up, peak, and ramp-down periods across at least three separate sessions; reserve a complete later session for untouched evaluation. Ensure the held-out session contains at least 30 high-load target rows for each resource, plus sustained transitions, rather than 30 nearly identical adjacent samples. Do not merge or synthesize rows to make the training set larger. Retain raw files and use a versioned, deterministic preprocessing script. If these conditions cannot be met, demonstrate a functioning capacity decision workflow while describing model accuracy as unverified.
