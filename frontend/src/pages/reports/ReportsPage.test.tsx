import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import ReportsPage from "./ReportsPage";

const mocks = vi.hoisted(() => ({
  listReports: vi.fn(),
  requestReport: vi.fn(),
}));

vi.mock("../../api/reports", () => ({
  listReports: mocks.listReports,
  requestReport: mocks.requestReport,
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

const existingReport = {
  id: 1,
  kind: "summary",
  status: "SUCCESS" as const,
  parameters: {},
  result: {
    machines: [{ status: "ONLINE", count: 3 }],
    active_alerts: 2,
    anomalies: 1,
    generated_at: "2026-08-30T12:00:00Z",
  },
  artifact_path: "/srv/private/report.json",
  requested_at: "2026-08-30T12:00:00Z",
  completed_at: "2026-08-30T12:00:01Z",
};

const page = (results = [existingReport]) => ({
  count: results.length,
  next: null,
  previous: null,
  results,
});

describe("rapports asynchrones", () => {
  beforeEach(() => {
    mocks.listReports.mockReset();
    mocks.requestReport.mockReset();
  });

  it("liste les rapports réels et suit honnêtement une tâche sans inventer son rapport", async () => {
    mocks.listReports.mockResolvedValue(page());
    mocks.requestReport.mockResolvedValue({
      task_id: "celery-report-42",
      status: "queued",
    });
    const actor = userEvent.setup();
    renderWithApp(<ReportsPage />, { route: "/reports" });

    expect(
      await screen.findByText("3 machines · 2 alertes actives · 1 anomalies"),
    ).toBeInTheDocument();
    expect(screen.getByText("Stocké côté serveur")).toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /télécharg/i }),
    ).not.toBeInTheDocument();

    await actor.click(
      screen.getByRole("button", { name: "Générer une synthèse" }),
    );

    await waitFor(() =>
      expect(mocks.requestReport).toHaveBeenCalledWith(
        expect.objectContaining({
          kind: "summary",
          idempotency_key: expect.stringMatching(/^ui-summary-\d+$/),
        }),
      ),
    );
    expect(
      await screen.findByText("Génération mise en file"),
    ).toBeInTheDocument();
    expect(screen.queryByText("Rapport généré")).not.toBeInTheDocument();
    expect(
      screen.getByText(/ne permet pas d’associer sûrement un rapport/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Tâche Celery celery-report-42"),
    ).toBeInTheDocument();
  });

  it("affiche un état erreur réessayable quand la liste échoue", async () => {
    mocks.listReports.mockRejectedValue(new Error("API indisponible"));
    renderWithApp(<ReportsPage />, { route: "/reports" });
    expect(
      await screen.findByText("Impossible de récupérer les données"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Réessayer" }),
    ).toBeInTheDocument();
  });
});
