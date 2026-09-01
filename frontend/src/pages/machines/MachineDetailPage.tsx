import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  AlertTriangle,
  BrainCircuit,
  Clock3,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
  Pencil,
  Server,
  Trash2,
  Wifi,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import {
  Link,
  useNavigate,
  useParams,
  useSearchParams,
} from "react-router-dom";
import { apiProblem } from "../../api/client";
import { deleteOne, getOne, getPage, patchOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import { MetricChart } from "../../components/charts/MetricChart";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  Drawer,
  EmptyState,
  ErrorState,
  Field,
  Input,
  KeyValue,
  LoadingState,
  MetricCard,
  Modal,
  PageHeader,
  Select,
  SeverityBadge,
  SourceBadge,
  StatusBadge,
  TabPanel,
  Tabs,
  useToast,
  type Column,
} from "../../components/common";
import type {
  Agent,
  Alert,
  Anomaly,
  Environment,
  Machine,
  Metric,
  MonitoringRule,
  Prediction,
} from "../../types/api";
import {
  formatMetric,
  formatRelativeTime,
  formatRiskLevel,
  formatTimestamp,
  formatValue,
  metricLabel,
  sourceLabel,
  trendLabel,
} from "../../utils/format";
import { buildMetricChartGroups, latestMetrics } from "../../utils/metrics";

const tabItems = [
  { id: "overview", label: "Synthèse" },
  { id: "metrics", label: "Métriques" },
  { id: "history", label: "Historique" },
  { id: "alerts", label: "Alertes" },
  { id: "anomalies", label: "Anomalies ML" },
  { id: "predictions", label: "Prédictions" },
];

export default function MachineDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { notify } = useToast();
  const [params, setParams] = useSearchParams();
  const activeTab = tabItems.some((item) => item.id === params.get("tab"))
    ? params.get("tab")!
    : "overview";
  const [alertDetail, setAlertDetail] = useState<Alert | null>(null);
  const [editOpen, setEditOpen] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteText, setDeleteText] = useState("");
  const machine = useQuery({
    queryKey: queryKeys.machine(id),
    queryFn: () => getOne<Machine>(`/machines/${id}/`),
    enabled: Boolean(id),
  });
  const metrics = useQuery({
    queryKey: queryKeys.metrics(id, 1),
    queryFn: () => getPage<Metric>("/metrics/", { machine: id, page: 1 }),
    enabled: Boolean(machine.data),
  });
  const alerts = useQuery({
    queryKey: queryKeys.alerts({ machine: id }),
    queryFn: () => getPage<Alert>("/alerts/", { machine: id, page: 1 }),
    enabled: Boolean(machine.data),
  });
  const anomalies = useQuery({
    queryKey: queryKeys.anomalies({ machine: id }),
    queryFn: () => getPage<Anomaly>("/anomalies/", { machine: id, page: 1 }),
    enabled: Boolean(machine.data),
  });
  const predictions = useQuery({
    queryKey: queryKeys.predictions(id, 24),
    queryFn: () =>
      getOne<Prediction[]>(`/machines/${id}/trends/`, {
        params: { hours: 24 },
      }),
    enabled: Boolean(machine.data),
  });
  const agents = useQuery({
    queryKey: ["agents", "machine", id],
    queryFn: () => getPage<Agent>("/agents/"),
    enabled: Boolean(machine.data),
  });
  const environment = useQuery({
    queryKey: ["environment", machine.data?.environment],
    queryFn: () =>
      getOne<Environment>(`/environments/${machine.data!.environment}/`),
    enabled: Boolean(machine.data?.environment),
  });
  const rules = useQuery({
    queryKey: ["rules", "machine", id],
    queryFn: () => getPage<MonitoringRule>("/rules/"),
    enabled: Boolean(machine.data),
  });
  const agent = agents.data?.results.find((item) => item.machine === id);
  const latest = useMemo(
    () => latestMetrics(metrics.data?.results || []),
    [metrics.data],
  );
  const charts = useMemo(
    () => buildMetricChartGroups(metrics.data?.results || []),
    [metrics.data],
  );
  const primary = (name: string) =>
    latest.find((metric) => metric.metric_name === name);
  const partial = [metrics, alerts, anomalies, predictions, agents, rules].some(
    (query) => query.isError,
  );

  const update = useMutation({
    mutationFn: (body: Partial<Machine>) =>
      patchOne<Machine, Partial<Machine>>(`/machines/${id}/`, body),
    onSuccess: (updated) => {
      queryClient.setQueryData(queryKeys.machine(id), updated);
      void queryClient.invalidateQueries({ queryKey: ["machines"] });
      setEditOpen(false);
      notify({ tone: "success", title: "Machine mise à jour" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Modification impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const remove = useMutation({
    mutationFn: () => deleteOne(`/machines/${id}/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["machines"] });
      notify({ tone: "success", title: "Machine supprimée" });
      navigate("/machines", { replace: true });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Suppression impossible",
        detail: apiProblem(error).detail,
      }),
  });

  if (machine.isLoading)
    return <LoadingState label="Chargement de la machine…" />;
  if (machine.isError || !machine.data)
    return (
      <>
        <PageHeader
          title="Machine"
          breadcrumbs={[
            { label: "Machines", to: "/machines" },
            { label: "Introuvable" },
          ]}
        />
        <ErrorState
          title="Machine introuvable"
          description={apiProblem(machine.error).detail}
          retry={() => machine.refetch()}
        />
      </>
    );
  const item = machine.data;
  const editSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    update.mutate({
      hostname: String(form.get("hostname")),
      ip_address: String(form.get("ip_address") || "") || null,
      status: String(form.get("status")) as Machine["status"],
      agent_version: String(form.get("agent_version") || ""),
    });
  };

  const metricColumns: Column<Metric>[] = [
    {
      key: "metric",
      header: "Métrique",
      sortValue: (row) => metricLabel(row.metric_name),
      cell: (row) => (
        <div>
          <strong>{formatMetric(row).label}</strong>
          <small className="technical-id">{row.metric_name}</small>
        </div>
      ),
    },
    {
      key: "value",
      header: "Valeur lisible",
      sortValue: (row) => row.metric_value ?? Number.NEGATIVE_INFINITY,
      cell: (row) => <strong>{formatMetric(row).text}</strong>,
    },
    {
      key: "status",
      header: "État source",
      cell: (row) =>
        row.status ? (
          <Badge
            tone={
              row.status === "OK" || row.status === "NORMAL"
                ? "success"
                : "warning"
            }
          >
            {row.status}
          </Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "time",
      header: "Horodatage",
      sortValue: (row) => Date.parse(row.timestamp),
      cell: (row) => (
        <time title={formatTimestamp(row.timestamp)}>
          {formatRelativeTime(row.timestamp)}
        </time>
      ),
    },
  ];
  const alertColumns: Column<Alert>[] = [
    {
      key: "severity",
      header: "Sévérité",
      cell: (row) => <SeverityBadge severity={row.severity} />,
    },
    {
      key: "incident",
      header: "Incident",
      cell: (row) => (
        <div>
          <strong>{row.message}</strong>
          <small>
            {row.source} · {row.type}
          </small>
        </div>
      ),
    },
    {
      key: "status",
      header: "État",
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "occurrences",
      header: "Occurrences",
      sortValue: (row) => row.occurrences,
      cell: (row) => row.occurrences,
    },
    {
      key: "time",
      header: "Dernière occurrence",
      sortValue: (row) => Date.parse(row.last_seen_at),
      cell: (row) => formatRelativeTime(row.last_seen_at),
    },
  ];
  const anomalyColumns: Column<Anomaly>[] = [
    {
      key: "model",
      header: "Modèle",
      cell: (row) => (
        <div>
          <strong>Isolation Forest</strong>
          <small className="technical-id" title={row.model_version}>
            {row.model_version}
          </small>
        </div>
      ),
    },
    {
      key: "score",
      header: "Interprétation",
      sortValue: (row) => row.score,
      cell: (row) => (
        <div>
          <Badge tone="ml">Comportement inhabituel</Badge>
          <small>{row.acknowledged ? "Acquittée" : "À examiner"}</small>
        </div>
      ),
    },
    {
      key: "detected",
      header: "Détection",
      sortValue: (row) => Date.parse(row.detected_at),
      cell: (row) => (
        <time title={formatTimestamp(row.detected_at)}>
          {formatRelativeTime(row.detected_at)}
        </time>
      ),
    },
  ];

  return (
    <div className="machine-detail-page">
      <PageHeader
        breadcrumbs={[
          { label: "Machines", to: "/machines" },
          { label: item.hostname },
        ]}
        title={item.hostname}
        description="Télémétrie normalisée, incidents, anomalies et risques prédictifs de cette machine réelle."
        actions={
          <>
            <SourceBadge source={item.source_type} />
            <StatusBadge status={item.status} />
            {canManage(user) && (
              <Button
                variant="secondary"
                icon={Pencil}
                onClick={() => setEditOpen(true)}
              >
                Modifier
              </Button>
            )}
            {canManage(user) && (
              <Button
                variant="ghost"
                icon={Trash2}
                onClick={() => setDeleteOpen(true)}
              >
                Supprimer
              </Button>
            )}
          </>
        }
      />
      {partial && (
        <div className="inline-notice inline-notice--warning">
          <AlertTriangle />
          Certaines sections secondaires sont indisponibles. Les données
          disponibles restent affichées.
        </div>
      )}
      <Card className="machine-identity">
        <div className="details-grid">
          <KeyValue label="Hostname" value={item.hostname} />
          <KeyValue
            label="Système"
            value={String(
              item.os_information.caption ||
                item.os_information.name ||
                item.os_information.product_name ||
                item.os_information.platform ||
                item.os_information.system ||
                "Non remonté",
            )}
          />
          <KeyValue
            label="Adresse IP"
            value={item.ip_address || "Non remontée"}
          />
          <KeyValue
            label="Environnement"
            value={environment.data?.name || sourceLabel(item.source_type)}
          />
          <KeyValue
            label="Agent"
            value={
              agent ? (agent.enabled ? "Actif" : "Révoqué") : "Non associé"
            }
            hint={
              agent
                ? `v${agent.version || item.agent_version || "—"}`
                : undefined
            }
          />
          <KeyValue
            label="Dernier heartbeat"
            value={formatRelativeTime(agent?.last_heartbeat || item.last_seen)}
            hint={formatTimestamp(agent?.last_heartbeat || item.last_seen)}
          />
          <KeyValue
            label="Uptime"
            value={
              primary("system.uptime")
                ? formatMetric(primary("system.uptime")!).text
                : "Non remonté"
            }
          />
          <KeyValue label="Identifiant externe" value={item.external_id} />
          <KeyValue
            label="Tenant"
            value={
              user?.customer ? String(user.customer).slice(0, 13) : "Plateforme"
            }
          />
        </div>
      </Card>
      <div className="metric-grid machine-kpis">
        <MetricCard
          label="CPU"
          value={
            primary("system.cpu.utilization")
              ? formatMetric(primary("system.cpu.utilization")!).text
              : "—"
          }
          tone="accent"
        />
        <MetricCard
          label="Mémoire"
          value={
            primary("system.memory.utilization")
              ? formatMetric(primary("system.memory.utilization")!).text
              : "—"
          }
          tone="blue"
        />
        <MetricCard
          label="Disque"
          value={
            primary("system.disk.utilization")
              ? formatMetric(primary("system.disk.utilization")!).text
              : "—"
          }
          tone="warning"
        />
        <MetricCard
          label="Réseau entrant"
          value={
            primary("system.network.in")
              ? formatMetric(primary("system.network.in")!).text
              : "—"
          }
          tone="ml"
        />
        <MetricCard
          label="Réseau sortant"
          value={
            primary("system.network.out")
              ? formatMetric(primary("system.network.out")!).text
              : "—"
          }
          tone="ml"
        />
        {primary("system.gpu.utilization") && (
          <MetricCard
            label="GPU"
            value={formatMetric(primary("system.gpu.utilization")!).text}
            tone="blue"
          />
        )}
        {latest.find((metric) => /vram/i.test(metric.metric_name)) && (
          <MetricCard
            label="VRAM"
            value={
              formatMetric(
                latest.find((metric) => /vram/i.test(metric.metric_name))!,
              ).text
            }
            tone="blue"
          />
        )}
        {latest.find((metric) => /temperature/i.test(metric.metric_name)) && (
          <MetricCard
            label="Température"
            value={
              formatMetric(
                latest.find((metric) =>
                  /temperature/i.test(metric.metric_name),
                )!,
              ).text
            }
            tone="warning"
          />
        )}
      </div>
      <Tabs
        items={tabItems.map((tab) => ({
          ...tab,
          count:
            tab.id === "metrics"
              ? metrics.data?.count
              : tab.id === "alerts"
                ? alerts.data?.count
                : tab.id === "anomalies"
                  ? anomalies.data?.count
                  : undefined,
        }))}
        active={activeTab}
        onChange={(tab) => setParams({ tab })}
        ariaLabel="Détails machine"
      />

      <TabPanel active={activeTab} id="overview">
        <div className="content-grid">
          <Card>
            <CardHeader
              title="Dernières mesures"
              description="Une valeur par métrique et dimension dans la page chargée."
            />
            {latest.length ? (
              <div className="latest-metrics-grid">
                {latest.slice(0, 12).map((metric) => (
                  <div
                    key={`${metric.metric_name}-${JSON.stringify(metric.metadata)}`}
                  >
                    <span>{formatMetric(metric).label}</span>
                    <strong>{formatMetric(metric).text}</strong>
                    <small title={formatTimestamp(metric.timestamp)}>
                      {formatRelativeTime(metric.timestamp)}
                    </small>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Aucune télémétrie"
                description="Aucune métrique réelle n’a été reçue pour cette machine."
              />
            )}
          </Card>
          <Card>
            <CardHeader
              title="Risque et recommandations"
              description="Contexte produit par les moteurs backend."
            />
            {(alerts.data?.results || []).some(
              (alert) =>
                alert.structured_recommendation || alert.recommendation,
            ) ? (
              <div className="recommendation-list">
                {alerts
                  .data!.results.filter(
                    (alert) =>
                      alert.structured_recommendation || alert.recommendation,
                  )
                  .slice(0, 4)
                  .map((alert) => (
                    <button
                      key={alert.id}
                      onClick={() => setAlertDetail(alert)}
                    >
                      <SeverityBadge severity={alert.severity} />
                      <strong>{alert.message}</strong>
                      <p>
                        {alert.structured_recommendation?.rationale ||
                          alert.recommendation}
                      </p>
                    </button>
                  ))}
              </div>
            ) : (
              <EmptyState
                title="Aucune recommandation"
                description="Aucune alerte de cette machine n’expose encore de recommandation."
              />
            )}
          </Card>
        </div>
      </TabPanel>

      <TabPanel active={activeTab} id="metrics">
        <Card className="table-card">
          <CardHeader
            title="Métriques normalisées"
            description="Les nombres utilisent de grandes unités et au maximum une décimale."
          />
          <DataTable
            columns={metricColumns}
            rows={metrics.data?.results || []}
            rowKey={(row) => row.id}
            loading={metrics.isLoading}
            error={metrics.error}
            retry={() => metrics.refetch()}
            caption="Métriques de la machine"
          />
        </Card>
      </TabPanel>
      <TabPanel active={activeTab} id="history">
        <div className="stack stack--lg">
          {metrics.isLoading ? (
            <LoadingState />
          ) : charts.length ? (
            charts.map((chart) => {
              const thresholds = (rules.data?.results || [])
                .filter(
                  (rule) =>
                    rule.enabled &&
                    (!rule.machine || rule.machine === id) &&
                    (!rule.environment ||
                      rule.environment === item.environment) &&
                    chart.series.some((series) =>
                      series.identity.startsWith(`${rule.metric}|`),
                    ),
                )
                .map((rule) => ({
                  value: rule.threshold,
                  label: rule.name,
                  severity: rule.severity,
                }));
              return (
                <MetricChart
                  key={chart.key}
                  group={chart}
                  thresholds={thresholds}
                />
              );
            })
          ) : (
            <Card>
              <EmptyState
                title="Historique insuffisant"
                description="Aucun point réel exploitable n’est disponible dans les 100 éléments chargés."
              />
            </Card>
          )}
          <div className="inline-notice">
            <Clock3 />
            L’API ne propose pas encore de filtre temporel ou de résolution
            configurable. Cette vue représente uniquement la page réelle
            chargée.
          </div>
        </div>
      </TabPanel>
      <TabPanel active={activeTab} id="alerts">
        <Card className="table-card">
          <CardHeader
            title="Alertes liées"
            description="Cycle de vie durable avec déduplication backend."
          />
          <DataTable
            columns={alertColumns}
            rows={alerts.data?.results || []}
            rowKey={(row) => row.id}
            loading={alerts.isLoading}
            error={alerts.error}
            retry={() => alerts.refetch()}
            onRowClick={setAlertDetail}
          />
        </Card>
      </TabPanel>
      <TabPanel active={activeTab} id="anomalies">
        <Card className="table-card">
          <CardHeader
            title="Anomalies ML"
            description="Signaux persistés par le modèle Isolation Forest actif."
          />
          <DataTable
            columns={anomalyColumns}
            rows={anomalies.data?.results || []}
            rowKey={(row) => row.id}
            loading={anomalies.isLoading}
            error={anomalies.error}
            retry={() => anomalies.refetch()}
          />
        </Card>
      </TabPanel>
      <TabPanel active={activeTab} id="predictions">
        {predictions.isLoading ? (
          <LoadingState />
        ) : predictions.data?.length ? (
          <div className="prediction-grid">
            {predictions.data.map((prediction) => {
              const risk = formatRiskLevel(prediction.risk_score);
              return (
                <Card className="prediction-card" key={prediction.metric_name}>
                  <header>
                    <div>
                      <span className="eyebrow">
                        Estimation · {prediction.confidence}
                      </span>
                      <h3>{metricLabel(prediction.metric_name)}</h3>
                    </div>
                    <div className={`risk-score risk-score--${risk.tone}`}>
                      <b>{prediction.risk_score}</b>
                      <small>/100</small>
                    </div>
                  </header>
                  <div className="prediction-values">
                    <KeyValue
                      label="Valeur actuelle"
                      value={formatValue(
                        prediction.last_value,
                        prediction.unit,
                      )}
                    />
                    <KeyValue
                      label="Moyenne"
                      value={formatValue(
                        prediction.rolling_average,
                        prediction.unit,
                      )}
                    />
                    <KeyValue
                      label="Variation / h"
                      value={`${formatValue(prediction.rate_of_change_per_hour, prediction.unit)} / h`}
                    />
                    <KeyValue
                      label="Tendance"
                      value={trendLabel(prediction.trend)}
                    />
                  </div>
                  <p>
                    {prediction.estimated_threshold_breach_at
                      ? `Franchissement estimé : ${formatTimestamp(prediction.estimated_threshold_breach_at)}`
                      : prediction.already_breached
                        ? "Le seuil associé est déjà franchi."
                        : "Aucun franchissement n’est estimé dans la fenêtre."}
                  </p>
                  <small>{prediction.disclaimer}</small>
                </Card>
              );
            })}
          </div>
        ) : (
          <Card>
            <EmptyState
              title="Données prédictives insuffisantes"
              description="Au moins trois points temporels réels sont nécessaires pour calculer une tendance."
            />
          </Card>
        )}
      </TabPanel>

      <Drawer
        open={Boolean(alertDetail)}
        onClose={() => setAlertDetail(null)}
        title={alertDetail?.message || "Incident"}
        description={
          alertDetail
            ? `${alertDetail.source} · ${alertDetail.type}`
            : undefined
        }
      >
        {alertDetail && (
          <div className="stack">
            <div className="cluster">
              <SeverityBadge severity={alertDetail.severity} />
              <StatusBadge status={alertDetail.status} />
              <Badge tone="neutral">
                {alertDetail.occurrences} occurrence(s)
              </Badge>
            </div>
            <KeyValue
              label="Dernière occurrence"
              value={formatTimestamp(alertDetail.last_seen_at)}
            />
            <Card className="drawer-section">
              <h3>Contexte</h3>
              <pre className="json-block">
                {JSON.stringify(alertDetail.context, null, 2)}
              </pre>
            </Card>
            <Card className="drawer-section">
              <h3>Recommandation non destructive</h3>
              <p>
                {alertDetail.structured_recommendation?.rationale ||
                  alertDetail.recommendation ||
                  "Aucune recommandation disponible."}
              </p>
              {alertDetail.structured_recommendation?.actions && (
                <ol>
                  {alertDetail.structured_recommendation.actions.map(
                    (action) => (
                      <li key={action}>{action}</li>
                    ),
                  )}
                </ol>
              )}
            </Card>
            <Link
              className="button button--secondary button--md"
              to={`/alerts/${alertDetail.id}`}
            >
              Ouvrir l’incident
            </Link>
          </div>
        )}
      </Drawer>
      <Modal
        open={editOpen}
        onClose={() => setEditOpen(false)}
        title="Modifier la machine"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setEditOpen(false)}>
              Annuler
            </Button>
            <Button
              type="submit"
              form="machine-edit-form"
              loading={update.isPending}
            >
              Enregistrer
            </Button>
          </div>
        }
      >
        <form
          id="machine-edit-form"
          className="form-grid"
          onSubmit={editSubmit}
        >
          <Field label="Hostname" required>
            <Input name="hostname" defaultValue={item.hostname} required />
          </Field>
          <Field label="Adresse IP">
            <Input name="ip_address" defaultValue={item.ip_address || ""} />
          </Field>
          <Field label="État">
            <Select name="status" defaultValue={item.status}>
              <option value="ONLINE">En ligne</option>
              <option value="OFFLINE">Hors ligne</option>
              <option value="UNKNOWN">Inconnu</option>
            </Select>
          </Field>
          <Field label="Version agent">
            <Input name="agent_version" defaultValue={item.agent_version} />
          </Field>
        </form>
      </Modal>
      <Modal
        open={deleteOpen}
        onClose={() => setDeleteOpen(false)}
        title="Supprimer définitivement la machine"
        description="Cette suppression déclenche les cascades définies par le backend (agent, métriques, alertes et anomalies)."
        size="sm"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setDeleteOpen(false)}>
              Annuler
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              disabled={deleteText !== item.hostname}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Supprimer
            </Button>
          </div>
        }
      >
        <Field label={`Saisissez ${item.hostname} pour confirmer`}>
          <Input
            value={deleteText}
            onChange={(event) => setDeleteText(event.target.value)}
          />
        </Field>
      </Modal>
    </div>
  );
}
