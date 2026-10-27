# Request-rate forecast alignment check

The saved LSTM takes the last 12 request-rate observations (req/s), scales them with its saved training-only MinMaxScaler, predicts one scaled value, and inverse-transforms it to req/s. The target is the observation **five seconds after the final input**. The model and scaler were not changed for this check.

The previous live path discarded Prometheus query timestamps and stamped current metrics with the backend call time. The backend then stored the one-step forecast in the same chart row as the current observation. The chart also drew a smoothed line through prediction values. This made forecasts appear to describe measurements at the wrong time.

The live path now requests 12 request-rate evaluations on a fixed five-second grid, rejects missing or stale counter data, queries the other metrics at the same origin time, and returns explicit origin and target timestamps. The backend stores a prediction at its target timestamp; the later observed value fills that same row. The chart uses actual time on the horizontal axis and discrete forecast markers. Prometheus `rate(...[30s])` remains a 30-second rolling rate evaluated every five seconds, so it is not an instantaneous request count.

## Read-only accuracy checks

```powershell
py -3.11 -s -B ml-service/evaluation/evaluate_forecast_session.py data/raw/sessions/quick_dev_01/metrics.csv
```

`quick_dev_01` is a **development** collection with 43 measurements, about five seconds apart. Its 31 eligible targets each use the preceding 12 rows and are paired with the next row's timestamp. Saved-artifact MAE was **6.330 req/s**; trailing-12 mean was **7.707 req/s**; persistence was **2.237 req/s**. For the 12 targets with an observed change of at least 3 req/s, LSTM MAE was **7.174 req/s** and persistence MAE was **3.863 req/s**. The saved scaler was fitted on training values from **2.540 to 53.104 req/s**; 36 of the 372 development input values were below that range. Training median was **25.330 req/s**, versus **8.121 req/s** in this collection. These are diagnostics from one short, non-independent session, not a validated generalization estimate.

The earlier chronological 750-row test of the processed training CSV reported LSTM MAE **2.0416 req/s**, trailing-12 mean **2.0644 req/s**, and persistence **2.6733 req/s**. That 1.1% LSTM improvement over the best baseline missed the predeclared 5% gate. Source measurements and preprocessing provenance for that CSV remain unverified. See [REPORT.md](REPORT.md) and [PROTOCOL.md](PROTOCOL.md).

During a bounded live normal-workload check, three successive forecast origin/target pairs were obtained through the updated inference code and matched to Prometheus values at their target times. Three points confirm the timestamp contract, not predictive accuracy. The running Docker services were not rebuilt during this local check; the updated decision engine and backend were run on separate local ports. A later test against rebuilt Compose images remains useful before presenting the dashboard.

The smallest justified next step for accuracy is to retain more raw, timestamped workload sessions with steady and changing loads, then compare the unchanged saved model to persistence on a complete later session. Retraining or replacing the model requires separate approval and evidence. A forecast should not be used as an automatic VM capacity reservation.
