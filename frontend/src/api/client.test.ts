import { AxiosHeaders } from "axios";
import { afterEach, describe, expect, it } from "vitest";
import {
  api,
  apiProblem,
  asPage,
  resolveApiBaseUrl,
  resolvePublicServerUrl,
  setAccessToken,
} from "./client";

afterEach(() => setAccessToken(null));

describe("client API", () => {
  it("normalise une URL configurée sans imposer localhost", () => {
    expect(resolveApiBaseUrl()).toBe("/api");
    expect(resolveApiBaseUrl(" https://monitoring.example/api/ ")).toBe(
      "https://monitoring.example/api",
    );
  });

  it("dérive l’URL serveur publique utilisée par l’agent", () => {
    expect(resolvePublicServerUrl("/api", "https://monitoring.example")).toBe(
      "https://monitoring.example",
    );
    expect(
      resolvePublicServerUrl(
        "http://192.0.2.10:8000/api",
        "https://unused.example",
      ),
    ).toBe("http://192.0.2.10:8000");
  });

  it("ajoute le bearer en mémoire aux requêtes authentifiées", async () => {
    let authorization: unknown;
    setAccessToken("jeton-ephemere");
    await api.get("/machines/", {
      adapter: async (config) => {
        authorization = AxiosHeaders.from(config.headers).get("Authorization");
        return { data: [], status: 200, statusText: "OK", headers: {}, config };
      },
    });
    expect(authorization).toBe("Bearer jeton-ephemere");
  });

  it("n’ajoute aucun bearer après effacement du token", async () => {
    let authorization: unknown;
    setAccessToken(null);
    await api.get("/machines/", {
      adapter: async (config) => {
        authorization = AxiosHeaders.from(config.headers).get("Authorization");
        return { data: [], status: 200, statusText: "OK", headers: {}, config };
      },
    });
    expect(authorization).toBeUndefined();
  });

  it("convertit les listes simples et conserve les pages DRF", () => {
    expect(asPage(["a", "b"])).toEqual({
      count: 2,
      next: null,
      previous: null,
      results: ["a", "b"],
    });
    const page = { count: 1, next: null, previous: null, results: ["a"] };
    expect(asPage(page)).toBe(page);
  });

  it("présente une erreur réseau sans exposer les détails techniques", () => {
    const problem = apiProblem({
      isAxiosError: true,
      code: "ERR_NETWORK",
      message: "socket hang up",
    });
    expect(problem).toEqual({
      title: "Impossible de récupérer les données",
      detail: "Le serveur API est injoignable.",
      status: undefined,
      fields: undefined,
    });
    expect(problem.detail).not.toContain("socket");
  });

  it("convertit les erreurs de validation DRF en champs lisibles", () => {
    const problem = apiProblem({
      isAxiosError: true,
      response: {
        status: 400,
        data: {
          detail: "Requête invalide.",
          email: ["Adresse invalide."],
          role: "Rôle refusé.",
        },
      },
    });
    expect(problem.status).toBe(400);
    expect(problem.detail).toBe("Requête invalide.");
    expect(problem.fields).toEqual({
      email: "Adresse invalide.",
      role: "Rôle refusé.",
    });
  });
});
