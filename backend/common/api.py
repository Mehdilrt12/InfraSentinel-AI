import secrets
import ipaddress
import re
import uuid
from django.contrib.auth.password_validation import validate_password
from django.core.cache import cache
from django.db import IntegrityError, connection, transaction
from django.db.models import Q
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify
from drf_spectacular.utils import OpenApiParameter, OpenApiResponse, extend_schema
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView
from accounts.models import Customer, User
from async_tasks.models import GeneratedReport, TaskRun
from async_tasks.tasks import generate_report
from integrations.models import CollectionRun
from integrations.tasks import collect_hyperv_connector, collect_vmware_connector
from inventory.models import (
    Agent,
    Environment,
    IntegrationEndpoint,
    Machine,
    VirtualAsset,
)
from inventory.services import authenticate_agent, create_enrollment_code, enroll_agent
from metrics.models import MetricAggregate, NormalizedMetric
from metrics.services import ingest_metrics
from ml_engine.models import MLModelVersion
from ml_engine.predictive import analyze_machine_trends
from ml_engine.tasks import evaluate_model, train_model
from monitoring.models import Alert, Anomaly, AuditLog, MonitoringRule
from monitoring.audit import (
    action_for_instance,
    client_ip,
    record_audit,
    request_change_metadata,
)
from notifications.models import NotificationDelivery, NotificationPreference
from realtime.models import RealtimeEvent
from realtime.publisher import publish
from realtime.tickets import issue_ticket
from .permissions import (
    IsActiveTenant,
    IsAdmin,
    IsAuditReader,
    IsPlatformAdminForWrite,
    ReadOnlyUnlessManager,
)
from .throttles import AgentEnrollmentThrottle, AgentRequestThrottle, RegistrationThrottle
from .openapi import (
    AUTH_ERRORS,
    NOT_FOUND_ERROR,
    VALIDATION_ERRORS,
    AgentEnrollmentRequestSerializer,
    AgentEnrollmentResponseSerializer,
    AgentHeartbeatRequestSerializer,
    AgentHeartbeatResponseSerializer,
    AgentMetricAcceptedSerializer,
    AgentMetricBatchSerializer,
    DashboardResponseSerializer,
    EnrollmentCodeRequestSerializer,
    EnrollmentCodeResponseSerializer,
    ErrorResponseSerializer,
    HealthResponseSerializer,
    IntegrationOverviewResponseSerializer,
    PredictionSerializer,
    RealtimeEventSerializer,
    RealtimeTicketResponseSerializer,
    RegistrationRequestSerializer,
    RegistrationResponseSerializer,
    ReportRequestSerializer,
    TaskQueuedResponseSerializer,
    TaskRequestSerializer,
    crud_schema,
    readonly_schema,
    read_patch_schema,
)
from .serializers import (
    AgentSerializer,
    AlertSerializer,
    AnomalySerializer,
    AuditLogSerializer,
    CollectionRunSerializer,
    ConnectorSerializer,
    CustomerSerializer,
    EnvironmentSerializer,
    MachineSerializer,
    MetricAggregateSerializer,
    MetricSerializer,
    MLModelSerializer,
    NotificationDeliverySerializer,
    NotificationPreferenceSerializer,
    ReportSerializer,
    RuleSerializer,
    TaskRunSerializer,
    UserSerializer,
    VirtualAssetSerializer,
)


def tenant_queryset(request, queryset, field="customer"):
    if request.user.is_superuser:
        customer_id = request.query_params.get("customer")
        if customer_id:
            try:
                customer_id = uuid.UUID(customer_id)
            except (TypeError, ValueError, AttributeError) as exc:
                raise ValidationError({"customer": "UUID client invalide."}) from exc
        return (
            queryset.filter(**{f"{field}_id": customer_id}) if customer_id else queryset
        )
    if not request.user.customer_id:
        return queryset.none()
    return queryset.filter(**{f"{field}_id": request.user.customer_id})


class TenantViewSet(viewsets.ModelViewSet):
    permission_classes = [ReadOnlyUnlessManager]
    tenant_field = "customer"

    def get_queryset(self):
        return tenant_queryset(self.request, super().get_queryset(), self.tenant_field)

    @transaction.atomic
    def perform_create(self, serializer):
        if not self.request.user.customer_id:
            raise serializers.ValidationError(
                "Le compte doit être associé à un client."
            )
        instance = serializer.save(customer=self.request.user.customer)
        record_audit(
            action_for_instance(instance, "create"),
            customer=self.request.user.customer,
            actor=self.request.user,
            target=instance,
            request=self.request,
            metadata=request_change_metadata(self.request, operation="create"),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        previous = {
            "enabled": getattr(serializer.instance, "enabled", None),
            "status": getattr(serializer.instance, "status", None),
        }
        instance = serializer.save()
        metadata = request_change_metadata(self.request, operation="update")
        for field in ("enabled", "status"):
            current = getattr(instance, field, None)
            if previous[field] is not None and previous[field] != current:
                metadata.setdefault("transitions", {})[field] = {
                    "from": previous[field],
                    "to": current,
                }
        record_audit(
            action_for_instance(instance, "update", previous),
            customer=getattr(instance, "customer", self.request.user.customer),
            actor=self.request.user,
            target=instance,
            request=self.request,
            metadata=metadata,
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        record_audit(
            action_for_instance(instance, "delete"),
            customer=getattr(instance, "customer", self.request.user.customer),
            actor=self.request.user,
            target=instance,
            request=self.request,
            metadata=request_change_metadata(self.request, operation="delete"),
        )
        instance.delete()


@crud_schema(
    "Customers",
    "clients",
    CustomerSerializer,
    permissions=["ADMIN"],
    read_permissions=["ADMIN"],
    tenant_filter=False,
)
class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.order_by("name", "pk")
    serializer_class = CustomerSerializer
    permission_classes = [IsPlatformAdminForWrite]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(pk=self.request.user.customer_id)

    @transaction.atomic
    def perform_create(self, serializer):
        customer = serializer.save()
        record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=customer,
            actor=self.request.user,
            target=customer,
            request=self.request,
            metadata=request_change_metadata(self.request, operation="create"),
        )

    @transaction.atomic
    def perform_update(self, serializer):
        customer = serializer.save()
        record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=customer,
            actor=self.request.user,
            target=customer,
            request=self.request,
            metadata=request_change_metadata(self.request, operation="update"),
        )

    @transaction.atomic
    def perform_destroy(self, instance):
        record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=instance,
            actor=self.request.user,
            target=instance,
            request=self.request,
            metadata=request_change_metadata(self.request, operation="delete"),
        )
        instance.delete()


@crud_schema(
    "Users",
    "utilisateurs",
    UserSerializer,
    permissions=["ADMIN"],
    read_permissions=["ADMIN"],
)
class UserViewSet(TenantViewSet):
    queryset = User.objects.select_related("customer").order_by("email", "pk")
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]


@crud_schema(
    "Environments",
    "environnements",
    EnvironmentSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class EnvironmentViewSet(TenantViewSet):
    queryset = Environment.objects.order_by("name", "pk")
    serializer_class = EnvironmentSerializer

    @extend_schema(
        tags=["Agents"],
        summary="Créer un code d'enrôlement agent",
        description=(
            "JWT/session requis. ADMIN ou SUPERVISOR. Le code est limité à "
            "l'environnement Windows du tenant et n'est renvoyé qu'une fois."
        ),
        request=EnrollmentCodeRequestSerializer,
        responses={
            201: EnrollmentCodeResponseSerializer,
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
            **NOT_FOUND_ERROR,
        },
        extensions={
            "x-permissions": ["ADMIN", "SUPERVISOR"],
            "x-tenant-scope": "customer",
        },
    )
    @action(detail=True, methods=["post"], permission_classes=[ReadOnlyUnlessManager])
    def enrollment_code(self, request, pk=None):
        environment = self.get_object()
        try:
            ttl_minutes = int(request.data.get("ttl_minutes", 30))
        except (TypeError, ValueError):
            raise serializers.ValidationError(
                {"ttl_minutes": "Un nombre entier est attendu."}
            )
        if not 1 <= ttl_minutes <= 1440:
            raise serializers.ValidationError(
                {"ttl_minutes": "La durée doit être comprise entre 1 et 1440 minutes."}
            )
        try:
            raw = create_enrollment_code(environment.customer, environment, ttl_minutes)
        except ValueError as exc:
            raise serializers.ValidationError({"environment": str(exc)}) from exc
        record_audit(
            AuditLog.Action.AGENT_ENROLLMENT_CODE_CREATED,
            customer=environment.customer,
            actor=request.user,
            target=environment,
            request=request,
            metadata={"ttl_minutes": ttl_minutes},
        )
        return Response(
            {
                "enrollment_code": raw,
                "expires_in_minutes": ttl_minutes,
            },
            status=201,
        )


@crud_schema(
    "Machines",
    "machines",
    MachineSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class MachineViewSet(TenantViewSet):
    queryset = Machine.objects.select_related("environment").order_by("hostname")
    serializer_class = MachineSerializer

    @extend_schema(
        tags=["Predictions"],
        summary="Analyser les tendances d'une machine",
        description=(
            "Produit des estimations linéaires explicables à partir des métriques "
            "normalisées réelles. JWT/session requis; isolation par client."
        ),
        parameters=[
            OpenApiParameter(
                "hours",
                int,
                OpenApiParameter.QUERY,
                required=False,
                default=24,
                description="Fenêtre historique comprise entre 1 et 720 heures.",
            )
        ],
        responses={
            200: PredictionSerializer(many=True),
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
            **NOT_FOUND_ERROR,
        },
        extensions={"x-permissions": ["AUTHENTICATED"], "x-tenant-scope": "customer"},
    )
    @action(detail=True, methods=["get"], pagination_class=None)
    def trends(self, request, pk=None):
        machine = self.get_object()
        try:
            hours = int(request.query_params.get("hours", 24))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"hours": "Un entier est attendu."})
        if not 1 <= hours <= 24 * 30:
            raise serializers.ValidationError(
                {"hours": "La fenêtre doit être comprise entre 1 et 720 heures."}
            )
        return Response(analyze_machine_trends(machine, hours=hours))


@read_patch_schema(
    "Agents",
    "agents",
    AgentSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class AgentViewSet(TenantViewSet):
    queryset = Agent.objects.select_related("machine").order_by("-created_at", "pk")
    serializer_class = AgentSerializer
    http_method_names = ["get", "patch", "head", "options"]


@crud_schema(
    "Operations",
    "connecteurs",
    ConnectorSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class ConnectorViewSet(TenantViewSet):
    queryset = IntegrationEndpoint.objects.select_related("environment").order_by(
        "name", "pk"
    )
    serializer_class = ConnectorSerializer

    @extend_schema(
        tags=["VMware", "Hyper-V"],
        summary="Déclencher une collecte de connecteur",
        description=(
            "Place une collecte VMware ou Hyper-V dans Celery sans bloquer la requête. "
            "JWT/session requis; ADMIN ou SUPERVISOR; connecteur du tenant courant."
        ),
        request=None,
        responses={
            202: TaskQueuedResponseSerializer,
            **AUTH_ERRORS,
            **NOT_FOUND_ERROR,
        },
        extensions={
            "x-permissions": ["ADMIN", "SUPERVISOR"],
            "x-tenant-scope": "customer",
        },
    )
    @action(detail=True, methods=["post"])
    def collect(self, _request, pk=None):
        connector = self.get_object()
        task = (
            collect_vmware_connector.delay(str(connector.pk))
            if connector.kind == IntegrationEndpoint.Kind.VMWARE
            else collect_hyperv_connector.delay(str(connector.pk))
        )
        record_audit(
            AuditLog.Action.CONNECTOR_COLLECTION_QUEUED,
            customer=connector.customer,
            actor=_request.user,
            target=connector,
            request=_request,
            metadata={"task_id": task.id, "kind": connector.kind},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)


@readonly_schema(
    "Operations",
    "assets virtuels",
    VirtualAssetSerializer,
    list_parameters=[
        OpenApiParameter(
            "kind", str, OpenApiParameter.QUERY, enum=["HOST", "VM", "DATASTORE"]
        ),
        OpenApiParameter(
            "source", str, OpenApiParameter.QUERY, enum=["VMWARE", "HYPERV"]
        ),
    ],
)
class VirtualAssetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VirtualAsset.objects.select_related("connector", "machine").order_by(
        "kind", "name", "pk"
    )
    serializer_class = VirtualAssetSerializer

    def get_queryset(self):
        qs = tenant_queryset(self.request, self.queryset)
        if self.request.query_params.get("kind"):
            qs = qs.filter(kind=self.request.query_params["kind"])
        if self.request.query_params.get("source"):
            qs = qs.filter(connector__kind=self.request.query_params["source"])
        return qs


@readonly_schema(
    "Metrics",
    "métriques normalisées",
    MetricSerializer,
    list_parameters=[
        OpenApiParameter(
            "machine", str, OpenApiParameter.QUERY, description="UUID de machine."
        ),
        OpenApiParameter("metric_name", str, OpenApiParameter.QUERY),
        OpenApiParameter(
            "source_type",
            str,
            OpenApiParameter.QUERY,
            enum=["WINDOWS", "VMWARE", "HYPERV"],
        ),
    ],
)
class MetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NormalizedMetric.objects.select_related("machine", "environment").all()
    serializer_class = MetricSerializer

    def get_queryset(self):
        qs = tenant_queryset(self.request, self.queryset)
        for key in ("machine", "metric_name", "source_type"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs


@readonly_schema("Metrics", "agrégats de métriques", MetricAggregateSerializer)
class MetricAggregateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MetricAggregate.objects.select_related("machine").order_by(
        "-bucket_start", "pk"
    )
    serializer_class = MetricAggregateSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "machine__customer")


@crud_schema(
    "Rules",
    "règles de supervision",
    RuleSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class RuleViewSet(TenantViewSet):
    queryset = MonitoringRule.objects.select_related("machine", "environment").order_by(
        "name", "pk"
    )
    serializer_class = RuleSerializer

    @extend_schema(
        tags=["Rules"],
        summary="Activer ou désactiver une règle",
        description="JWT/session requis; ADMIN ou SUPERVISOR; règle du tenant courant.",
        request=None,
        responses={200: RuleSerializer, **AUTH_ERRORS, **NOT_FOUND_ERROR},
        extensions={
            "x-permissions": ["ADMIN", "SUPERVISOR"],
            "x-tenant-scope": "customer",
        },
    )
    @action(detail=True, methods=["post"])
    def toggle(self, _request, pk=None):
        rule = self.get_object()
        rule.enabled = not rule.enabled
        rule.save(update_fields=["enabled", "updated_at"])
        record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=rule.customer,
            actor=_request.user,
            target=rule,
            request=_request,
            metadata={"operation": "toggle", "enabled": rule.enabled},
        )
        return Response(self.get_serializer(rule).data)


@read_patch_schema(
    "Alerts",
    "alertes",
    AlertSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
    list_parameters=[
        OpenApiParameter(
            "status", str, OpenApiParameter.QUERY, enum=list(Alert.Status.values)
        ),
        OpenApiParameter(
            "machine", str, OpenApiParameter.QUERY, description="UUID de machine."
        ),
    ],
)
class AlertViewSet(TenantViewSet):
    queryset = Alert.objects.select_related(
        "machine", "structured_recommendation"
    ).order_by("-timestamp", "pk")
    serializer_class = AlertSerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        if self.request.query_params.get("machine"):
            qs = qs.filter(machine_id=self.request.query_params["machine"])
        return qs

    def perform_update(self, serializer):
        super().perform_update(serializer)
        alert = serializer.instance
        publish(
            alert.customer,
            "alert.updated",
            {"id": str(alert.pk), "status": alert.status, "severity": alert.severity},
            alert.pk,
        )


@read_patch_schema(
    "Anomalies",
    "anomalies",
    AnomalySerializer,
    permissions=["ADMIN", "SUPERVISOR"],
    list_parameters=[
        OpenApiParameter(
            "machine", str, OpenApiParameter.QUERY, description="UUID de machine."
        )
    ],
)
class AnomalyViewSet(TenantViewSet):
    queryset = Anomaly.objects.select_related("machine").order_by("-detected_at", "pk")
    serializer_class = AnomalySerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("machine"):
            qs = qs.filter(machine_id=self.request.query_params["machine"])
        return qs


@read_patch_schema(
    "ML",
    "versions de modèles ML",
    MLModelSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class MLModelViewSet(TenantViewSet):
    queryset = MLModelVersion.objects.order_by("-display_number", "pk")
    serializer_class = MLModelSerializer
    http_method_names = ["get", "post", "patch", "head", "options"]

    @extend_schema(exclude=True)
    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed(
            "POST",
            detail=(
                "La création directe d'une version ML est interdite; utilisez "
                "l'action /api/ml/models/train/."
            ),
        )

    @extend_schema(
        tags=["ML"],
        summary="Planifier un entraînement Isolation Forest",
        description="JWT/session requis; client associé; traitement Celery idempotent.",
        request=TaskRequestSerializer,
        responses={
            202: TaskQueuedResponseSerializer,
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
        },
        extensions={
            "x-permissions": ["ADMIN", "SUPERVISOR"],
            "x-tenant-scope": "customer",
        },
    )
    @action(detail=False, methods=["post"])
    def train(self, request):
        if not request.user.customer_id:
            return Response({"detail": "Un client est requis."}, status=403)
        try:
            days = int(request.data.get("days", 30))
        except (TypeError, ValueError):
            return Response({"detail": "Le nombre de jours est invalide."}, status=400)
        if not 1 <= days <= 3650:
            return Response(
                {"detail": "Le nombre de jours doit être compris entre 1 et 3650."},
                status=400,
            )
        task = train_model.delay(
            str(request.user.customer_id),
            days,
            request.data.get("idempotency_key"),
        )
        record_audit(
            AuditLog.Action.MODEL_TRAINING_QUEUED,
            customer=request.user.customer,
            actor=request.user,
            target_type="ml_engine.MLModelVersion",
            request=request,
            metadata={"task_id": task.id, "days": days},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)

    @extend_schema(
        tags=["ML"],
        summary="Planifier l'évaluation d'un modèle",
        description="JWT/session requis; client associé; traitement Celery idempotent.",
        request=TaskRequestSerializer,
        responses={
            202: TaskQueuedResponseSerializer,
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
        },
        extensions={
            "x-permissions": ["ADMIN", "SUPERVISOR"],
            "x-tenant-scope": "customer",
        },
    )
    @action(detail=False, methods=["post"])
    def evaluate(self, request):
        if not request.user.customer_id:
            return Response({"detail": "Un client est requis."}, status=403)
        try:
            days = int(request.data.get("days", 30))
        except (TypeError, ValueError):
            return Response({"detail": "Le nombre de jours est invalide."}, status=400)
        if not 1 <= days <= 3650:
            return Response(
                {"detail": "Le nombre de jours doit être compris entre 1 et 3650."},
                status=400,
            )
        task = evaluate_model.delay(
            str(request.user.customer_id),
            days,
            request.data.get("idempotency_key"),
        )
        record_audit(
            AuditLog.Action.MODEL_EVALUATION_QUEUED,
            customer=request.user.customer,
            actor=request.user,
            target_type="ml_engine.MLModelVersion",
            request=request,
            metadata={"task_id": task.id, "days": days},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)


@crud_schema(
    "Notifications",
    "préférences de notification",
    NotificationPreferenceSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
)
class NotificationPreferenceViewSet(TenantViewSet):
    queryset = NotificationPreference.objects.order_by("channel", "destination", "pk")
    serializer_class = NotificationPreferenceSerializer


@readonly_schema(
    "Notifications", "livraisons de notification", NotificationDeliverySerializer
)
class NotificationDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationDelivery.objects.select_related(
        "event", "preference"
    ).order_by("-created_at", "pk")
    serializer_class = NotificationDeliverySerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "event__customer")


@readonly_schema("Operations", "exécutions de collecte", CollectionRunSerializer)
class CollectionRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CollectionRun.objects.select_related("connector").order_by(
        "-started_at", "pk"
    )
    serializer_class = CollectionRunSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "connector__customer")


class AuditLogPagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


@readonly_schema(
    "Operations",
    "événements d'audit",
    AuditLogSerializer,
    permissions=["ADMIN", "SUPERVISOR"],
    list_validation=True,
    list_parameters=[
        OpenApiParameter("action", str, description="Action exacte."),
        OpenApiParameter("actor", int, description="Identifiant de l'acteur."),
        OpenApiParameter("target_type", str, description="Type Django de la cible."),
        OpenApiParameter("target_id", str, description="Identifiant de la cible."),
        OpenApiParameter("ip_address", str, description="Adresse IP exacte."),
        OpenApiParameter(
            "from", {"type": "string", "format": "date-time"}, description="Début UTC inclus."
        ),
        OpenApiParameter(
            "to", {"type": "string", "format": "date-time"}, description="Fin UTC incluse."
        ),
        OpenApiParameter(
            "search",
            str,
            description="Recherche action, acteur, type, identifiant ou libellé cible.",
        ),
        OpenApiParameter(
            "ordering",
            str,
            enum=["timestamp", "-timestamp", "action", "-action"],
        ),
        OpenApiParameter("page", int, description="Numéro de page."),
        OpenApiParameter("page_size", int, description="Taille de page, maximum 200."),
    ],
)
class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor", "customer").all()
    serializer_class = AuditLogSerializer
    permission_classes = [IsAuditReader]
    pagination_class = AuditLogPagination

    def get_queryset(self):
        queryset = tenant_queryset(self.request, self.queryset)
        params = self.request.query_params
        exact_filters = {
            "action": "action",
            "target_type": "target_type",
            "target_id": "target_id",
        }
        for parameter, field in exact_filters.items():
            value = params.get(parameter, "").strip()
            if value:
                queryset = queryset.filter(**{field: value[:120]})
        actor = params.get("actor", "").strip()
        if actor:
            try:
                actor = int(actor)
            except ValueError as exc:
                raise ValidationError({"actor": "Identifiant acteur invalide."}) from exc
            queryset = queryset.filter(actor_id=actor)
        address = params.get("ip_address", "").strip()
        if address:
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError as exc:
                raise ValidationError({"ip_address": "Adresse IP invalide."}) from exc
            queryset = queryset.filter(ip_address=address)
        for parameter, lookup in (("from", "timestamp__gte"), ("to", "timestamp__lte")):
            raw = params.get(parameter, "").strip()
            if not raw:
                continue
            parsed = parse_datetime(raw)
            if parsed is None:
                raise ValidationError({parameter: "Date ISO 8601 invalide."})
            if timezone.is_naive(parsed):
                parsed = timezone.make_aware(parsed)
            queryset = queryset.filter(**{lookup: parsed})
        search = params.get("search", "").strip()
        if search:
            if len(search) > 200:
                raise ValidationError({"search": "Recherche trop longue."})
            queryset = queryset.filter(
                Q(action__icontains=search)
                | Q(actor_email__icontains=search)
                | Q(target_type__icontains=search)
                | Q(target_id__icontains=search)
                | Q(target_repr__icontains=search)
            )
        ordering = params.get("ordering", "-timestamp")
        if ordering not in {"timestamp", "-timestamp", "action", "-action"}:
            raise ValidationError({"ordering": "Tri invalide."})
        return queryset.order_by(ordering, "-pk")


@readonly_schema(
    "Operations",
    "tâches asynchrones",
    TaskRunSerializer,
    permissions=["ADMIN"],
)
class TaskRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TaskRun.objects.order_by("-started_at", "-pk")
    serializer_class = TaskRunSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset)


@readonly_schema("Operations", "rapports", ReportSerializer)
class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GeneratedReport.objects.order_by("-requested_at", "pk")
    serializer_class = ReportSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset)

    @extend_schema(
        tags=["Operations"],
        summary="Planifier la génération d'un rapport",
        description="JWT/session requis; traitement Celery non bloquant et isolé par client.",
        request=ReportRequestSerializer,
        responses={
            202: TaskQueuedResponseSerializer,
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
        },
        extensions={"x-permissions": ["AUTHENTICATED"], "x-tenant-scope": "customer"},
    )
    @action(detail=False, methods=["post"])
    def generate(self, request):
        task = generate_report.delay(
            str(request.user.customer_id),
            request.data.get("kind", "summary"),
            request.data.get("idempotency_key"),
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    @extend_schema(
        tags=["System"],
        summary="Vérifier l'état de l'API",
        description="Endpoint public sans accès aux données métier.",
        auth=[],
        responses={
            200: HealthResponseSerializer,
            503: OpenApiResponse(
                HealthResponseSerializer,
                "L'API répond, mais PostgreSQL ou Redis est indisponible.",
            ),
        },
        extensions={"x-permissions": ["PUBLIC"]},
    )
    def get(self, _request):
        components = {"database": "unavailable", "redis": "unavailable"}
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            components["database"] = "ok"
        except Exception:
            pass

        cache_key = "healthcheck"
        try:
            cache.set(cache_key, "ok", timeout=10)
            if cache.get(cache_key) == "ok":
                components["redis"] = "ok"
        except Exception:
            pass

        healthy = all(value == "ok" for value in components.values())
        payload = {
            "status": "ok" if healthy else "unavailable",
            "version": "2.0.0",
            "time": timezone.now(),
            "components": components,
        }
        return Response(payload, status=200 if healthy else 503)


class RegisterView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegistrationThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Créer un client et son administrateur",
        description=(
            "Endpoint public. Crée atomiquement un customer, un compte ADMIN et son "
            "premier environnement Windows."
        ),
        auth=[],
        request=RegistrationRequestSerializer,
        responses={
            201: RegistrationResponseSerializer,
            **VALIDATION_ERRORS,
            429: OpenApiResponse(
                ErrorResponseSerializer, "Limite de requêtes dépassée."
            ),
        },
        extensions={"x-permissions": ["PUBLIC"]},
    )
    @transaction.atomic
    def post(self, request):
        from django.conf import settings

        if not settings.PUBLIC_REGISTRATION_ENABLED:
            return Response({"detail": "Inscription publique désactivée."}, status=403)
        try:
            email = serializers.EmailField().run_validation(request.data.get("email"))
        except serializers.ValidationError:
            return Response({"detail": "Adresse email invalide."}, status=400)
        email = email.strip().lower()
        password = request.data.get("password", "")
        organization = str(request.data.get("organization", "")).strip()
        if (
            not email
            or not isinstance(password, str)
            or not 10 <= len(password) <= 128
            or not organization
            or len(organization) > 160
        ):
            return Response(
                {
                    "detail": "Organisation, email et mot de passe de 10 caractères minimum requis."
                },
                status=400,
            )
        try:
            validate_password(password)
        except DjangoValidationError as exc:
            return Response({"detail": list(exc.messages)}, status=400)
        base = slugify(organization)[:60] or "customer"
        slug = base
        while Customer.objects.filter(slug=slug).exists():
            slug = f"{base}-{secrets.token_hex(2)}"
        try:
            customer = Customer.objects.create(name=organization, slug=slug)
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                customer=customer,
                role=User.Role.ADMIN,
            )
        except IntegrityError:
            return Response(
                {"detail": "Inscription impossible avec les informations fournies."},
                status=400,
            )
        environment = Environment.objects.create(
            customer=customer, name="Windows", kind=Environment.Kind.WINDOWS
        )
        record_audit(
            AuditLog.Action.USER_CREATED,
            customer=customer,
            actor=user,
            target=user,
            request=request,
            metadata={"source": "public_registration", "role": user.role},
        )
        record_audit(
            AuditLog.Action.CONFIG_CHANGED,
            customer=customer,
            actor=user,
            target=environment,
            request=request,
            metadata={"operation": "create", "source": "public_registration"},
        )
        return Response(
            {
                "user_id": user.pk,
                "customer_id": customer.pk,
                "environment_id": environment.pk,
            },
            status=201,
        )


class MeView(APIView):
    permission_classes = [IsActiveTenant]

    @extend_schema(
        tags=["Authentication"],
        summary="Consulter le profil courant",
        description="JWT Bearer ou session Django requis.",
        responses={200: UserSerializer, **AUTH_ERRORS},
        extensions={"x-permissions": ["AUTHENTICATED"]},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DashboardView(APIView):
    @extend_schema(
        tags=["Dashboard"],
        summary="Obtenir la synthèse globale",
        description="JWT/session requis. Tous les compteurs sont limités au client courant.",
        responses={200: DashboardResponseSerializer, **AUTH_ERRORS},
        extensions={"x-permissions": ["AUTHENTICATED"], "x-tenant-scope": "customer"},
    )
    def get(self, request):
        machines = tenant_queryset(request, Machine.objects.all())
        alerts = tenant_queryset(
            request, Alert.objects.exclude(status=Alert.Status.RESOLVED)
        )
        anomalies = tenant_queryset(request, Anomaly.objects.all())
        assets = tenant_queryset(request, VirtualAsset.objects.all())
        return Response(
            {
                "total_assets": machines.count(),
                "online": machines.filter(status=Machine.Status.ONLINE).count(),
                "offline": machines.filter(status=Machine.Status.OFFLINE).count(),
                "critical": alerts.filter(severity="CRITICAL").count(),
                "warning": alerts.filter(severity="WARNING").count(),
                "anomalies": anomalies.count(),
                "vmware_hosts": assets.filter(
                    kind="HOST", connector__kind="VMWARE"
                ).count(),
                "hyperv_hosts": assets.filter(
                    kind="HOST", connector__kind="HYPERV"
                ).count(),
                "active_alerts": alerts.count(),
            }
        )


class AgentEnrollView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AgentEnrollmentThrottle]

    @extend_schema(
        tags=["Agents"],
        summary="Enrôler un agent Windows",
        description=(
            "Endpoint public limité par débit. Un code d'enrôlement valide détermine le "
            "client et l'environnement. Le jeton agent n'est renvoyé qu'une fois."
        ),
        auth=[],
        request=AgentEnrollmentRequestSerializer,
        responses={
            201: AgentEnrollmentResponseSerializer,
            **VALIDATION_ERRORS,
            429: OpenApiResponse(
                ErrorResponseSerializer, "Limite de requêtes dépassée."
            ),
        },
        extensions={"x-permissions": ["VALID_ENROLLMENT_CODE"]},
    )
    def post(self, request):
        serializer = AgentEnrollmentRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            agent, token = enroll_agent(
                payload["enrollment_code"],
                external_id=payload["external_id"].strip(),
                hostname=payload["hostname"].strip(),
                ip_address=payload.get("ip_address"),
                os_information=payload.get("os_information") or {},
                version=payload.get("version", "").strip(),
                audit_ip=client_ip(request),
            )
        except (KeyError, ValueError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response(
            {"agent_id": agent.pk, "machine_id": agent.machine_id, "token": token},
            status=201,
        )


def request_agent(request):
    authorization = request.headers.get("Authorization", "")
    raw = (
        authorization[7:]
        if authorization.startswith("Bearer ")
        else request.headers.get("X-Agent-Token", "")
    )
    raw = raw.strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{64}", raw):
        return None
    return authenticate_agent(raw)


class AgentHeartbeatView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AgentRequestThrottle]

    @extend_schema(
        tags=["Agents"],
        summary="Envoyer un heartbeat agent",
        description=(
            "Jeton agent requis dans X-Agent-Token ou Authorization: Bearer. "
            "Le jeton ne donne accès qu'à la machine enrôlée."
        ),
        auth=[{"agentToken": []}],
        request=AgentHeartbeatRequestSerializer,
        responses={
            200: AgentHeartbeatResponseSerializer,
            401: OpenApiResponse(
                ErrorResponseSerializer, "Jeton agent absent ou invalide."
            ),
            429: OpenApiResponse(
                ErrorResponseSerializer, "Limite de requêtes agent dépassée."
            ),
        },
        extensions={
            "x-permissions": ["ENROLLED_AGENT"],
            "x-tenant-scope": "agent-machine",
        },
    )
    def post(self, request):
        agent = request_agent(request)
        if not agent:
            return Response({"detail": "Token agent invalide."}, status=401)
        serializer = AgentHeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        version = serializer.validated_data.get("version", agent.version)
        was_online = agent.machine.status == Machine.Status.ONLINE
        now = timezone.now()
        Agent.objects.filter(pk=agent.pk).update(
            last_heartbeat=now, version=version
        )
        Machine.objects.filter(pk=agent.machine_id).update(
            status=Machine.Status.ONLINE,
            last_seen=now,
            agent_version=version,
        )
        if not was_online:
            from monitoring.alert_service import resolve_machine_alerts

            resolve_machine_alerts(agent.machine, "MACHINE_OFFLINE")
        if not was_online:
            publish(
                agent.customer,
                "machine.online",
                {
                    "machine_id": str(agent.machine_id),
                    "hostname": agent.machine.hostname,
                },
                agent.machine_id,
            )
        return Response(
            {
                "status": "ok",
                "server_time": now,
                "agent_id": agent.pk,
                "machine_id": agent.machine_id,
            }
        )


class AgentIngestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [AgentRequestThrottle]

    @extend_schema(
        tags=["Agents", "Metrics"],
        summary="Publier un lot de métriques agent",
        description=(
            "Jeton agent requis. Accepte 1 à 5000 métriques normalisables et refuse "
            "toute publication vers la machine d'un autre agent."
        ),
        auth=[{"agentToken": []}],
        request=AgentMetricBatchSerializer,
        responses={
            202: AgentMetricAcceptedSerializer,
            **VALIDATION_ERRORS,
            401: OpenApiResponse(
                ErrorResponseSerializer, "Jeton agent absent ou invalide."
            ),
            403: OpenApiResponse(
                ErrorResponseSerializer,
                "La machine demandée n'est pas celle de l'agent.",
            ),
            429: OpenApiResponse(
                ErrorResponseSerializer, "Limite de requêtes agent dépassée."
            ),
        },
        extensions={
            "x-permissions": ["ENROLLED_AGENT"],
            "x-tenant-scope": "agent-machine",
        },
    )
    def post(self, request):
        agent = request_agent(request)
        if not agent:
            return Response({"detail": "Token agent invalide."}, status=401)
        if str(request.data.get("machine_id", agent.machine_id)) != str(
            agent.machine_id
        ):
            return Response(
                {"detail": "Un agent ne peut publier que pour sa machine."}, status=403
            )
        serializer = AgentMetricBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data
        try:
            accepted = ingest_metrics(
                machine=agent.machine,
                source_type=agent.machine.source_type,
                items=payload["metrics"],
            )
        except (ValueError, serializers.ValidationError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"accepted": accepted}, status=202)


class RealtimeTicketView(APIView):
    @extend_schema(
        tags=["Realtime"],
        summary="Créer un ticket WebSocket à usage unique",
        description="JWT/session requis. Le ticket expire après 60 secondes et reste lié au tenant.",
        request=None,
        responses={200: RealtimeTicketResponseSerializer, **AUTH_ERRORS},
        extensions={"x-permissions": ["AUTHENTICATED"], "x-tenant-scope": "customer"},
    )
    def post(self, request):
        try:
            ticket = issue_ticket(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=403)
        return Response({"ticket": ticket, "expires_in": 60})


class RealtimeReplayView(APIView):
    @extend_schema(
        tags=["Realtime"],
        summary="Rejouer les événements manqués",
        description="JWT/session requis. Renvoie au plus 500 événements du tenant courant.",
        parameters=[
            OpenApiParameter(
                "since",
                int,
                OpenApiParameter.QUERY,
                required=False,
                default=0,
                description="Dernier numéro de séquence reçu, entier positif.",
            )
        ],
        responses={
            200: RealtimeEventSerializer(many=True),
            **VALIDATION_ERRORS,
            **AUTH_ERRORS,
        },
        extensions={"x-permissions": ["AUTHENTICATED"], "x-tenant-scope": "customer"},
    )
    def get(self, request):
        try:
            since = int(request.query_params.get("since", 0))
            if since < 0:
                raise ValueError
        except (TypeError, ValueError):
            return Response({"detail": "Curseur de replay invalide."}, status=400)
        qs = (
            tenant_queryset(request, RealtimeEvent.objects.all())
            .filter(sequence__gt=since)
            .order_by("sequence")[:500]
        )
        return Response(
            [
                {
                    "sequence": e.sequence,
                    "event_type": e.event_type,
                    "aggregate_id": e.aggregate_id,
                    "payload": e.payload,
                    "created_at": e.created_at,
                }
                for e in qs
            ]
        )


class IntegrationOverviewView(APIView):
    def get(self, request, source):
        source = source.upper()
        connectors = tenant_queryset(
            request, IntegrationEndpoint.objects.filter(kind=source)
        )
        assets = tenant_queryset(
            request, VirtualAsset.objects.filter(connector__kind=source)
        )
        return Response(
            {
                "source": source,
                "connectors": ConnectorSerializer(connectors, many=True).data,
                "hosts": VirtualAssetSerializer(
                    assets.filter(kind="HOST"), many=True
                ).data,
                "vms": VirtualAssetSerializer(assets.filter(kind="VM"), many=True).data,
                "datastores": VirtualAssetSerializer(
                    assets.filter(kind="DATASTORE"), many=True
                ).data,
                "partial": connectors.filter(last_error__gt="").exists(),
            }
        )


def integration_overview_schema(tag, technology):
    return extend_schema(
        tags=[tag],
        summary=f"Consulter l'inventaire {technology}",
        description=(
            "JWT/session requis. Inventaire réel découvert par les connecteurs du tenant; "
            "partial=true signale au moins une erreur de connecteur."
        ),
        responses={200: IntegrationOverviewResponseSerializer, **AUTH_ERRORS},
        extensions={
            "x-permissions": ["AUTHENTICATED"],
            "x-tenant-scope": "customer",
        },
    )


class VMwareOverviewView(IntegrationOverviewView):
    @integration_overview_schema("VMware", "VMware/vCenter")
    def get(self, request, source):
        return super().get(request, source)


class HyperVOverviewView(IntegrationOverviewView):
    @integration_overview_schema("Hyper-V", "Microsoft Hyper-V")
    def get(self, request, source):
        return super().get(request, source)
