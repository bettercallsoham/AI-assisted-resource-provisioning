from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from capacity import assess_capacity
from integration import IntegrationError, run_ml_pipeline
from models import Host, Infrastructure, VM
from placement import place_vms

app = FastAPI(title="Decision Engine")


class ResourceDemand(BaseModel):
    cpu: float = Field(ge=0)
    memory: float = Field(ge=0)
    network: float = Field(ge=0)


class DecisionRequest(BaseModel):
    hosts: list[dict]
    vms: list[dict] = []
    predicted: ResourceDemand
    safety_threshold: float = Field(default=0.8, gt=0, le=1)


class LiveDecisionRequest(BaseModel):
    hosts: list[dict]
    vms: list[dict] = Field(default_factory=list)
    safety_threshold: float = Field(default=0.8, gt=0, le=1)


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.post("/decision")
def decision(request: DecisionRequest) -> dict:
    infrastructure = Infrastructure([Host(**host) for host in request.hosts], [VM(**vm) for vm in request.vms])
    result = assess_capacity(infrastructure, request.predicted.model_dump(), request.safety_threshold)
    return result.__dict__


@app.post("/decision/live")
def live_decision(request: LiveDecisionRequest) -> dict:
    try:
        metrics, workload, resources, explanation = run_ml_pipeline()
    except IntegrationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    infrastructure = Infrastructure([Host(**host) for host in request.hosts], [VM(**vm) for vm in request.vms])
    capacity = assess_capacity(
        infrastructure,
        {
            "cpu": resources["predicted_cpu"],
            "memory": resources["predicted_memory"],
            "network": resources["predicted_network"],
        },
        request.safety_threshold,
    )
    placement = place_vms(infrastructure.hosts, infrastructure.vms)
    return {
        "current_metrics": metrics,
        "predicted_workload": workload,
        "predicted_cpu": resources["predicted_cpu"],
        "predicted_memory": resources["predicted_memory"],
        "predicted_network": resources["predicted_network"],
        "capacity_status": {
            "bottleneck": capacity.bottleneck,
            "predicted_demand": capacity.predicted_demand,
            "available_capacity": capacity.available_capacity,
        },
        "decision": capacity.decision,
        "reason": capacity.reason,
        "explanation": explanation,
        "placement": placement,
    }


@app.post("/placement")
def placement(request: DecisionRequest) -> dict:
    hosts = [Host(**host) for host in request.hosts]
    return place_vms(hosts, [VM(**vm) for vm in request.vms])