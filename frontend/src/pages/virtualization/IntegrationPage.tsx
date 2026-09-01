import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Boxes,
  CloudCog,
  Database,
  ExternalLink,
  HardDrive,
  Play,
  Plus,
  Server,
  Workflow,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { getOne, getPage, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  EmptyState,
  ErrorState,
  KeyValue,
  LoadingState,
  PageHeader,
  PartialState,
  SourceBadge,
  StatCard,
  StatusBadge,
  TabPanel,
  Tabs,
  useToast,
  type Column,
} from "../../components/common";
import type {
  CollectionRun,
  Connector,
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

export type IntegrationSource = "VMWARE" | "HYPERV";
const COPY = {
  VMWARE: {
    title: "VMware / vCenter",
    description:
      "Inventaire réel des vCenter, hôtes ESXi, machines virtuelles et datastores collectés par pyVmomi.",
    icon: CloudCog,
  },
  HYPERV: {
    title: "Microsoft Hyper-V",
    description:
      "Inventaire réel des hôtes et VM collectés par PowerShell, CIM/WMI et les cmdlets Hyper-V.",
    icon: Boxes,
  },
};

function metadataValue(asset: VirtualAsset, keys: string[]) {
  for (const key of keys) {
    const value = asset.metadata?.[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return null;
}
function utilization(asset: VirtualAsset, keys: string[]) {
  const value = metadataValue(asset, keys);
  return value === null || !Number.isFinite(Number(value))
    ? "—"
    : `${formatValue(Number(value))} %`;
}

export default function IntegrationPage({
  source,
}: {
  source: IntegrationSource;
}) {
  const copy = COPY[source];
  const Icon = copy.icon;
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [tab, setTab] = useState("overview");
  const overview = useQuery({
    queryKey: queryKeys.integration(source),
    queryFn: () =>
      getOne<IntegrationOverview>(
        `/${source === "VMWARE" ? "vmware" : "hyperv"}/overview/`,
      ),
  });
  const runs = useQuery({
    queryKey: ["collection-runs", source],
    queryFn: () => getPage<CollectionRun>("/collection-runs/"),
  });
  const machines = useQuery({
    queryKey: ["machines", source],
    queryFn: () => getPage<Machine>("/machines/"),
  });
  const collect = useMutation({
    mutationFn: (connector: Connector) =>
      postOne<{ task_id: string; status: string }>(
        `/connectors/${connector.id}/collect/`,
      ),
    onSuccess: (data) => {
      void queryClient.invalidateQueries({ queryKey: ["collection-runs"] });
      notify({
        tone: "success",
        title: "Collecte mise en file",
        detail: `Tâche Celery ${data.task_id}.`,
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Collecte non planifiée",
        detail: apiProblem(error).detail,
      }),
  });
  const machineMap = useMemo(
    () =>
      new Map(
        (machines.data?.results || []).map((machine) => [machine.id, machine]),
      ),
    [machines.data],
  );
  if (overview.isLoading)
    return <LoadingState label={`Chargement de l’inventaire ${source}…`} />;
  if (overview.isError || !overview.data)
    return (
      <>
        <PageHeader title={copy.title} description={copy.description} />
        <ErrorState
          description={apiProblem(overview.error).detail}
          retry={() => overview.refetch()}
        />
      </>
    );
  const data = overview.data;
  const connectorIds = new Set(
    data.connectors.map((connector) => connector.id),
  );
  const relatedRuns = (runs.data?.results || []).filter((run) =>
    connectorIds.has(run.connector),
  );
  const configured = data.connectors.length > 0;
  const assetColumns: Column<VirtualAsset>[] = [
    {
      key: "name",
      header: "Asset",
      sortValue: (row) => row.name,
      cell: (row) => (
        <div className="entity-cell">
          <span className="machine-icon">
            {row.kind === "HOST" ? (
              <Server />
            ) : row.kind === "DATASTORE" ? (
              <Database />
            ) : (
              <Boxes />
            )}
          </span>
          <div>
            <strong>{row.name}</strong>
            <small>
              {row.kind} ·{" "}
              <span className="technical-id">{row.external_id}</span>
            </small>
          </div>
        </div>
      ),
    },
    {
      key: "state",
      header: "État",
      sortValue: (row) => row.state,
      cell: (row) => <StatusBadge status={row.state || "UNKNOWN"} />,
    },
    {
      key: "cpu",
      header: "CPU",
      cell: (row) =>
        utilization(row, [
          "cpu_utilization",
          "cpu_percent",
          "cpu_usage_percent",
        ]),
    },
    {
      key: "memory",
      header: "Mémoire",
      cell: (row) =>
        utilization(row, [
          "memory_utilization",
          "memory_percent",
          "memory_usage_percent",
        ]),
    },
    {
      key: "parent",
      header: "Parent",
      cell: (row) =>
        row.parent_external_id || <span className="muted">Racine</span>,
    },
    {
      key: "seen",
      header: "Dernière collecte",
      sortValue: (row) => Date.parse(row.last_seen || "0"),
      cell: (row) => (
        <time title={formatTimestamp(row.last_seen)}>
          {formatRelativeTime(row.last_seen)}
        </time>
      ),
    },
  ];
  const connectorColumns: Column<Connector>[] = [
    {
      key: "name",
      header: "Connecteur",
      cell: (row) => (
        <div>
          <strong>{row.name}</strong>
          <small>{row.endpoint}</small>
        </div>
      ),
    },
    {
      key: "state",
      header: "État",
      cell: (row) => (
        <Badge
          tone={
            !row.enabled ? "neutral" : row.last_error ? "critical" : "success"
          }
          dot
        >
          {!row.enabled ? "Désactivé" : row.last_error ? "Erreur" : "Actif"}
        </Badge>
      ),
    },
    {
      key: "tls",
      header: "Sécurité",
      cell: (row) => (
        <Badge tone={row.verify_tls ? "success" : "warning"}>
          {row.verify_tls ? "TLS vérifié" : "TLS non vérifié"}
        </Badge>
      ),
    },
    {
      key: "sync",
      header: "Dernière synchro",
      cell: (row) => formatRelativeTime(row.last_sync_at),
    },
    {
      key: "actions",
      header: "Action",
      cell: (row) =>
        canManage(user) ? (
          <Button
            size="sm"
            variant="secondary"
            icon={Play}
            loading={collect.isPending}
            disabled={!row.enabled}
            onClick={(event) => {
              event.stopPropagation();
              collect.mutate(row);
            }}
          >
            Collecter
          </Button>
        ) : (
          <span className="muted">Lecture seule</span>
        ),
    },
  ];
  const runColumns: Column<CollectionRun>[] = [
    {
      key: "id",
      header: "Exécution",
      cell: (row) => <span className="technical-id">#{row.id}</span>,
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
      key: "inventory",
      header: "Découverte",
      cell: (row) =>
        `${row.discovered_hosts} hôte(s) · ${row.discovered_vms} VM · ${row.discovered_datastores} datastore(s)`,
    },
    {
      key: "metrics",
      header: "Métriques",
      sortValue: (row) => row.metric_count,
      cell: (row) => row.metric_count,
    },
    {
      key: "started",
      header: "Démarrage",
      cell: (row) => formatTimestamp(row.started_at),
    },
    {
      key: "duration",
      header: "Fin",
      cell: (row) => formatTimestamp(row.finished_at),
    },
  ];
  return (
    <div>
      <PageHeader
        title={copy.title}
        description={copy.description}
        actions={
          <>
            {data.partial && <Badge tone="warning">Données partielles</Badge>}
            {canManage(user) && (
              <Link
                className="button button--secondary button--md"
                to="/settings?tab=integrations"
              >
                <Plus />
                Configurer
              </Link>
            )}
          </>
        }
      />
      {data.partial && (
        <PartialState>
          Au moins un connecteur signale une erreur de collecte. Les assets déjà
          historisés restent visibles.
        </PartialState>
      )}
      {!configured && (
        <Card className="integration-empty">
          <Icon />
          <div>
            <span className="eyebrow">Non configuré</span>
            <h2>
              Aucun connecteur {source === "VMWARE" ? "vCenter" : "Hyper-V"}
            </h2>
            <p>
              L’intégration est implémentée mais aucune source réelle n’est
              configurée pour ce tenant. Aucune donnée de démonstration n’est
              générée.
            </p>
            {canManage(user) && (
              <Link
                className="button button--primary button--md"
                to="/settings?tab=integrations"
              >
                Configurer une source
              </Link>
            )}
          </div>
        </Card>
      )}
      <div className="stats-grid">
        <StatCard
          label="Connecteurs"
          value={data.connectors.length}
          icon={<Workflow />}
        />
        <StatCard
          label="Hôtes découverts"
          value={data.hosts.length}
          icon={<Server />}
          tone="blue"
        />
        <StatCard
          label="Machines virtuelles"
          value={data.vms.length}
          icon={<Boxes />}
        />
        <StatCard
          label={source === "VMWARE" ? "Datastores" : "Exécutions chargées"}
          value={
            source === "VMWARE" ? data.datastores.length : relatedRuns.length
          }
          icon={<HardDrive />}
          tone="warning"
        />
      </div>
      <Tabs
        items={[
          { id: "overview", label: "Vue infrastructure" },
          { id: "hosts", label: "Hôtes", count: data.hosts.length },
          { id: "vms", label: "Machines virtuelles", count: data.vms.length },
          ...(source === "VMWARE"
            ? [
                {
                  id: "datastores",
                  label: "Datastores",
                  count: data.datastores.length,
                },
              ]
            : []),
          {
            id: "connectors",
            label: "Connecteurs",
            count: data.connectors.length,
          },
          { id: "runs", label: "Collectes", count: relatedRuns.length },
        ]}
        active={tab}
        onChange={setTab}
      />
      <TabPanel active={tab} id="overview">
        <div className="content-grid content-grid--equal">
          <Card>
            <CardHeader
              title="Topologie réelle"
              description="Relation connecteurs → hôtes → VM telle que persistée par le backend."
            />
            {data.hosts.length ? (
              <div className="topology-list">
                {data.hosts.map((host) => (
                  <button
                    key={host.id}
                    onClick={() =>
                      navigate(`/${source.toLowerCase()}/${host.id}`)
                    }
                  >
                    <span className="topology-icon">
                      <Server />
                    </span>
                    <div>
                      <strong>{host.name}</strong>
                      <small>
                        {
                          data.vms.filter(
                            (vm) => vm.parent_external_id === host.external_id,
                          ).length
                        }{" "}
                        VM associée(s)
                      </small>
                    </div>
                    <StatusBadge status={host.state} />
                    <ExternalLink />
                  </button>
                ))}
              </div>
            ) : (
              <EmptyState
                title="Aucun hôte découvert"
                description={
                  configured
                    ? "Aucune collecte réussie n’a encore persisté d’hôte."
                    : "Configurez une source réelle pour commencer la découverte."
                }
              />
            )}
          </Card>
          <Card>
            <CardHeader
              title="Santé des connecteurs"
              description="État réel de la dernière synchronisation."
            />
            {data.connectors.length ? (
              <div className="connector-health">
                {data.connectors.map((connector) => (
                  <Link
                    to={`/${source.toLowerCase()}/${connector.id}`}
                    key={connector.id}
                  >
                    <div className="split">
                      <strong>{connector.name}</strong>
                      <Badge
                        tone={
                          !connector.enabled
                            ? "neutral"
                            : connector.last_error
                              ? "critical"
                              : "success"
                        }
                      >
                        {!connector.enabled
                          ? "Désactivé"
                          : connector.last_error
                            ? "Erreur"
                            : "Actif"}
                      </Badge>
                    </div>
                    <p>{connector.endpoint}</p>
                    {connector.last_error ? (
                      <small className="error-text">
                        {connector.last_error}
                      </small>
                    ) : (
                      <small>
                        Dernière synchro :{" "}
                        {formatRelativeTime(connector.last_sync_at)}
                      </small>
                    )}
                  </Link>
                ))}
              </div>
            ) : (
              <EmptyState />
            )}
          </Card>
        </div>
      </TabPanel>
      <TabPanel active={tab} id="hosts">
        <Card className="table-card">
          <DataTable
            columns={assetColumns}
            rows={data.hosts}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/${source.toLowerCase()}/${row.id}`)}
            emptyTitle="Aucun hôte"
          />
        </Card>
      </TabPanel>
      <TabPanel active={tab} id="vms">
        <Card className="table-card">
          <DataTable
            columns={assetColumns}
            rows={data.vms}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/${source.toLowerCase()}/${row.id}`)}
            emptyTitle="Aucune VM"
          />
        </Card>
      </TabPanel>
      {source === "VMWARE" && (
        <TabPanel active={tab} id="datastores">
          <Card className="table-card">
            <DataTable
              columns={assetColumns}
              rows={data.datastores}
              rowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/vmware/${row.id}`)}
              emptyTitle="Aucun datastore"
            />
          </Card>
        </TabPanel>
      )}
      <TabPanel active={tab} id="connectors">
        <Card className="table-card">
          <DataTable
            columns={connectorColumns}
            rows={data.connectors}
            rowKey={(row) => row.id}
            onRowClick={(row) => navigate(`/${source.toLowerCase()}/${row.id}`)}
            emptyTitle="Aucun connecteur"
          />
        </Card>
      </TabPanel>
      <TabPanel active={tab} id="runs">
        <Card className="table-card">
          <DataTable
            columns={runColumns}
            rows={relatedRuns}
            rowKey={(row) => row.id}
            loading={runs.isLoading}
            error={runs.error}
            retry={() => runs.refetch()}
            emptyTitle="Aucune collecte historisée"
          />
        </Card>
      </TabPanel>
      <div className="inline-notice integration-disclaimer">
        <Icon />
        Les collecteurs sont des intégrations réelles. Leur connexion à une
        infrastructure externe reste non testée dans cet environnement local ;
        zéro asset ne signifie pas qu’une plateforme externe a été validée.
      </div>
    </div>
  );
}
