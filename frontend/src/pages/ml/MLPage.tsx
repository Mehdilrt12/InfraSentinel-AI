import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  Beaker,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  Database,
  FlaskConical,
  Play,
  RefreshCw,
  ShieldQuestion,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { getPage, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { can, canManage } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  KeyValue,
  LoadingState,
  PageHeader,
  Select,
  StatCard,
  TabPanel,
  Tabs,
  useToast,
  type Column,
} from "../../components/common";
import type { Anomaly, MLModel, TaskRun } from "../../types/api";
import {
  formatCount,
  formatRelativeTime,
  formatTimestamp,
  formatValue,
} from "../../utils/format";

const modelName = (model?: MLModel) =>
  model
    ? `${model.algorithm.replace(/([a-z])([A-Z])/g, "$1 $2")} — Modèle ${model.display_number}`
    : "Aucun modèle actif";
const jsonNumber = (object: Record<string, unknown>, ...keys: string[]) => {
  for (const key of keys)
    if (object[key] !== undefined && object[key] !== null)
      return Number(object[key]);
  return null;
};
const jsonText = (object: Record<string, unknown>, ...keys: string[]) => {
  for (const key of keys)
    if (object[key] !== undefined && object[key] !== null)
      return String(object[key]);
  return null;
};

export default function MLPage() {
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState("overview");
  const [days, setDays] = useState(30);
  const [selected, setSelected] = useState<MLModel | null>(null);
  const models = useQuery({
    queryKey: queryKeys.models,
    queryFn: () => getPage<MLModel>("/ml/models/"),
  });
  const anomalies = useQuery({
    queryKey: ["anomalies", "ml-page"],
    queryFn: () => getPage<Anomaly>("/anomalies/"),
  });
  const tasks = useQuery({
    queryKey: ["tasks", "ml-page"],
    queryFn: () => getPage<TaskRun>("/tasks/"),
    enabled: can(user, "read:tasks"),
  });
  const ordered = useMemo(
    () =>
      [...(models.data?.results || [])].sort(
        (a, b) =>
          b.display_number - a.display_number ||
          Date.parse(b.created_at) - Date.parse(a.created_at),
      ),
    [models.data],
  );
  const active = ordered.find((model) => model.active) || ordered[0];
  const current = selected || active;
  const queue = useMutation({
    mutationFn: (action: "train" | "evaluate") =>
      postOne<
        { task_id: string; status: string },
        { days: number; idempotency_key: string }
      >(`/ml/models/${action}/`, {
        days,
        idempotency_key: `ui-${action}-${Date.now()}`,
      }),
    onSuccess: (data, action) => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.models });
      notify({
        tone: "success",
        title:
          action === "train"
            ? "Entraînement mis en file"
            : "Évaluation mise en file",
        detail: `Celery : ${data.task_id}. Cet ID n’est pas directement adressable par /api/tasks/{id}.`,
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Tâche non planifiée",
        detail: apiProblem(error).detail,
      }),
  });
  if (models.isLoading)
    return <LoadingState label="Chargement du registre des modèles…" />;
  const datasetSamples = current
    ? jsonNumber(
        current.dataset,
        "sample_count",
        "samples",
        "window_count",
        "rows",
      )
    : null;
  const contamination = current
    ? jsonNumber(current.parameters, "contamination")
    : null;
  const estimators = current
    ? jsonNumber(current.parameters, "n_estimators")
    : null;
  const precision = current
    ? jsonNumber(current.evaluation_metrics, "precision")
    : null;
  const recall = current
    ? jsonNumber(current.evaluation_metrics, "recall")
    : null;
  const overlap = current
    ? jsonNumber(current.evaluation_metrics, "overlap_count", "overlap")
    : null;
  const anomalyColumns: Column<Anomaly>[] = [
    {
      key: "machine",
      header: "Machine",
      sortValue: (row) => row.hostname,
      cell: (row) => (
        <Link
          className="entity-link"
          to={`/machines/${row.machine}?tab=anomalies`}
        >
          {row.hostname || String(row.machine).slice(0, 8)}
        </Link>
      ),
    },
    {
      key: "model",
      header: "Version",
      cell: (row) => <Badge tone="ml">{row.model_version}</Badge>,
    },
    {
      key: "score",
      header: "Score / seuil",
      sortValue: (row) => row.score,
      cell: (row) =>
        `${formatValue(row.score)} / ${formatValue(row.threshold)}`,
    },
    {
      key: "status",
      header: "État",
      cell: (row) => (
        <Badge tone={row.acknowledged ? "success" : "high"}>
          {row.acknowledged ? "Acquittée" : "À examiner"}
        </Badge>
      ),
    },
    {
      key: "time",
      header: "Détection",
      sortValue: (row) => Date.parse(row.detected_at),
      cell: (row) => (
        <time title={formatTimestamp(row.detected_at)}>
          {formatRelativeTime(row.detected_at)}
        </time>
      ),
    },
  ];
  const taskColumns: Column<TaskRun>[] = [
    {
      key: "task",
      header: "Tâche",
      cell: (row) => (
        <div>
          <strong>{row.task_name}</strong>
          <small className="technical-id">{row.celery_task_id || row.id}</small>
        </div>
      ),
    },
    {
      key: "status",
      header: "État",
      cell: (row) => (
        <Badge
          tone={
            row.status === "SUCCESS"
              ? "success"
              : row.status === "FAILED"
                ? "critical"
                : "info"
          }
        >
          {row.status}
        </Badge>
      ),
    },
    {
      key: "started",
      header: "Début",
      cell: (row) => formatTimestamp(row.started_at),
    },
    {
      key: "finished",
      header: "Fin",
      cell: (row) => formatTimestamp(row.finished_at),
    },
  ];
  return (
    <div className="ml-page">
      <PageHeader
        title="Machine Learning"
        description="Pipeline scientifique Isolation Forest entraîné sur les métriques normalisées réelles, avec versionnement et traçabilité."
        actions={
          canManage(user) && (
            <div className="cluster">
              <Select
                aria-label="Fenêtre d’entraînement"
                value={days}
                onChange={(event) => setDays(Number(event.target.value))}
              >
                <option value={7}>7 jours</option>
                <option value={30}>30 jours</option>
                <option value={90}>90 jours</option>
                <option value={365}>1 an</option>
              </Select>
              <Button
                variant="secondary"
                icon={FlaskConical}
                loading={queue.isPending}
                onClick={() => queue.mutate("evaluate")}
              >
                Évaluer
              </Button>
              <Button
                icon={Play}
                loading={queue.isPending}
                onClick={() => queue.mutate("train")}
              >
                Entraîner
              </Button>
            </div>
          )
        }
      />
      <div className="stats-grid">
        <StatCard
          label="Modèles versionnés"
          value={models.data?.count ?? 0}
          icon={<BrainCircuit />}
          tone="ml"
        />
        <StatCard
          label="Anomalies chargées"
          value={anomalies.data?.count ?? "—"}
          icon={<Activity />}
          tone="warning"
        />
        <StatCard
          label="Fenêtres du dataset"
          value={datasetSamples === null ? "—" : formatCount(datasetSamples)}
          icon={<Database />}
        />
        <StatCard
          label="Seuil de décision"
          value={
            current?.decision_threshold === null ||
            current?.decision_threshold === undefined
              ? "—"
              : formatValue(current.decision_threshold)
          }
          icon={<ShieldQuestion />}
          tone="blue"
        />
      </div>
      <Card className="model-hero">
        <div className="model-hero__identity">
          <span className="model-orbit">
            <BrainCircuit />
          </span>
          <div>
            <span className="eyebrow">Modèle sélectionné</span>
            <h2>{modelName(current)}</h2>
            <div className="cluster">
              {current?.active && (
                <Badge tone="success" dot>
                  Modèle actif
                </Badge>
              )}
              <Badge
                tone={
                  current?.status === "READY"
                    ? "success"
                    : current?.status === "FAILED"
                      ? "critical"
                      : "ml"
                }
              >
                {current?.status || "Non disponible"}
              </Badge>
            </div>
          </div>
        </div>
        <div className="model-hero__facts">
          <KeyValue
            label="Entraîné"
            value={formatTimestamp(current?.trained_at)}
          />
          <KeyValue
            label="Contamination"
            value={
              contamination === null
                ? "—"
                : `${formatValue(contamination * 100)} %`
            }
          />
          <KeyValue
            label="Estimateurs"
            value={estimators === null ? "—" : formatCount(estimators)}
          />
          <KeyValue label="Features" value={current?.features?.length || 0} />
        </div>
      </Card>
      <Tabs
        items={[
          { id: "overview", label: "Vue scientifique" },
          {
            id: "history",
            label: "Historique des modèles",
            count: ordered.length,
          },
          { id: "anomalies", label: "Anomalies", count: anomalies.data?.count },
          { id: "evaluation", label: "Évaluation" },
          {
            id: "tasks",
            label: "Tâches asynchrones",
            count: tasks.data?.count,
          },
        ]}
        active={tab}
        onChange={setTab}
      />
      <TabPanel active={tab} id="overview">
        {current ? (
          <div className="content-grid content-grid--equal">
            <Card>
              <CardHeader
                title="Pipeline reproductible"
                description="Configuration persistée avec la version du modèle."
              />
              <div className="pipeline-flow">
                <span>Raw metrics</span>
                <i>→</i>
                <span>Validation</span>
                <i>→</i>
                <span>Features</span>
                <i>→</i>
                <span>RobustScaler</span>
                <i>→</i>
                <span>Isolation Forest</span>
                <i>→</i>
                <span>Inference</span>
              </div>
              <div className="card-body details-grid">
                <KeyValue label="Algorithme" value={current.algorithm} />
                <KeyValue
                  label="Random state"
                  value={jsonText(current.parameters, "random_state") || "—"}
                />
                <KeyValue
                  label="Contamination"
                  value={
                    contamination === null
                      ? "—"
                      : `${formatValue(contamination * 100)} %`
                  }
                />
                <KeyValue
                  label="Estimateurs"
                  value={estimators === null ? "—" : estimators}
                />
              </div>
            </Card>
            <Card>
              <CardHeader
                title="Features utilisées"
                description="Les features réellement enregistrées dans cette version."
              />
              <div className="feature-list">
                {current.features?.length ? (
                  current.features.map((feature) => (
                    <Badge tone="ml" key={feature}>
                      {feature}
                    </Badge>
                  ))
                ) : (
                  <EmptyState
                    title="Schéma absent"
                    description="Aucune feature n’est renseignée dans cette version."
                  />
                )}
              </div>
            </Card>
            <Card>
              <CardHeader
                title="Prétraitement"
                description="Paramètres sérialisés par le pipeline."
              />
              <div className="card-body">
                <pre className="json-block">
                  {JSON.stringify(current.preprocessing, null, 2)}
                </pre>
              </div>
            </Card>
            <Card>
              <CardHeader
                title="Dataset"
                description="Provenance et fenêtre de données déclarées par le backend."
              />
              <div className="card-body">
                <pre className="json-block">
                  {JSON.stringify(current.dataset, null, 2)}
                </pre>
              </div>
            </Card>
          </div>
        ) : (
          <Card>
            <EmptyState
              title="Aucun modèle réel"
              description="Aucune version de modèle ML n’est disponible pour ce tenant. Un entraînement exige au moins 200 fenêtres réelles valides."
            />
          </Card>
        )}
      </TabPanel>
      <TabPanel active={tab} id="history">
        {ordered.length ? (
          <div className="model-history">
            {ordered.map((model) => (
              <button
                className={current?.id === model.id ? "is-selected" : ""}
                key={model.id}
                onClick={() => {
                  setSelected(model);
                  setTab("overview");
                }}
              >
                <span className="history-node">
                  <Beaker />
                </span>
                <div>
                  <div className="cluster">
                    <strong>{modelName(model)}</strong>
                    {model.active && <Badge tone="success">Actif</Badge>}
                    <Badge
                      tone={
                        model.status === "READY"
                          ? "success"
                          : model.status === "FAILED"
                            ? "critical"
                            : "ml"
                      }
                    >
                      {model.status}
                    </Badge>
                  </div>
                  <p>
                    Créé {formatRelativeTime(model.created_at)} · entraîné{" "}
                    {formatTimestamp(model.trained_at)}
                  </p>
                  <small className="technical-id">
                    Version technique : {model.version}
                  </small>
                </div>
              </button>
            ))}
          </div>
        ) : (
          <EmptyState
            title="Historique vide"
            description="Aucune version scientifique n’est persistée."
          />
        )}
      </TabPanel>
      <TabPanel active={tab} id="anomalies">
        <Card className="table-card">
          <CardHeader
            title="Anomalies persistées"
            description="Dernière page réelle renvoyée par l’API."
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
      <TabPanel active={tab} id="evaluation">
        {current ? (
          <div className="content-grid content-grid--equal">
            <Card>
              <CardHeader
                title="Métriques d’évaluation"
                description="Valeurs réellement enregistrées ; aucun résultat absent n’est reconstruit."
              />
              <div className="card-body details-grid">
                <KeyValue
                  label="Précision"
                  value={
                    precision === null
                      ? "Non calculable sans labels"
                      : formatValue(precision)
                  }
                />
                <KeyValue
                  label="Rappel"
                  value={
                    recall === null
                      ? "Non calculable sans labels"
                      : formatValue(recall)
                  }
                />
                <KeyValue
                  label="Chevauchements"
                  value={overlap === null ? "—" : formatCount(overlap)}
                />
                <KeyValue
                  label="Seuil"
                  value={
                    current.decision_threshold === null
                      ? "—"
                      : formatValue(current.decision_threshold)
                  }
                />
              </div>
            </Card>
            <Card>
              <CardHeader
                title="Limite scientifique"
                description="Interprétation correcte de l’évaluation actuelle."
              />
              <div className="card-body">
                <div className="inline-notice inline-notice--warning">
                  <ShieldQuestion />
                  Le backend compare les anomalies ML aux alertes de règles dans
                  une fenêtre temporelle. Sans labels de vérité terrain,
                  précision et rappel ne doivent pas être présentés comme
                  validés.
                </div>
                <pre className="json-block">
                  {JSON.stringify(current.evaluation_metrics, null, 2)}
                </pre>
              </div>
            </Card>
          </div>
        ) : (
          <EmptyState />
        )}
      </TabPanel>
      <TabPanel active={tab} id="tasks">
        {can(user, "read:tasks") ? (
          <Card className="table-card">
            <CardHeader
              title="Exécutions Celery"
              description="Accès réservé aux administrateurs par le backend."
              action={
                <Button
                  variant="ghost"
                  icon={RefreshCw}
                  onClick={() => tasks.refetch()}
                >
                  Actualiser
                </Button>
              }
            />
            <DataTable
              columns={taskColumns}
              rows={(tasks.data?.results || []).filter(
                (task) =>
                  task.task_name.toLowerCase().includes("model") ||
                  task.task_name.toLowerCase().includes("ml"),
              )}
              rowKey={(row) => row.id}
              loading={tasks.isLoading}
              error={tasks.error}
              retry={() => tasks.refetch()}
            />
          </Card>
        ) : (
          <Card>
            <EmptyState
              title="Journal réservé aux administrateurs"
              description="Votre rôle peut lancer une tâche ML s’il est superviseur, mais l’API /tasks reste réservée aux administrateurs."
            />
          </Card>
        )}
      </TabPanel>
      <Card className="scientific-note">
        <Clock3 />
        <div>
          <strong>Détection stable, pas instantanée</strong>
          <p>
            L’inférence demande une dernière fenêtre anormale et au moins trois
            anomalies sur cinq. La récupération exige trois fenêtres normales
            consécutives.
          </p>
        </div>
        <CheckCircle2 />
      </Card>
    </div>
  );
}
