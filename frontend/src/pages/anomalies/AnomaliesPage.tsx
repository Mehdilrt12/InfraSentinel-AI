import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  BrainCircuit,
  CheckCheck,
  Eye,
  Search,
  Waves,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
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
  Drawer,
  EmptyState,
  Input,
  KeyValue,
  PageHeader,
  Pagination,
  Select,
  StatCard,
  useToast,
  type Column,
} from "../../components/common";
import type { Anomaly, Machine } from "../../types/api";
import {
  formatRelativeTime,
  formatTimestamp,
  formatValue,
  metricLabel,
} from "../../utils/format";

function anomalyFeatures(anomaly: Anomaly) {
  const features = anomaly.explanation?.features;
  return features && typeof features === "object" && !Array.isArray(features)
    ? Object.keys(features as Record<string, unknown>)
    : [];
}

function anomalyInterpretation(anomaly: Anomaly) {
  const count = anomalyFeatures(anomaly).length;
  const evidence = anomaly.explanation?.temporal_evidence as
    Record<string, unknown> | undefined;
  const windows = Number(evidence?.anomalous_windows);
  const lookback = Number(evidence?.lookback_windows);
  const persistence =
    Number.isFinite(windows) && Number.isFinite(lookback)
      ? ` Le signal persiste sur ${windows} fenêtre(s) parmi ${lookback}.`
      : "";
  return `${count ? `${count} indicateur(s) ont été analysés dans ce profil multivarié.` : "Le détail des indicateurs n’est pas disponible."}${persistence}`;
}

export default function AnomaliesPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState("OPEN");
  const [dateRange, setDateRange] = useState("ALL");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Anomaly | null>(null);
  const anomalies = useQuery({
    queryKey: queryKeys.anomalies({ page }),
    queryFn: () => getPage<Anomaly>("/anomalies/", { page }),
  });
  const machines = useQuery({
    queryKey: ["machines", "anomaly-lookup"],
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
      (anomalies.data?.results || []).filter((anomaly) => {
        const ageHours =
          (Date.now() - Date.parse(anomaly.detected_at)) / 3_600_000;
        const matchesDate =
          dateRange === "ALL" || ageHours <= Number(dateRange);
        return (
          (filter === "ALL" ||
            (filter === "OPEN"
              ? !anomaly.acknowledged
              : anomaly.acknowledged)) &&
          matchesDate &&
          (!search ||
            `${anomaly.hostname} ${anomaly.model_version} ${JSON.stringify(anomaly.explanation)}`
              .toLowerCase()
              .includes(search.toLowerCase()))
        );
      }),
    [anomalies.data, dateRange, filter, search],
  );
  const acknowledge = useMutation({
    mutationFn: (item: Anomaly) =>
      patchOne<Anomaly, { acknowledged: boolean }>(`/anomalies/${item.id}/`, {
        acknowledged: !item.acknowledged,
      }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ["anomalies"] });
      setSelected(updated);
      notify({
        tone: "success",
        title: updated.acknowledged
          ? "Anomalie acquittée"
          : "Anomalie rouverte",
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Action impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const data = anomalies.data?.results || [];
  const unacknowledged = data.filter((item) => !item.acknowledged).length;
  const models = new Set(data.map((item) => item.model_version)).size;
  const columns: Column<Anomaly>[] = [
    {
      key: "machine",
      header: "Machine",
      sortValue: (row) => row.hostname,
      cell: (row) => (
        <div>
          <strong>
            {row.hostname ||
              machineMap.get(row.machine)?.hostname ||
              String(row.machine).slice(0, 8)}
          </strong>
          <small className="technical-id">{row.machine}</small>
        </div>
      ),
    },
    {
      key: "signal",
      header: "Signal",
      sortValue: (row) => row.score,
      cell: (row) => (
        <div>
          <Badge tone="ml">Comportement inhabituel</Badge>
          <small>
            {anomalyFeatures(row).length || "Aucun"} indicateur(s) documenté(s)
          </small>
        </div>
      ),
    },
    {
      key: "model",
      header: "Modèle",
      sortValue: (row) => row.model_version,
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
      key: "status",
      header: "Traitement",
      sortValue: (row) => Number(row.acknowledged),
      cell: (row) => (
        <Badge tone={row.acknowledged ? "success" : "high"} dot>
          {row.acknowledged ? "Acquittée" : "À examiner"}
        </Badge>
      ),
    },
    {
      key: "detected",
      header: "Détectée",
      sortValue: (row) => Date.parse(row.detected_at),
      cell: (row) => (
        <time title={formatTimestamp(row.detected_at)}>
          {formatRelativeTime(row.detected_at)}
        </time>
      ),
    },
    {
      key: "action",
      header: "Détail",
      cell: (row) => (
        <Button
          variant="ghost"
          size="sm"
          icon={Eye}
          onClick={(event) => {
            event.stopPropagation();
            setSelected(row);
          }}
        >
          Examiner
        </Button>
      ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Anomalies ML"
        description="Comportements multidimensionnels inhabituels persistés par le pipeline Isolation Forest actif."
        actions={
          <Link className="button button--secondary button--md" to="/ml">
            <BrainCircuit />
            Modèles scientifiques
          </Link>
        }
      />
      <div className="stats-grid">
        <StatCard
          label="Anomalies dans cette page"
          value={data.length}
          icon={<Waves />}
          tone="ml"
        />
        <StatCard
          label="À examiner"
          value={unacknowledged}
          icon={<Activity />}
          tone="warning"
        />
        <StatCard
          label="Acquittées"
          value={data.length - unacknowledged}
          icon={<CheckCheck />}
        />
        <StatCard
          label="Versions de modèle visibles"
          value={models}
          icon={<BrainCircuit />}
          tone="blue"
        />
      </div>
      <Card className="table-card resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Signaux détectés</h2>
            <p>
              Le backend ne fournit pas encore de filtre de traitement, modèle
              ou date : critères locaux sur la page courante.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search />
              <Input
                aria-label="Rechercher une anomalie"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Machine, modèle, explication…"
              />
            </label>
            <Select
              aria-label="Filtrer le traitement"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="OPEN">À examiner</option>
              <option value="ACK">Acquittées</option>
              <option value="ALL">Toutes</option>
            </Select>
            <Select
              aria-label="Filtrer par date"
              value={dateRange}
              onChange={(event) => setDateRange(event.target.value)}
            >
              <option value="ALL">Toutes les dates</option>
              <option value="24">Dernières 24 h</option>
              <option value="168">7 derniers jours</option>
              <option value="720">30 derniers jours</option>
            </Select>
            <Badge tone="neutral">Filtre local</Badge>
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={anomalies.isLoading}
          error={anomalies.error}
          retry={() => anomalies.refetch()}
          onRowClick={setSelected}
          emptyTitle="Aucune anomalie"
          emptyDescription="Aucune anomalie réelle ne correspond aux critères de cette page."
        />
        <Pagination
          page={page}
          count={anomalies.data?.count || 0}
          onPage={setPage}
        />
      </Card>
      <Drawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title="Analyse d’anomalie"
        description={
          selected
            ? `${selected.hostname || machineMap.get(selected.machine)?.hostname || selected.machine} · ${selected.model_version}`
            : undefined
        }
        footer={
          selected && canManage(user) ? (
            <div className="modal-actions">
              <Button
                variant="secondary"
                loading={acknowledge.isPending}
                onClick={() => acknowledge.mutate(selected)}
              >
                {selected.acknowledged ? "Rouvrir" : "Acquitter"}
              </Button>
              <Link
                className="button button--primary button--md"
                to={`/machines/${selected.machine}?tab=anomalies`}
              >
                Ouvrir la machine
              </Link>
            </div>
          ) : undefined
        }
      >
        {selected ? (
          <div className="stack stack--lg">
            <div className="cluster">
              <Badge tone="ml">Anomalie ML</Badge>
              <Badge tone={selected.acknowledged ? "success" : "high"}>
                {selected.acknowledged ? "Acquittée" : "À examiner"}
              </Badge>
            </div>
            <div className="details-grid drawer-details">
              <KeyValue
                label="Fenêtre analysée"
                value={formatTimestamp(selected.window_start)}
              />
              <KeyValue
                label="Détection"
                value={formatTimestamp(selected.detected_at)}
              />
            </div>
            <Card className="drawer-section">
              <h3>Interprétation opérationnelle</h3>
              <p>{anomalyInterpretation(selected)}</p>
              {anomalyFeatures(selected).length ? (
                <div className="feature-list">
                  {anomalyFeatures(selected).map((feature) => (
                    <Badge tone="ml" key={feature}>
                      {metricLabel(feature)}
                    </Badge>
                  ))}
                </div>
              ) : null}
              <p className="muted">
                Cette explication décrit le signal observé sans inventer de
                cause racine.
              </p>
            </Card>
            <Card className="drawer-section">
              <details>
                <summary>Détails scientifiques</summary>
                <div className="details-grid drawer-details">
                  <KeyValue
                    label="Score technique"
                    value={formatValue(selected.score)}
                  />
                  <KeyValue
                    label="Seuil du modèle"
                    value={formatValue(selected.threshold)}
                  />
                </div>
                <h3>Explication brute fournie par le backend</h3>
                {Object.keys(selected.explanation || {}).length ? (
                  <pre className="json-block">
                    {JSON.stringify(selected.explanation, null, 2)}
                  </pre>
                ) : (
                  <EmptyState
                    title="Explication indisponible"
                    description="Le modèle n’a pas persisté d’explication structurée pour ce signal."
                  />
                )}
              </details>
            </Card>
            <div className="inline-notice">
              <BrainCircuit />
              Ce signal ne constitue pas à lui seul une panne. Il indique un
              comportement inhabituel à investiguer avec le contexte
              opérationnel.
            </div>
          </div>
        ) : null}
      </Drawer>
    </div>
  );
}
