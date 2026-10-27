import assert from "node:assert/strict";
import test from "node:test";
import express from "express";
import { api } from "./api.js";

test("demo HTTP controls validate presets, stop safely, reset, and report outages", async () => {
  const nativeFetch = globalThis.fetch;
  let state = "IDLE";
  let scenario: string | null = null;
  let outage = false;
  const status = () => ({ state, scenario, phase: state === "RUNNING" ? "normal" : null,
    started_at: null, ended_at: null, requests: 0, successful: 0, failed: 0, error: null });
  globalThis.fetch = async (input, init) => {
    const url = String(input);
    if (url.includes("localhost:8000/demo/")) {
      if (outage) throw new Error("connection refused");
      if (url.endsWith("/start")) {
        const next = (JSON.parse(String(init?.body)) as { scenario: string }).scenario;
        if (state === "RUNNING" && scenario !== next) return Response.json({ detail: "Already running" }, { status: 409 });
        state = "RUNNING"; scenario = next;
      } else if (url.endsWith("/stop")) state = "STOPPED";
      else if (url.endsWith("/reset")) { state = "IDLE"; scenario = null; }
      return Response.json(status());
    }
    return nativeFetch(input, init);
  };
  const app = express(); app.use(express.json()); app.use("/api", api);
  const server = app.listen(0);
  const address = server.address();
  assert.ok(address && typeof address !== "string");
  const base = `http://127.0.0.1:${address.port}/api/demo`;
  const post = (path: string, body: object) => nativeFetch(`${base}${path}`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body),
  });
  try {
    assert.equal((await post("/start", { scenario: "shell-command" })).status, 422);
    assert.equal((await (await post("/start", { scenario: "normal" })).json()).state, "RUNNING");
    assert.equal((await (await post("/start", { scenario: "normal" })).json()).state, "RUNNING");
    assert.equal((await post("/start", { scenario: "high" })).status, 409);
    assert.equal((await post("/reset", {})).status, 409);
    assert.equal((await (await post("/stop", {})).json()).state, "STOPPED");
    assert.equal((await (await post("/stop", {})).json()).state, "STOPPED");
    assert.equal((await (await post("/reset", {})).json()).status, "RESET");
    outage = true;
    const failed = await (await nativeFetch(`${base}/status`)).json();
    assert.match(failed.error, /Workload service unavailable/);
  } finally { globalThis.fetch = nativeFetch; server.close(); }
});
