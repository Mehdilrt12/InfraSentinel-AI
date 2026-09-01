import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertOctagon,
  CheckCircle2,
  CircleDotDashed,
  Search,
  Siren,
} from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { getPage, patchOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Input,
  PageHeader,
  Pagination,
  Select,
  SeverityBadge,
  StatCard,
  StatusBadge,
  useToast,
  type Column,
} from "../../components/common";
import type { Alert, AlertStatus, Machine, Severity } from "../../types/api";
import { formatRelativeTime, formatTimestamp } from "../../utils/format";

export function alertOrigin(alert: Pick<Alert, "source" | "type">) {
  const combined = `${alert.source} ${alert.type}`.toUpperCase();
  if (combined.includes("ML") || combined.includes("ANOMAL"))
    return { label: "Anomalie ML", tone: "ml" };
  if (combined.includes("PREDICT"))
    return { label: "Risque prédictif", tone: "warning" };
  return { label: "Règle de supervision", tone: "info" };
}

export default function AlertsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [status, setStatus] = useState("ACTIVE");
  const [severity, setSeverity] = useState("ALL");
  const [search, setSearch] = useState("");
  const serverStatus = [
    "NEW",
    "ACKNOWLEDGED",
    "IN_PROGRESS",
    "RESOLVED",
  ].includes(status)
    ? status
    : undefined;
  const alerts = useQuery({
    queryKey: queryKeys.alerts({ page, status: serverStatus }),
    queryFn: () =>
      getPage<Alert>("/alerts/", {
        page,
        ...(serverStatus ? { status: serverStatus } : {}),
      }),
  });
  const machines = useQuery({
    queryKey: ["machines", "alert-lookup"],
    queryFn: () => getPage<Machine>("/machines/"),
  });
  const machineMap = useMemo(
    () =>
      new Map(
        (machines.data?.results || []).map((machine) => [machine.id, machine]),
      ),
    [machines.data],
  );
  const rows = useMemo(
    () =>
      (alerts.data?.results || []).filter((alert) => {
        const active = status !== "ACTIVE" || alert.status !== "RESOLVED";
        return (
          active &&
          (severity === "ALL" || alert.severity === severity) &&
          (!search ||
            `${alert.hostname} ${alert.message} ${alert.type} ${alert.source}`
              .toLowerCase()
              .includes(search.toLowerCase()))
        );
      }),
    [alerts.data, search, severity, status],
  );
  const mutateStatus = useMutation({
    mutationFn: ({ id, value }: { id: string; value: AlertStatus }) =>
      patchOne<Alert, { status: AlertStatus }>(`/alerts/${id}/`, {
        status: value,
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      notify({ tone: "success", title: "Cycle de vie mis à jour" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Action impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const local = alerts.data?.results || [];
  const counts = {
    active: local.filter((item) => item.status !== "RESOLVED").length,
    critical: local.filter(
      (item) => item.status !== "RESOLVED" && item.severity === "CRITICAL",
    ).length,
    progressing: local.filter((item) => item.status === "IN_PROGRESS").length,
    resolved: local.filter((item) => item.status === "RESOLVED").length,
  };
  const columns: Column<Alert>[] = [
    {
      key: "severity",
      header: "Sévérité",
      sortValue: (row) =>
        ({ CRITICAL: 4, HIGH: 3, WARNING: 2, INFO: 1 })[row.severity],
      cell: (row) => <SeverityBadge severity={row.severity} />,
    },
    {
      key: "incident",
      header: "Incident",
      sortValue: (row) => row.message,
      cell: (row) => (
        <div>
          <strong>{row.message}</strong>
          <small>
            {row.hostname ||
              machineMap.get(row.machine)?.hostname ||
              String(row.machine).slice(0, 8)}
          </small>
        </div>
      ),
    },
    {
      key: "origin",
      header: "Origine",
      cell: (row) => {
        const origin = alertOrigin(row);
        return <Badge tone={origin.tone}>{origin.label}</Badge>;
      },
    },
    {
      key: "status",
      header: "État",
      sortValue: (row) => row.status,
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "occurrences",
      header: "Occurrences",
      sortValue: (row) => row.occurrences,
      cell: (row) => (
        <div>
          <strong>{row.occurrences}</strong>
          <small>Escalade {row.escalation_level}</small>
        </div>
      ),
    },
    {
      key: "updated",
      header: "Dernière activité",
      sortValue: (row) => Date.parse(row.last_seen_at),
      cell: (row) => (
        <time title={formatTimestamp(row.last_seen_at)}>
          {formatRelativeTime(row.last_seen_at)}
        </time>
      ),
    },
    {
      key: "actions",
      header: "Action",
      cell: (row) =>
        canManage(user) ? (
          <div
            className="row-actions"
            onClick={(event) => event.stopPropagation()}
          >
            {row.status === "NEW" && (
              <Button
                size="sm"
                variant="secondary"
                onClick={() =>
                  mutateStatus.mutate({ id: row.id, value: "ACKNOWLEDGED" })
                }
              >
                Acquitter
              </Button>
            )}
            {row.status !== "RESOLVED" && (
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  mutateStatus.mutate({ id: row.id, value: "RESOLVED" })
                }
              >
                Résoudre
              </Button>
            )}
          </div>
        ) : (
          <span className="muted">Lecture seule</span>
        ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Centre d’incidents"
        description="Alertes durables issues des règles et du moteur ML, avec déduplication, corrélation et cycle de vie."
      />
      <div className="stats-grid">
        <StatCard
          label="Actives sur cette page"
          value={counts.active}
          icon={<Siren />}
          tone="warning"
        />
        <StatCard
          label="Critiques sur cette page"
          value={counts.critical}
          icon={<AlertOctagon />}
          tone="critical"
        />
        <StatCard
          label="En cours"
          value={counts.progressing}
          icon={<CircleDotDashed />}
          tone="blue"
        />
        <StatCard
          label="Résolues sur cette page"
          value={counts.resolved}
          icon={<CheckCircle2 />}
        />
      </div>
      <Card className="table-card resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Alertes</h2>
            <p>
              La sévérité et la recherche sont locales à la page chargée ; le
              statut est filtré côté serveur quand il est explicite.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search />
              <Input
                aria-label="Rechercher une alerte"
                placeholder="Machine, message, type…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <Select
              aria-label="Filtrer par statut"
              value={status}
              onChange={(event) => {
                setStatus(event.target.value);
                setPage(1);
              }}
            >
              <option value="ACTIVE">Toutes les actives</option>
              <option value="NEW">Nouvelles</option>
              <option value="ACKNOWLEDGED">Acquittées</option>
              <option value="IN_PROGRESS">En cours</option>
              <option value="RESOLVED">Résolues</option>
              <option value="ALL">Toutes</option>
            </Select>
            <Select
              aria-label="Filtrer par sévérité"
              value={severity}
              onChange={(event) => setSeverity(event.target.value)}
            >
              <option value="ALL">Toutes les sévérités</option>
              {(["CRITICAL", "HIGH", "WARNING", "INFO"] as Severity[]).map(
                (item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ),
              )}
            </Select>
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={alerts.isLoading}
          error={alerts.error}
          retry={() => alerts.refetch()}
          onRowClick={(row) => navigate(`/alerts/${row.id}`)}
          emptyTitle="Aucune alerte"
          emptyDescription="Aucune alerte réelle ne correspond aux filtres courants."
        />
        <Pagination
          page={page}
          count={alerts.data?.count || 0}
          onPage={setPage}
        />
      </Card>
    </div>
  );
}
