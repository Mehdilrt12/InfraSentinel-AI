import { QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ToastProvider } from "../common";
import { makeTestQueryClient } from "../../test/render";
import { AppShell } from "./AppShell";

const logout = vi.fn().mockResolvedValue(undefined);

vi.mock("../../auth/AuthProvider", () => ({
  useAuth: () => ({
    user: {
      id: "user-1",
      email: "admin@example.test",
      role: "ADMIN",
      customer: "customer-1",
      is_active: true,
      is_superuser: false,
    },
    logout,
  }),
}));

vi.mock("../../realtime/RealtimeProvider", () => ({
  useRealtime: () => ({
    status: "live",
    events: [],
    lastEventAt: null,
    reconnect: vi.fn(),
  }),
}));

describe("AppShell", () => {
  beforeEach(() => logout.mockClear());

  it("exposes logout from the sidebar used by the mobile drawer", async () => {
    const client = makeTestQueryClient();
    render(
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/dashboard"]}>
          <ToastProvider>
            <Routes>
              <Route element={<AppShell />}>
                <Route path="/dashboard" element={<div>Dashboard</div>} />
              </Route>
              <Route path="/login" element={<div>Login</div>} />
            </Routes>
          </ToastProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Se déconnecter" }));

    await waitFor(() => expect(logout).toHaveBeenCalledOnce());
    expect(screen.getByText("Login")).toBeInTheDocument();
  });
});
