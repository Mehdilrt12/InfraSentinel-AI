import type { ElementType, ReactNode } from "react";

export function Card({
  children,
  className = "",
  interactive = false,
  as: Component = "section",
}: {
  children: ReactNode;
  className?: string;
  interactive?: boolean;
  as?: ElementType;
}) {
  return (
    <Component
      className={`card ${interactive ? "card--interactive" : ""} ${className}`}
    >
      {children}
    </Component>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <header className="card__header">
      <div>
        <h2 className="card__title">{title}</h2>
        {description && <p className="card__description">{description}</p>}
      </div>
      {action && <div className="card__action">{action}</div>}
    </header>
  );
}

export function StatCard({
  label,
  value,
  icon,
  tone = "accent",
  detail,
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: string;
  detail?: ReactNode;
}) {
  return (
    <Card className={`stat-card stat-card--${tone}`}>
      <div className="stat-card__icon">{icon}</div>
      <div>
        <strong>{value}</strong>
        <span>{label}</span>
        {detail && <small>{detail}</small>}
      </div>
    </Card>
  );
}

export function MetricCard({
  label,
  value,
  detail,
  tone = "accent",
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: string;
}) {
  return (
    <Card className={`metric-card metric-card--${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
    </Card>
  );
}
