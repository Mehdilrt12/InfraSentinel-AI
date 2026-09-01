import { CheckCircle2, Info, TriangleAlert, X, XCircle } from "lucide-react";
import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type ToastTone = "success" | "error" | "warning" | "info";
interface ToastItem {
  id: number;
  tone: ToastTone;
  title: string;
  detail?: string;
}
interface ToastApi {
  notify: (toast: Omit<ToastItem, "id">) => void;
}
const ToastContext = createContext<ToastApi | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const remove = useCallback(
    (id: number) =>
      setItems((current) => current.filter((item) => item.id !== id)),
    [],
  );
  const notify = useCallback(
    (toast: Omit<ToastItem, "id">) => {
      const id = Date.now() + Math.random();
      setItems((current) => [...current.slice(-3), { ...toast, id }]);
      window.setTimeout(() => remove(id), 5_000);
    },
    [remove],
  );
  const value = useMemo(() => ({ notify }), [notify]);
  const icons = {
    success: CheckCircle2,
    error: XCircle,
    warning: TriangleAlert,
    info: Info,
  };
  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="toast-region"
        aria-live="polite"
        aria-label="Notifications"
      >
        {items.map((item) => {
          const Icon = icons[item.tone];
          return (
            <div className={`toast toast--${item.tone}`} key={item.id}>
              <Icon aria-hidden />
              <div>
                <strong>{item.title}</strong>
                {item.detail && <p>{item.detail}</p>}
              </div>
              <button aria-label="Fermer" onClick={() => remove(item.id)}>
                <X />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context)
    throw new Error("useToast doit être utilisé dans ToastProvider");
  return context;
}
