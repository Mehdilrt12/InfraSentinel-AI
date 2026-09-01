import axios, {
  AxiosError,
  AxiosHeaders,
  type InternalAxiosRequestConfig,
} from "axios";

export const resolveApiBaseUrl = (configured?: string) =>
  (configured?.trim() || "/api").replace(/\/$/, "");
export const API_BASE_URL = resolveApiBaseUrl(
  import.meta.env.VITE_API_BASE_URL || import.meta.env.VITE_API_URL,
);
export function resolvePublicServerUrl(apiBase: string, pageOrigin: string) {
  const url = new URL(apiBase, pageOrigin);
  url.pathname = url.pathname.replace(/\/api\/?$/, "") || "/";
  url.search = "";
  url.hash = "";
  return url.toString().replace(/\/$/, "");
}

let accessToken: string | null = null;
let csrfToken: string | null = null;
let refreshPromise: Promise<string> | null = null;
let sessionExpiredHandler: (() => void) | null = null;

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  withCredentials: true,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
});

const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 15_000,
  withCredentials: true,
  headers: { Accept: "application/json", "Content-Type": "application/json" },
});

export function setAccessToken(token: string | null) {
  accessToken = token || null;
}
export function hasAccessToken() {
  return Boolean(accessToken);
}
export function onSessionExpired(handler: (() => void) | null) {
  sessionExpiredHandler = handler;
}

export async function ensureCsrfToken() {
  if (csrfToken) return csrfToken;
  const { data } = await authApi.get<{ csrf_token: string }>(
    "/auth/browser/csrf/",
  );
  csrfToken = data.csrf_token;
  return csrfToken;
}

export async function loginBrowser(email: string, password: string) {
  const csrf = await ensureCsrfToken();
  const { data } = await authApi.post<{ access: string; expires_in: number }>(
    "/auth/browser/login/",
    { email, password },
    { headers: { "X-CSRFToken": csrf } },
  );
  setAccessToken(data.access);
  return data;
}

export async function refreshBrowserSession() {
  refreshPromise ??= ensureCsrfToken()
    .then((csrf) =>
      authApi.post<{ access: string; expires_in: number }>(
        "/auth/browser/refresh/",
        {},
        { headers: { "X-CSRFToken": csrf } },
      ),
    )
    .then(({ data }) => {
      setAccessToken(data.access);
      return data.access;
    })
    .catch((error) => {
      setAccessToken(null);
      throw error;
    })
    .finally(() => {
      refreshPromise = null;
    });
  return refreshPromise;
}

export async function logoutBrowser() {
  try {
    const csrf = await ensureCsrfToken();
    await authApi.post(
      "/auth/browser/logout/",
      {},
      { headers: { "X-CSRFToken": csrf } },
    );
  } finally {
    setAccessToken(null);
  }
}

api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (accessToken) {
    const headers = AxiosHeaders.from(config.headers);
    headers.set("Authorization", `Bearer ${accessToken}`);
    config.headers = headers;
  }
  return config;
});

api.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as
      (InternalAxiosRequestConfig & { _retried?: boolean }) | undefined;
    if (
      error.response?.status !== 401 ||
      !original ||
      original._retried ||
      original.url?.includes("/auth/")
    ) {
      return Promise.reject(error);
    }
    original._retried = true;
    try {
      const token = await refreshBrowserSession();
      const headers = AxiosHeaders.from(original.headers);
      headers.set("Authorization", `Bearer ${token}`);
      original.headers = headers;
      return api(original);
    } catch (refreshError) {
      sessionExpiredHandler?.();
      return Promise.reject(refreshError);
    }
  },
);

export interface ApiProblem {
  status?: number;
  title: string;
  detail: string;
  fields?: Record<string, string>;
}

export function apiProblem(error: unknown): ApiProblem {
  if (!axios.isAxiosError(error))
    return {
      title: "Erreur inattendue",
      detail: "Une erreur inattendue est survenue.",
    };
  const status = error.response?.status;
  const data = error.response?.data as Record<string, unknown> | undefined;
  const detail =
    typeof data?.detail === "string"
      ? data.detail
      : status === 403
        ? "Vous n'avez pas l'autorisation d'effectuer cette action."
        : status === 404
          ? "La ressource demandée est introuvable."
          : status === 429
            ? "Trop de requêtes. Réessayez dans quelques instants."
            : status && status >= 500
              ? "Le serveur rencontre un problème temporaire."
              : error.code === "ECONNABORTED"
                ? "Le serveur n'a pas répondu à temps."
                : !error.response
                  ? "Le serveur API est injoignable."
                  : "La requête a été refusée.";
  const fields = data
    ? Object.fromEntries(
        Object.entries(data)
          .filter(([key]) => key !== "detail")
          .map(([key, value]) => [
            key,
            Array.isArray(value) ? value.join(" ") : String(value),
          ]),
      )
    : undefined;
  return {
    status,
    title:
      status === 403
        ? "Accès refusé"
        : status === 404
          ? "Introuvable"
          : "Impossible de récupérer les données",
    detail,
    fields,
  };
}

export function asPage<T>(
  data:
    | T[]
    | {
        count: number;
        next: string | null;
        previous: string | null;
        results: T[];
      },
) {
  return Array.isArray(data)
    ? { count: data.length, next: null, previous: null, results: data }
    : data;
}
