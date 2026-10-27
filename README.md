# AI-Driven Resource Provisioning System

This final-year prototype monitors a local workload, forecasts its next request rate from the planned demo scenario or a saved LSTM outside Demo Mode, estimates next-step CPU/memory/network observations with saved Random Forests, validates **explicit** VM resource requests against simulated hosts, and lets an operator approve a **simulated** allocation. It does not create or resize real VMs.

## Objective and actual architecture

The objective is a demonstrable, capacity-aware decision workflow for on-premises infrastructure. Forecasts are visible operational signals; they do not automatically become VM reservations because no measured conversion policy exists.

```text
Dashboard Demo Mode -> backend bounded scenario control -> workload /work
Workload /work -> /metrics -> Prometheus -> decision-engine /decision/live
                                          -> scenario or LSTM request-rate forecast
                                          -> Random Forest CPU/memory/network indicators + tree-path explanations
Dashboard <- backend /api/state <- capacity and placement decision on explicit VM request
Dashboard -> backend proposal -> operator approve/decline -> simulated adapter
                                                   -> verify host limits -> commit or fail unchanged
```

| Component | Technology | Current role |
| --- | --- | --- |
| Workload and telemetry | FastAPI, psutil, Prometheus | Generates CPU work and exports workload metrics. The bounded Demo Mode presets reuse the collection scenario engine. cAdvisor is optional and is not used by the collection queries. |
| ML service | FastAPI, TensorFlow/Keras, scikit-learn | Loads existing LSTM and three RF artifacts for one-step inference and explanation. |
| Decision engine | FastAPI/Python | Checks vCPU, GiB, and B/s limits at 80% safety headroom; proposes multi-resource placement. |
| Backend | Express/TypeScript | Combines live signals with decisions; stores an in-memory simulated host inventory and operator proposals. |
| Dashboard | React, Material UI, Recharts | Shows measurements, model indicators, capacity, proposal status, verification, and errors. |

The scenario projection forecasts the demo's next 30-second request rate; outside Demo Mode, the LSTM predicts the next-row request rate (req/s). RF outputs predict CPU and memory utilization (%) and network throughput (B/s). VM requirements and host capacities use **vCPU, GiB, and B/s** respectively. The displayed network forecast is informational; it does not set a bandwidth reservation. For an existing pinned VM, the decision engine checks only the requested increase above its current allocation. A feasible decision has a complete placement; an infeasible plan has no executable placements.

## Model evidence and data limits

The saved models load and infer, but [the Phase 3 evaluation](ml-service/evaluation/REPORT.md) did **not** establish reliable accuracy. On the available 750-row chronological test slice, LSTM request-rate MAE improved about 1.1% over the better simple baseline, below the predeclared 5% gate. RF CPU, memory, and network MAE were all worse than a trailing-mean baseline. High-load test samples were insufficient. Keep the current models for the integration demo; do not claim they outperform baselines or retrain them without a new approved evaluation.

The deployed RF artifacts still come from the legacy training path with an in-sample upstream LSTM feature mismatch. Phase 3's leakage-safe experiment was separate and deliberately did not replace these artifacts. An apparently precise live RF number is therefore not a validated capacity requirement.

`final_dataset.csv` has 5,000 internally clean rows, but its original laptop measurements and Claude preprocessing steps are unavailable, so its provenance, transformations, and units cannot be verified. The separately captured `quick_dev_01` session has 43 valid rows across six short workload phases: it verifies telemetry collection and variation, **not** predictive accuracy. Preserve all raw session files. Collection semantics and multi-session instructions are in [data/collection/README.md](data/collection/README.md). No complete independent held-out live session has been evaluated.

## Prerequisites and saved artifacts

- Docker Desktop with Compose is the simplest full-stack route on Windows. Node.js 22+ and Python 3.11/3.12 are needed for local development and the host workload generator. Python 3.13 is not suitable for the pinned TensorFlow 2.18 environment.
- The existing `ml-service/models/` directory must contain `lstm_model.keras`, `lstm_scaler.joblib`, `rf_scaler.joblib`, and `rf_cpu.joblib`, `rf_memory.joblib`, `rf_network.joblib` **before** building the ML image. These artifacts are ignored by Git and are not created automatically. Preserve them; the training endpoints are not part of the demo.
- Ports 8000 (workload), 9090 (Prometheus), 8001 (ML), 8002 (decision engine), 3000 (backend), and 5173 (dashboard) must be free.

## Start the full demo with Docker Compose

From PowerShell at the repository root:

```powershell
docker compose up -d --build workload prometheus ml-service decision-engine backend dashboard
docker compose ps
Invoke-RestMethod http://localhost:8000/health
Invoke-RestMethod http://localhost:9090/-/ready
Invoke-RestMethod http://localhost:8001/health
Invoke-RestMethod http://localhost:8002/health
Invoke-RestMethod http://localhost:3000/api/health
```

Open `http://localhost:5173` and use **Demo Mode → Start Demo**. The dashboard asks the backend to start a bounded normal → high → cooldown scenario inside the workload service. The UI sends only a preset name; it cannot run shell commands or choose a target URL. **Stop Demo** stops future requests, and **Reset Simulated State** clears the backend's in-memory VM allocations and proposal history after traffic stops. Reset does not delete Prometheus samples or datasets. The forecast chart needs 12 recent five-second request-rate samples; allow roughly one minute of traffic before expecting the full live path. An idle latency query may return `NaN`, which the dashboard reports as a partial-service warning while capacity checking remains available.

To check that the services and real metric counters are available:

```powershell
Invoke-RestMethod http://localhost:3000/api/demo/status
Invoke-RestMethod http://localhost:8000/metrics | Select-String 'workload_requests_total|workload_cpu_utilization_percent'
Invoke-RestMethod 'http://localhost:9090/api/v1/query?query=workload_requests_total'
```

The old command-line generator remains available for independent collection or troubleshooting. Install its dependency once if needed (`python -m pip install -r workload-generator/requirements.txt`):

```powershell
python workload-generator/generator.py --url http://localhost:8000/work --rate 5 --duration 120 --scenario
```

The generator uses fractional pacing; requested rate is an attempt, and completed request rate must be read from monitoring. Stop the stack with `docker compose down` when finished. This does not erase the saved datasets or model artifacts.

### Windows local development

If running the application processes directly on Windows, first prepare the existing dependencies from the repository root:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r workload-generator\requirements.txt -r decision-engine\requirements.txt -r ml-service\requirements.txt
cd backend; npm.cmd ci
cd ../dashboard; npm.cmd ci
cd ..
```

Run these commands in **separate terminals**, each starting from the repository root:

```powershell
cd workload-generator; ..\.venv\Scripts\python.exe -m uvicorn app:app --port 8000
cd ml-service; ..\.venv\Scripts\python.exe -m uvicorn main:app --port 8001
cd decision-engine; ..\.venv\Scripts\python.exe -m uvicorn main:app --port 8002
cd backend; npm.cmd run dev
cd dashboard; npm.cmd run dev
```

Prometheus must still be running. For a native Prometheus installation, replace the Docker-only `workload:8000` target in [monitoring/prometheus.yml](monitoring/prometheus.yml) with an address reachable from Prometheus. Host-local network measurements may include unrelated traffic, so use Docker Compose for comparable telemetry. Do not use `uvicorn decision-engine.main:app`: the hyphenated directory is not a Python package name.

## Demonstrate the workflow

1. Click **Start Demo** or **Run Normal Workload**. Confirm the successful-request counter rises, then show the request-rate chart, scenario forecast, RF indicators, and tree-path explanations. These are forecasts, not allocations. **Stop Demo** is safe to click again after stopping.
2. Click **Propose 2 vCPU / 4 GiB VM**. The decision engine returns `RECOMMEND` only when the entire VM fits a host's safe capacity. The proposal remains `PENDING_APPROVAL`; host allocations have not changed.
3. Click **Approve & simulate**. The backend rechecks capacity, applies placements to a copy of its simulated inventory, verifies every requested increment and host limit, then commits it. The proposal becomes `SUCCEEDED` and host allocations increase. Use `GET /api/infrastructure` to confirm.
4. Click **Run High-Load** after the current scenario ends or is stopped. Observe the actual response, then click **Try Unsafe Allocation**. High traffic is not converted automatically into a VM reservation; this separate explicit request exceeds host limits. It becomes `REJECTED`, has no executable placement, and cannot be approved.
5. For recovery behavior, create another feasible proposal and click **Test failure**. The simulated adapter fails after its first tentative assignment; the proposal becomes `FAILED`, verification reports failure, and the original inventory remains unchanged. **Decline** records an operator rejection without executing.
6. If ML or monitoring is unavailable, the dashboard shows the error. When the decision engine remains available, explicit capacity checking still works; a failed model call does not silently become a successful prediction.

The backend demo accepts **new VM requests**; the underlying decision engine also supports pinned incremental-resize checks through its direct API. The simulation has no authentication, durable storage, or hypervisor adapter. Its inventory, VM list, and proposal history reset when the backend process restarts. Run it only in a trusted local demo environment. No live VM migration, energy optimization, SLA enforcement, XGBoost, or multi-laptop architecture is implemented.

Demo traffic presets are limited to 5 or 20 requested HTTP calls per second for 90 seconds, or a 105-second walkthrough. Actual completed rate depends on host performance and is measured by Prometheus. The controller keeps status in one workload process; run one Uvicorn worker. The dashboard polls the backend for state every five seconds and the demo controller every two seconds. If a service is down, the dashboard shows a partial or unavailable state with the failed action rather than inventing measurements. Demo Mode does not write telemetry sessions for model training; use the separate [collection workflow](data/collection/README.md) for reproducible sessions.

### Direct API demonstration

| Endpoint | Purpose |
| --- | --- |
| `GET /api/state` | Current monitoring, predictions, capacity result, proposal, errors, and events. |
| `GET /api/infrastructure` | Current committed simulated host allocations and provisioned VM records. |
| `GET /api/demo/status` | Current bounded workload scenario, phase, real HTTP request counts, and errors. |
| `POST /api/demo/start` | Start the `walkthrough`, `normal`, or `high` preset. Starting the same running preset is idempotent; a different concurrent preset returns 409. |
| `POST /api/demo/stop` | Stop the current scenario; repeated stops return the current status. |
| `POST /api/demo/reset` | After traffic stops, clear demo status and the backend's in-memory simulated inventory and proposals. |
| `POST /api/proposals` | Validate `{ "vms": [...] }` with the decision engine and create a pending or rejected proposal. |
| `POST /api/proposals/:id/approve` | Human approval, fresh capacity check, simulated execution, and verification. `{ "simulate_failure": true }` tests failure without changing inventory. |
| `POST /api/proposals/:id/reject` | Record operator decline without executing. |

Approval and rejection are explicit API calls; dashboard polling alone never executes a proposal. HTTP 422 identifies invalid request data, 409 an invalid proposal state, and 503 an unavailable decision service. A simulated adapter failure returns a proposal with `status: "FAILED"` and `verification.passed: false`.

```powershell
$body = '{"vms":[{"id":"demo-vm","cpu_required":2,"memory_required":4,"network_required":100000}]}'
$proposal = Invoke-RestMethod -Method Post -Uri http://localhost:3000/api/proposals -ContentType 'application/json' -Body $body
$proposal | Select-Object id,status,reason
Invoke-RestMethod -Method Post -Uri "http://localhost:3000/api/proposals/$($proposal.id)/approve" -ContentType 'application/json' -Body '{}'
Invoke-RestMethod http://localhost:3000/api/infrastructure
```

## Validation commands

```powershell
cd backend
npm.cmd test
cd ../dashboard
npm.cmd run build
cd ..
python -m unittest discover -s workload-generator -p 'test_*.py' -v
python -m unittest discover -s decision-engine/tests -p 'test_*.py' -v
python -m unittest discover -s data/collection -p 'test_*.py' -v
```

The Python tests require the pinned service dependencies, including `httpx`. The detailed Phase 3 evaluation protocol and results remain in `ml-service/evaluation/`; do not repeat final-test model selection against the same held-out slice.
