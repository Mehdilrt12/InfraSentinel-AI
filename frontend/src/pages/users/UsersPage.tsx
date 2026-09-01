import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Pencil,
  Plus,
  Search,
  Shield,
  Trash2,
  UserCheck,
  UserRound,
  UserX,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { apiProblem } from "../../api/client";
import { deleteOne, getPage, patchOne, postOne } from "../../api/resources";
import { queryKeys } from "../../app/queryClient";
import { useAuth } from "../../auth/AuthProvider";
import { roleLabel } from "../../auth/permissions";
import {
  Badge,
  Button,
  Card,
  DataTable,
  Field,
  Input,
  Modal,
  PageHeader,
  Pagination,
  Select,
  StatCard,
  useToast,
  type Column,
} from "../../components/common";
import type { Role, User } from "../../types/api";
import { CustomersPanel } from "./CustomersPanel";

interface UserForm {
  email: string;
  username: string;
  first_name: string;
  last_name: string;
  role: Role;
  is_active: boolean;
  password: string;
}
const blankForm: UserForm = {
  email: "",
  username: "",
  first_name: "",
  last_name: "",
  role: "VIEWER",
  is_active: true,
  password: "",
};

export default function UsersPage() {
  const { user: currentUser } = useAuth();
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState("");
  const [role, setRole] = useState("ALL");
  const [state, setState] = useState("ALL");
  const [modalOpen, setModalOpen] = useState(false);
  const [editing, setEditing] = useState<User | null>(null);
  const [form, setForm] = useState<UserForm>(blankForm);
  const [deleteTarget, setDeleteTarget] = useState<User | null>(null);
  const [confirm, setConfirm] = useState("");
  const users = useQuery({
    queryKey: queryKeys.users(page),
    queryFn: () => getPage<User>("/users/", { page }),
  });
  const rows = useMemo(
    () =>
      (users.data?.results || []).filter(
        (user) =>
          (role === "ALL" || user.role === role) &&
          (state === "ALL" || user.is_active === (state === "ACTIVE")) &&
          (!search ||
            `${user.email} ${user.username} ${user.first_name} ${user.last_name}`
              .toLowerCase()
              .includes(search.toLowerCase())),
      ),
    [role, search, state, users.data],
  );
  const local = users.data?.results || [];
  const stats = {
    active: local.filter((item) => item.is_active).length,
    inactive: local.filter((item) => !item.is_active).length,
    admins: local.filter((item) => item.role === "ADMIN").length,
  };
  const save = useMutation({
    mutationFn: () => {
      const body = {
        ...form,
        ...(form.password ? {} : { password: undefined }),
      };
      return editing
        ? patchOne<User, Partial<UserForm>>(`/users/${editing.id}/`, body)
        : postOne<User, UserForm>("/users/", body as UserForm);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      setModalOpen(false);
      notify({
        tone: "success",
        title: editing ? "Utilisateur modifié" : "Utilisateur créé",
      });
    },
    onError: (error) =>
      notify({
        tone: "error",
        title: "Enregistrement impossible",
        detail: `${apiProblem(error).detail}${apiProblem(error).fields ? ` ${Object.values(apiProblem(error).fields!).join(" ")}` : ""}`,
      }),
  });
  const remove = useMutation({
    mutationFn: () => deleteOne(`/users/${deleteTarget!.id}/`),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
      setDeleteTarget(null);
      setConfirm("");
      notify({ tone: "success", title: "Utilisateur supprimé" });
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
    setForm(blankForm);
    setModalOpen(true);
  };
  const openEdit = (user: User) => {
    setEditing(user);
    setForm({
      email: user.email,
      username: user.username,
      first_name: user.first_name,
      last_name: user.last_name,
      role: user.role,
      is_active: user.is_active,
      password: "",
    });
    setModalOpen(true);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  const columns: Column<User>[] = [
    {
      key: "user",
      header: "Utilisateur",
      sortValue: (row) => row.email,
      cell: (row) => (
        <div className="entity-cell">
          <span className="user-avatar">
            {(row.first_name?.[0] || row.email[0]).toUpperCase()}
          </span>
          <div>
            <strong>
              {[row.first_name, row.last_name].filter(Boolean).join(" ") ||
                row.username}
            </strong>
            <small>{row.email}</small>
          </div>
        </div>
      ),
    },
    {
      key: "role",
      header: "Rôle",
      sortValue: (row) => row.role,
      cell: (row) => (
        <Badge
          tone={
            row.role === "ADMIN"
              ? "critical"
              : row.role === "SUPERVISOR"
                ? "warning"
                : "info"
          }
        >
          {roleLabel(row.role)}
        </Badge>
      ),
    },
    {
      key: "status",
      header: "État",
      sortValue: (row) => Number(row.is_active),
      cell: (row) => (
        <Badge tone={row.is_active ? "success" : "neutral"} dot>
          {row.is_active ? "Actif" : "Désactivé"}
        </Badge>
      ),
    },
    {
      key: "tenant",
      header: "Tenant",
      cell: (row) =>
        row.customer ? (
          <span className="technical-id">
            {String(row.customer).slice(0, 13)}
          </span>
        ) : (
          <Badge tone="ml">Plateforme</Badge>
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
            icon={Pencil}
            onClick={(event) => {
              event.stopPropagation();
              openEdit(row);
            }}
          >
            Modifier
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={Trash2}
            onClick={(event) => {
              event.stopPropagation();
              setDeleteTarget(row);
              setConfirm("");
            }}
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
        title="Utilisateurs et clients"
        description="Gestion des comptes du tenant et consultation des clients autorisés. Les permissions effectives restent appliquées par le backend."
        actions={
          <Button icon={Plus} onClick={openCreate}>
            Créer un utilisateur
          </Button>
        }
      />
      <div className="stats-grid">
        <StatCard
          label="Comptes du tenant"
          value={users.data?.count ?? "—"}
          icon={<UserRound />}
        />
        <StatCard
          label="Actifs sur cette page"
          value={stats.active}
          icon={<UserCheck />}
        />
        <StatCard
          label="Désactivés sur cette page"
          value={stats.inactive}
          icon={<UserX />}
          tone="warning"
        />
        <StatCard
          label="Administrateurs sur cette page"
          value={stats.admins}
          icon={<Shield />}
          tone="critical"
        />
      </div>
      <div className="inline-notice inline-notice--warning users-admin-warning">
        <Shield />
        Le backend permet actuellement à un administrateur de se rétrograder, se
        désactiver ou se supprimer. Vérifiez toujours qu’un autre administrateur
        actif existe.
      </div>
      <Card className="table-card resource-card">
        <div className="resource-toolbar">
          <div className="resource-toolbar__title">
            <h2>Comptes</h2>
            <p>
              L’API ne propose pas de recherche ou filtre : critères locaux à la
              page chargée.
            </p>
          </div>
          <div className="filters-bar">
            <label className="search-control">
              <Search />
              <Input
                aria-label="Rechercher un utilisateur"
                placeholder="Nom, email, username…"
                value={search}
                onChange={(event) => setSearch(event.target.value)}
              />
            </label>
            <Select
              aria-label="Filtrer par rôle"
              value={role}
              onChange={(event) => setRole(event.target.value)}
            >
              <option value="ALL">Tous les rôles</option>
              {(
                [
                  "ADMIN",
                  "SUPERVISOR",
                  "TECHNICIAN",
                  "CLIENT",
                  "VIEWER",
                ] as Role[]
              ).map((item) => (
                <option key={item} value={item}>
                  {roleLabel(item)}
                </option>
              ))}
            </Select>
            <Select
              aria-label="Filtrer par état"
              value={state}
              onChange={(event) => setState(event.target.value)}
            >
              <option value="ALL">Tous les états</option>
              <option value="ACTIVE">Actifs</option>
              <option value="INACTIVE">Désactivés</option>
            </Select>
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(row) => row.id}
          loading={users.isLoading}
          error={users.error}
          retry={() => users.refetch()}
          emptyTitle="Aucun utilisateur"
        />
        <Pagination
          page={page}
          count={users.data?.count || 0}
          onPage={setPage}
        />
      </Card>
      {currentUser && <CustomersPanel currentUser={currentUser} />}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editing ? "Modifier un utilisateur" : "Créer un utilisateur"}
        description={
          editing?.id === currentUser?.id
            ? "Vous modifiez votre propre compte. Une désactivation ou rétrogradation peut fermer votre accès."
            : undefined
        }
        footer={
          <div className="modal-actions">
            <Button variant="ghost" onClick={() => setModalOpen(false)}>
              Annuler
            </Button>
            <Button form="user-form" type="submit" loading={save.isPending}>
              {editing ? "Enregistrer" : "Créer"}
            </Button>
          </div>
        }
      >
        <form id="user-form" className="form-grid" onSubmit={submit}>
          <Field label="Email" required>
            <Input
              type="email"
              value={form.email}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  email: event.target.value,
                }))
              }
              required
            />
          </Field>
          <Field label="Nom utilisateur" required>
            <Input
              value={form.username}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  username: event.target.value,
                }))
              }
              required
            />
          </Field>
          <Field label="Prénom">
            <Input
              value={form.first_name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  first_name: event.target.value,
                }))
              }
            />
          </Field>
          <Field label="Nom">
            <Input
              value={form.last_name}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  last_name: event.target.value,
                }))
              }
            />
          </Field>
          <Field label="Rôle" required>
            <Select
              value={form.role}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  role: event.target.value as Role,
                }))
              }
            >
              {(
                [
                  "ADMIN",
                  "SUPERVISOR",
                  "TECHNICIAN",
                  "CLIENT",
                  "VIEWER",
                ] as Role[]
              ).map((item) => (
                <option key={item} value={item}>
                  {roleLabel(item)}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label={
              editing ? "Nouveau mot de passe (facultatif)" : "Mot de passe"
            }
            hint="Validé par les règles de sécurité Django."
            required={!editing}
          >
            <Input
              type="password"
              autoComplete="new-password"
              value={form.password}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  password: event.target.value,
                }))
              }
              required={!editing}
            />
          </Field>
          <label className="checkbox">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(event) =>
                setForm((current) => ({
                  ...current,
                  is_active: event.target.checked,
                }))
              }
            />
            <span />
            Compte actif
          </label>
        </form>
      </Modal>
      <Modal
        open={Boolean(deleteTarget)}
        onClose={() => setDeleteTarget(null)}
        title="Supprimer le compte"
        description={
          deleteTarget?.id === currentUser?.id
            ? "Attention : il s’agit de votre propre compte."
            : "Cette opération est définitive."
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
              disabled={confirm !== deleteTarget?.email}
              loading={remove.isPending}
              onClick={() => remove.mutate()}
            >
              Supprimer
            </Button>
          </div>
        }
      >
        <Field label={`Saisissez ${deleteTarget?.email || ""} pour confirmer`}>
          <Input
            value={confirm}
            onChange={(event) => setConfirm(event.target.value)}
          />
        </Field>
      </Modal>
    </div>
  );
}
