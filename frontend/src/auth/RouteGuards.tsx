import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";
import { LoadingState } from "../components/common/DataStates";
import { useAuth } from "./AuthProvider";
import { can, type Capability } from "./permissions";

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading)
    return <LoadingState label="Vérification de la session…" fullPage />;
  return user ? (
    children
  ) : (
    <Navigate to="/login" replace state={{ from: location }} />
  );
}

export function RoleRoute({
  capability,
  children,
}: {
  capability: Capability;
  children: ReactNode;
}) {
  const { user, loading } = useAuth();
  if (loading)
    return <LoadingState label="Vérification des autorisations…" fullPage />;
  return can(user, capability) ? (
    children
  ) : (
    <Navigate to="/forbidden" replace />
  );
}
