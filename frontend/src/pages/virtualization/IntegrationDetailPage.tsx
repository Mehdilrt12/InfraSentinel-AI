import { useQuery } from "@tanstack/react-query";
import { Boxes, CloudCog, Database, Server } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { getOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import {
  Badge,
  Card,
  CardHeader,
  EmptyState,
  ErrorState,
  KeyValue,
  LoadingState,
  PageHeader,
  SourceBadge,
  StatusBadge,
} from "../../components/common";
import type {
  IntegrationOverview,
  Machine,
  VirtualAsset,
} from "../../types/api";
import {
  formatBytes,
  formatRelativeTime,
  formatTimestamp,
  formatValue,
} from "../../utils/format";
import type { IntegrationSource } from "./IntegrationPage";

function pick(metadata: Record<string, unknown>, keys: string[]) {
  for (const key of keys)
    if (
      metadata[key] !== undefined &&
      metadata[key] !== null &&
      metadata[key] !== ""
    )
      return metadata[key];
  return null;
}
function displayMetadataValue(key: string, value: unknown) {
  if (value === null || value === undefined || value === "") return "—";
  if (
    /bytes|capacity|memory|storage|disk|free/i.test(key) &&
    Number.isFinite(Number(value))
  )
    return formatBytes(Number(value));
  if (/percent|utilization/i.test(key) && Number.isFinite(Number(value)))
    return `${formatValue(Number(value))} %`;
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export default function IntegrationDetailPage({
  source,
}: {
  source: IntegrationSource;
}) {
  const { id = "" } = useParams();
  const route = source === "VMWARE" ? "vmware" : "hyperv";
  const overview = useQuery({
    queryKey: queryKeys.integration(source),
    queryFn: () => getOne<IntegrationOverview>(`/${route}/overview/`),
  });
  const allAssets = overview.data
    ? [
        ...overview.data.hosts,
        ...overview.data.vms,
        ...overview.data.datastores,
      ]
    : [];
  const asset = allAssets.find((item) => item.id === id);
  const connector = overview.data?.connectors.find((item) => item.id === id);
  const machine = useQuery({
    queryKey: queryKeys.machine(asset?.machine || ""),
    queryFn: () => getOne<Machine>(`/machines/${asset!.machine}/`),
    enabled: Boolean(asset?.machine),
  });
  if (overview.isLoading) return <LoadingState />;
  if (overview.isError) return <ErrorState retry={() => overview.refetch()} />;
  if (!asset && !connector)
    return (
      <>
        <PageHeader
          title="Ressource introuvable"
          breadcrumbs={[
            {
              label: source === "VMWARE" ? "VMware" : "Hyper-V",
              to: `/${route}`,
            },
            { label: "Introuvable" },
          ]}
        />
        <ErrorState
          title="Asset ou connecteur introuvable"
          description="Cette ressource n’apparaît pas dans l’overview réel du tenant."
        />
      </>
    );
  if (connector)
    return (
      <div>
        <PageHeader
          breadcrumbs={[
            {
              label: source === "VMWARE" ? "VMware" : "Hyper-V",
              to: `/${route}`,
            },
            { label: connector.name },
          ]}
          title={connector.name}
          description="Configuration publique et santé opérationnelle du connecteur. La valeur du secret n’est jamais exposée."
          actions={
            <>
              <SourceBadge source={source} />
              <Badge
                tone={
                  !connector.enabled
                    ? "neutral"
                    : connector.last_error
                      ? "critical"
                      : "success"
                }
                dot
              >
                {!connector.enabled
                  ? "Désactivé"
                  : connector.last_error
                    ? "Erreur"
                    : "Actif"}
              </Badge>
            </>
          }
        />
        <Card>
          <div className="details-grid">
            <KeyValue label="Endpoint" value={connector.endpoint} />
            <KeyValue
              label="Utilisateur"
              value={connector.username || "Non renseigné"}
            />
            <KeyValue
              label="TLS"
              value={
                connector.verify_tls
                  ? "Vérification activée"
                  : "Vérification désactivée"
              }
            />
            <KeyValue
              label="Timeout"
              value={`${connector.timeout_seconds} s`}
            />
            <KeyValue
              label="Dernière synchronisation"
              value={formatRelativeTime(connector.last_sync_at)}
              hint={formatTimestamp(connector.last_sync_at)}
            />
            <KeyValue label="Environnement" value={connector.environment} />
            <KeyValue
              label="État"
              value={connector.enabled ? "Activé" : "Désactivé"}
            />
            <KeyValue label="Secret" value="Référence serveur masquée" />
          </div>
        </Card>
        {connector.last_error && (
          <Card className="connector-error">
            <CardHeader
              title="Dernière erreur publique"
              description="Message nettoyé exposé par l’API."
            />
            <div className="card-body">
              <p>{connector.last_error}</p>
            </div>
          </Card>
        )}
        <Card>
          <CardHeader
            title="Configuration non sensible"
            description="Aucun mot de passe, token ou credential ne peut être stocké dans cet objet."
          />
          <div className="card-body">
            <pre className="json-block">
              {JSON.stringify(connector.config, null, 2)}
            </pre>
          </div>
        </Card>
      </div>
    );
  const AssetIcon =
    asset!.kind === "HOST"
      ? Server
      : asset!.kind === "DATASTORE"
        ? Database
        : Boxes;
  const parent = allAssets.find(
    (item) => item.external_id === asset!.parent_external_id,
  );
  return (
    <div>
      <PageHeader
        breadcrumbs={[
          {
            label: source === "VMWARE" ? "VMware" : "Hyper-V",
            to: `/${route}`,
          },
          { label: asset!.name },
        ]}
        title={asset!.name}
        description={`${asset!.kind} découvert et historisé par le connecteur ${source}.`}
        actions={
          <>
            <SourceBadge source={source} />
            <StatusBadge status={asset!.state} />
          </>
        }
      />
      <div className="asset-hero">
        <span>
          <AssetIcon />
        </span>
        <Card>
          <div className="details-grid">
            <KeyValue label="Type" value={asset!.kind} />
            <KeyValue label="État" value={asset!.state || "Inconnu"} />
            <KeyValue
              label="Parent"
              value={
                parent ? (
                  <Link className="entity-link" to={`/${route}/${parent.id}`}>
                    {parent.name}
                  </Link>
                ) : (
                  asset!.parent_external_id || "Racine"
                )
              }
            />
            <KeyValue
              label="Dernière observation"
              value={formatRelativeTime(asset!.last_seen)}
              hint={formatTimestamp(asset!.last_seen)}
            />
            <KeyValue
              label="Machine normalisée"
              value={
                machine.data ? (
                  <Link
                    className="entity-link"
                    to={`/machines/${machine.data.id}`}
                  >
                    {machine.data.hostname}
                  </Link>
                ) : (
                  asset!.machine || "Non associée"
                )
              }
            />
            <KeyValue label="Identifiant externe" value={asset!.external_id} />
            <KeyValue
              label="CPU"
              value={displayMetadataValue(
                "cpu_utilization",
                pick(asset!.metadata, [
                  "cpu_utilization",
                  "cpu_percent",
                  "cpu_usage_percent",
                ]),
              )}
            />
            <KeyValue
              label="Mémoire"
              value={displayMetadataValue(
                "memory_utilization",
                pick(asset!.metadata, [
                  "memory_utilization",
                  "memory_percent",
                  "memory_usage_percent",
                ]),
              )}
            />
          </div>
        </Card>
      </div>
      <Card>
        <CardHeader
          title="Métadonnées spécifiques préservées"
          description="Informations spécifiques VMware/Hyper-V conservées sans casser le modèle commun de métriques."
        />
        {Object.keys(asset!.metadata || {}).length ? (
          <div className="metadata-grid">
            {Object.entries(asset!.metadata).map(([key, value]) => (
              <KeyValue
                key={key}
                label={key.replaceAll("_", " ")}
                value={displayMetadataValue(key, value)}
              />
            ))}
          </div>
        ) : (
          <EmptyState
            title="Métadonnées absentes"
            description="Aucune information spécifique n’est persistée pour cet asset."
          />
        )}
      </Card>
    </div>
  );
}
