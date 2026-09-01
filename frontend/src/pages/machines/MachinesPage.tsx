import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MonitorCog, Plus, Search, Server, Wifi, WifiOff } from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiProblem } from "../../api/client";
import { getPage, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { canManage } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  Column,
  DataTable,
  Field,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  SourceBadge,
  StatCard,
  StatusBadge,
  useToast,
} from "../../components/common";
import type {
  Agent,
  Environment,
  Machine,
  Metric,
  SourceType,
} from "../../types/api";
import {
  formatMetric,
  formatRelativeTime,
  formatTimestamp,
  sourceLabel,
} from "../../utils/format";
import { latestMetrics } from "../../utils/metrics";

interface MachineForm {
  environment: string;
  source_type: SourceType;
  external_id: string;
  hostname: string;
  ip_address: string;
  status: "UNKNOWN" | "ONLINE" | "OFFLINE";
}
const initialForm: MachineForm = {
  environment: "",
  source_type: "WINDOWS",
  external_id: "",
  hostname: "",
  ip_address: "",
  status: "UNKNOWN",
};

export default function MachinesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("ALL");
  const [source, setSource] = useState("ALL");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState<MachineForm>(initialForm);
  const machines = useQuery({
    queryKey: queryKeys.machines(page),
    queryFn: () => getPage<Machine>("/machines/", { page }),
  });
  const environments = useQuery({
    queryKey: queryKeys.environments,
    queryFn: () => getPage<Environment>("/environments/"),
  });
  const metrics = useQuery({
    queryKey: ["metrics", "inventory"],
    queryFn: () => getPage<Metric>("/metrics/", { page: 1 }),
  });
  const agents = useQuery({
    queryKey: ["agents", "inventory"],
    queryFn: () => getPage<Agent>("/agents/", { page: 1 }),
  });
  const latest = useMemo(
    () => latestMetrics(metrics.data?.results || []),
    [metrics.data],
  );
  const agentByMachine = useMemo(
    () =>
      new Map(
        (agents.data?.results || []).map((agent) => [agent.machine, agent]),
      ),
    [agents.data],
  );
  const environmentById = useMemo(
    () =>
      new Map(
        (environments.data?.results || []).map((environment) => [
          environment.id,
          environment,
        ]),
      ),
    [environments.data],
  );
  const latestMetric = (machine: string, name: string) =>
    latest.find(
      (metric) => metric.machine === machine && metric.metric_name === name,
    );
  const rows = useMemo(
    () =>
      (machines.data?.results || []).filter((machine) => {
        const matchesSearch =
          !search ||
          `${machine.hostname} ${machine.ip_address || ""} ${machine.external_id}`
            .toLowerCase()
            .includes(search.toLowerCase());
        return (
          matchesSearch &&
          (status === "ALL" || machine.status === status) &&
          (source === "ALL" || machine.source_type === source)
        );
      }),
    [machines.data, search, source, status],
  );
  const counts = useMemo(
    () => ({
      online: rows.filter((item) => item.status === "ONLINE").length,
      offline: rows.filter((item) => item.status === "OFFLINE").length,
      unknown: rows.filter((item) => item.status === "UNKNOWN").length,
    }),
    [rows],
  );
  const create = useMutation({
    mutationFn: () =>
      postOne<Machine, Record<string, unknown>>("/machines/", {
        ...form,
        ip_address: form.ip_address || null,
        os_information: {},
        metadata: {},
        agent_version: "",
      }),
    onSuccess: (machine) => {
      void queryClient.invalidateQueries({ queryKey: ["machines"] });
      void queryClient.invalidateQueries({ queryKey: queryKeys.dashboard });
      setOpen(false);
      setForm(initialForm);
      notify({
        tone: "success",
        title: "Machine créée",
        detail: `${machine.hostname} est maintenant enregistrée.`,
      });
      navigate(`/machines/${machine.id}`);
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Création impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };

  const columns: Column<Machine>[] = [
    {
      key: "hostname",
      header: "Machine",
      sortValue: (row) => row.hostname,
      cell: (row) => (
        <div className="entity-cell">
          <span
            className={`machine-icon machine-icon--${row.status.toLowerCase()}`}
          >
            <Server />
          </span>
          <div>
            <strong>{row.hostname}</strong>
            <small className="technical-id">{row.external_id}</small>
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "État",
      sortValue: (row) => row.status,
      cell: (row) => <StatusBadge status={row.status} />,
    },
    {
      key: "source",
      header: "Environnement",
      sortValue: (row) => row.source_type,
      cell: (row) => (
        <div>
          <SourceBadge source={row.source_type} />
          <small>
            {environmentById.get(row.environment)?.name ||
              String(row.environment).slice(0, 8)}
          </small>
        </div>
      ),
    },
    {
      key: "os",
      header: "OS",
      cell: (row) => {
        const os = row.os_information || {};
        const label = [os.product_name, os.system, os.release]
          .filter((value) => typeof value === "string" && value)
          .join(" ");
        return label || <span className="muted">Non remonté</span>;
      },
    },
    {
      key: "ip",
      header: "Adresse IP",
      cell: (row) =>
        row.ip_address || <span className="muted">Non remontée</span>,
    },
    {
      key: "cpu",
      header: "CPU",
      cell: (row) => {
        const metric = latestMetric(row.id, "system.cpu.utilization");
        return metric ? (
          <strong>{formatMetric(metric).text}</strong>
        ) : (
          <span className="muted">—</span>
        );
      },
    },
    {
      key: "ram",
      header: "RAM",
      cell: (row) => {
        const metric = latestMetric(row.id, "system.memory.utilization");
        return metric ? (
          <strong>{formatMetric(metric).text}</strong>
        ) : (
          <span className="muted">—</span>
        );
      },
    },
    {
      key: "disk",
      header: "Disque",
      cell: (row) => {
        const metric = latestMetric(row.id, "system.disk.utilization");
        return metric ? (
          <strong>{formatMetric(metric).text}</strong>
        ) : (
          <span className="muted">—</span>
        );
      },
    },
    {
      key: "agent",
      header: "Agent",
      cell: (row) => {
        const agent = agentByMachine.get(row.id);
        return agent ? (
          <div>
            <Badge tone={agent.enabled ? "success" : "neutral"} dot>
              {agent.enabled ? "Actif" : "Révoqué"}
            </Badge>
            <small>
              {agent.version ? `v${agent.version}` : "Version inconnue"}
            </small>
          </div>
        ) : (
          <span className="muted">Non associé</span>
        );
      },
    },
    {
      key: "seen",
      header: "Dernière activité",
      sortValue: (row) => Date.parse(row.last_seen || "0"),
      cell: (row) => (
        <time title={formatTimestamp(row.last_seen)}>
          {formatRelativeTime(row.last_seen)}
        </time>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Machines"
        description="Inventaire centralisé des machines physiques et virtuelles réellement enregistrées."
        actions={
          canManage(user) && (
            <Button icon={Plus} onClick={() => setOpen(true)}>
              Ajouter une machine
            </Button>
          )
        }
      />
      <div className="stats-grid machine-summary">
        <StatCard
          label="Total enregistré"
          value={machines.data?.count ?? "—"}
          icon={<MonitorCog />}
        />
        <StatCard
          label="En ligne sur cette page"
          value={counts.online}
          icon={<Wifi />}
        />
        <StatCard
          label="État inconnu sur cette page"
          value={counts.unknown}
          icon={<Server />}
          tone="warning"
        />
        <StatCard
          label="Hors ligne sur cette page"
          value={counts.offline}
          icon={<WifiOff />}
          tone="critical"
        />
      </div>
      <Card className="table-card resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Inventaire</h2>
            <p>
              Recherche et filtres appliqués aux{" "}
              {machines.data?.results.length || 0} lignes chargées de cette
              page.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search aria-hidden />
              <Input
                aria-label="Rechercher une machine"
                placeholder="Hostname, IP ou identifiant…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <Select
              aria-label="Filtrer par état"
              value={status}
              onChange={(event) => setStatus(event.target.value)}
            >
              <option value="ALL">Tous les états</option>
              <option value="ONLINE">En ligne</option>
              <option value="OFFLINE">Hors ligne</option>
              <option value="UNKNOWN">Inconnu</option>
            </Select>
            <Select
              aria-label="Filtrer par source"
              value={source}
              onChange={(event) => setSource(event.target.value)}
            >
              <option value="ALL">Toutes les sources</option>
              {(["WINDOWS", "VMWARE", "HYPERV"] as SourceType[]).map((item) => (
                <option value={item} key={item}>
                  {sourceLabel(item)}
                </option>
              ))}
            </Select>
            <Badge tone="neutral">Filtres locaux</Badge>
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={machines.isLoading}
          error={machines.error}
          retry={() => machines.refetch()}
          onRowClick={(row) => navigate(`/machines/${row.id}`)}
          emptyTitle="Aucune machine"
          emptyDescription="Aucune machine réelle ne correspond aux filtres de cette page."
          caption="Machines supervisées"
        />
        <Pagination
          page={page}
          count={machines.data?.count || 0}
          onPage={setPage}
        />
      </Card>
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Ajouter une machine"
        description="Création manuelle via le contrat backend existant. Un agent Windows doit ensuite être enrôlé séparément."
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setOpen(false)}>
              Annuler
            </Button>
            <Button
              type="submit"
              form="machine-create-form"
              loading={create.isPending}
            >
              Créer
            </Button>
          </div>
        }
      >
        <form id="machine-create-form" className="form-grid" onSubmit={submit}>
          <Field label="Environnement" required>
            <Select
              value={form.environment}
              onChange={(event) => {
                const environment = environments.data?.results.find(
                  (item) => item.id === event.target.value,
                );
                setForm((current) => ({
                  ...current,
                  environment: event.target.value,
                  source_type: environment?.kind || current.source_type,
                }));
              }}
              required
            >
              <option value="">Sélectionner…</option>
              {environments.data?.results.map((environment) => (
                <option key={environment.id} value={environment.id}>
                  {environment.name} · {sourceLabel(environment.kind)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Type de source" required>
            <Select
              value={form.source_type}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  source_type: event.target.value as SourceType,
                }))
              }
            >
              {(["WINDOWS", "VMWARE", "HYPERV"] as SourceType[]).map((item) => (
                <option value={item} key={item}>
                  {sourceLabel(item)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Hostname" required>
            <Input
              value={form.hostname}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  hostname: event.target.value,
                }))
              }
              maxLength={255}
              required
            />
          </Field>
          <Field
            label="Identifiant externe"
            hint="Identifiant stable et unique dans la source."
            required
          >
            <Input
              value={form.external_id}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  external_id: event.target.value,
                }))
              }
              maxLength={255}
              required
            />
          </Field>
          <Field label="Adresse IP">
            <Input
              value={form.ip_address}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  ip_address: event.target.value,
                }))
              }
              placeholder="192.168.1.10"
            />
          </Field>
          <Field label="État initial">
            <Select
              value={form.status}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  status: event.target.value as MachineForm["status"],
                }))
              }
            >
              <option value="UNKNOWN">Inconnu</option>
              <option value="ONLINE">En ligne</option>
              <option value="OFFLINE">Hors ligne</option>
            </Select>
          </Field>
        </form>
      </Modal>
    </div>
  );
}
