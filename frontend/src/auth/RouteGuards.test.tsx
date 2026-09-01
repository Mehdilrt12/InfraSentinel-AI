import { screen } from "@testing-library/react";
import { Route, Routes } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../test/render";
import { ProtectedRoute, RoleRoute } from "./RouteGuards";
import type { User } from "../types/api";

const auth = vi.hoisted(() => ({ user: null as User | null, loading: false }));
vi.mock("./AuthProvider", () => ({ useAuth: () => auth }));
const admin: User = {
  id: 1,
  email: "admin@example.test",
  username: "admin",
  first_name: "",
  last_name: "",
  role: "ADMIN",
  customer: "tenant-a",
  is_active: true,
  is_superuser: false,
};

describe("gardes de routes", () => {
  beforeEach(() => {
    auth.user = null;
    auth.loading = false;
  });
  it("redirige un visiteur vers login", async () => {
    renderWithApp(
      <Routes>
        <Route
          path="/private"
          element={
            <ProtectedRoute>
              <div>Privé</div>
            </ProtectedRoute>
          }
        />
        <Route path="/login" element={<div>Connexion requise</div>} />
      </Routes>,
      { route: "/private" },
    );
    expect(await screen.findByText("Connexion requise")).toBeInTheDocument();
  });
  it("rend une route protégée après authentification", () => {
    auth.user = admin;
    renderWithApp(
      <ProtectedRoute>
        <div>Contenu sécurisé</div>
      </ProtectedRoute>,
    );
    expect(screen.getByText("Contenu sécurisé")).toBeInTheDocument();
  });
  it("redirige un rôle insuffisant vers 403", async () => {
    auth.user = { ...admin, role: "VIEWER" };
    renderWithApp(
      <Routes>
        <Route
          path="/users"
          element={
            <RoleRoute capability="manage:users">
              <div>Utilisateurs</div>
            </RoleRoute>
          }
        />
        <Route path="/forbidden" element={<div>Accès refusé</div>} />
      </Routes>,
      { route: "/users" },
    );
    expect(await screen.findByText("Accès refusé")).toBeInTheDocument();
  });
});
