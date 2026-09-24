from fastapi import FastAPI
from pydantic import BaseModel, Field

from capacity import assess_capacity
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


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.post("/decision")
def decision(request: DecisionRequest) -> dict:
    infrastructure = Infrastructure([Host(**host) for host in request.hosts], [VM(**vm) for vm in request.vms])
    result = assess_capacity(infrastructure, request.predicted.model_dump(), request.safety_threshold)
    return result.__dict__


@app.post("/placement")
def placement(request: DecisionRequest) -> dict:
    hosts = [Host(**host) for host in request.hosts]
    return place_vms(hosts, [VM(**vm) for vm in request.vms])