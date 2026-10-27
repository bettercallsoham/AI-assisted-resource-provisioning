import assert from "node:assert/strict";
import test from "node:test";
import { mergeForecastHistory } from "./forecastHistory.js";

test("forecast is plotted at its five-second target and matched to the later observation", () => {
  const origin = "2026-10-27T05:00:00Z";
  const target = "2026-10-27T05:00:05Z";
  const forecast = { origin_timestamp: origin, target_timestamp: target, predicted_request_rate: 8 };
  const issued = mergeForecastHistory([], [{ timestamp: origin, value: 4 }], forecast);
  assert.deepEqual(issued.map(point => [point.actual, point.predicted]), [[4, null], [null, 8]]);
  const realized = mergeForecastHistory(issued, [{ timestamp: target, value: 9 }], null);
  assert.deepEqual(realized.map(point => [point.actual, point.predicted]), [[4, null], [9, 8]]);
  assert.deepEqual(mergeForecastHistory(realized, [{ timestamp: target, value: 9 }], null), realized);
});

test("rejects a forecast with a wrong horizon", () => {
  assert.throws(() => mergeForecastHistory([], [], {
    origin_timestamp: "2026-10-27T05:00:00Z", target_timestamp: "2026-10-27T05:00:00Z",
    predicted_request_rate: 8,
  }), /five seconds/);
});
