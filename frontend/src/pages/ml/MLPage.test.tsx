import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import MLPage from "./MLPage";

const mocks = vi.hoisted(() => ({ getPage: vi.fn(), postOne: vi.fn() }));
vi.mock("../../api/resources", () => ({
  getPage: mocks.getPage,
  postOne: mocks.postOne,
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

describe("présentation scientifique ML", () => {
  it("présente les paramètres réels et indique les métriques non calculables", async () => {
    mocks.getPage.mockImplementation(async (path: string) =>
      path === "/ml/models/"
        ? {
            count: 1,
            next: null,
            previous: null,
            results: [
              {
                id: "model-1",
                display_number: 6,
                version: "iforest-20260830",
                algorithm: "IsolationForest",
                features: ["cpu", "memory"],
                preprocessing: { scaler: "RobustScaler" },
                parameters: {
                  contamination: 0.02,
                  n_estimators: 200,
                  random_state: 42,
                },
                dataset: { sample_count: 250 },
                evaluation_metrics: {
                  precision: null,
                  recall: null,
                  overlap_count: 3,
                },
                decision_threshold: -0.12,
                trained_at: "2026-08-30T00:49:00Z",
                status: "READY",
                active: true,
                created_at: "2026-08-30T00:49:00Z",
              },
            ],
          }
        : { count: 0, next: null, previous: null, results: [] },
    );
    const actor = userEvent.setup();
    renderWithApp(<MLPage />, { route: "/ml" });
    expect(
      await screen.findByText("Isolation Forest — Modèle 6"),
    ).toBeInTheDocument();
    expect(screen.getAllByText("200")).toHaveLength(2);
    expect(screen.getAllByText("2 %")).toHaveLength(2);
    await actor.click(screen.getByRole("tab", { name: "Évaluation" }));
    expect(screen.getAllByText("Non calculable sans labels")).toHaveLength(2);
  });
});
