import { lazy, Suspense } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { ProtectedRoute, RoleRoute } from "../auth/RouteGuards";
import { AppShell } from "../components/layout/AppShell";
import { LoadingState } from "../components/common";
import { RealtimeProvider } from "../realtime/RealtimeProvider";

const LoginPage = lazy(() => import("../pages/auth/LoginPage"));
const RegisterPage = lazy(() => import("../pages/auth/RegisterPage"));
const DashboardPage = lazy(() => import("../pages/dashboard/DashboardPage"));
const MachinesPage = lazy(() => import("../pages/machines/MachinesPage"));
const MachineDetailPage = lazy(
  () => import("../pages/machines/MachineDetailPage"),
);
const AgentsPage = lazy(() => import("../pages/agents/AgentsPage"));
const AlertsPage = lazy(() => import("../pages/alerts/AlertsPage"));
const AlertDetailPage = lazy(() => import("../pages/alerts/AlertDetailPage"));
const AnomaliesPage = lazy(() => import("../pages/anomalies/AnomaliesPage"));
const PredictionsPage = lazy(
  () => import("../pages/predictions/PredictionsPage"),
);
const MLPage = lazy(() => import("../pages/ml/MLPage"));
const VMwarePage = lazy(() => import("../pages/virtualization/VMwarePage"));
const VMwareDetailPage = lazy(
  () => import("../pages/virtualization/VMwareDetailPage"),
);
const HyperVPage = lazy(() => import("../pages/virtualization/HyperVPage"));
const HyperVDetailPage = lazy(
  () => import("../pages/virtualization/HyperVDetailPage"),
);
const UsersPage = lazy(() => import("../pages/users/UsersPage"));
const AuditPage = lazy(() => import("../pages/audit/AuditPage"));
const ReportsPage = lazy(() => import("../pages/reports/ReportsPage"));
const SettingsPage = lazy(() => import("../pages/settings/SettingsPage"));
const ForbiddenPage = lazy(() => import("../pages/system/ForbiddenPage"));
const NotFoundPage = lazy(() => import("../pages/system/NotFoundPage"));

function SecuredShell() {
  return (
    <ProtectedRoute>
      <RealtimeProvider>
        <AppShell />
      </RealtimeProvider>
    </ProtectedRoute>
  );
}

export default function App() {
  return (
    <Suspense
      fallback={<LoadingState label="Chargement du module…" fullPage />}
    >
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route element={<SecuredShell />}>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/machines" element={<MachinesPage />} />
          <Route path="/machines/:id" element={<MachineDetailPage />} />
          <Route path="/agents" element={<AgentsPage />} />
          <Route path="/alerts" element={<AlertsPage />} />
          <Route path="/alerts/:id" element={<AlertDetailPage />} />
          <Route path="/anomalies" element={<AnomaliesPage />} />
          <Route path="/predictions" element={<PredictionsPage />} />
          <Route path="/ml" element={<MLPage />} />
          <Route path="/vmware" element={<VMwarePage />} />
          <Route path="/vmware/:id" element={<VMwareDetailPage />} />
          <Route path="/hyperv" element={<HyperVPage />} />
          <Route path="/hyperv/:id" element={<HyperVDetailPage />} />
          <Route
            path="/users"
            element={
              <RoleRoute capability="manage:users">
                <UsersPage />
              </RoleRoute>
            }
          />
          <Route
            path="/audit"
            element={
              <RoleRoute capability="read:audit">
                <AuditPage />
              </RoleRoute>
            }
          />
          <Route
            path="/reports"
            element={
              <RoleRoute capability="read:reports">
                <ReportsPage />
              </RoleRoute>
            }
          />
          <Route
            path="/settings"
            element={
              <RoleRoute capability="manage:operations">
                <SettingsPage />
              </RoleRoute>
            }
          />
          <Route path="/forbidden" element={<ForbiddenPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Route>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Suspense>
  );
}
