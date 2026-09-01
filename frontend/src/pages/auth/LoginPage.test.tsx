import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { renderWithApp } from "../../test/render";
import LoginPage from "./LoginPage";

const auth = vi.hoisted(() => ({
  user: null,
  loading: false,
  sessionExpired: false,
  login: vi.fn(),
  logout: vi.fn(),
  register: vi.fn(),
}));
vi.mock("../../auth/AuthProvider", () => ({ useAuth: () => auth }));

describe("connexion navigateur", () => {
  it("envoie les identifiants au flux AuthProvider et navigue au dashboard", async () => {
    auth.login.mockResolvedValueOnce(undefined);
    const actor = userEvent.setup();
    renderWithApp(
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/dashboard" element={<div>Dashboard chargé</div>} />
      </Routes>,
      { route: "/login" },
    );
    await actor.type(
      screen.getByLabelText(/Adresse email/),
      "admin@example.test",
    );
    await actor.type(
      screen.getByLabelText(/Mot de passe/),
      "mot-de-passe-solide",
    );
    await actor.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(auth.login).toHaveBeenCalledWith(
      "admin@example.test",
      "mot-de-passe-solide",
    );
    expect(await screen.findByText("Dashboard chargé")).toBeInTheDocument();
  });
  it("affiche clairement une session expirée", () => {
    auth.sessionExpired = true;
    renderWithApp(<LoginPage />, { route: "/login" });
    expect(screen.getByText(/Votre session a expiré/)).toBeInTheDocument();
    auth.sessionExpired = false;
  });
  it("permet d’afficher puis de masquer le mot de passe", async () => {
    const actor = userEvent.setup();
    renderWithApp(<LoginPage />, { route: "/login" });
    const password = screen.getByLabelText(/Mot de passe/);
    expect(password).toHaveAttribute("type", "password");
    await actor.click(
      screen.getByRole("button", { name: "Afficher le mot de passe" }),
    );
    expect(password).toHaveAttribute("type", "text");
    await actor.click(
      screen.getByRole("button", { name: "Masquer le mot de passe" }),
    );
    expect(password).toHaveAttribute("type", "password");
  });
  it("présente un refus 401 sans exposer le détail backend", async () => {
    auth.login.mockRejectedValueOnce({
      isAxiosError: true,
      response: { status: 401, data: { detail: "Signature JWT invalide" } },
    });
    const actor = userEvent.setup();
    renderWithApp(<LoginPage />, { route: "/login" });
    await actor.type(
      screen.getByLabelText(/Adresse email/),
      "admin@example.test",
    );
    await actor.type(
      screen.getByLabelText(/Mot de passe/),
      "mot-de-passe-solide",
    );
    await actor.click(screen.getByRole("button", { name: "Se connecter" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Email ou mot de passe incorrect.",
    );
    expect(screen.queryByText(/Signature JWT/)).not.toBeInTheDocument();
  });
});
