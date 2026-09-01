import { useQuery } from "@tanstack/react-query";
import {
  CalendarDays,
  ClipboardList,
  Filter,
  Search,
  ShieldCheck,
  UserRound,
} from "lucide-react";
import { useState, type FormEvent } from "react";
import { getPage } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Drawer,
  Field,
  Input,
  KeyValue,
  PageHeader,
  Pagination,
  Select,
  StatCard,
  type Column,
} from "../../components/common";
import type { AuditLog } from "../../types/api";
import { formatRelativeTime, formatTimestamp } from "../../utils/format";

const actionLabel = (action: string) =>
  action
    .replaceAll("_", " ")
    .toLowerCase()
    .replace(/^./, (letter) => letter.toUpperCase());
const actionTone = (action: string) =>
  /REVOKED|DELETED|FAILED/.test(action)
    ? "critical"
    : /CREATED|ENROLLED|LOGIN|TRAINED/.test(action)
      ? "success"
      : /UPDATED|CONFIG|ACKNOWLEDGED/.test(action)
        ? "warning"
        : "info";

export function auditDateBoundary(value: string, endOfDay = false) {
  if (!value) return "";
  const date = new Date(
    `${value}T${endOfDay ? "23:59:59.999" : "00:00:00.000"}`,
  );
  return Number.isNaN(date.getTime()) ? "" : date.toISOString();
}

export default function AuditPage() {
  const [page, setPage] = useState(1);
  const [draft, setDraft] = useState({
    search: "",
    action: "",
    from: "",
    to: "",
    ordering: "-timestamp",
  });
  const [filters, setFilters] = useState(draft);
  const [selected, setSelected] = useState<AuditLog | null>(null);
  const audit = useQuery({
    queryKey: queryKeys.audit({ page, ...filters }),
    queryFn: () => {
      const { from, to, ...otherFilters } = filters;
      return getPage<AuditLog>("/audit/", {
        page,
        page_size: 50,
        ...Object.fromEntries(
          Object.entries({
            ...otherFilters,
            from: auditDateBoundary(from),
            to: auditDateBoundary(to, true),
          }).filter(([, value]) => value),
        ),
      });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setPage(1);
    setFilters(draft);
  };
  const rows = audit.data?.results || [];
  const actors = new Set(rows.map((row) => row.actor_email).filter(Boolean))
    .size;
  const security = rows.filter((row) =>
    /LOGIN|LOGOUT|REVOKED|ENROLLED/.test(row.action),
  ).length;
  const changes = rows.filter((row) =>
    /CREATED|UPDATED|CONFIG|RESOLVED|ACKNOWLEDGED/.test(row.action),
  ).length;
  const columns: Column<AuditLog>[] = [
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
    {
      key: "action",
      header: "Action",
      sortValue: (row) => row.action,
      cell: (row) => (
        <Badge tone={actionTone(row.action)}>{actionLabel(row.action)}</Badge>
      ),
    },
    {
      key: "actor",
      header: "Acteur",
      sortValue: (row) => row.actor_email || "",
      cell: (row) => (
        <div>
          <strong>{row.actor_email || "Système"}</strong>
          <small>{row.ip_address || "IP non enregistrée"}</small>
        </div>
      ),
    },
    {
      key: "target",
      header: "Cible",
      sortValue: (row) => row.target_repr,
      cell: (row) => (
        <div>
          <strong>{row.target_repr || row.target_id || "—"}</strong>
          <small>{row.target_type}</small>
        </div>
      ),
    },
    {
      key: "customer",
      header: "Client",
      cell: (row) =>
        row.customer_name || (
          <span className="technical-id">{row.customer || "Plateforme"}</span>
        ),
    },
  ];
  return (
    <div>
      <PageHeader
        title="Journal d’audit"
        description="Traçabilité immuable des actions sensibles. Ces événements sont en lecture seule à tous les niveaux exposés."
        actions={
          <Badge tone="success">
            <ShieldCheck /> Immuable
          </Badge>
        }
      />
      <div className="stats-grid">
        <StatCard
          label="Événements"
          value={audit.data?.count ?? "—"}
          icon={<ClipboardList />}
        />
        <StatCard
          label="Acteurs sur cette page"
          value={actors}
          icon={<UserRound />}
        />
        <StatCard
          label="Événements sécurité"
          value={security}
          icon={<ShieldCheck />}
          tone="blue"
        />
        <StatCard
          label="Changements sur cette page"
          value={changes}
          icon={<Filter />}
          tone="warning"
        />
      </div>
      <Card className="audit-filters">
        <form onSubmit={submit}>
          <Field label="Recherche">
            <div className="search-control">
              <Search />
              <Input
                value={draft.search}
                onChange={(event) =>
                  setDraft((current) => ({
                    ...current,
                    search: event.target.value,
                  }))
                }
                placeholder="Acteur, cible, action, IP…"
              />
            </div>
          </Field>
          <Field label="Action">
            <Input
              value={draft.action}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  action: event.target.value.toUpperCase(),
                }))
              }
              placeholder="USER_LOGIN"
            />
          </Field>
          <Field label="Depuis">
            <Input
              type="date"
              value={draft.from}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  from: event.target.value,
                }))
              }
            />
          </Field>
          <Field label="Jusqu’à">
            <Input
              type="date"
              value={draft.to}
              onChange={(event) =>
                setDraft((current) => ({ ...current, to: event.target.value }))
              }
            />
          </Field>
          <Field label="Ordre">
            <Select
              value={draft.ordering}
              onChange={(event) =>
                setDraft((current) => ({
                  ...current,
                  ordering: event.target.value,
                }))
              }
            >
              <option value="-timestamp">Plus récents</option>
              <option value="timestamp">Plus anciens</option>
              <option value="action">Action A–Z</option>
              <option value="-action">Action Z–A</option>
            </Select>
          </Field>
          <Button type="submit" icon={Filter}>
            Appliquer
          </Button>
        </form>
      </Card>
      <Card className="table-card">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={audit.isLoading}
          error={audit.error}
          retry={() => audit.refetch()}
          onRowClick={setSelected}
          emptyTitle="Aucun événement"
          emptyDescription="Aucun événement d’audit ne correspond aux critères serveur."
        />
        <Pagination
          page={page}
          count={audit.data?.count || 0}
          pageSize={50}
          onPage={setPage}
        />
      </Card>
      <Drawer
        open={Boolean(selected)}
        onClose={() => setSelected(null)}
        title={selected ? actionLabel(selected.action) : "Événement"}
        description={selected ? formatTimestamp(selected.timestamp) : undefined}
      >
        {selected && (
          <div className="stack stack--lg">
            <div className="cluster">
              <Badge tone={actionTone(selected.action)}>
                {selected.action}
              </Badge>
              <Badge tone="neutral">Lecture seule</Badge>
            </div>
            <div className="details-grid drawer-details">
              <KeyValue
                label="Acteur"
                value={selected.actor_email || "Système"}
              />
              <KeyValue
                label="Adresse IP"
                value={selected.ip_address || "Non enregistrée"}
              />
              <KeyValue
                label="Client"
                value={
                  selected.customer_name || selected.customer || "Plateforme"
                }
              />
              <KeyValue
                label="Timestamp"
                value={formatTimestamp(selected.timestamp)}
              />
              <KeyValue label="Type cible" value={selected.target_type} />
              <KeyValue label="ID cible" value={selected.target_id || "—"} />
              <KeyValue
                label="Représentation"
                value={selected.target_repr || "—"}
              />
              <KeyValue label="Identifiant audit" value={selected.id} />
            </div>
            <Card className="drawer-section">
              <h3>Métadonnées expurgées</h3>
              <pre className="json-block">
                {JSON.stringify(selected.metadata, null, 2)}
              </pre>
            </Card>
            <div className="inline-notice">
              <CalendarDays />
              Les secrets, mots de passe, tokens, cookies et credentials sont
              expurgés côté serveur avant persistance.
            </div>
          </div>
        )}
      </Drawer>
    </div>
  );
}
