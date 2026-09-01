import type {
  InputHTMLAttributes,
  LabelHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
  TextareaHTMLAttributes,
} from "react";

export function Field({
  label,
  hint,
  error,
  children,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <label className={`field ${error ? "field--error" : ""}`}>
      <span className="field__label">
        {label}
        {required && <em> *</em>}
      </span>
      {children}
      {error ? (
        <span className="field__error">{error}</span>
      ) : hint ? (
        <span className="field__hint">{hint}</span>
      ) : null}
    </label>
  );
}

export function Input(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={`input ${props.className || ""}`} {...props} />;
}
export function Select({
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={`select ${props.className || ""}`} {...props}>
      {children}
    </select>
  );
}
export function Textarea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea className={`textarea ${props.className || ""}`} {...props} />
  );
}

export function Checkbox({
  label,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string }) {
  return (
    <label className="checkbox">
      <input type="checkbox" {...props} />
      <span aria-hidden />
      {label}
    </label>
  );
}

export function SearchField({
  label = "Rechercher",
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string }) {
  return (
    <label className="search-field">
      <span className="sr-only">{label}</span>
      <Input type="search" placeholder={label} {...props} />
    </label>
  );
}

export function FieldsetLabel(props: LabelHTMLAttributes<HTMLLegendElement>) {
  return <legend className="fieldset-label" {...props} />;
}
