export type ForecastPoint = { timestamp: string; actual: number | null; predicted: number | null };
export type Observation = { timestamp: string; value: number };
export type TimedForecast = { origin_timestamp: string; target_timestamp: string; predicted_request_rate: number };

function timestamp(value: string): number {
  const parsed = Date.parse(value);
  if (!Number.isFinite(parsed)) throw new Error(`Invalid forecast timestamp: ${value}`);
  return parsed;
}

/** Pair a forecast with the observation at its target time, never its origin. */
export function mergeForecastHistory(previous: ForecastPoint[], observations: Observation[],
  forecast: TimedForecast | null, limit = 40): ForecastPoint[] {
  const points = new Map<number, ForecastPoint>();
  for (const point of previous) points.set(timestamp(point.timestamp), { ...point });
  for (const observation of observations) {
    if (!Number.isFinite(observation.value) || observation.value < 0) continue;
    const instant = timestamp(observation.timestamp);
    const current = points.get(instant);
    points.set(instant, { timestamp: new Date(instant).toISOString(),
      actual: observation.value, predicted: current?.predicted ?? null });
  }
  if (forecast && Number.isFinite(forecast.predicted_request_rate)) {
    const origin = timestamp(forecast.origin_timestamp);
    const target = timestamp(forecast.target_timestamp);
    if (target - origin !== 5_000) throw new Error("Forecast target must be five seconds after its origin");
    const current = points.get(target);
    points.set(target, { timestamp: new Date(target).toISOString(),
      actual: current?.actual ?? null, predicted: forecast.predicted_request_rate });
  }
  return [...points.entries()].sort(([left], [right]) => left - right)
    .slice(-limit).map(([, point]) => point);
}
