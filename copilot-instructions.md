# Project Implementation Instructions

IMPORTANT DEVELOPMENT RULE:

Implement the project incrementally.

Do NOT generate or modify the entire project at once unless explicitly asked.

The implementation order is:

Phase 1 — Workload application + Docker
Phase 2 — Prometheus monitoring
Phase 3 — Workload generation
Phase 4 — Data collection and preprocessing
Phase 5 — LSTM prediction
Phase 6 — Random Forest resource prediction
Phase 7 — Capacity-aware decision engine
Phase 8 — Best-Fit Decreasing placement
Phase 9 — SHAP explainability
Phase 10 — Backend orchestration
Phase 11 — React dashboard
Phase 12 — End-to-end integration and demonstration

For each phase:
1. Implement only that phase.
2. Run/test it.
3. Fix errors.
4. Do not move to the next phase until the current phase works.
5. Preserve existing working code.
6. Do not rewrite unrelated files.
7. Do not introduce new technologies without a clear reason.

When asked to implement a phase, first inspect the existing project structure and code before making changes.


You are helping me implement my final-year project:

"AI-Driven Resource Provisioning System for On-Premises Virtualized Infrastructure"

IMPORTANT:
This is a final-year student project and I need a WORKING, DEMONSTRABLE prototype quickly. Do not over-engineer it. Do not introduce Kubernetes, Kafka, Redis, microservices, OpenStack, Terraform, cloud deployment, authentication, or other unnecessary technologies unless explicitly requested later.

We are implementing the project phase by phase, but I want you to create the complete initial codebase with clean, modular code so we can implement and test each phase independently.

==================================================
PROJECT OBJECTIVE
==================================================

The system should demonstrate this complete flow:

Workload increases
        ↓
Infrastructure metrics are collected
        ↓
Data is preprocessed
        ↓
LSTM predicts future request/workload rate
        ↓
Random Forest predicts future CPU/memory/network requirements
        ↓
Capacity-aware decision engine checks available infrastructure capacity
        ↓
System decides HOLD / SCALE_UP / SCALE_DOWN / REBALANCE / OVERLOAD
        ↓
Best-Fit Decreasing places VMs/workloads on hosts
        ↓
SHAP explains why the ML model produced its prediction
        ↓
Dashboard displays the current state, prediction, decision, placement and explanation

The most important live demonstration should be:

Workload changes
→ metrics change
→ LSTM predicts future workload
→ Random Forest estimates future resources
→ decision engine makes a provisioning decision
→ placement/scaling state changes
→ dashboard shows the decision and reason.

==================================================
IMPORTANT IMPLEMENTATION PRINCIPLE
==================================================

Separate the system into:

1. Monitoring
2. Workload generation
3. ML prediction
4. Decision engine
5. Resource/VM placement simulation
6. Explainability
7. Backend API
8. Dashboard

ML should PREDICT.

The decision engine should DECIDE.

The infrastructure simulator/provisioning layer should EXECUTE the decision.

Do not make the ML model directly control infrastructure.

==================================================
TECHNOLOGY STACK
==================================================

Use:

Backend:
- Node.js
- Express.js
- TypeScript

ML:
- Python
- FastAPI for exposing ML APIs
- TensorFlow/Keras for LSTM
- scikit-learn RandomForestRegressor
- SHAP

Monitoring:
- Prometheus
- cAdvisor if useful for Docker container metrics

Workload:
- Python
- FastAPI

Frontend:
- React
- TypeScript
- Material UI
- Recharts

Infrastructure:
- Docker
- Docker Compose

Data:
- CSV/JSON initially
- Do NOT add PostgreSQL unless it is actually necessary
- Keep persistent storage simple for the first implementation

Communication:
- REST APIs
- HTTP between Node backend and Python ML service

==================================================
DIRECTORY STRUCTURE
==================================================

Use this structure:

ai-resource-provisioning/
│
├── backend/
│   ├── src/
│   │   ├── routes/
│   │   ├── controllers/
│   │   ├── services/
│   │   ├── types/
│   │   └── server.ts
│   ├── package.json
│   └── tsconfig.json
│
├── ml-service/
│   ├── models/
│   ├── training/
│   ├── prediction/
│   ├── explainability/
│   ├── data/
│   ├── main.py
│   └── requirements.txt
│
├── decision-engine/
│   ├── capacity.py
│   ├── scaling.py
│   ├── placement.py
│   ├── models.py
│   ├── main.py
│   └── tests/
│
├── workload-generator/
│   ├── app.py
│   ├── generator.py
│   ├── requirements.txt
│   └── tests/
│
├── monitoring/
│   └── prometheus.yml
│
├── dashboard/
│   └── React application
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── sample/
│
├── docker-compose.yml
├── .gitignore
└── README.md

==================================================
PHASE 1 — WORKLOAD APPLICATION
==================================================

Create a FastAPI workload application.

It should expose:

GET /

GET /work

GET /health

The /work endpoint should perform controlled CPU work so that increasing request volume creates measurable resource utilization.

Do NOT make the workload artificially report CPU usage.

The actual container/system should experience workload.

Return JSON containing:
- status
- processing time
- timestamp

Add basic application metrics that Prometheus can scrape if practical.

==================================================
PHASE 1 — WORKLOAD GENERATOR
==================================================

Create generator.py that can generate configurable HTTP requests against the workload application.

It should support:

- target URL
- requests per second
- duration
- gradual increase
- spike mode

Example:

python generator.py --url http://localhost:8000/work --rate 10 --duration 60

Also support a scenario such as:

NORMAL
→ INCREASE
→ HIGH LOAD
→ DECREASE

The workload generator should print:

timestamp
request count
successful requests
failed requests
average latency

Keep it simple.

==================================================
PHASE 1 — MONITORING
==================================================

Create Prometheus configuration.

Prometheus should scrape:

- workload application metrics
- cAdvisor/container metrics if available

We eventually need:

- request rate
- CPU utilization
- memory utilization
- network throughput
- response latency

Do not fabricate infrastructure metrics.

Where a metric is not available directly, clearly document how it is derived.

==================================================
PHASE 2 — DATA COLLECTION / PREPROCESSING
==================================================

Create Python modules for collecting/processing metrics.

Expected normalized dataset:

timestamp
request_rate
cpu_utilization
memory_utilization
network_throughput
response_latency

Implement:

- missing-value handling
- sorting by timestamp
- basic outlier handling
- normalization/scaling
- chronological train/validation/test split

IMPORTANT:
Do NOT randomly shuffle time-series data.

Create reusable preprocessing functions.

==================================================
PHASE 3 — LSTM WORKLOAD PREDICTION
==================================================

Implement an LSTM model for predicting future request/workload rate.

Input:
historical request-rate sequence

Output:
future request rate

Keep the model small enough to train on a normal laptop.

Example architecture:

Input sequence
→ LSTM
→ Dense
→ predicted request rate

Provide:

training script
prediction module
model saving/loading
scaler saving/loading

Save model to:

ml-service/models/lstm_model.keras

Save scaler appropriately.

Calculate:

- MAE
- RMSE

Also provide an evaluation script that generates:

actual vs predicted values

Do not claim accuracy numbers unless they are actually calculated.

==================================================
PHASE 4 — RANDOM FOREST RESOURCE PREDICTION
==================================================

Implement Random Forest regression for resource demand estimation.

Inputs can include:

- predicted request rate
- current request rate
- CPU utilization
- memory utilization
- network throughput
- response latency

Outputs:

- predicted CPU requirement
- predicted memory requirement
- predicted network requirement

Use either:
- one RandomForestRegressor per resource

or another simple, explainable approach.

Prefer separate models:

rf_cpu.pkl
rf_memory.pkl
rf_network.pkl

Provide:

training
prediction
evaluation
model loading

Calculate appropriate regression metrics such as:

MAE
RMSE
R²

Do not fabricate results.

==================================================
PHASE 5 — DECISION ENGINE
==================================================

Implement a deterministic capacity-aware resource provisioning engine.

Represent physical hosts using something like:

Host:
- id
- total_cpu
- total_memory
- total_network
- allocated_cpu
- allocated_memory
- allocated_network

Represent VMs:

VM:
- id
- cpu_required
- memory_required
- network_required
- host_id

The decision engine receives:

current infrastructure state

+

predicted resource requirements

and produces:

HOLD
SCALE_UP
SCALE_DOWN
REBALANCE
OVERLOAD

Use configurable safety thresholds.

Example:

if predicted demand exceeds available safe capacity:
    SCALE_UP

if predicted demand is comfortably below capacity:
    HOLD

Do NOT use arbitrary hardcoded decisions that have no explanation.

Return:

decision
bottleneck resource
predicted demand
available capacity
reason
timestamp

Example:

{
  "decision": "SCALE_UP",
  "bottleneck": "memory",
  "predicted_memory": 84,
  "available_memory": 76,
  "reason": "Predicted memory demand exceeds available safe capacity"
}

==================================================
PHASE 6 — BEST-FIT DECREASING PLACEMENT
==================================================

Implement VM placement.

Create several simulated physical hosts.

Example:

Host-01:
CPU: 8
RAM: 16 GB
Network: 1000 Mbps

Host-02:
CPU: 12
RAM: 32 GB
Network: 1000 Mbps

Host-03:
CPU: 16
RAM: 32 GB
Network: 10000 Mbps

Create VM objects with resource requirements.

Implement Best-Fit Decreasing for multi-resource placement.

Sort VMs by resource demand.

For each VM:

- identify hosts with sufficient capacity
- calculate a multi-resource fit score
- choose the best fitting feasible host
- update host allocation

The implementation must be deterministic and explainable.

Do NOT pretend this is a novel algorithm.

Expose the placement result clearly:

VM-01 → Host-02
VM-02 → Host-01
VM-03 → Host-02

Also return remaining host capacity.

==================================================
PHASE 7 — SHAP EXPLAINABILITY
==================================================

Use SHAP with the Random Forest model.

The system should explain resource predictions using features such as:

- request rate
- CPU utilization
- memory utilization
- network throughput
- response latency

Return feature contributions.

Example:

{
  "prediction": 82,
  "features": [
    {
      "name": "request_rate",
      "contribution": 0.61
    },
    {
      "name": "memory_utilization",
      "contribution": 0.22
    }
  ]
}

Important:

SHAP explains model contribution.

Do NOT describe SHAP as proving causation.

==================================================
PHASE 8 — PYTHON ML API
==================================================

Create a FastAPI ML service.

Endpoints:

GET /health

POST /predict/workload

POST /predict/resources

POST /explain/resources

POST /train/lstm

POST /train/random-forest

The APIs should return clean JSON.

Example:

POST /predict/workload

Input:
{
  "history": [100, 120, 140, 160, 180]
}

Output:
{
  "predicted_request_rate": 205
}

==================================================
PHASE 9 — NODE BACKEND
==================================================

Create the Express TypeScript backend.

It should act as the main orchestration API.

Suggested endpoints:

GET /api/health

GET /api/metrics

GET /api/infrastructure

GET /api/prediction

GET /api/decision

GET /api/placement

GET /api/explanation

GET /api/events

POST /api/workload

POST /api/provision

The backend should communicate with:

Prometheus
ML service
Decision engine

Do not duplicate ML logic in Node.

Do not duplicate placement logic in Node.

Python owns ML and decision/placement logic.

Node acts as the API/orchestration layer.

==================================================
PHASE 10 — EVENT / DECISION LOG
==================================================

Every important system event should be recorded in memory or a simple JSON file initially.

Examples:

WORKLOAD_INCREASED
LSTM_PREDICTION
RESOURCE_PREDICTION
CAPACITY_WARNING
SCALE_UP
SCALE_DOWN
VM_PLACED
REBALANCE
SHAP_EXPLANATION

Each event should contain:

timestamp
event_type
message
relevant values

Example:

{
  "timestamp": "...",
  "event_type": "SCALE_UP",
  "message": "Memory demand is predicted to exceed safe capacity",
  "details": {
    "predicted_memory": 84,
    "available_memory": 76
  }
}

==================================================
PHASE 11 — DASHBOARD
==================================================

Build a React + TypeScript + Material UI dashboard.

The dashboard should NOT be a generic monitoring dashboard.

The main purpose is to demonstrate the intelligence of the system.

Page 1:
"Intelligent Infrastructure"

Top cards:

1. Current Request Rate
2. CPU Utilization
3. Memory Utilization
4. Network Throughput

Prediction section:

- actual request rate
- LSTM predicted request rate
- actual vs predicted line chart

Resource prediction section:

Table:

Resource | Current | Predicted | Available Capacity | Status

Example:

CPU       71%       79%       85%       OK
Memory    78%       87%       80%       OVERLOAD
Network   61%       66%       90%       OK

Decision section:

Make this visually prominent.

Show:

CURRENT DECISION:
SCALE UP

Bottleneck:
MEMORY

Predicted:
87%

Available:
80%

Reason:
Predicted memory demand exceeds available safe capacity.

Placement section:

Host
VMs
CPU
Memory
Network
Remaining capacity

SHAP section:

Show horizontal bars for feature contributions.

Example:

Request Rate       +0.61
Memory Utilization +0.24
CPU Utilization    +0.09
Network            +0.05

Event log:

timestamp
event
reason

Also show a system status indicator:

NORMAL
WARNING
OVERLOAD
PROVISIONING

==================================================
REAL-TIME DEMONSTRATION
==================================================

The system must support this demo:

1. Start Docker Compose.

2. Open dashboard.

3. Initially show normal workload.

4. Start workload generator at a low rate.

5. Increase workload.

6. Monitoring metrics increase.

7. LSTM predicts increasing future workload.

8. Random Forest predicts increased resource demand.

9. Decision engine detects capacity pressure.

10. Dashboard changes to SCALE_UP or another appropriate decision.

11. Best-Fit Decreasing produces a placement decision.

12. SHAP shows which features influenced the Random Forest prediction.

13. Event log records all major decisions.

The dashboard should update periodically without requiring manual page refresh if practical.

Polling every few seconds is acceptable.

DO NOT implement WebSockets unless necessary.

==================================================
DOCKER COMPOSE
==================================================

Create a docker-compose.yml containing the minimum services required.

Initial services:

- workload
- prometheus
- backend
- ml-service

Add cAdvisor if practical.

Dashboard can either run separately during development or be included in Compose if simple.

Use environment variables for service URLs.

Do not hardcode localhost between Docker containers.

Within Docker Compose, services should communicate using service names.

==================================================
CODE QUALITY
==================================================

Rules:

1. Keep code simple.
2. Use clear function names.
3. Add type definitions.
4. Avoid unnecessary abstractions.
5. Add comments only where they explain non-obvious logic.
6. Do not generate enormous files.
7. Keep modules focused.
8. Do not duplicate logic.
9. Handle errors properly.
10. Use configuration/environment variables where appropriate.
11. Do not hardcode fake ML predictions.
12. Do not generate fake monitoring values.
13. Do not claim infrastructure actions occurred unless the simulator actually performed them.

==================================================
TESTING
==================================================

Add basic tests for:

- preprocessing
- LSTM input preparation
- Random Forest prediction
- capacity checking
- scaling decision
- Best-Fit Decreasing placement

Especially test:

Case 1:
Enough capacity → HOLD

Case 2:
CPU capacity exceeded → SCALE_UP, bottleneck CPU

Case 3:
Memory capacity exceeded → SCALE_UP, bottleneck memory

Case 4:
Multiple hosts → correct placement

Case 5:
No host can fit VM → OVERLOAD

==================================================
IMPORTANT SIMPLIFICATION
==================================================

For the first implementation, infrastructure provisioning can be simulated.

Represent hosts and VMs as software objects.

Do NOT require actual Hyper-V/VMware/OpenStack VM creation.

The architecture must however be designed so an actual virtualization backend could be connected later.

The important thing is that:

prediction
→ decision
→ placement
→ state change

actually happens in software.

==================================================
README
==================================================

Create a README explaining:

- project objective
- architecture
- directory structure
- setup
- how to run locally
- how to run Docker Compose
- how to start workload
- how to train models
- how to start dashboard
- how the prediction pipeline works
- how the decision engine works
- how the demo should be performed

==================================================
VERY IMPORTANT
==================================================

Do NOT just create placeholder files.

Implement the core functionality.

However, do not invent complex functionality that isn't required.

If something cannot reasonably be implemented yet, create a clean interface/stub and clearly mark it TODO rather than pretending it works.

Do not fabricate ML accuracy.

Do not fabricate infrastructure metrics.

Do not fabricate successful provisioning actions.

Use real generated workload and real calculations wherever possible.

After generating the code, provide:

1. Complete file tree
2. Files created
3. Commands to install dependencies
4. Commands to run locally
5. Commands to run Docker Compose
6. Order in which the services should be tested
7. Any files that still require manual configuration
8. Known limitations

Most importantly:

BUILD A SIMPLE WORKING SYSTEM FIRST.

Do not optimize architecture prematurely.

Do not add unnecessary technologies.

The final result should be something a final-year student can run locally with Docker and explain during a project demonstration.