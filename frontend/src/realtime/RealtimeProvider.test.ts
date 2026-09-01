import { describe, expect, it } from "vitest";
import {
  nextReconnectDelay,
  resolvePollInterval,
  shouldAcceptRealtimeEvent,
} from "./RealtimeProvider";
import type { RealtimeEvent } from "../types/api";

const event = (sequence: number): RealtimeEvent => ({
  sequence,
  event_type: "metric.update",
  aggregate_id: "machine-1",
  payload: {},
  created_at: "2026-08-30T12:00:00Z",
});

describe("résilience temps réel", () => {
  it("accepte uniquement une séquence plus récente", () => {
    expect(shouldAcceptRealtimeEvent(10, event(11))).toBe(true);
    expect(shouldAcceptRealtimeEvent(10, event(10))).toBe(false);
    expect(shouldAcceptRealtimeEvent(10, event(9))).toBe(false);
  });
  it("rejette une séquence non numérique", () =>
    expect(shouldAcceptRealtimeEvent(0, event(Number.NaN))).toBe(false));
  it("applique un backoff exponentiel borné", () => {
    expect(nextReconnectDelay(0, 0.5)).toBe(1_000);
    expect(nextReconnectDelay(3, 0.5)).toBe(8_000);
    expect(nextReconnectDelay(10, 0.5)).toBe(30_000);
  });
  it("ajoute un jitter contrôlé", () => {
    expect(nextReconnectDelay(1, 0)).toBe(1_600);
    expect(nextReconnectDelay(1, 1)).toBe(2_400);
  });
  it("borne le polling et rejette les valeurs non numériques", () => {
    expect(resolvePollInterval(2_000)).toBe(10_000);
    expect(resolvePollInterval("45000")).toBe(45_000);
    expect(resolvePollInterval("30s")).toBe(30_000);
  });
});
