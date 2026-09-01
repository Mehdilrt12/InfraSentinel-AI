import { type FormEvent } from "react";
import { Button, Field, Input, Modal, Select } from "../../components/common";
import type {
  Connector,
  Environment,
  Machine,
  MonitoringRule,
  NotificationPreference,
  Severity,
  SourceType,
} from "../../types/api";
import { sourceLabel } from "../../utils/format";

export type SettingsEditorState =
  | { kind: "rule"; value?: MonitoringRule }
  | { kind: "preference"; value?: NotificationPreference }
  | { kind: "environment"; value?: Environment }
  | { kind: "connector"; value?: Connector }
  | null;

export interface SettingsSavePayload {
  path: string;
  body: Record<string, unknown>;
  id?: string | number;
}

interface SettingsEditorProps {
  editor: SettingsEditorState;
  close: () => void;
  save: (payload: SettingsSavePayload) => void;
  loading: boolean;
  environments: Environment[];
  machines: Machine[];
  currentUserId: number;
}

const severityOptions: Severity[] = ["INFO", "WARNING", "HIGH", "CRITICAL"];

export function buildEnvironmentBody(data: FormData): Record<string, unknown> {
  return {
    name: data.get("name"),
    kind: data.get("kind"),
  };
}

export function buildConnectorBody(data: FormData): Record<string, unknown> {
  const secret = String(data.get("secret_ref") || "");
  const body: Record<string, unknown> = {
    environment: data.get("environment"),
    kind: data.get("kind"),
    name: data.get("name"),
    endpoint: data.get("endpoint"),
    username: data.get("username"),
    verify_tls: data.get("verify_tls") === "on",
    timeout_seconds: Number(data.get("timeout_seconds")),
    enabled: data.get("enabled") === "on",
  };
  if (secret) body.secret_ref = secret;
  return body;
}

export function SettingsEditor({
  editor,
  close,
  save,
  loading,
  environments,
  machines,
  currentUserId,
}: SettingsEditorProps) {
  if (!editor) return null;
  const value = editor.value;
  const titles = {
    rule: value ? "Modifier la règle" : "Créer une règle",
    preference: value
      ? "Modifier la préférence"
      : "Ajouter une préférence email",
    environment: value ? "Modifier l’environnement" : "Créer un environnement",
    connector: value ? "Modifier le connecteur" : "Créer un connecteur",
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    if (editor.kind === "rule")
      save({
        path: "/rules/",
        id: (value as MonitoringRule | undefined)?.id,
        body: {
          name: data.get("name"),
          metric: data.get("metric"),
          operator: data.get("operator"),
          threshold: Number(data.get("threshold")),
          duration_seconds: Number(data.get("duration_seconds")),
          cooldown_seconds: Number(data.get("cooldown_seconds")),
          severity: data.get("severity"),
          enabled: data.get("enabled") === "on",
          environment: data.get("environment") || null,
          machine: data.get("machine") || null,
        },
      });
    if (editor.kind === "preference")
      save({
        path: "/notifications/preferences/",
        id: (value as NotificationPreference | undefined)?.id,
        body: {
          user: data.get("scope") === "user" ? currentUserId : null,
          channel: "EMAIL",
          destination: data.get("destination"),
          minimum_severity: data.get("minimum_severity"),
          cooldown_seconds: Number(data.get("cooldown_seconds")),
          enabled: data.get("enabled") === "on",
        },
      });
    if (editor.kind === "environment")
      save({
        path: "/environments/",
        id: (value as Environment | undefined)?.id,
        body: buildEnvironmentBody(data),
      });
    if (editor.kind === "connector")
      save({
        path: "/connectors/",
        id: (value as Connector | undefined)?.id,
        body: buildConnectorBody(data),
      });
  };
  return (
    <Modal
      open
      onClose={close}
      title={titles[editor.kind]}
      size="lg"
      footer={
        <div className="modal-actions">
          <Button variant="ghost" onClick={close}>
            Annuler
          </Button>
          <Button type="submit" form="settings-editor" loading={loading}>
            Enregistrer
          </Button>
        </div>
      }
    >
      <form id="settings-editor" className="form-grid" onSubmit={submit}>
        {editor.kind === "rule" && (
          <RuleFields
            value={value as MonitoringRule | undefined}
            environments={environments}
            machines={machines}
          />
        )}
        {editor.kind === "preference" && (
          <PreferenceFields
            value={value as NotificationPreference | undefined}
          />
        )}
        {editor.kind === "environment" && (
          <EnvironmentFields value={value as Environment | undefined} />
        )}
        {editor.kind === "connector" && (
          <ConnectorFields
            value={value as Connector | undefined}
            environments={environments}
          />
        )}
      </form>
    </Modal>
  );
}

function RuleFields({
  value,
  environments,
  machines,
}: {
  value?: MonitoringRule;
  environments: Environment[];
  machines: Machine[];
}) {
  return (
    <>
      <Field label="Nom" required>
        <Input name="name" defaultValue={value?.name} required />
      </Field>
      <Field
        label="Métrique canonique"
        hint="Ex. system.cpu.utilization"
        required
      >
        <Input name="metric" defaultValue={value?.metric} required />
      </Field>
      <Field label="Opérateur" required>
        <Select name="operator" defaultValue={value?.operator || ">"}>
          {[">", "<", ">=", "<=", "==", "!="].map((operator) => (
            <option key={operator}>{operator}</option>
          ))}
        </Select>
      </Field>
      <Field label="Seuil" required>
        <Input
          name="threshold"
          type="number"
          step="any"
          defaultValue={value?.threshold ?? 90}
          required
        />
      </Field>
      <Field label="Durée (secondes)" required>
        <Input
          name="duration_seconds"
          type="number"
          min={0}
          defaultValue={value?.duration_seconds ?? 300}
          required
        />
      </Field>
      <Field label="Cooldown (secondes)" required>
        <Input
          name="cooldown_seconds"
          type="number"
          min={0}
          defaultValue={value?.cooldown_seconds ?? 300}
          required
        />
      </Field>
      <Field label="Sévérité">
        <Select name="severity" defaultValue={value?.severity || "WARNING"}>
          {severityOptions.map((severity) => (
            <option key={severity}>{severity}</option>
          ))}
        </Select>
      </Field>
      <Field label="Environnement (facultatif)">
        <Select name="environment" defaultValue={value?.environment || ""}>
          <option value="">Tout le tenant</option>
          {environments.map((environment) => (
            <option key={environment.id} value={environment.id}>
              {environment.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Machine (facultatif)">
        <Select name="machine" defaultValue={value?.machine || ""}>
          <option value="">Toutes les machines</option>
          {machines.map((machine) => (
            <option key={machine.id} value={machine.id}>
              {machine.hostname}
            </option>
          ))}
        </Select>
      </Field>
      <label className="checkbox">
        <input
          name="enabled"
          type="checkbox"
          defaultChecked={value?.enabled ?? true}
        />
        <span />
        Règle active
      </label>
    </>
  );
}

function PreferenceFields({ value }: { value?: NotificationPreference }) {
  return (
    <>
      <Field label="Canal">
        <Select disabled>
          <option>Email</option>
          <option>Teams — non implémenté</option>
          <option>Slack — non implémenté</option>
          <option>Telegram — non implémenté</option>
        </Select>
      </Field>
      <Field label="Destination email" required>
        <Input
          name="destination"
          type="email"
          defaultValue={value?.destination}
          required
        />
      </Field>
      <Field label="Portée">
        <Select name="scope" defaultValue={value?.user ? "user" : "tenant"}>
          <option value="tenant">Tout le tenant</option>
          <option value="user">Utilisateur courant</option>
        </Select>
      </Field>
      <Field label="Sévérité minimale">
        <Select
          name="minimum_severity"
          defaultValue={value?.minimum_severity || "HIGH"}
        >
          {severityOptions.map((severity) => (
            <option key={severity}>{severity}</option>
          ))}
        </Select>
      </Field>
      <Field label="Cooldown anti-spam (secondes)">
        <Input
          name="cooldown_seconds"
          type="number"
          min={0}
          defaultValue={value?.cooldown_seconds ?? 300}
          required
        />
      </Field>
      <label className="checkbox">
        <input
          name="enabled"
          type="checkbox"
          defaultChecked={value?.enabled ?? true}
        />
        <span />
        Préférence active
      </label>
    </>
  );
}

function EnvironmentFields({ value }: { value?: Environment }) {
  return (
    <>
      <Field label="Nom" required>
        <Input name="name" defaultValue={value?.name} required />
      </Field>
      <Field label="Type">
        <Select name="kind" defaultValue={value?.kind || "WINDOWS"}>
          {(["WINDOWS", "VMWARE", "HYPERV", "MIXED"] as SourceType[]).map(
            (kind) => (
              <option value={kind} key={kind}>
                {sourceLabel(kind)}
              </option>
            ),
          )}
        </Select>
      </Field>
    </>
  );
}

function ConnectorFields({
  value,
  environments,
}: {
  value?: Connector;
  environments: Environment[];
}) {
  return (
    <>
      <Field label="Environnement" required>
        <Select
          name="environment"
          defaultValue={value?.environment || ""}
          required
        >
          <option value="">Sélectionner…</option>
          {environments
            .filter((environment) =>
              ["VMWARE", "HYPERV", "MIXED"].includes(environment.kind),
            )
            .map((environment) => (
              <option value={environment.id} key={environment.id}>
                {environment.name} · {sourceLabel(environment.kind)}
              </option>
            ))}
        </Select>
      </Field>
      <Field label="Type">
        <Select name="kind" defaultValue={value?.kind || "VMWARE"}>
          <option value="VMWARE">VMware / vCenter</option>
          <option value="HYPERV">Microsoft Hyper-V</option>
        </Select>
      </Field>
      <Field label="Nom" required>
        <Input name="name" defaultValue={value?.name} required />
      </Field>
      <Field
        label="Endpoint"
        hint="VMware exige HTTPS ; Hyper-V un nom DNS/IP sans schéma."
        required
      >
        <Input name="endpoint" defaultValue={value?.endpoint} required />
      </Field>
      <Field label="Utilisateur">
        <Input name="username" defaultValue={value?.username} />
      </Field>
      <Field
        label={
          value
            ? "Nouvelle référence de secret (facultatif)"
            : "Référence de secret"
        }
        hint="Nom de variable INFRASENTINEL_CUSTOMER_<UUID>_... ; jamais la valeur du mot de passe."
        required={!value}
      >
        <Input
          name="secret_ref"
          type="text"
          autoComplete="off"
          required={!value}
        />
      </Field>
      <Field label="Timeout (secondes)">
        <Input
          name="timeout_seconds"
          type="number"
          min={1}
          max={300}
          defaultValue={value?.timeout_seconds ?? 30}
          required
        />
      </Field>
      <label className="checkbox">
        <input
          name="verify_tls"
          type="checkbox"
          defaultChecked={value?.verify_tls ?? true}
        />
        <span />
        Vérifier le certificat TLS
      </label>
      <label className="checkbox">
        <input
          name="enabled"
          type="checkbox"
          defaultChecked={value?.enabled ?? true}
        />
        <span />
        Connecteur actif
      </label>
    </>
  );
}
