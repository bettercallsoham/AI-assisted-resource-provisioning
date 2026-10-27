# Phase 3 evaluation protocol (locked before the held-out evaluation)

## Question and immutable inputs

Assess the existing one-step LSTM request-rate forecaster and three Random Forest resource regressors. Do not replace the saved models in `ml-service/models/` or edit either source CSV. Record SHA-256 hashes of every dataset and model artifact used. The origin of `final_dataset.csv` is presently unverified; metrics on it are exploratory until provenance is supplied.

## Timing and targets

Sort by parsed UTC timestamp and reject missing or duplicate timestamps. An input ending at row `t` predicts row `t+1`. The nominal spacing is five seconds in `final_dataset.csv`; report actual interval statistics and gaps. Use the same eligible target rows for persistence, rolling-mean, LSTM, RF, and full-pipeline comparisons. No feature or scaler may use information later than its forecast origin. The targets and units are request rate (req/s), CPU utilization (percentage points), memory utilization (percentage points), and network throughput (B/s). These are observations, not VM allocations.

## Split and leakage rules

Use chronological 70% train, 15% validation, 15% final test by **target row index**, with boundaries recorded in the result. Hold the final 15% aside until the protocol and model choices are fixed. Fit scalers on training rows only. Early stopping and any tuning may use validation but not test. RF training must not consume LSTM predictions from a model fitted on the same RF target rows as if those predictions were out-of-sample. Use expanding, past-only folds for stacked training features, or clearly label results from the existing in-sample RF feature construction as legacy/non-comparable. An upstream LSTM used on final test may be fitted on train and selected on validation, never on test. Never use actual `request_rate[t+1]` as an RF input when predicting resources at `t+1`.

## Baselines and metrics

- Request rate: persistence (`request_rate[t]`) and trailing-12 mean.
- Each resource: persistence (`resource[t]`) and trailing-12 mean.
- Primary metric: MAE in the target unit. Secondary: RMSE, WAPE = `sum(abs(error)) / sum(abs(actual))` when the denominator is nonzero, and mean signed error. Report R² only as supplementary.
- Report sample count and metrics for the full test and for high-load targets (at or above the training 75th percentile). Report underprediction MAE in that subset. Do not calculate per-sample MAPE at zero or near-zero demand.
- Evaluate the LSTM forecast alone; each RF target with the actual upstream forecast supplied by the chosen leakage-safe protocol; and the combined LSTM-to-RF path on identical test origins. If an independent RF-stage result cannot be defined without an oracle or feature-distribution mismatch, state that and report the conditional and end-to-end result distinctly.

## Predeclared acceptance gate

For each target, the existing model must reduce MAE by at least 5% versus the **better** simple baseline on the same held-out origins and must not increase RMSE. If the high-load subset has at least 30 rows, its MAE and mean underprediction must each be no more than 10% worse than the better baseline on that subset. With fewer than 30 high-load rows, mark this safety check inconclusive rather than passing it. Full-pipeline resource predictions must satisfy the same gate. A credible reliability claim additionally needs verifiable real-data provenance, stable metric definitions, and an independent measured session with workload regimes represented. If those prerequisites are absent, classify the result as exploratory and do not claim the model is production-reliable or better than an alternative.

The 5% margin is a project selection rule, not an externally validated service-level threshold. This phase may conclude that the available data cannot decide model adequacy. No XGBoost experiment is authorized by this protocol.
