# AI-Driven Resource Provisioning System

This is a demonstrable prototype for AI-assisted resource provisioning on simulated on-premises infrastructure. The system keeps prediction, decision, and execution separate:

`workload -> Prometheus -> Node orchestration API -> ML prediction -> capacity decision -> best-fit placement -> dashboard`

## Components

- `workload-generator/app.py`: FastAPI workload that performs real CPU work and exposes Prometheus metrics.
- `workload-generator/generator.py`: configurable HTTP load generator.
- `ml-service`: chronological preprocessing, optional Keras LSTM training, Random Forest resource models, and TreeSHAP explanations.
- `decision-engine`: deterministic capacity checking and multi-resource Best-Fit Decreasing placement.
- `backend`: Express/TypeScript orchestration API. It does not duplicate ML or placement logic.
- `dashboard`: React, Material UI, and Recharts control-room view.
- `monitoring/prometheus.yml`: Prometheus scrape configuration for workload and cAdvisor.

## Local setup

Prerequisites: Python 3.12+, Node.js 22+, npm, and optionally Docker Desktop.

```powershell
cd e:\AIProvisioning\ai-resource-provisioning
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r workload-generator\requirements.txt
pip install -r decision-engine\requirements.txt
pip install -r ml-service\requirements.txt
cd backend; npm install; npm run build
cd ..\dashboard; npm install; npm run build
```

## Run locally

Open separate terminals from the repository root:

```powershell
cd workload-generator; uvicorn app:app --reload --port 8000
uvicorn decision-engine.main:app --reload --port 8002
cd ml-service; uvicorn main:app --reload --port 8001
cd backend; npm run dev
cd dashboard; npm run dev
```

The dashboard is normally at `http://localhost:5173`, the API at `http://localhost:3000/api`, and workload metrics at `http://localhost:8000/metrics`.

Train the models before expecting resource predictions and SHAP output:

```powershell
curl -X POST http://localhost:8001/train/random-forest
curl -X POST "http://localhost:8001/train/lstm&epochs=20"
```

The second command may be easier in PowerShell as:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/train/lstm?epochs=20'
```

Generate load:

```powershell
python workload-generator\generator.py --url http://localhost:8000/work --rate 5 --duration 60
python workload-generator\generator.py --url http://localhost:8000/work --rate 10 --duration 90 --spike
```

## Docker Compose

```powershell
docker compose up --build
```

Open `http://localhost:5173`. Services use Compose DNS names internally. The first ML image build is large because TensorFlow is included. Train models after startup:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/train/random-forest'
Invoke-RestMethod -Method Post -Uri 'http://localhost:8001/train/lstm?epochs=20'
```

Run the generator from the host with `http://localhost:8000/work`. Stop with `docker compose down`.

## Tests and verification

```powershell
python -m pip install pytest
python -m pytest decision-engine/tests ml-service/tests -q
cd backend; npm run build
cd ..\dashboard; npm run build
```

## Live demonstration

1. Start Compose and open the dashboard.
2. Train both model families through the ML API.
3. Start the generator at a low rate and wait for Prometheus samples.
4. Increase the rate or use `--spike`.
5. Watch request rate and workload latency change in Prometheus and the dashboard.
6. The backend sends the observed history to the ML service, then sends resource predictions to the decision engine.
7. The decision panel reports HOLD, SCALE_UP, or OVERLOAD with its bottleneck and reason.
8. Placement lists the deterministic VM-to-host assignments, while SHAP lists model feature contributions.
9. The event stream records forecast updates in memory for the current backend process.

## Limitations and manual steps

- TensorFlow and cAdvisor make Docker startup resource-intensive; local LSTM training can take time.
- The included CSV is a small training/demo dataset, not a claim of production accuracy. No accuracy numbers are fabricated.
- Prometheus container CPU/memory query labels differ across Docker environments; inspect Prometheus targets and adjust the cAdvisor queries if they return no series.
- The dashboard static build uses the default API URL `http://localhost:3000/api`; set `VITE_API_URL` when serving it from a different origin.
- Provisioning is intentionally simulated as Python host/VM objects. No real Hyper-V or VMware action occurs.
- Events are held in backend memory and reset when the backend restarts.
