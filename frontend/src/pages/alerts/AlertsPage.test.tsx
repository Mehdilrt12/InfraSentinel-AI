import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import AlertsPage, { alertOrigin } from "./AlertsPage";

const mocks = vi.hoisted(() => ({ getPage: vi.fn(), patchOne: vi.fn() }));
vi.mock("../../api/resources", () => ({
  getPage: mocks.getPage,
  patchOne: mocks.patchOne,
}));
vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: {
      id: 2,
      role: "VIEWER",
      is_active: true,
      is_superuser: false,
      customer: "tenant-a",
    },
  }),
}));

const alert = (id: string, severity: string, source: string) => ({
  id,
  machine: "m1",
  hostname: "LEGION",
  timestamp: "2026-08-30T12:00:00Z",
  updated_at: "2026-08-30T12:00:00Z",
  type: source === "ML" ? "ML_ANOMALY" : "THRESHOLD",
  severity,
  source,
  message: severity === "CRITICAL" ? "CPU critique" : "RAM élevée",
  context: {},
  anomaly_score: source === "ML" ? -0.4 : null,
  recommendation: "",
  structured_recommendation: null,
  status: "NEW",
  dedup_key: id,
  first_seen_at: "2026-08-30T12:00:00Z",
  last_seen_at: "2026-08-30T12:00:00Z",
  occurrences: 2,
  escalation_level: 0,
});

describe("centre d’incidents", () => {
  it("distingue règle, ML et prédiction", () => {
    expect(alertOrigin({ source: "RULE", type: "THRESHOLD" }).label).toBe(
      "Règle de supervision",
    );
    expect(alertOrigin({ source: "ML", type: "ML_ANOMALY" }).label).toBe(
      "Anomalie ML",
    );
    expect(alertOrigin({ source: "PREDICTIVE", type: "RISK" }).label).toBe(
      "Risque prédictif",
    );
  });
  it("filtre la sévérité localement sans inventer un filtre serveur", async () => {
    mocks.getPage.mockImplementation(async (path: string) =>
      path === "/alerts/"
        ? {
            count: 2,
            next: null,
            previous: null,
            results: [
              alert("a1", "CRITICAL", "RULE"),
              alert("a2", "WARNING", "ML"),
            ],
          }
        : { count: 0, next: null, previous: null, results: [] },
    );
    const actor = userEvent.setup();
    renderWithApp(<AlertsPage />, { route: "/alerts" });
    expect(await screen.findByText("CPU critique")).toBeInTheDocument();
    expect(screen.getByText("RAM élevée")).toBeInTheDocument();
    await actor.selectOptions(
      screen.getByLabelText("Filtrer par sévérité"),
      "CRITICAL",
    );
    expect(screen.getByText("CPU critique")).toBeInTheDocument();
    expect(screen.queryByText("RAM élevée")).not.toBeInTheDocument();
  });
});
