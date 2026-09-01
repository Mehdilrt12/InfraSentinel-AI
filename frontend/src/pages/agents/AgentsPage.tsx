import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Bot,
  Check,
  Clipboard,
  Download,
  KeyRound,
  Power,
  RefreshCw,
  Search,
  ShieldCheck,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import {
  API_BASE_URL,
  apiProblem,
  resolvePublicServerUrl,
} from "../../api/client";
import { getPage, patchOne, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Field,
  Input,
  KeyValue,
  Modal,
  PageHeader,
  Pagination,
  Select,
  SourceBadge,
  StatCard,
  StatusBadge,
  useToast,
  type Column,
} from "../../components/common";
import type { Agent, Environment, Machine } from "../../types/api";
import {
  formatRelativeTime,
  formatTimestamp,
  sourceLabel,
} from "../../utils/format";

interface EnrollmentResult {
  enrollment_code: string;
  expires_in_minutes: number;
}

export default function AgentsPage() {
  const { user } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("ALL");
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [environmentId, setEnvironmentId] = useState("");
  const [ttl, setTtl] = useState(30);
  const [enrollment, setEnrollment] = useState<EnrollmentResult | null>(null);
  const [copied, setCopied] = useState(false);
  const publicServerUrl = resolvePublicServerUrl(
    API_BASE_URL,
    window.location.origin,
  );
  const agents = useQuery({
    queryKey: queryKeys.agents(page),
    queryFn: () => getPage<Agent>("/agents/", { page }),
  });
  const machines = useQuery({
    queryKey: ["machines", "agent-lookup"],
    queryFn: () => getPage<Machine>("/machines/"),
  });
  const environments = useQuery({
    queryKey: queryKeys.environments,
    queryFn: () => getPage<Environment>("/environments/"),
    enabled: canManage(user),
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
      (agents.data?.results || []).filter((agent) => {
        const machine = machineMap.get(agent.machine);
        const status = !agent.enabled
          ? "REVOKED"
          : machine?.status || "UNKNOWN";
        return (
          (filter === "ALL" || filter === status) &&
          (!search ||
            `${agent.hostname} ${agent.version} ${machine?.ip_address || ""}`
              .toLowerCase()
              .includes(search.toLowerCase()))
        );
      }),
    [agents.data, filter, machineMap, search],
  );
  const stats = {
    enabled: (agents.data?.results || []).filter((item) => item.enabled).length,
    revoked: (agents.data?.results || []).filter((item) => !item.enabled)
      .length,
    online: (agents.data?.results || []).filter(
      (item) =>
        item.enabled && machineMap.get(item.machine)?.status === "ONLINE",
    ).length,
  };
  const toggle = useMutation({
    mutationFn: (agent: Agent) =>
      patchOne<Agent, { enabled: boolean }>(`/agents/${agent.id}/`, {
        enabled: !agent.enabled,
      }),
    onSuccess: (updated) => {
      void queryClient.invalidateQueries({ queryKey: ["agents"] });
      notify({
        tone: updated.enabled ? "success" : "warning",
        title: updated.enabled ? "Agent réactivé" : "Agent révoqué",
        detail: updated.enabled
          ? "Le token existant redevient accepté."
          : "Le token de cet agent est désormais refusé.",
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Action impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const generate = useMutation({
    mutationFn: () =>
      postOne<EnrollmentResult, { ttl_minutes: number }>(
        `/environments/${environmentId}/enrollment_code/`,
        { ttl_minutes: ttl },
      ),
    onSuccess: (data) => {
      setEnrollment(data);
      setCopied(false);
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Code non généré",
        detail: apiProblem(error).detail,
      }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    generate.mutate();
  };
  const closeEnrollment = () => {
    setEnrollOpen(false);
    setEnrollment(null);
    setCopied(false);
  };
  const copy = async () => {
    if (!enrollment) return;
    await navigator.clipboard.writeText(enrollment.enrollment_code);
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1800);
  };
  const installer = import.meta.env.VITE_AGENT_INSTALLER_URL;
  const columns: Column<Agent>[] = [
    {
      key: "agent",
      header: "Agent",
      sortValue: (row) => row.hostname,
      cell: (row) => (
        <div className="entity-cell">
          <span className="machine-icon">
            <Bot />
          </span>
          <div>
            <strong>{row.hostname}</strong>
            <small className="technical-id">{row.id}</small>
          </div>
        </div>
      ),
    },
    {
      key: "state",
      header: "État machine",
      sortValue: (row) => machineMap.get(row.machine)?.status || "UNKNOWN",
      cell: (row) =>
        row.enabled ? (
          <StatusBadge
            status={machineMap.get(row.machine)?.status || "UNKNOWN"}
          />
        ) : (
          <Badge tone="critical" dot>
            Révoqué
          </Badge>
        ),
    },
    {
      key: "source",
      header: "Source",
      cell: (row) => (
        <SourceBadge
          source={machineMap.get(row.machine)?.source_type || "WINDOWS"}
        />
      ),
    },
    {
      key: "version",
      header: "Version",
      sortValue: (row) => row.version,
      cell: (row) => (row.version ? `v${row.version}` : "—"),
    },
    {
      key: "heartbeat",
      header: "Heartbeat",
      sortValue: (row) => Date.parse(row.last_heartbeat || "0"),
      cell: (row) => (
        <time title={formatTimestamp(row.last_heartbeat)}>
          {formatRelativeTime(row.last_heartbeat)}
        </time>
      ),
    },
    {
      key: "ip",
      header: "Adresse IP",
      cell: (row) =>
        machineMap.get(row.machine)?.ip_address || (
          <span className="muted">Non remontée</span>
        ),
    },
    {
      key: "actions",
      header: "Action",
      cell: (row) =>
        canManage(user) ? (
          <Button
            size="sm"
            variant={row.enabled ? "ghost" : "secondary"}
            icon={Power}
            loading={toggle.isPending}
            onClick={(event) => {
              event.stopPropagation();
              toggle.mutate(row);
            }}
          >
            {row.enabled ? "Révoquer" : "Réactiver"}
          </Button>
        ) : (
          <span className="muted">Lecture seule</span>
        ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Agents Windows"
        description="Identités d’agents enrôlées, heartbeat, version et état de révocation. Les secrets ne sont jamais affichés."
        actions={
          <>
            {installer && (
              <a
                className="button button--secondary button--md"
                href={installer}
                rel="noreferrer"
              >
                <Download />
                Télécharger l’agent
              </a>
            )}
            {canManage(user) && (
              <Button icon={KeyRound} onClick={() => setEnrollOpen(true)}>
                Enrôler un agent
              </Button>
            )}
          </>
        }
      />
      <div className="stats-grid">
        <StatCard
          label="Agents enregistrés"
          value={agents.data?.count ?? "—"}
          icon={<Bot />}
        />
        <StatCard
          label="Actifs sur cette page"
          value={stats.enabled}
          icon={<ShieldCheck />}
        />
        <StatCard
          label="Machines en ligne"
          value={stats.online}
          icon={<RefreshCw />}
        />
        <StatCard
          label="Révoqués sur cette page"
          value={stats.revoked}
          icon={<Power />}
          tone="critical"
        />
      </div>
      <Card className="table-card resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Parc d’agents</h2>
            <p>
              État machine joint depuis l’inventaire chargé. Les filtres sont
              locaux à la page courante.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search />
              <Input
                aria-label="Rechercher un agent"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Hostname, IP ou version…"
              />
            </label>
            <Select
              aria-label="Filtrer l’état"
              value={filter}
              onChange={(event) => setFilter(event.target.value)}
            >
              <option value="ALL">Tous</option>
              <option value="ONLINE">En ligne</option>
              <option value="OFFLINE">Hors ligne</option>
              <option value="UNKNOWN">Inconnu</option>
              <option value="REVOKED">Révoqué</option>
            </Select>
            <Badge tone="neutral">Filtre local</Badge>
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={agents.isLoading}
          error={agents.error}
          retry={() => agents.refetch()}
          emptyTitle="Aucun agent"
          emptyDescription="Aucun agent Windows réel n’est enregistré dans ce tenant."
        />
        <Pagination
          page={page}
          count={agents.data?.count || 0}
          onPage={setPage}
        />
      </Card>
      <Card className="onboarding-card">
        <div>
          <span className="eyebrow">Parcours professionnel</span>
          <h2>De l’installation au statut ONLINE</h2>
          <p>
            Le code d’enrôlement est à usage unique. Le token permanent est reçu
            par l’agent puis protégé par Windows DPAPI.
          </p>
        </div>
        <ol className="onboarding-steps">
          {[
            "Générer un code temporaire",
            "Télécharger le setup signé",
            "Configurer l’URL HTTPS",
            "Installer le service Windows",
            "Attendre le heartbeat",
            "Confirmer le statut ONLINE",
          ].map((step, index) => (
            <li key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </li>
          ))}
        </ol>
      </Card>
      <Modal
        open={enrollOpen}
        onClose={closeEnrollment}
        title={
          enrollment ? "Code d’enrôlement généré" : "Préparer un enrôlement"
        }
        description={
          enrollment
            ? "Ce secret n’est affiché qu’ici. Copiez-le dans un canal protégé, puis fermez cette fenêtre."
            : "Le code sera limité au tenant, à un environnement Windows/Mixte et à la durée choisie."
        }
        size="md"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={closeEnrollment}>
              {enrollment ? "Fermer et effacer" : "Annuler"}
            </Button>
            {!enrollment && (
              <Button
                form="enrollment-form"
                type="submit"
                loading={generate.isPending}
              >
                Générer une fois
              </Button>
            )}
          </div>
        }
      >
        {enrollment ? (
          <div className="enrollment-result">
            <div className="inline-notice inline-notice--warning">
              <KeyRound />
              Ne placez jamais ce code dans une ligne de commande, un log ou un
              ticket non protégé.
            </div>
            <div className="secret-box">
              <code>{enrollment.enrollment_code}</code>
              <Button
                variant="secondary"
                icon={copied ? Check : Clipboard}
                onClick={copy}
              >
                {copied ? "Copié" : "Copier"}
              </Button>
            </div>
            <div className="details-grid">
              <KeyValue
                label="Expiration"
                value={`${enrollment.expires_in_minutes} minutes`}
              />
              <KeyValue label="URL serveur" value={publicServerUrl} />
            </div>
            <pre className="json-block">
              {JSON.stringify(
                {
                  backend_url: publicServerUrl,
                  machine_name: "NOM-DU-PC",
                  interval_seconds: 30,
                  heartbeat_seconds: 60,
                  verify_tls: window.location.protocol === "https:",
                },
                null,
                2,
              )}
            </pre>
            <small>
              Le code temporaire est saisi séparément dans l’installateur et ne
              doit pas être ajouté à `config.json`.
            </small>
          </div>
        ) : (
          <form id="enrollment-form" className="form-grid" onSubmit={submit}>
            <Field label="Environnement Windows" required>
              <Select
                value={environmentId}
                onChange={(event) => setEnvironmentId(event.target.value)}
                required
              >
                <option value="">Sélectionner…</option>
                {environments.data?.results
                  .filter((item) => ["WINDOWS", "MIXED"].includes(item.kind))
                  .map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.name} · {sourceLabel(item.kind)}
                    </option>
                  ))}
              </Select>
            </Field>
            <Field
              label="Durée de validité"
              hint="Entre 1 et 1 440 minutes."
              required
            >
              <Input
                type="number"
                value={ttl}
                min={1}
                max={1440}
                onChange={(event) => setTtl(Number(event.target.value))}
                required
              />
            </Field>
          </form>
        )}
      </Modal>
    </div>
  );
}
