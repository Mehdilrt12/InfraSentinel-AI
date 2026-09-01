import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bell,
  CloudCog,
  Gauge,
  Mail,
  Pencil,
  Plus,
  Power,
  ServerCog,
  Trash2,
} from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { deleteOne, getPage, patchOne, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { SettingsEditor, type SettingsEditorState } from "./SettingsEditor";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  DataTable,
  Modal,
  PageHeader,
  SourceBadge,
  StatusBadge,
  TabPanel,
  Tabs,
  useToast,
  type Column,
} from "../../components/common";
import type {
  Connector,
  Environment,
  Machine,
  MonitoringRule,
  NotificationDelivery,
  NotificationPreference,
} from "../../types/api";
import {
  formatDuration,
  formatRelativeTime,
  formatTimestamp,
  metricLabel,
} from "../../utils/format";

export default function SettingsPage() {
  const { user } = useAuth();
  const { notify } = useToast();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedTab = searchParams.get("tab");
  const tab = [
    "rules",
    "notifications",
    "environments",
    "integrations",
  ].includes(requestedTab || "")
    ? requestedTab!
    : "rules";
  const [editor, setEditor] = useState<SettingsEditorState>(null);
  const [deleteTarget, setDeleteTarget] = useState<{
    kind: string;
    id: string | number;
    label: string;
  } | null>(null);
  const rules = useQuery({
    queryKey: queryKeys.rules,
    queryFn: () => getPage<MonitoringRule>("/rules/"),
  });
  const preferences = useQuery({
    queryKey: queryKeys.notificationPreferences,
    queryFn: () =>
      getPage<NotificationPreference>("/notifications/preferences/"),
  });
  const deliveries = useQuery({
    queryKey: queryKeys.notificationDeliveries,
    queryFn: () => getPage<NotificationDelivery>("/notifications/deliveries/"),
  });
  const environments = useQuery({
    queryKey: queryKeys.environments,
    queryFn: () => getPage<Environment>("/environments/"),
  });
  const machines = useQuery({
    queryKey: ["machines", "settings"],
    queryFn: () => getPage<Machine>("/machines/"),
  });
  const connectors = useQuery({
    queryKey: queryKeys.connectors,
    queryFn: () => getPage<Connector>("/connectors/"),
  });
  const invalidate = (...roots: string[]) =>
    roots.forEach(
      (root) => void queryClient.invalidateQueries({ queryKey: [root] }),
    );
  const toggleRule = useMutation({
    mutationFn: (rule: MonitoringRule) =>
      postOne<MonitoringRule>(`/rules/${rule.id}/toggle/`),
    onSuccess: () => {
      invalidate("rules");
      notify({ tone: "success", title: "État de la règle modifié" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Action impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const togglePreference = useMutation({
    mutationFn: (preference: NotificationPreference) =>
      patchOne<NotificationPreference, { enabled: boolean }>(
        `/notifications/preferences/${preference.id}/`,
        { enabled: !preference.enabled },
      ),
    onSuccess: () => {
      invalidate("notification-preferences");
      notify({ tone: "success", title: "Préférence mise à jour" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Action impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const save = useMutation({
    mutationFn: async ({
      path,
      body,
      id,
    }: {
      path: string;
      body: Record<string, unknown>;
      id?: string | number;
    }) => (id ? patchOne(`${path}${id}/`, body) : postOne(path, body)),
    onSuccess: () => {
      invalidate(
        "rules",
        "notification-preferences",
        "environments",
        "connectors",
      );
      setEditor(null);
      notify({ tone: "success", title: "Configuration enregistrée" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Configuration refusée",
        detail: `${apiProblem(error).detail}${apiProblem(error).fields ? ` ${Object.values(apiProblem(error).fields!).join(" ")}` : ""}`,
      }),
  });
  const remove = useMutation({
    mutationFn: () => deleteOne(`/${deleteTarget!.kind}/${deleteTarget!.id}/`),
    onSuccess: () => {
      invalidate(
        "rules",
        "notification-preferences",
        "environments",
        "connectors",
      );
      setDeleteTarget(null);
      notify({ tone: "success", title: "Configuration supprimée" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Suppression impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const ruleColumns: Column<MonitoringRule>[] = [
    {
      key: "name",
      header: "Règle",
      sortValue: (row) => row.name,
      cell: (row) => (
        <div>
          <strong>{row.name}</strong>
          <small>
            {metricLabel(row.metric)} ·{" "}
            <span className="technical-id">{row.metric}</span>
          </small>
        </div>
      ),
    },
    {
      key: "condition",
      header: "Condition",
      cell: (row) => (
        <strong>
          {row.operator} {row.threshold}
        </strong>
      ),
    },
    {
      key: "duration",
      header: "Durée / cooldown",
      cell: (row) => (
        <div>
          {formatDuration(row.duration_seconds)}
          <small>Cooldown {formatDuration(row.cooldown_seconds)}</small>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Sévérité",
      cell: (row) => (
        <Badge tone={row.severity.toLowerCase()}>{row.severity}</Badge>
      ),
    },
    {
      key: "scope",
      header: "Portée",
      cell: (row) =>
        row.machine
          ? `Machine · ${machines.data?.results.find((machine) => machine.id === row.machine)?.hostname || String(row.machine).slice(0, 8)}`
          : row.environment
            ? `Environnement · ${environments.data?.results.find((environment) => environment.id === row.environment)?.name || String(row.environment).slice(0, 8)}`
            : "Tout le tenant",
    },
    {
      key: "enabled",
      header: "État",
      cell: (row) => (
        <Badge tone={row.enabled ? "success" : "neutral"} dot>
          {row.enabled ? "Active" : "Désactivée"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="row-actions">
          <Button
            variant="ghost"
            size="sm"
            icon={Power}
            onClick={(event) => {
              event.stopPropagation();
              toggleRule.mutate(row);
            }}
          >
            {row.enabled ? "Désactiver" : "Activer"}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={Pencil}
            onClick={(event) => {
              event.stopPropagation();
              setEditor({ kind: "rule", value: row });
            }}
          >
            Modifier
          </Button>
          <Button
            variant="ghost"
            size="sm"
            icon={Trash2}
            onClick={(event) => {
              event.stopPropagation();
              setDeleteTarget({ kind: "rules", id: row.id, label: row.name });
            }}
          >
            Supprimer
          </Button>
        </div>
      ),
    },
  ];
  const preferenceColumns: Column<NotificationPreference>[] = [
    {
      key: "channel",
      header: "Canal",
      cell: (row) => (
        <Badge tone={row.channel === "EMAIL" ? "success" : "neutral"}>
          {row.channel}
        </Badge>
      ),
    },
    {
      key: "destination",
      header: "Destination",
      cell: (row) => (
        <div>
          <strong>{row.destination}</strong>
          <small>
            {row.user ? `Utilisateur #${row.user}` : "Tenant entier"}
          </small>
        </div>
      ),
    },
    {
      key: "severity",
      header: "Sévérité minimale",
      cell: (row) => (
        <Badge tone={row.minimum_severity.toLowerCase()}>
          {row.minimum_severity}
        </Badge>
      ),
    },
    {
      key: "cooldown",
      header: "Anti-spam",
      cell: (row) => formatDuration(row.cooldown_seconds),
    },
    {
      key: "enabled",
      header: "État",
      cell: (row) => (
        <Badge tone={row.enabled ? "success" : "neutral"} dot>
          {row.enabled ? "Active" : "Désactivée"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="row-actions">
          <Button
            size="sm"
            variant="ghost"
            icon={Power}
            onClick={() => togglePreference.mutate(row)}
          >
            {row.enabled ? "Désactiver" : "Activer"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Pencil}
            onClick={() => setEditor({ kind: "preference", value: row })}
          >
            Modifier
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Trash2}
            onClick={() =>
              setDeleteTarget({
                kind: "notifications/preferences",
                id: row.id,
                label: row.destination,
              })
            }
          >
            Supprimer
          </Button>
        </div>
      ),
    },
  ];
  const deliveryColumns: Column<NotificationDelivery>[] = [
    {
      key: "status",
      header: "État",
      cell: (row) => (
        <Badge
          tone={
            row.status === "SENT"
              ? "success"
              : row.status === "FAILED"
                ? "critical"
                : row.status === "RETRY"
                  ? "warning"
                  : "info"
          }
        >
          {row.status}
        </Badge>
      ),
    },
    {
      key: "preference",
      header: "Préférence",
      cell: (row) => `#${row.preference}`,
    },
    { key: "attempts", header: "Tentatives", cell: (row) => row.attempts },
    {
      key: "sent",
      header: "Envoyée",
      cell: (row) => formatTimestamp(row.sent_at),
    },
    {
      key: "retry",
      header: "Prochain essai",
      cell: (row) => formatTimestamp(row.next_attempt_at),
    },
    {
      key: "error",
      header: "Dernière erreur",
      cell: (row) => row.last_error || "—",
    },
  ];
  const environmentColumns: Column<Environment>[] = [
    {
      key: "name",
      header: "Environnement",
      cell: (row) => <strong>{row.name}</strong>,
    },
    {
      key: "kind",
      header: "Type",
      cell: (row) => <SourceBadge source={row.kind} />,
    },
    {
      key: "machines",
      header: "Machines chargées",
      cell: (row) =>
        (machines.data?.results || []).filter(
          (machine) => machine.environment === row.id,
        ).length,
    },
    {
      key: "created",
      header: "Créé",
      cell: (row) => formatTimestamp(row.created_at),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="row-actions">
          <Button
            size="sm"
            variant="ghost"
            icon={Pencil}
            onClick={() => setEditor({ kind: "environment", value: row })}
          >
            Modifier
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Trash2}
            onClick={() =>
              setDeleteTarget({
                kind: "environments",
                id: row.id,
                label: row.name,
              })
            }
          >
            Supprimer
          </Button>
        </div>
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
      key: "kind",
      header: "Source",
      cell: (row) => <SourceBadge source={row.kind} />,
    },
    {
      key: "state",
      header: "État",
      cell: (row) => (
        <Badge
          tone={
            !row.enabled ? "neutral" : row.last_error ? "critical" : "success"
          }
        >
          {!row.enabled ? "Désactivé" : row.last_error ? "Erreur" : "Actif"}
        </Badge>
      ),
    },
    {
      key: "tls",
      header: "TLS",
      cell: (row) => (
        <Badge tone={row.verify_tls ? "success" : "warning"}>
          {row.verify_tls ? "Vérifié" : "Non vérifié"}
        </Badge>
      ),
    },
    {
      key: "sync",
      header: "Dernière collecte",
      cell: (row) => formatRelativeTime(row.last_sync_at),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) => (
        <div className="row-actions">
          <Button
            size="sm"
            variant="ghost"
            icon={Pencil}
            onClick={() => setEditor({ kind: "connector", value: row })}
          >
            Modifier
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Trash2}
            onClick={() =>
              setDeleteTarget({
                kind: "connectors",
                id: row.id,
                label: row.name,
              })
            }
          >
            Supprimer
          </Button>
        </div>
      ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Configuration"
        description="Règles, notifications et sources supervisées. Les secrets restent exclusivement côté serveur."
      />
      <Tabs
        items={[
          { id: "rules", label: "Règles", count: rules.data?.count },
          {
            id: "notifications",
            label: "Notifications",
            count: preferences.data?.count,
          },
          {
            id: "environments",
            label: "Environnements",
            count: environments.data?.count,
          },
          {
            id: "integrations",
            label: "VMware / Hyper-V",
            count: connectors.data?.count,
          },
        ]}
        active={tab}
        onChange={(value) => setSearchParams({ tab: value })}
      />
      <TabPanel active={tab} id="rules">
        <Card className="table-card">
          <CardHeader
            title="Moteur de règles"
            description="Seuils persistants avec durée, portée et cooldown."
            action={
              <Button icon={Plus} onClick={() => setEditor({ kind: "rule" })}>
                Créer une règle
              </Button>
            }
          />
          <DataTable
            columns={ruleColumns}
            rows={rules.data?.results || []}
            rowKey={(row) => row.id}
            loading={rules.isLoading}
            error={rules.error}
            retry={() => rules.refetch()}
            emptyTitle="Aucune règle"
          />
        </Card>
      </TabPanel>
      <TabPanel active={tab} id="notifications">
        <div className="stack stack--lg">
          <div className="inline-notice">
            <Mail />
            Email est le seul adaptateur d’envoi fonctionnel. Teams, Slack et
            Telegram sont prévus par le modèle mais ne sont pas encore
            implémentés.
          </div>
          <Card className="table-card">
            <CardHeader
              title="Préférences"
              description="Sévérité minimale, cooldown et destination validée dans l’interface."
              action={
                <Button
                  icon={Plus}
                  onClick={() => setEditor({ kind: "preference" })}
                >
                  Ajouter une préférence
                </Button>
              }
            />
            <DataTable
              columns={preferenceColumns}
              rows={preferences.data?.results || []}
              rowKey={(row) => row.id}
              loading={preferences.isLoading}
              error={preferences.error}
              retry={() => preferences.refetch()}
              emptyTitle="Aucune préférence"
            />
          </Card>
          <Card className="table-card">
            <CardHeader
              title="Journal de livraison"
              description="Tentatives, retry et erreurs publiques, en lecture seule."
            />
            <DataTable
              columns={deliveryColumns}
              rows={deliveries.data?.results || []}
              rowKey={(row) => row.id}
              loading={deliveries.isLoading}
              error={deliveries.error}
              retry={() => deliveries.refetch()}
              emptyTitle="Aucune livraison"
            />
          </Card>
        </div>
      </TabPanel>
      <TabPanel active={tab} id="environments">
        <Card className="table-card">
          <CardHeader
            title="Environnements"
            description="Portées logiques associant machines, agents et connecteurs."
            action={
              <Button
                icon={Plus}
                onClick={() => setEditor({ kind: "environment" })}
              >
                Créer un environnement
              </Button>
            }
          />
          <DataTable
            columns={environmentColumns}
            rows={environments.data?.results || []}
            rowKey={(row) => row.id}
            loading={environments.isLoading}
            error={environments.error}
            retry={() => environments.refetch()}
            emptyTitle="Aucun environnement"
          />
        </Card>
      </TabPanel>
      <TabPanel active={tab} id="integrations">
        <div className="stack stack--lg">
          <div className="inline-notice inline-notice--warning">
            <CloudCog />
            La valeur du mot de passe n’est jamais enregistrée ici.{" "}
            <code>secret_ref</code>
            doit désigner une variable d’environnement serveur autorisée par le
            tenant.
          </div>
          <Card className="table-card">
            <CardHeader
              title="Connecteurs d’infrastructure"
              description="vCenter HTTPS ou hôte Hyper-V autorisé, timeout et TLS explicites."
              action={
                <Button
                  icon={Plus}
                  onClick={() => setEditor({ kind: "connector" })}
                >
                  Créer un connecteur
                </Button>
              }
            />
            <DataTable
              columns={connectorColumns}
              rows={connectors.data?.results || []}
              rowKey={(row) => row.id}
              loading={connectors.isLoading}
              error={connectors.error}
              retry={() => connectors.refetch()}
              emptyTitle="Aucun connecteur"
            />
          </Card>
        </div>
      </TabPanel>
      <SettingsEditor
        editor={editor}
        close={() => setEditor(null)}
        save={(payload) => save.mutate(payload)}
        loading={save.isPending}
        environments={environments.data?.results || []}
        machines={machines.data?.results || []}
        currentUserId={user!.id}
      />
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Supprimer cette configuration ?"
        description={
          deleteTarget
            ? `${deleteTarget.label} sera supprimé selon les contraintes du backend.`
            : undefined
        }
        size="sm"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              Annuler
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Supprimer
            </Button>
          </div>
        }
      >
        <p>
          Cette action ne sera pas exécutée automatiquement sans confirmation.
        </p>
      </Modal>
    </div>
  );
}
