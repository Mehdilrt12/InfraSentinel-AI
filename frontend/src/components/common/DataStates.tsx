import {
  AlertTriangle,
  DatabaseZap,
  Inbox,
  LoaderCircle,
  WifiOff,
} from "lucide-react";
import type { ReactNode } from "react";
import { Button } from "./Button";

export function LoadingState({
  label = "Chargement des données…",
  fullPage = false,
}: {
  label?: string;
  fullPage?: boolean;
}) {
  return (
    <div
      className={`state state--loading ${fullPage ? "state--page" : ""}`}
      role="status"
    >
      <LoaderCircle className="spin" aria-hidden />
      <span>{label}</span>
    </div>
  );
}

export function Skeleton({
  lines = 3,
  className = "",
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`skeleton-stack ${className}`} aria-hidden>
      {Array.from({ length: lines }, (_, index) => (
        <span className="skeleton" key={index} />
      ))}
    </div>
  );
}

export function EmptyState({
  title = "Aucune donnée",
  description = "Aucune donnée réelle n’est disponible pour le moment.",
  icon: Icon = Inbox,
  action,
}: {
  title?: string;
  description?: string;
  icon?: typeof Inbox;
  action?: ReactNode;
}) {
  return (
    <div className="state state--empty">
      <Icon aria-hidden />
      <h3>{title}</h3>
      <p>{description}</p>
      {action}
    </div>
  );
}

export function ErrorState({
  title = "Impossible de récupérer les données",
  description,
  retry,
  compact = false,
}: {
  title?: string;
  description?: string;
  retry?: () => void;
  compact?: boolean;
}) {
  return (
    <div
      className={`state state--error ${compact ? "state--compact" : ""}`}
      role="alert"
    >
      <AlertTriangle aria-hidden />
      <h3>{title}</h3>
      <p>{description || "Le service est temporairement indisponible."}</p>
      {retry && (
        <Button variant="secondary" onClick={retry}>
          Réessayer
        </Button>
      )}
    </div>
  );
}

export function OfflineState() {
  return (
    <div className="state state--offline" role="status">
      <WifiOff aria-hidden />
      <div>
        <strong>Connexion réseau interrompue</strong>
        <p>
          Les dernières données chargées restent visibles. Reconnexion
          automatique en attente.
        </p>
      </div>
    </div>
  );
}

export function PartialState({ children }: { children?: ReactNode }) {
  return (
    <div className="inline-notice inline-notice--warning">
      <DatabaseZap aria-hidden />
      <span>
        {children || "Certaines données n’ont pas pu être récupérées."}
      </span>
    </div>
  );
}
