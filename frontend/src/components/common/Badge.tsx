import type { ReactNode } from "react";
import type {
  AlertStatus,
  MachineStatus,
  Severity,
  SourceType,
} from "../../types/api";

export function Badge({
  tone = "neutral",
  children,
  dot = false,
}: {
  tone?: string;
  children: ReactNode;
  dot?: boolean;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      {dot && <span className="badge__dot" aria-hidden />}
      {children}
    </span>
  );
}

const STATUS_LABELS: Record<string, string> = {
  ONLINE: "En ligne",
  OFFLINE: "Hors ligne",
  UNKNOWN: "Inconnu",
  NEW: "Nouvelle",
  ACKNOWLEDGED: "Acquittée",
  IN_PROGRESS: "En cours",
  RESOLVED: "Résolue",
  READY: "Prêt",
  TRAINING: "En entraînement",
  FAILED: "Échec",
  ARCHIVED: "Archivé",
  SUCCESS: "Succès",
  PENDING: "En attente",
  RUNNING: "En cours",
  SENT: "Envoyée",
  RETRY: "Nouvel essai",
};

export const statusTone = (status?: string) =>
  ({
    ONLINE: "success",
    READY: "success",
    SUCCESS: "success",
    SENT: "success",
    RESOLVED: "success",
    OFFLINE: "critical",
    FAILED: "critical",
    NEW: "critical",
    WARNING: "warning",
    PENDING: "warning",
    RETRY: "warning",
    ACKNOWLEDGED: "info",
    IN_PROGRESS: "info",
    RUNNING: "info",
    TRAINING: "ml",
  })[String(status || "").toUpperCase()] || "neutral";

export function StatusBadge({
  status,
}: {
  status?: MachineStatus | AlertStatus | string;
}) {
  return (
    <Badge tone={statusTone(status)} dot>
      {STATUS_LABELS[String(status || "").toUpperCase()] || status || "Inconnu"}
    </Badge>
  );
}

export function SeverityBadge({ severity }: { severity?: Severity | string }) {
  const value = String(severity || "INFO").toUpperCase();
  const labels: Record<string, string> = {
    CRITICAL: "Critique",
    HIGH: "Élevée",
    WARNING: "Avertissement",
    INFO: "Information",
  };
  const tones: Record<string, string> = {
    CRITICAL: "critical",
    HIGH: "high",
    WARNING: "warning",
    INFO: "info",
  };
  return (
    <Badge tone={tones[value] || "neutral"} dot>
      {labels[value] || value}
    </Badge>
  );
}

export function SourceBadge({ source }: { source?: SourceType | string }) {
  const value = String(source || "UNKNOWN").toUpperCase();
  return (
    <Badge tone={value.toLowerCase()}>
      {(
        {
          WINDOWS: "Windows",
          VMWARE: "VMware",
          HYPERV: "Hyper-V",
          MIXED: "Mixte",
        } as Record<string, string>
      )[value] || value}
    </Badge>
  );
}
