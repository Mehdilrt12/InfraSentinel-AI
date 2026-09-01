import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 15_000,
      gcTime: 5 * 60_000,
      retry: (failures, error: unknown) => {
        const status = (error as { response?: { status?: number } })?.response
          ?.status;
        return status === 401 || status === 403 || status === 404
          ? false
          : failures < 2;
      },
      refetchOnWindowFocus: true,
    },
    mutations: { retry: false },
  },
});

export const queryKeys = {
  dashboard: ["dashboard"] as const,
  machines: (page = 1) => ["machines", page] as const,
  machine: (id: string) => ["machines", id] as const,
  metrics: (machine: string, page = 1) => ["metrics", machine, page] as const,
  predictions: (machine: string, hours = 24) =>
    ["predictions", machine, hours] as const,
  agents: (page = 1) => ["agents", page] as const,
  alerts: (filters: object = {}) => ["alerts", filters] as const,
  anomalies: (filters: object = {}) => ["anomalies", filters] as const,
  models: ["ml-models"] as const,
  integration: (source: string) => ["integration", source] as const,
  assets: (source: string) => ["assets", source] as const,
  users: (page = 1) => ["users", page] as const,
  customers: (page = 1) => ["customers", page] as const,
  audit: (filters: object = {}) => ["audit", filters] as const,
  reportsRoot: ["reports"] as const,
  reports: (page = 1) => ["reports", page] as const,
  environments: ["environments"] as const,
  rules: ["rules"] as const,
  connectors: ["connectors"] as const,
  notificationPreferences: ["notification-preferences"] as const,
  notificationDeliveries: ["notification-deliveries"] as const,
};
