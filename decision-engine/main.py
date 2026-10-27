from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, FiniteFloat

from capacity import assess_capacity
from integration import IntegrationError, run_ml_pipeline
from models import Host, Infrastructure, VM
from placement import place_vms

app = FastAPI(title="Decision Engine")


class ResourceDemand(BaseModel):
    cpu: FiniteFloat = Field(ge=0)
    memory: FiniteFloat = Field(ge=0)
    network: FiniteFloat = Field(ge=0)


class HostRequest(BaseModel):
    id: str = Field(min_length=1)
    total_cpu: FiniteFloat = Field(gt=0)
    total_memory: FiniteFloat = Field(gt=0)
    total_network: FiniteFloat = Field(gt=0)
    allocated_cpu: FiniteFloat = Field(default=0, ge=0)
    allocated_memory: FiniteFloat = Field(default=0, ge=0)
    allocated_network: FiniteFloat = Field(default=0, ge=0)


class VMRequest(BaseModel):
    id: str = Field(min_length=1)
    cpu_required: FiniteFloat = Field(ge=0)
    memory_required: FiniteFloat = Field(ge=0)
    network_required: FiniteFloat = Field(ge=0)
    host_id: str | None = None
    current_cpu: FiniteFloat = Field(default=0, ge=0)
    current_memory: FiniteFloat = Field(default=0, ge=0)
    current_network: FiniteFloat = Field(default=0, ge=0)


class DecisionRequest(BaseModel):
    hosts: list[HostRequest]
    vms: list[VMRequest] = Field(default_factory=list)
    predicted: ResourceDemand | None = None
    safety_threshold: float = Field(default=0.8, gt=0, le=1)


class LiveDecisionRequest(BaseModel):
    hosts: list[HostRequest]
    vms: list[VMRequest] = Field(default_factory=list)
    safety_threshold: float = Field(default=0.8, gt=0, le=1)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


def infrastructure_from_request(request: DecisionRequest | LiveDecisionRequest) -> Infrastructure:
    try:
        return Infrastructure(
            [Host(**host.model_dump()) for host in request.hosts],
            [VM(**vm.model_dump()) for vm in request.vms],
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.post("/decision")
def decision(request: DecisionRequest) -> dict:
    infrastructure = infrastructure_from_request(request)
    result = assess_capacity(infrastructure, request.predicted.model_dump() if request.predicted else None,
                             request.safety_threshold)
    return result.__dict__


@app.post("/decision/live")
def live_decision(request: LiveDecisionRequest) -> dict:
    infrastructure = infrastructure_from_request(request)
    try:
        metrics, workload, resources, explanation, request_history = run_ml_pipeline()
    except IntegrationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    capacity = assess_capacity(
        infrastructure,
        {
            "cpu": resources["predicted_cpu"],
            "memory": resources["predicted_memory"],
            "network": resources["predicted_network"],
        },
        request.safety_threshold,
    )
    return {
        "current_metrics": metrics,
        "predicted_workload": workload,
        "request_history": request_history,
        "predicted_cpu": resources["predicted_cpu"],
        "predicted_memory": resources["predicted_memory"],
        "predicted_network": resources["predicted_network"],
        "capacity_status": {
            "bottleneck": capacity.bottleneck,
            "available_capacity": capacity.available_capacity,
            "safe_available_capacity": capacity.safe_available_capacity,
            "requested_increment": capacity.requested_increment,
            "units": capacity.units,
            "prediction_units": {"cpu": "%", "memory": "%", "network": "B/s"},
            "feasible": capacity.feasible,
        },
        "decision": capacity.decision,
        "reason": capacity.reason,
        "explanation": explanation,
        "placement": capacity.placement,
    }


@app.post("/placement")
def placement(request: DecisionRequest) -> dict:
    infrastructure = infrastructure_from_request(request)
    return place_vms(infrastructure.hosts, infrastructure.vms, request.safety_threshold)
