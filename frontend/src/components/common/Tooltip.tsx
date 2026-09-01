import type { ReactNode } from "react";

export function Tooltip({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <span className="tooltip" tabIndex={0} aria-label={label}>
      {children}
      <span className="tooltip__content" role="tooltip">
        {label}
      </span>
    </span>
  );
}
