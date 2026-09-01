import { useQueries, useQuery } from "@tanstack/react-query";
import {
  Activity,
  AlertOctagon,
  Boxes,
  BrainCircuit,
  CloudCog,
  MonitorCheck,
  MonitorX,
  Server,
} from "lucide-react";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { getOne, getPage } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useRealtime } from "../../realtime/RealtimeProvider";
import type {
  Alert,
  Anomaly,
  DashboardSummary,
  Machine,
  Metric,
  Prediction,
} from "../../types/api";
import {
  formatMetric,
  formatRelativeTime,
  formatRiskLevel,
  formatTimestamp,
  formatValue,
  sourceLabel,
  toBaseValue,
} from "../../utils/format";
import { latestMetrics } from "../../utils/metrics";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  MetricCard,
  PageHeader,
  PartialState,
  SeverityBadge,
  StatCard,
  StatusBadge,
} from "../../components/common";

export default function DashboardPage() {
  const navigate = useNavigate();
  const realtime = useRealtime();
  const dashboard = useQuery({
    queryKey: queryKeys.dashboard,
    queryFn: () => getOne<DashboardSummary>("/dashboard/"),
  });
  const machines = useQuery({
    queryKey: queryKeys.machines(1),
    queryFn: () => getPage<Machine>("/machines/", { page: 1 }),
  });
  const metrics = useQuery({
    queryKey: ["metrics", "dashboard"],
    queryFn: () => getPage<Metric>("/metrics/", { page: 1 }),
  });
  const alerts = useQuery({
    queryKey: queryKeys.alerts({ dashboard: true }),
    queryFn: () => getPage<Alert>("/alerts/", { page: 1 }),
  });
  const anomalies = useQuery({
    queryKey: queryKeys.anomalies({ dashboard: true }),
    queryFn: () => getPage<Anomaly>("/anomalies/", { page: 1 }),
  });
  const predictionQueries = useQueries({
    queries: (machines.data?.results || []).slice(0, 8).map((machine) => ({
      queryKey: queryKeys.predictions(machine.id, 24),
      queryFn: () =>
        getOne<Prediction[]>(`/machines/${machine.id}/trends/`, {
          params: { hours: 24 },
        }),
      staleTime: 60_000,
    })),
  });

  const loadedMachines = useMemo(
    () => machines.data?.results || [],
    [machines.data],
  );
  const machineMap = useMemo(
    () => new Map(loadedMachines.map((item) => [item.id, item])),
    [loadedMachines],
  );
  const latestAll = useMemo(
    () => latestMetrics(metrics.data?.results || []),
    [metrics.data],
  );
  const latest = latestAll.slice(0, 10);
  const activeAlerts = (alerts.data?.results || []).filter(
    (item) => item.status !== "RESOLVED",
  );
  const severityOrder = { CRITICAL: 4, HIGH: 3, WARNING: 2, INFO: 1 };
  const problemMachines = loadedMachines
    .filter(
      (item) =>
        item.status !== "ONLINE" ||
        activeAlerts.some((alert) => alert.machine === item.id),
    )
    .sort((left, right) => {
      const severityFor = (machineId: string) =>
        Math.max(
          0,
          ...activeAlerts
            .filter((alert) => alert.machine === machineId)
            .map((alert) => severityOrder[alert.severity]),
        );
      return (
        severityFor(right.id) - severityFor(left.id) ||
        Number(right.status === "OFFLINE") - Number(left.status === "OFFLINE")
      );
    })
    .slice(0, 6);
  const healthValue = (
    names: string[],
    aggregate: "average" | "sum" = "average",
  ) => {
    const points = latestAll.filter((metric) =>
      names.includes(metric.metric_name),
    );
    if (!points.length) return "—";
    const values = points
      .map((metric) => toBaseValue(metric.metric_value, metric.unit))
      .filter((value): value is number => value !== null);
    if (!values.length) return "—";
    const total = values.reduce((sum, value) => sum + value, 0);
    return formatValue(
      total / (aggregate === "average" ? values.length : 1),
      points[0].unit,
    );
  };
  const risks = predictionQueries
    .flatMap((query, index) =>
      (query.data || []).map((prediction) => ({
        prediction,
        machine: loadedMachines[index],
      })),
    )
    .filter((item) => item.prediction.risk_score > 0)
    .sort((a, b) => b.prediction.risk_score - a.prediction.risk_score)
    .slice(0, 5);
  const partial = [machines, metrics, alerts, anomalies].some(
    (query) => query.isError,
  );

  if (dashboard.isError)
    return (
      <>
        <PageHeader
          title="Vue globale"
          description="État consolidé de toutes les sources supervisées."
        />
        <ErrorState retry={() => dashboard.refetch()} />
      </>
    );
  const summary = dashboard.data;
  return (
    <div className="dashboard-page">
      <PageHeader
        title="Vue globale"
        description="État consolidé de vos sources Windows, VMware et Hyper-V, enrichi par les règles, l’IA et l’analyse prédictive."
        actions={
          <Badge tone={realtime.status === "live" ? "success" : "warning"} dot>
            {realtime.status === "live"
              ? "Synchronisation temps réel"
              : "Fallback actif"}
          </Badge>
        }
      />
      {partial && (
        <PartialState>
          La synthèse principale est disponible, mais une ou plusieurs vues
          secondaires sont partielles.
        </PartialState>
      )}
      <div className="stats-grid dashboard-stats">
        <StatCard
          label="Machines supervisées"
          value={summary?.total_assets ?? "—"}
          icon={<Server />}
        />
        <StatCard
          label="En ligne"
          value={summary?.online ?? "—"}
          icon={<MonitorCheck />}
          tone="accent"
        />
        <StatCard
          label="Hors ligne"
          value={summary?.offline ?? "—"}
          icon={<MonitorX />}
          tone="critical"
        />
        <StatCard
          label="Alertes critiques"
          value={summary?.critical ?? "—"}
          icon={<AlertOctagon />}
          tone="critical"
        />
        <StatCard
          label="Avertissements"
          value={summary?.warning ?? "—"}
          icon={<Activity />}
          tone="warning"
        />
        <StatCard
          label="Anomalies ML"
          value={summary?.anomalies ?? "—"}
          icon={<BrainCircuit />}
          tone="ml"
        />
        <StatCard
          label="Hôtes VMware"
          value={summary?.vmware_hosts ?? "—"}
          icon={<CloudCog />}
          tone="blue"
        />
        <StatCard
          label="Hôtes Hyper-V"
          value={summary?.hyperv_hosts ?? "—"}
          icon={<Boxes />}
          tone="blue"
        />
      </div>

      <Card className="infrastructure-health">
        <CardHeader
          title="Santé de l’infrastructure"
          description="Synthèse calculée à partir des dernières mesures présentes dans la page API chargée (100 points maximum)."
          action={<Badge tone="neutral">Aucun score artificiel</Badge>}
        />
        <div className="metric-grid">
          <MetricCard
            label="CPU moyen"
            value={healthValue(["system.cpu.utilization"])}
            detail="Mesures disponibles"
          />
          <MetricCard
            label="RAM moyenne"
            value={healthValue(["system.memory.utilization"])}
            detail="Mesures disponibles"
          />
          <MetricCard
            label="Disque moyen"
            value={healthValue(["system.disk.utilization"])}
            detail="Volumes disponibles"
          />
          <MetricCard
            label="Débit réseau cumulé"
            value={healthValue(
              ["system.network.in", "system.network.out"],
              "sum",
            )}
            detail="Entrant + sortant"
            tone="blue"
          />
        </div>
      </Card>

      <div className="content-grid">
        <Card>
          <CardHeader
            title="État de l’infrastructure"
            description="Machines problématiques parmi la page actuellement chargée."
            action={
              <Link className="text-link" to="/machines">
                Voir toutes les machines
              </Link>
            }
          />
          {machines.isLoading ? (
            <div className="skeleton-stack">
              <span className="skeleton" />
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          ) : machines.isError ? (
            <ErrorState compact retry={() => machines.refetch()} />
          ) : problemMachines.length ? (
            <div className="incident-list">
              {problemMachines.map((machine) => {
                const metric = latest.find(
                  (item) => item.machine === machine.id,
                );
                const incident = activeAlerts.find(
                  (item) => item.machine === machine.id,
                );
                return (
                  <button
                    key={machine.id}
                    onClick={() => navigate(`/machines/${machine.id}`)}
                  >
                    <div className="incident-list__identity">
                      <span
                        className={`machine-icon machine-icon--${machine.status.toLowerCase()}`}
                      >
                        <Server />
                      </span>
                      <div>
                        <strong>{machine.hostname}</strong>
                        <small>
                          {sourceLabel(machine.source_type)} ·{" "}
                          {machine.ip_address || "IP non remontée"}
                        </small>
                      </div>
                    </div>
                    <StatusBadge status={machine.status} />
                    <div>
                      {incident && (
                        <SeverityBadge severity={incident.severity} />
                      )}
                      <span>
                        {incident?.message || "Aucun incident détaillé chargé"}
                      </span>
                      <small>
                        {metric
                          ? `${formatMetric(metric).label} · ${formatMetric(metric).text}`
                          : "Dernière mesure non disponible"}
                      </small>
                    </div>
                    <time title={formatTimestamp(machine.last_seen)}>
                      {formatRelativeTime(machine.last_seen)}
                    </time>
                  </button>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="Infrastructure stable"
              description="Aucune machine problématique dans la page chargée."
            />
          )}
        </Card>
        <Card>
          <CardHeader
            title="Priorité opérationnelle"
            description="Alertes actives de la page courante."
            action={
              <Link className="text-link" to="/alerts">
                Centre d’incidents
              </Link>
            }
          />
          {alerts.isLoading ? (
            <div className="skeleton-stack">
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          ) : activeAlerts.length ? (
            <div className="priority-list">
              {activeAlerts.slice(0, 5).map((alert) => (
                <Link to={`/alerts/${alert.id}`} key={alert.id}>
                  <div>
                    <SeverityBadge severity={alert.severity} />
                    <strong>
                      {alert.hostname ||
                        machineMap.get(alert.machine)?.hostname ||
                        "Machine"}
                    </strong>
                  </div>
                  <p>{alert.message}</p>
                  <small>
                    {alert.occurrences} occurrence
                    {alert.occurrences > 1 ? "s" : ""} ·{" "}
                    {formatRelativeTime(alert.last_seen_at)}
                  </small>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Aucune alerte active"
              description="Aucun incident actif n’est présent dans la page chargée."
            />
          )}
        </Card>
      </div>

      <div className="content-grid content-grid--equal">
        <Card>
          <CardHeader
            title="Risques prédictifs"
            description="Estimations linéaires réelles sur un maximum de huit machines chargées."
            action={
              <Link className="text-link" to="/predictions">
                Analyse complète
              </Link>
            }
          />
          {predictionQueries.some((query) => query.isLoading) &&
          !risks.length ? (
            <div className="skeleton-stack">
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          ) : risks.length ? (
            <div className="risk-list">
              {risks.map(({ prediction, machine }) => {
                const risk = formatRiskLevel(prediction.risk_score);
                return (
                  <Link
                    to={`/machines/${machine.id}?tab=predictions`}
                    key={`${machine.id}-${prediction.metric_name}`}
                  >
                    <div>
                      <strong>{machine.hostname}</strong>
                      <span>{prediction.metric_name.replaceAll(".", " ")}</span>
                    </div>
                    <div className={`risk-score risk-score--${risk.tone}`}>
                      <b>{prediction.risk_score}</b>
                      <small>/100</small>
                    </div>
                    <p>
                      {prediction.estimated_threshold_breach_at
                        ? `Franchissement estimé ${formatRelativeTime(prediction.estimated_threshold_breach_at)}`
                        : prediction.already_breached
                          ? "Seuil déjà franchi"
                          : "Aucun franchissement estimé"}
                    </p>
                  </Link>
                );
              })}
            </div>
          ) : (
            <EmptyState
              title="Aucun risque calculé"
              description="Les séries chargées ne permettent pas encore d’identifier un risque prédictif."
            />
          )}
        </Card>
        <Card>
          <CardHeader
            title="Activité télémétrique"
            description="Dernières mesures normalisées de la page API courante."
            action={<Badge tone="neutral">100 points max.</Badge>}
          />
          {metrics.isLoading ? (
            <div className="skeleton-stack">
              <span className="skeleton" />
              <span className="skeleton" />
            </div>
          ) : latest.length ? (
            <div className="telemetry-list">
              {latest.map((metric) => (
                <Link
                  to={`/machines/${metric.machine}?tab=metrics`}
                  key={metric.id}
                >
                  <span className="metric-pulse" />
                  <div>
                    <strong>
                      {machineMap.get(metric.machine)?.hostname ||
                        String(metric.machine).slice(0, 8)}
                    </strong>
                    <small>{formatMetric(metric).label}</small>
                  </div>
                  <b>{formatMetric(metric).text}</b>
                  <time title={formatTimestamp(metric.timestamp)}>
                    {formatRelativeTime(metric.timestamp)}
                  </time>
                </Link>
              ))}
            </div>
          ) : (
            <EmptyState
              title="Aucune métrique"
              description="Aucune mesure normalisée réelle n’a été retournée."
            />
          )}
        </Card>
      </div>
    </div>
  );
}
