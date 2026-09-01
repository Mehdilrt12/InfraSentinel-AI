import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  BellRing,
  CheckCircle2,
  Clock3,
  FileBarChart2,
  FilePlus2,
  HardDriveDownload,
  ListChecks,
  RefreshCw,
  Server,
  ShieldAlert,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { apiProblem } from "../../api/client";
import { listReports, requestReport } from "../../api/reports";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  Drawer,
  KeyValue,
  PageHeader,
  Pagination,
  StatCard,
  StatusBadge,
  useToast,
  type Column,
} from "../../components/common";
import type { Report } from "../../types/api";
import {
  formatCount,
  formatRelativeTime,
  formatTimestamp,
} from "../../utils/format";

const PAGE_SIZE = 100;

interface GenerationTracking {
  taskId: string;
  expiresAt: number;
  expired: boolean;
}

const TRACKING_DURATION_MS = 120_000;

const reportKindLabel = (kind: string) =>
  kind === "summary" ? "Synthèse d’infrastructure" : kind;

function reportNumber(report: Report, key: string) {
  const value = report.result[key];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function machineBreakdown(report: Report) {
  const machines = report.result.machines;
  if (!Array.isArray(machines)) return [];
  return machines.flatMap((item) => {
    if (!item || typeof item !== "object") return [];
    const status = "status" in item ? String(item.status) : "UNKNOWN";
    const count = "count" in item ? Number(item.count) : Number.NaN;
    return Number.isFinite(count) ? [{ status, count }] : [];
  });
}

function reportSummary(report: Report) {
  const machines = machineBreakdown(report);
  const machineCount = machines.reduce((total, item) => total + item.count, 0);
  const alerts = reportNumber(report, "active_alerts");
  const anomalies = reportNumber(report, "anomalies");
  const parts = [
    machines.length ? `${formatCount(machineCount)} machines` : null,
    alerts === null ? null : `${formatCount(alerts)} alertes actives`,
    anomalies === null ? null : `${formatCount(anomalies)} anomalies`,
  ].filter(Boolean);
  return parts.join(" · ") || "Résultat structuré disponible";
}

export default function ReportsPage() {
  const { user } = useAuth();
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<Report | null>(null);
  const [tracking, setTracking] = useState<GenerationTracking | null>(null);
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const reports = useQuery({
    queryKey: queryKeys.reports(page),
    queryFn: () => listReports(page),
    refetchInterval: (query) => {
      const hasRunningReport = query.state.data?.results.some(
        (report) => report.status === "RUNNING",
      );
      return (tracking && !tracking.expired) || hasRunningReport
        ? 3_000
        : false;
    },
  });
  const rows = useMemo(() => reports.data?.results ?? [], [reports.data]);

  useEffect(() => {
    if (!tracking || tracking.expired) return;
    const remaining = tracking.expiresAt - Date.now();
    if (remaining <= 0) {
      setTracking((current) =>
        current ? { ...current, expired: true } : current,
      );
      return;
    }
    const timeout = window.setTimeout(
      () =>
        setTracking((current) =>
          current ? { ...current, expired: true } : current,
        ),
      remaining,
    );
    return () => window.clearTimeout(timeout);
  }, [tracking]);

  const generation = useMutation({
    mutationFn: ({ kind }: { kind: string }) =>
      requestReport({
        kind,
        idempotency_key: `ui-${kind}-${Date.now()}`,
      }),
    onSuccess: (data) => {
      setTracking({
        taskId: data.task_id,
        expiresAt: Date.now() + TRACKING_DURATION_MS,
        expired: false,
      });
      setPage(1);
      void queryClient.invalidateQueries({ queryKey: queryKeys.reportsRoot });
      notify({
        tone: "success",
        title: "Rapport mis en file",
        detail: `La tâche ${data.task_id} a été acceptée. La liste sera actualisée automatiquement.`,
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Génération non planifiée",
        detail: apiProblem(error).detail,
      }),
  });

  const generate = () => {
    if (!user?.customer) return;
    generation.mutate({ kind: "summary" });
  };

  const completedOnPage = rows.filter(
    (report) => report.status === "SUCCESS",
  ).length;
  const runningOnPage = rows.filter(
    (report) => report.status === "RUNNING",
  ).length;
  const failedOnPage = rows.filter(
    (report) => report.status === "FAILED",
  ).length;
  const latest = rows[0];

  const columns: Column<Report>[] = [
    {
      key: "kind",
      header: "Rapport",
      sortValue: (report) => report.kind,
      cell: (report) => (
        <div>
          <strong>{reportKindLabel(report.kind)}</strong>
          <small className="technical-id">Rapport #{report.id}</small>
        </div>
      ),
    },
    {
      key: "status",
      header: "État",
      sortValue: (report) => report.status,
      cell: (report) => <StatusBadge status={report.status} />,
    },
    {
      key: "result",
      header: "Synthèse du résultat",
      cell: (report) => reportSummary(report),
    },
    {
      key: "requested",
      header: "Demandé",
      sortValue: (report) => Date.parse(report.requested_at),
      cell: (report) => (
        <time title={formatTimestamp(report.requested_at)}>
          {formatRelativeTime(report.requested_at)}
        </time>
      ),
    },
    {
      key: "completed",
      header: "Terminé",
      sortValue: (report) =>
        report.completed_at ? Date.parse(report.completed_at) : 0,
      cell: (report) => formatTimestamp(report.completed_at),
    },
    {
      key: "artifact",
      header: "Artefact",
      cell: (report) => (
        <Badge tone={report.artifact_path ? "info" : "neutral"}>
          {report.artifact_path ? "Stocké côté serveur" : "Non exposé"}
        </Badge>
      ),
    },
  ];

  return (
    <div className="reports-page">
      <PageHeader
        title="Rapports"
        description="Générez et consultez les synthèses persistées de votre infrastructure, sans données simulées."
        actions={
          <Button
            icon={FilePlus2}
            loading={generation.isPending}
            disabled={!user?.customer}
            title={
              user?.customer
                ? undefined
                : "La génération nécessite un compte associé à un client."
            }
            onClick={generate}
          >
            Générer une synthèse
          </Button>
        }
      />

      {!user?.customer && (
        <div className="inline-notice inline-notice--warning">
          <ShieldAlert aria-hidden />
          La génération nécessite un compte associé à un client. La consultation
          reste disponible selon le périmètre autorisé par le backend.
        </div>
      )}

      {user?.is_superuser && (
        <div className="inline-notice inline-notice--warning">
          <ShieldAlert aria-hidden />
          Le backend peut retourner plusieurs clients à un superutilisateur,
          mais le contrat rapport n’expose pas l’identifiant client. Cette vue
          ne déduit donc aucune attribution tenant.
        </div>
      )}

      <div className="stats-grid">
        <StatCard
          label="Rapports persistés"
          value={reports.data?.count ?? "—"}
          icon={<FileBarChart2 />}
        />
        <StatCard
          label="Terminés sur cette page"
          value={completedOnPage}
          icon={<CheckCircle2 />}
          tone="success"
        />
        <StatCard
          label="En cours sur cette page"
          value={runningOnPage}
          icon={<Clock3 />}
          tone="blue"
        />
        <StatCard
          label="Échecs sur cette page"
          value={failedOnPage}
          icon={<ShieldAlert />}
          tone="warning"
        />
      </div>

      {tracking && (
        <Card className="report-tracking" as="section">
          <div className="report-tracking__icon">
            {tracking.expired ? (
              <Clock3 aria-hidden />
            ) : (
              <BellRing aria-hidden />
            )}
          </div>
          <div>
            <strong>Génération mise en file</strong>
            <p>
              {tracking.expired
                ? "Le suivi automatique est arrêté après deux minutes. Actualisez la liste pour vérifier le résultat."
                : "L’API a accepté la tâche et la liste est actualisée. Le contrat ne permet pas d’associer sûrement un rapport à ce task_id."}
            </p>
            <small className="technical-id">
              Tâche Celery {tracking.taskId}
            </small>
          </div>
          <Button
            variant="secondary"
            size="sm"
            icon={RefreshCw}
            loading={reports.isFetching}
            onClick={() => reports.refetch()}
          >
            Actualiser
          </Button>
        </Card>
      )}

      <Card className="table-card reports-table">
        <CardHeader
          title="Historique"
          description={
            latest
              ? `Dernier rapport demandé ${formatRelativeTime(latest.requested_at).toLowerCase()}.`
              : "Les rapports apparaîtront ici après leur persistance côté serveur."
          }
          action={
            reports.isFetching && !reports.isLoading ? (
              <Badge tone="info">Actualisation…</Badge>
            ) : undefined
          }
        />
        <DataTable
          caption="Rapports renvoyés pour le périmètre autorisé"
          columns={columns}
          rows={rows}
          rowKey={(report) => report.id}
          loading={reports.isLoading}
          error={reports.error}
          retry={() => reports.refetch()}
          onRowClick={setSelected}
          emptyTitle="Aucun rapport généré"
          emptyDescription="Demandez une synthèse pour créer le premier rapport à partir des données réelles du périmètre autorisé."
        />
        <Pagination
          page={page}
          count={reports.data?.count ?? 0}
          pageSize={PAGE_SIZE}
          onPage={setPage}
        />
      </Card>

      <Card className="report-artifact-note">
        <HardDriveDownload aria-hidden />
        <div>
          <strong>Téléchargement non exposé par l’API</strong>
          <p>
            La présence éventuelle d’un artefact est indiquée sans révéler son
            chemin serveur. Aucun téléchargement n’est proposé tant qu’un
            endpoint authentifié dédié n’existe pas.
          </p>
        </div>
      </Card>

      <Drawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? reportKindLabel(selected.kind) : "Rapport"}
        description={
          selected
            ? `Rapport #${selected.id} · demandé ${formatTimestamp(selected.requested_at)}`
            : undefined
        }
      >
        {selected && (
          <div className="stack stack--lg">
            <div className="cluster">
              <StatusBadge status={selected.status} />
              <Badge tone="neutral">Lecture seule</Badge>
            </div>
            <div className="details-grid drawer-details">
              <KeyValue label="Type" value={reportKindLabel(selected.kind)} />
              <KeyValue
                label="Demandé"
                value={formatTimestamp(selected.requested_at)}
              />
              <KeyValue
                label="Terminé"
                value={formatTimestamp(selected.completed_at)}
              />
              <KeyValue label="Identifiant" value={selected.id} />
            </div>
            <Card className="drawer-section">
              <CardHeader
                title="Synthèse opérationnelle"
                description="Valeurs enregistrées dans le résultat du rapport."
              />
              <div className="report-result-grid">
                <KeyValue
                  label="Machines"
                  value={formatCount(
                    machineBreakdown(selected).reduce(
                      (total, item) => total + item.count,
                      0,
                    ),
                  )}
                />
                <KeyValue
                  label="Alertes actives"
                  value={formatCount(reportNumber(selected, "active_alerts"))}
                />
                <KeyValue
                  label="Anomalies"
                  value={formatCount(reportNumber(selected, "anomalies"))}
                />
              </div>
              {machineBreakdown(selected).length > 0 && (
                <div className="cluster report-machine-statuses">
                  {machineBreakdown(selected).map((item) => (
                    <Badge key={item.status} tone="neutral">
                      {item.status} · {formatCount(item.count)}
                    </Badge>
                  ))}
                </div>
              )}
            </Card>
            <Card className="drawer-section">
              <CardHeader
                title="Résultat structuré"
                description="Contenu JSON renvoyé et persisté par le backend."
                action={<ListChecks />}
              />
              <pre className="json-block">
                {JSON.stringify(selected.result, null, 2)}
              </pre>
            </Card>
            <div className="inline-notice">
              <Server aria-hidden />
              {selected.artifact_path
                ? "Un artefact existe côté serveur, mais aucun endpoint sécurisé de téléchargement n’est disponible."
                : "Aucun artefact téléchargeable n’est associé à ce rapport."}
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
