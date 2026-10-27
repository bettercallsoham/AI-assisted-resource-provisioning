export type DemoScenario = "walkthrough" | "normal" | "high";
export type DemoStatus = {
  state: "IDLE" | "RUNNING" | "STOPPING" | "STOPPED" | "COMPLETED" | "FAILED";
  scenario: DemoScenario | null; phase: string | null;
  started_at: string | null; ended_at: string | null;
  requests: number; successful: number; failed: number; error: string | null;
};

const workloadUrl = process.env.WORKLOAD_URL ?? "http://localhost:8000";

export class DemoServiceError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

async function call(path: string, method: "GET" | "POST", body?: object): Promise<DemoStatus> {
  let response: Response;
  try {
    response = await fetch(`${workloadUrl}${path}`, {
      method, headers: body ? { "content-type": "application/json" } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(15_000),
    });
  } catch {
    throw new DemoServiceError(503, "Workload service unavailable. Start or rebuild the workload and Prometheus services.");
  }
  if (!response.ok) {
    let detail = "Workload control failed";
    try {
      const payload = await response.json() as { detail?: string };
      detail = typeof payload.detail === "string" ? payload.detail : detail;
    } catch { /* Keep the generic message. */ }
    throw new DemoServiceError(response.status === 404 ? 503 : response.status,
      response.status === 404 ? "Demo control is unavailable. Rebuild the workload service image." : detail);
  }
  return response.json() as Promise<DemoStatus>;
}

export const demoStatus = () => call("/demo/status", "GET");
export const startDemo = (scenario: DemoScenario) => call("/demo/start", "POST", { scenario });
export const stopDemo = () => call("/demo/stop", "POST");
export const resetWorkloadDemo = () => call("/demo/reset", "POST");
