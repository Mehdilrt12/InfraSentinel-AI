import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  Clock3,
  ExternalLink,
  ShieldCheck,
  Wrench,
} from "lucide-react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { getOne, patchOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import { alertOrigin } from "./AlertsPage";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  ErrorState,
  KeyValue,
  LoadingState,
  PageHeader,
  SeverityBadge,
  StatusBadge,
  useToast,
} from "../../components/common";
import type { Alert, AlertStatus, Machine } from "../../types/api";
import {
  formatRelativeTime,
  formatTimestamp,
  formatValue,
} from "../../utils/format";

export default function AlertDetailPage() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { notify } = useToast();
  const alert = useQuery({
    queryKey: ["alerts", id],
    queryFn: () => getOne<Alert>(`/alerts/${id}/`),
  });
  const machine = useQuery({
    queryKey: queryKeys.machine(alert.data?.machine || ""),
    queryFn: () => getOne<Machine>(`/machines/${alert.data!.machine}/`),
    enabled: Boolean(alert.data?.machine),
  });
  const update = useMutation({
    mutationFn: (status: AlertStatus) =>
      patchOne<Alert, { status: AlertStatus }>(`/alerts/${id}/`, { status }),
    onSuccess: (data) => {
      queryClient.setQueryData(["alerts", id], data);
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      notify({ tone: "success", title: `Alerte ${data.status.toLowerCase()}` });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Mise à jour impossible",
        detail: apiProblem(error).detail,
      }),
  });
  if (alert.isLoading)
    return <LoadingState label="Chargement de l’incident…" />;
  if (alert.isError || !alert.data)
    return (
      <>
        <PageHeader
          title="Incident"
          breadcrumbs={[
            { label: "Alertes", to: "/alerts" },
            { label: "Introuvable" },
          ]}
        />
        <ErrorState
          title="Alerte introuvable"
          description={apiProblem(alert.error).detail}
          retry={() => alert.refetch()}
        />
      </>
    );
  const item = alert.data;
  const origin = alertOrigin(item);
  const recommendation = item.structured_recommendation;
  const sourceDescription =
    origin.label === "Règle de supervision"
      ? "Seuil configurable évalué dans le temps."
      : origin.label === "Anomalie ML"
        ? "Comportement multidimensionnel inhabituel détecté par Isolation Forest."
        : "Tendance statistique estimant un risque futur.";
  return (
    <div>
      <PageHeader
        breadcrumbs={[
          { label: "Alertes", to: "/alerts" },
          { label: item.id.slice(0, 8) },
        ]}
        title={item.message}
        description="Dossier d’incident centralisé, contexte technique et recommandation explicable."
        actions={
          <>
            <SeverityBadge severity={item.severity} />
            <StatusBadge status={item.status} />
          </>
        }
      />
      <div className="incident-hero">
        <Card>
          <div className="details-grid">
            <KeyValue
              label="Machine"
              value={machine.data?.hostname || item.hostname || item.machine}
              hint={machine.data?.ip_address}
            />
            <KeyValue
              label="Origine"
              value={<Badge tone={origin.tone}>{origin.label}</Badge>}
              hint={sourceDescription}
            />
            <KeyValue
              label="Première détection"
              value={formatRelativeTime(item.first_seen_at)}
              hint={formatTimestamp(item.first_seen_at)}
            />
            <KeyValue
              label="Dernière activité"
              value={formatRelativeTime(item.last_seen_at)}
              hint={formatTimestamp(item.last_seen_at)}
            />
            <KeyValue label="Occurrences" value={item.occurrences} />
            <KeyValue label="Niveau d’escalade" value={item.escalation_level} />
            <KeyValue
              label="Score anomalie"
              value={
                item.anomaly_score === null
                  ? "Non applicable"
                  : formatValue(item.anomaly_score)
              }
            />
            <KeyValue
              label="Source technique"
              value={item.source}
              hint={item.type}
            />
          </div>
        </Card>
        {canManage(user) && (
          <div className="incident-actions">
            <span>Mettre à jour le cycle de vie :</span>
            {item.status === "NEW" && (
              <Button
                variant="secondary"
                icon={ShieldCheck}
                loading={update.isPending}
                onClick={() => update.mutate("ACKNOWLEDGED")}
              >
                Acquitter
              </Button>
            )}
            {["NEW", "ACKNOWLEDGED"].includes(item.status) && (
              <Button
                variant="secondary"
                icon={Clock3}
                loading={update.isPending}
                onClick={() => update.mutate("IN_PROGRESS")}
              >
                Prendre en charge
              </Button>
            )}
            {item.status !== "RESOLVED" && (
              <Button
                icon={CheckCircle2}
                loading={update.isPending}
                onClick={() => update.mutate("RESOLVED")}
              >
                Résoudre
              </Button>
            )}
          </div>
        )}
      </div>
      <div className="content-grid content-grid--equal">
        <Card>
          <CardHeader
            title="Contexte de détection"
            description="Données techniques persistées par le moteur d’alerte."
          />
          <div className="card-body">
            <pre className="json-block">
              {JSON.stringify(item.context, null, 2)}
            </pre>
          </div>
        </Card>
        <Card className="recommendation-card">
          <CardHeader
            title="Recommandation exploitable"
            description="Conseils contextualisés, explicables et non destructifs par défaut."
            action={<Wrench />}
          />
          <div className="card-body">
            <p className="recommendation-rationale">
              {recommendation?.rationale ||
                item.recommendation ||
                "Aucune recommandation n’a été générée pour cet incident."}
            </p>
            {recommendation?.diagnosis_hints?.length ? (
              <section>
                <h3>Indices de diagnostic</h3>
                <ul>
                  {recommendation.diagnosis_hints.map((hint) => (
                    <li key={hint}>{hint}</li>
                  ))}
                </ul>
              </section>
            ) : null}
            {recommendation?.actions?.length ? (
              <section>
                <h3>Actions suggérées</h3>
                <ol>
                  {recommendation.actions.map((action) => (
                    <li key={action}>{action}</li>
                  ))}
                </ol>
              </section>
            ) : null}
            {recommendation && (
              <Badge tone={recommendation.destructive ? "critical" : "success"}>
                {recommendation.destructive
                  ? "Action potentiellement destructive"
                  : "Non destructif par défaut"}
              </Badge>
            )}
          </div>
        </Card>
      </div>
      <Card className="incident-timeline">
        <CardHeader
          title="Chronologie"
          description="La granularité disponible correspond aux timestamps et compteurs exposés par l’API."
        />
        <ol>
          <li>
            <span />
            <div>
              <strong>Incident créé</strong>
              <time>{formatTimestamp(item.timestamp)}</time>
            </div>
          </li>
          <li>
            <span />
            <div>
              <strong>Première occurrence consolidée</strong>
              <time>{formatTimestamp(item.first_seen_at)}</time>
            </div>
          </li>
          <li>
            <span />
            <div>
              <strong>Dernière occurrence</strong>
              <time>{formatTimestamp(item.last_seen_at)}</time>
            </div>
          </li>
          <li className={item.status === "RESOLVED" ? "is-complete" : ""}>
            <span />
            <div>
              <strong>
                {item.status === "RESOLVED"
                  ? "Incident résolu"
                  : "Résolution en attente"}
              </strong>
              <time>
                {item.status === "RESOLVED"
                  ? formatTimestamp(item.updated_at)
                  : "—"}
              </time>
            </div>
          </li>
        </ol>
      </Card>
      <div className="page-bottom-actions">
        <Button
          variant="ghost"
          icon={ArrowLeft}
          onClick={() => navigate("/alerts")}
        >
          Retour aux alertes
        </Button>
        <Link
          className="button button--secondary button--md"
          to={`/machines/${item.machine}?tab=alerts`}
        >
          <ExternalLink />
          Ouvrir la machine
        </Link>
        {origin.label === "Anomalie ML" && (
          <Link className="button button--secondary button--md" to="/ml">
            <BrainCircuit />
            Ouvrir le modèle ML
          </Link>
        )}
      </div>
    </div>
  );
}
