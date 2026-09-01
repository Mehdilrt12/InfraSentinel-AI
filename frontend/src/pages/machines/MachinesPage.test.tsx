import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import MachinesPage from "./MachinesPage";

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

describe("inventaire machines", () => {
  it("affiche uniquement des machines backend et filtre la page chargée", async () => {
    mocks.getPage.mockResolvedValue({
      count: 2,
      next: null,
      previous: null,
      results: [
        {
          id: "m1",
          environment: "e1",
          source_type: "WINDOWS",
          external_id: "legion-real",
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
        {
          id: "m2",
          environment: "e1",
          source_type: "WINDOWS",
          external_id: "server-real",
          hostname: "SERVER-02",
          ip_address: "192.168.1.4",
          os_information: {},
          status: "OFFLINE",
          last_seen: null,
          agent_version: "",
          metadata: {},
          created_at: "",
          updated_at: "",
        },
      ],
    });
    const actor = userEvent.setup();
    renderWithApp(<MachinesPage />, { route: "/machines" });
    expect(await screen.findByText("LEGION")).toBeInTheDocument();
    expect(screen.getByText("SERVER-02")).toBeInTheDocument();
    await actor.type(screen.getByLabelText("Rechercher une machine"), "LEGION");
    expect(screen.getByText("LEGION")).toBeInTheDocument();
    expect(screen.queryByText("SERVER-02")).not.toBeInTheDocument();
    expect(screen.getByText("Filtres locaux")).toBeInTheDocument();
  });
});
