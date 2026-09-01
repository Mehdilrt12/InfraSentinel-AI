import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { User } from "../types/api";
import { AuthProvider, useAuth } from "./AuthProvider";

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  loginBrowser: vi.fn(),
  logoutBrowser: vi.fn(),
  refreshBrowserSession: vi.fn(),
  setAccessToken: vi.fn(),
  expiredHandler: null as (() => void) | null,
}));

vi.mock("../api/client", () => ({
  api: { get: mocks.get, post: mocks.post },
  loginBrowser: mocks.loginBrowser,
  logoutBrowser: mocks.logoutBrowser,
  refreshBrowserSession: mocks.refreshBrowserSession,
  setAccessToken: mocks.setAccessToken,
  onSessionExpired: (handler: (() => void) | null) => {
    mocks.expiredHandler = handler;
  },
}));

const user: User = {
  id: 7,
  email: "admin@example.test",
  username: "admin",
  first_name: "Admin",
  last_name: "InfraSentinel",
  role: "ADMIN",
  customer: "tenant-a",
  is_active: true,
  is_superuser: false,
};

function AuthProbe() {
  const auth = useAuth();
  return (
    <>
      <output>
        {auth.loading ? "Chargement" : auth.user?.email || "Anonyme"}
      </output>
      <output>
        {auth.sessionExpired ? "Session expirée" : "Session active"}
      </output>
      <button
        type="button"
        onClick={() => void auth.login(user.email, "secret-fiable")}
      >
        Connexion
      </button>
      <button type="button" onClick={() => void auth.logout()}>
        Déconnexion
      </button>
      <button
        type="button"
        onClick={() =>
          void auth.register({
            organization: "Acme",
            email: user.email,
            password: "secret-fiable",
          })
        }
      >
        Inscription
      </button>
    </>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <AuthProbe />
    </AuthProvider>,
  );
}

describe("AuthProvider", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocks.expiredHandler = null;
    mocks.refreshBrowserSession.mockResolvedValue("access-token");
    mocks.get.mockResolvedValue({ data: user });
    mocks.loginBrowser.mockResolvedValue({
      access: "access-token",
      expires_in: 300,
    });
    mocks.logoutBrowser.mockResolvedValue(undefined);
    mocks.post.mockResolvedValue({ data: {} });
  });

  it("restaure une session navigateur puis charge le profil courant", async () => {
    renderProvider();
    expect(screen.getByText("Chargement")).toBeInTheDocument();
    expect(await screen.findByText(user.email)).toBeInTheDocument();
    expect(mocks.refreshBrowserSession).toHaveBeenCalledOnce();
    expect(mocks.get).toHaveBeenCalledWith("/auth/me/");
  });

  it("reste anonyme lorsque le refresh initial échoue", async () => {
    mocks.refreshBrowserSession.mockRejectedValueOnce(
      new Error("refresh refusé"),
    );
    renderProvider();
    expect(await screen.findByText("Anonyme")).toBeInTheDocument();
    expect(mocks.setAccessToken).toHaveBeenCalledWith(null);
    expect(mocks.get).not.toHaveBeenCalled();
  });

  it("connecte via le flux navigateur sans persister de token côté composant", async () => {
    mocks.refreshBrowserSession.mockRejectedValueOnce(
      new Error("aucune session"),
    );
    const actor = userEvent.setup();
    renderProvider();
    await screen.findByText("Anonyme");
    await actor.click(screen.getByRole("button", { name: "Connexion" }));
    expect(await screen.findByText(user.email)).toBeInTheDocument();
    expect(mocks.loginBrowser).toHaveBeenCalledWith(
      user.email,
      "secret-fiable",
    );
    expect(mocks.get).toHaveBeenCalledWith("/auth/me/");
  });

  it("efface localement la session même si le serveur de déconnexion est indisponible", async () => {
    mocks.logoutBrowser.mockRejectedValueOnce(new Error("API indisponible"));
    sessionStorage.setItem("infrasentinel.realtime.tenant-a.sequence", "42");
    const actor = userEvent.setup();
    renderProvider();
    await screen.findByText(user.email);
    await actor.click(screen.getByRole("button", { name: "Déconnexion" }));
    expect(await screen.findByText("Anonyme")).toBeInTheDocument();
    expect(
      sessionStorage.getItem("infrasentinel.realtime.tenant-a.sequence"),
    ).toBeNull();
  });

  it("invalide immédiatement la session sur notification 401 définitive", async () => {
    sessionStorage.setItem("infrasentinel.realtime.tenant-a.sequence", "17");
    renderProvider();
    await screen.findByText(user.email);
    expect(mocks.expiredHandler).not.toBeNull();
    act(() => mocks.expiredHandler?.());
    expect(await screen.findByText("Session expirée")).toBeInTheDocument();
    expect(screen.getByText("Anonyme")).toBeInTheDocument();
    expect(mocks.setAccessToken).toHaveBeenCalledWith(null);
    expect(
      sessionStorage.getItem("infrasentinel.realtime.tenant-a.sequence"),
    ).toBeNull();
  });

  it("enchaîne inscription puis connexion avec les mêmes identifiants", async () => {
    mocks.refreshBrowserSession.mockRejectedValueOnce(
      new Error("aucune session"),
    );
    const actor = userEvent.setup();
    renderProvider();
    await screen.findByText("Anonyme");
    await actor.click(screen.getByRole("button", { name: "Inscription" }));
    await waitFor(() =>
      expect(mocks.post).toHaveBeenCalledWith("/auth/register/", {
        organization: "Acme",
        email: user.email,
        password: "secret-fiable",
      }),
    );
    expect(mocks.loginBrowser).toHaveBeenCalledWith(
      user.email,
      "secret-fiable",
    );
    expect(await screen.findByText(user.email)).toBeInTheDocument();
  });
});
