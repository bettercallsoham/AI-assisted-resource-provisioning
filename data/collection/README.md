# Reproducible workload telemetry sessions

## What the metrics mean

These measurements describe the **workload service process/container**, not a physical host or a VM allocation. They are observed indicators. A network throughput observation is not a bandwidth reservation.

| CSV field | Prometheus source | Unit and scope |
| --- | --- | --- |
| `timestamp` | Latest timestamp among the five returned Prometheus samples | UTC; the collector rejects samples more than two polling intervals apart and repeated timestamps. |
| `request_rate` | `rate(workload_requests_total{endpoint="work",status="success"}[30s])` | Successful `/work` requests per second, averaged over 30 seconds. |
| `cpu_utilization` | `workload_cpu_utilization_percent` | Workload **process** CPU percent from `psutil.Process.cpu_percent`; it may exceed 100 on several cores. |
| `memory_utilization` | `workload_memory_utilization_percent` | Workload process RSS divided by the smaller finite cgroup memory limit or host physical RAM, times 100. Inspect `workload_process_rss_bytes` and `workload_memory_limit_bytes` to verify the numerator and denominator. An unlimited or sentinel cgroup limit is ignored. This is not total container memory use. |
| `network_throughput` | `workload_network_throughput_bytes_per_second` | Sum of sent and received **non-loopback network-namespace** bytes per second, using the difference between `/metrics` scrapes. In the dedicated Docker container it includes that namespace's traffic, including monitoring traffic; when run directly on a host, unrelated host traffic may enter the value. It is neither per-request traffic nor available link capacity. The first scrape yields zero. |
| `response_latency` | Histogram sum/count rates over 30 seconds, multiplied by 1,000 | Request-weighted mean `/work` latency in milliseconds. It can be unavailable after an idle period with no requests. |

Prometheus scrapes every five seconds in `monitoring/prometheus.yml`. The collector polls the five queries sequentially, so their timestamps may differ. It writes the exact returned API JSON for every poll to `prometheus_responses.ndjson` before producing a CSV row. A row is written only when all five values are present, finite, nonnegative, fresh, and close in time. No interpolation, smoothing, imputation, generated samples, or random splitting occurs. The CSV contains query results, not raw host counters; the NDJSON retains the source responses and query definitions are recorded in the manifest.

The existing `final_dataset.csv` predates this procedure. Its original laptop measurements and Claude preprocessing are unavailable, so these definitions cannot be retroactively assigned to that file. The existing `data/raw/metrics.csv` is also preserved. The older `collect_metrics.py` still defaults to overwriting that legacy path; use `collect_session.py` for new evidence.

An older, untracked `documentation.md` describes a 322-row live run, while the current `data/raw/metrics.csv` has 40 rows. The claimed older run cannot be reconstructed from the files currently present. Treat that account as historical, not as evidence for these new sessions.

## Collect separate sessions

1. Start Docker Desktop and the existing Compose stack from the repository root: `docker compose up --build`. Verify `http://localhost:9090/-/ready`, the `workload` target in Prometheus, and `http://localhost:8000/metrics`. Check that `workload_process_rss_bytes`, `workload_memory_limit_bytes`, and `workload_memory_utilization_percent` are positive and that `RSS / limit * 100` matches the percentage. Record the container memory limit and the host RAM in your lab notes. Run the workload in its own Docker network namespace; host-local network traffic is not a comparable target.
2. In a second terminal, collect a named **development** session. In a third terminal, immediately run the changing workload. Example:

   ```powershell
   python data\collection\collect_session.py --session-id dev_01 --role development --duration 1860 --interval 5 --scenario "workload_scenario.py --phase-duration 300 --event-log data/raw/sessions/dev_01/scenario.jsonl" --environment "Docker Compose; host RAM and container limit recorded in lab notes"
   python data\collection\workload_scenario.py --url http://localhost:8000/work --phase-duration 300 --event-log data/raw/sessions/dev_01/scenario.jsonl
   ```

   The workload command belongs in the third terminal. Wait until the collector creates its session directory. Six 300-second phases give low, medium, high, spike, decrease, and mixed regimes. The extra collection minute allows startup/warm-up and cooldown. `scenario.jsonl` records each actual phase start/end and request counts; its hash is included in the collector manifest if the scenario finishes before collection ends. Exact times are preserved, not aligned by fabrication.
3. Repeat with a new ID such as `dev_02` on a separate run. After the procedure and preprocessing rules are fixed, collect a **later complete** session as `heldout_01 --role heldout`. Keep its entire directory out of model fitting, scaler fitting, threshold selection, preprocessing decisions, and debugging. A test session with errors should be marked as such and replaced by another later untouched session rather than patched.
4. Each session creates `data/raw/sessions/<session-id>/prometheus_responses.ndjson`, `metrics.csv`, and `manifest.json`, plus `scenario.jsonl` when the scenario uses `--event-log`. The manifest records the declared role and scenario, exact queries and units, requested cadence, start/end times, skipped-row reasons, script hashes, Git revision when available, platform, row counts, and data-file hashes. Existing session directories cause an error instead of being overwritten.

Check the manifest status, nonzero complete-row count, skipped reasons, and hashes after **each** run:

```powershell
Get-Content data\raw\sessions\dev_01\manifest.json
Get-FileHash data\raw\sessions\dev_01\metrics.csv -Algorithm SHA256
Get-FileHash data\raw\sessions\dev_01\prometheus_responses.ndjson -Algorithm SHA256
python ml-service\evaluation\audit_data.py data\raw\sessions\dev_01\metrics.csv
```

The CSV audit reports missing values, duplicate and out-of-order timestamps, ranges, and cadence. Compare it with the manifest. Raw NDJSON polls may contain missing/NaN responses during idle traffic; those are retained and counted as skipped CSV rows. Do not convert absent latency to zero. Keep raw files unchanged and implement any later transformation as a versioned, deterministic script, with decisions made using development sessions only.

Before treating the data as useful for model selection, verify sustained variation in every target, plausible ranges and metric scope, adequate high-load observations, and an untouched later session. The Phase 3 protocol requires at least 30 high-load **target rows** for each resource, but adjacent five-second readings are correlated; several sustained transitions and independent sessions matter more than an artificial row count. If the workload does not vary memory or network materially, this setup cannot support a credible memory or network prediction claim. Do not retrain existing models or evaluate the held-out session until the next phase is approved.


