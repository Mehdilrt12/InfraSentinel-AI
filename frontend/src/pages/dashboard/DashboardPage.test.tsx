import { screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import DashboardPage from "./DashboardPage";

const mocks = vi.hoisted(() => ({ getOne: vi.fn(), getPage: vi.fn() }));
vi.mock("../../api/resources", () => ({
  getOne: mocks.getOne,
  getPage: mocks.getPage,
}));
vi.mock("../../realtime/RealtimeProvider", () => ({
  useRealtime: () => ({
    status: "live",
    lastEventAt: "2026-08-30T12:00:00Z",
    events: [],
    reconnect: vi.fn(),
  }),
}));

describe("dashboard consolidé", () => {
  it("rend les statistiques du backend et les risques calculés", async () => {
    mocks.getOne.mockImplementation(async (path: string) =>
      path === "/dashboard/"
        ? {
            total_assets: 1,
            online: 1,
            offline: 0,
            critical: 0,
            warning: 1,
            anomalies: 2,
            vmware_hosts: 0,
            hyperv_hosts: 0,
            active_alerts: 1,
          }
        : [
            {
              metric_name: "system.memory.utilization",
              unit: "%",
              sample_count: 20,
              window_hours: 24,
              last_value: 82,
              rolling_average: 78,
              rate_of_change_per_hour: 2,
              trend: "increasing",
              risk_score: 70,
              rule_id: null,
              threshold: 90,
              estimated_threshold_breach_at: "2026-08-31T12:00:00Z",
              already_breached: false,
              confidence: "MEDIUM",
              is_estimate: true,
              disclaimer: "Estimation linéaire.",
            },
          ],
    );
    mocks.getPage.mockImplementation(async (path: string) => {
      if (path === "/machines/")
        return {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "m1",
              environment: "e1",
              source_type: "WINDOWS",
              external_id: "legion",
              hostname: "LEGION",
              ip_address: "192.168.1.3",
              os_information: {},
              status: "ONLINE",
              last_seen: "2026-08-30T12:00:00Z",
              agent_version: "2.0.0",
              metadata: {},
              created_at: "",
              updated_at: "",
            },
          ],
        };
      if (path === "/alerts/")
        return {
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: "a1",
              machine: "m1",
              hostname: "LEGION",
              timestamp: "",
              updated_at: "",
              type: "THRESHOLD",
              severity: "WARNING",
              source: "RULE",
              message: "RAM élevée",
              context: {},
              anomaly_score: null,
              recommendation: "",
              structured_recommendation: null,
              status: "NEW",
              dedup_key: "x",
              first_seen_at: "",
              last_seen_at: "2026-08-30T12:00:00Z",
              occurrences: 1,
              escalation_level: 0,
            },
          ],
        };
      return { count: 0, next: null, previous: null, results: [] };
    });
    renderWithApp(<DashboardPage />, { route: "/dashboard" });
    expect(await screen.findByText("Machines supervisées")).toBeInTheDocument();
    expect(screen.getByText("Synchronisation temps réel")).toBeInTheDocument();
    expect((await screen.findAllByText("LEGION")).length).toBeGreaterThan(0);
    expect(await screen.findByText("70")).toBeInTheDocument();
  });
});
