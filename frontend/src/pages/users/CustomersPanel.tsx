import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { apiProblem } from "../../api/client";
import { deleteOne, getPage, patchOne, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Field,
  Input,
  Modal,
  Pagination,
  useToast,
  type Column,
} from "../../components/common";
import type { Customer, User } from "../../types/api";
import { formatTimestamp } from "../../utils/format";

interface CustomerForm {
  name: string;
  slug: string;
  active: boolean;
}
const blankCustomer: CustomerForm = { name: "", slug: "", active: true };

export function CustomersPanel({ currentUser }: { currentUser: User }) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [editing, setEditing] = useState<Customer | null>(null);
  const [form, setForm] = useState<CustomerForm>(blankCustomer);
  const [formOpen, setFormOpen] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Customer | null>(null);
  const [confirm, setConfirm] = useState("");
  const customers = useQuery({
    queryKey: queryKeys.customers(page),
    queryFn: () => getPage<Customer>("/customers/", { page }),
  });
  const platformAdmin = currentUser.is_superuser;

  const save = useMutation({
    mutationFn: () =>
      editing
        ? patchOne<Customer, CustomerForm>(`/customers/${editing.id}/`, form)
        : postOne<Customer, CustomerForm>("/customers/", form),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["customers"] });
      setFormOpen(false);
      notify({
        tone: "success",
        title: editing ? "Client mis à jour" : "Client créé",
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Enregistrement impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const remove = useMutation({
    mutationFn: () => deleteOne(`/customers/${deleteTarget!.id}/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["customers"] });
      setDeleteTarget(null);
      setConfirm("");
      notify({ tone: "success", title: "Client supprimé" });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Suppression impossible",
        detail: apiProblem(error).detail,
      }),
  });
  const openCreate = () => {
    setEditing(null);
    setForm(blankCustomer);
    setFormOpen(true);
  };
  const openEdit = (customer: Customer) => {
    setEditing(customer);
    setForm({
      name: customer.name,
      slug: customer.slug,
      active: customer.active,
    });
    setFormOpen(true);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const columns: Column<Customer>[] = [
    {
      key: "name",
      header: "Client",
      sortValue: (row) => row.name,
      cell: (row) => (
        <div className="entity-cell">
          <span className="user-avatar">
            <Building2 />
          </span>
          <div>
            <strong>{row.name}</strong>
            <small>{row.slug}</small>
          </div>
        </div>
      ),
    },
    {
      key: "status",
      header: "État",
      sortValue: (row) => Number(row.active),
      cell: (row) => (
        <Badge tone={row.active ? "success" : "neutral"} dot>
          {row.active ? "Actif" : "Désactivé"}
        </Badge>
      ),
    },
    {
      key: "created",
      header: "Créé le",
      sortValue: (row) => row.created_at,
      cell: (row) => (
        <time dateTime={row.created_at}>{formatTimestamp(row.created_at)}</time>
      ),
    },
    {
      key: "id",
      header: "Identifiant tenant",
      cell: (row) => (
        <span className="technical-id" title={row.id}>
          {row.id.slice(0, 13)}
        </span>
      ),
    },
    ...(platformAdmin
      ? [
          {
            key: "actions",
            header: "Actions",
            cell: (row: Customer) => (
              <div className="row-actions">
                <Button
                  size="sm"
                  variant="ghost"
                  icon={Pencil}
                  onClick={() => openEdit(row)}
                >
                  Modifier
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  icon={Trash2}
                  onClick={() => {
                    setDeleteTarget(row);
                    setConfirm("");
                  }}
                >
                  Supprimer
                </Button>
              </div>
            ),
          } satisfies Column<Customer>,
        ]
      : []),
  ];

  return (
    <Card className="table-card resource-card">
      <div className="resource-toolbar">
        <div className="resource-toolbar__title">
          <h2>Clients / tenants</h2>
          <p>
            {platformAdmin
              ? "Vue plateforme et gestion des tenants."
              : "Votre tenant courant, en lecture seule."}
          </p>
        </div>
        {platformAdmin && (
          <Button icon={Plus} variant="secondary" onClick={openCreate}>
            Créer un client
          </Button>
        )}
      </div>
      <DataTable
        columns={columns}
        rows={customers.data?.results || []}
        rowKey={(row) => row.id}
        loading={customers.isLoading}
        error={customers.error}
        retry={() => customers.refetch()}
        emptyTitle="Aucun client"
        caption="Clients de la plateforme"
      />
      <Pagination
        page={page}
        count={customers.data?.count || 0}
        onPage={setPage}
      />
      <Modal
        open={formOpen}
        onClose={() => setFormOpen(false)}
        title={editing ? "Modifier le client" : "Créer un client"}
        description="Réservé à l’administrateur plateforme ; les autorisations restent contrôlées par le backend."
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setFormOpen(false)}>
              Annuler
            </Button>
            <Button type="submit" form="customer-form" loading={save.isPending}>
              {editing ? "Enregistrer" : "Créer"}
            </Button>
          </div>
        }
      >
        <form id="customer-form" className="form-grid" onSubmit={submit}>
          <Field label="Nom" required>
            <Input
              value={form.name}
              maxLength={160}
              onChange={(event) =>
                setForm((value) => ({ ...value, name: event.target.value }))
              }
              required
            />
          </Field>
          <Field
            label="Slug unique"
            hint="Lettres minuscules, chiffres, tirets et underscores."
            required
          >
            <Input
              value={form.slug}
              maxLength={80}
              pattern="[-a-zA-Z0-9_]+"
              onChange={(event) =>
                setForm((value) => ({ ...value, slug: event.target.value }))
              }
              required
            />
          </Field>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.active}
              onChange={(event) =>
                setForm((value) => ({ ...value, active: event.target.checked }))
              }
            />
            <span />
            Tenant actif
          </label>
        </form>
      </Modal>
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Supprimer le client"
        description="Le backend refusera la suppression si des comptes protégés utilisent encore ce tenant."
        size="sm"
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setDeleteTarget(null)}>
              Annuler
            </Button>
            <Button
              variant="danger"
              icon={Trash2}
              disabled={confirm !== deleteTarget?.slug}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Supprimer
            </Button>
          </div>
        }
      >
        <Field label={`Saisissez ${deleteTarget?.slug || ""} pour confirmer`}>
          <Input
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </Field>
      </Modal>
    </Card>
  );
}
