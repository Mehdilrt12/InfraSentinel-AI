from django.urls import path
from rest_framework.routers import DefaultRouter
from .api import (
    AgentEnrollView,
    AgentHeartbeatView,
    AgentIngestView,
    AgentViewSet,
    AlertViewSet,
    AnomalyViewSet,
    AuditLogViewSet,
    CollectionRunViewSet,
    ConnectorViewSet,
    CustomerViewSet,
    DashboardView,
    EnvironmentViewSet,
    HealthView,
    HyperVOverviewView,
    MLModelViewSet,
    MachineViewSet,
    MeView,
    MetricAggregateViewSet,
    MetricViewSet,
    NotificationDeliveryViewSet,
    NotificationPreferenceViewSet,
    RealtimeReplayView,
    RealtimeTicketView,
    RegisterView,
    ReportViewSet,
    RuleViewSet,
    TaskRunViewSet,
    UserViewSet,
    VirtualAssetViewSet,
    VMwareOverviewView,
)

router = DefaultRouter()
router.register("customers", CustomerViewSet, basename="customer")
router.register("users", UserViewSet, basename="user")
router.register("environments", EnvironmentViewSet, basename="environment")
router.register("machines", MachineViewSet, basename="machine")
router.register("agents", AgentViewSet, basename="agent")
router.register("connectors", ConnectorViewSet, basename="connector")
router.register("assets", VirtualAssetViewSet, basename="asset")
router.register("metrics", MetricViewSet, basename="metric")
router.register(
    "metric-aggregates", MetricAggregateViewSet, basename="metric-aggregate"
)
router.register("rules", RuleViewSet, basename="rule")
router.register("alerts", AlertViewSet, basename="alert")
router.register("anomalies", AnomalyViewSet, basename="anomaly")
router.register("ml/models", MLModelViewSet, basename="ml-model")
router.register(
    "notifications/preferences",
    NotificationPreferenceViewSet,
    basename="notification-preference",
)
router.register(
    "notifications/deliveries",
    NotificationDeliveryViewSet,
    basename="notification-delivery",
)
router.register("collection-runs", CollectionRunViewSet, basename="collection-run")
router.register("audit", AuditLogViewSet, basename="audit")
router.register("tasks", TaskRunViewSet, basename="task")
router.register("reports", ReportViewSet, basename="report")

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("auth/register/", RegisterView.as_view()),
    path("auth/me/", MeView.as_view()),
    path("dashboard/", DashboardView.as_view()),
    path("agent/enroll/", AgentEnrollView.as_view()),
    path("agent/heartbeat/", AgentHeartbeatView.as_view()),
    path("agent/metrics/", AgentIngestView.as_view()),
    path("realtime/ticket/", RealtimeTicketView.as_view()),
    path("realtime/replay/", RealtimeReplayView.as_view()),
    path("vmware/overview/", VMwareOverviewView.as_view(), {"source": "VMWARE"}),
    path("hyperv/overview/", HyperVOverviewView.as_view(), {"source": "HYPERV"}),
] + router.urls
