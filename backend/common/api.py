import secrets
from django.contrib.auth.password_validation import validate_password
from django.core.validators import validate_ipv46_address
from django.db import IntegrityError, transaction
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
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
from notifications.models import NotificationDelivery, NotificationPreference
from realtime.models import RealtimeEvent
from realtime.publisher import publish
from realtime.tickets import issue_ticket
from .permissions import IsAdmin, ReadOnlyUnlessManager
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

    def perform_create(self, serializer):
        if not self.request.user.customer_id:
            raise serializers.ValidationError(
                "Le compte doit être associé à un client."
            )
        instance = serializer.save(customer=self.request.user.customer)
        AuditLog.objects.create(
            customer=self.request.user.customer,
            actor=self.request.user,
            action="CREATE",
            target_type=instance._meta.label,
            target_id=str(instance.pk),
        )

    def perform_update(self, serializer):
        instance = serializer.save()
        AuditLog.objects.create(
            customer=getattr(instance, "customer", self.request.user.customer),
            actor=self.request.user,
            action="UPDATE",
            target_type=instance._meta.label,
            target_id=str(instance.pk),
        )

    def perform_destroy(self, instance):
        AuditLog.objects.create(
            customer=getattr(instance, "customer", self.request.user.customer),
            actor=self.request.user,
            action="DELETE",
            target_type=instance._meta.label,
            target_id=str(instance.pk),
        )
        instance.delete()


class CustomerViewSet(viewsets.ModelViewSet):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        if self.request.user.is_superuser:
            return self.queryset
        return self.queryset.filter(pk=self.request.user.customer_id)


class UserViewSet(TenantViewSet):
    queryset = User.objects.select_related("customer").all()
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]


class EnvironmentViewSet(TenantViewSet):
    queryset = Environment.objects.all()
    serializer_class = EnvironmentSerializer

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
        AuditLog.objects.create(
            customer=environment.customer,
            actor=request.user,
            action="AGENT_ENROLLMENT_CODE_CREATED",
            target_type=environment._meta.label,
            target_id=str(environment.pk),
            context={"ttl_minutes": ttl_minutes},
        )
        return Response(
            {
                "enrollment_code": raw,
                "expires_in_minutes": ttl_minutes,
            },
            status=201,
        )


class MachineViewSet(TenantViewSet):
    queryset = Machine.objects.select_related("environment").order_by("hostname")
    serializer_class = MachineSerializer

    @action(detail=True, methods=["get"])
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


class AgentViewSet(TenantViewSet):
    queryset = Agent.objects.select_related("machine").all()
    serializer_class = AgentSerializer
    http_method_names = ["get", "patch", "head", "options"]


class ConnectorViewSet(TenantViewSet):
    queryset = IntegrationEndpoint.objects.select_related("environment").all()
    serializer_class = ConnectorSerializer

    @action(detail=True, methods=["post"])
    def collect(self, _request, pk=None):
        connector = self.get_object()
        task = (
            collect_vmware_connector.delay(str(connector.pk))
            if connector.kind == IntegrationEndpoint.Kind.VMWARE
            else collect_hyperv_connector.delay(str(connector.pk))
        )
        AuditLog.objects.create(
            customer=connector.customer,
            actor=_request.user,
            action="CONNECTOR_COLLECTION_QUEUED",
            target_type=connector._meta.label,
            target_id=str(connector.pk),
            context={"task_id": task.id, "kind": connector.kind},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)


class VirtualAssetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = VirtualAsset.objects.select_related("connector", "machine").all()
    serializer_class = VirtualAssetSerializer

    def get_queryset(self):
        qs = tenant_queryset(self.request, self.queryset)
        if self.request.query_params.get("kind"):
            qs = qs.filter(kind=self.request.query_params["kind"])
        if self.request.query_params.get("source"):
            qs = qs.filter(connector__kind=self.request.query_params["source"])
        return qs


class MetricViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NormalizedMetric.objects.select_related("machine", "environment").all()
    serializer_class = MetricSerializer

    def get_queryset(self):
        qs = tenant_queryset(self.request, self.queryset)
        for key in ("machine", "metric_name", "source_type"):
            if self.request.query_params.get(key):
                qs = qs.filter(**{key: self.request.query_params[key]})
        return qs


class MetricAggregateViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MetricAggregate.objects.select_related("machine").all()
    serializer_class = MetricAggregateSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "machine__customer")


class RuleViewSet(TenantViewSet):
    queryset = MonitoringRule.objects.select_related("machine", "environment").all()
    serializer_class = RuleSerializer

    @action(detail=True, methods=["post"])
    def toggle(self, _request, pk=None):
        rule = self.get_object()
        rule.enabled = not rule.enabled
        rule.save(update_fields=["enabled", "updated_at"])
        AuditLog.objects.create(
            customer=rule.customer,
            actor=_request.user,
            action="MONITORING_RULE_TOGGLED",
            target_type=rule._meta.label,
            target_id=str(rule.pk),
            context={"enabled": rule.enabled},
        )
        return Response(self.get_serializer(rule).data)


class AlertViewSet(TenantViewSet):
    queryset = Alert.objects.select_related(
        "machine", "structured_recommendation"
    ).all()
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


class AnomalyViewSet(TenantViewSet):
    queryset = Anomaly.objects.select_related("machine").all()
    serializer_class = AnomalySerializer
    http_method_names = ["get", "patch", "head", "options"]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("machine"):
            qs = qs.filter(machine_id=self.request.query_params["machine"])
        return qs


class MLModelViewSet(TenantViewSet):
    queryset = MLModelVersion.objects.all()
    serializer_class = MLModelSerializer
    http_method_names = ["get", "patch", "head", "options"]

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
        AuditLog.objects.create(
            customer=request.user.customer,
            actor=request.user,
            action="ML_TRAINING_QUEUED",
            target_type="ml_engine.MLModelVersion",
            context={"task_id": task.id, "days": days},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)

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
        AuditLog.objects.create(
            customer=request.user.customer,
            actor=request.user,
            action="ML_EVALUATION_QUEUED",
            target_type="ml_engine.MLModelVersion",
            context={"task_id": task.id, "days": days},
        )
        return Response({"task_id": task.id, "status": "queued"}, status=202)


class NotificationPreferenceViewSet(TenantViewSet):
    queryset = NotificationPreference.objects.all()
    serializer_class = NotificationPreferenceSerializer


class NotificationDeliveryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = NotificationDelivery.objects.select_related("event", "preference").all()
    serializer_class = NotificationDeliverySerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "event__customer")


class CollectionRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CollectionRun.objects.select_related("connector").all()
    serializer_class = CollectionRunSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset, "connector__customer")


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset)


class TaskRunViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = TaskRun.objects.order_by("-started_at", "-pk")
    serializer_class = TaskRunSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset)


class ReportViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = GeneratedReport.objects.all()
    serializer_class = ReportSerializer

    def get_queryset(self):
        return tenant_queryset(self.request, self.queryset)

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

    def get(self, _request):
        return Response({"status": "ok", "version": "2.0.0", "time": timezone.now()})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @transaction.atomic
    def post(self, request):
        try:
            email = serializers.EmailField().run_validation(request.data.get("email"))
        except serializers.ValidationError:
            return Response({"detail": "Adresse email invalide."}, status=400)
        email = email.strip().lower()
        password = request.data.get("password", "")
        organization = str(request.data.get("organization", "")).strip()
        if not email or len(password) < 10 or not organization:
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
            return Response({"detail": "Cette adresse email existe déjà."}, status=400)
        environment = Environment.objects.create(
            customer=customer, name="Windows", kind=Environment.Kind.WINDOWS
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
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class DashboardView(APIView):
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_ingest"

    def post(self, request):
        external_id = str(request.data.get("external_id", "")).strip()
        hostname = str(request.data.get("hostname", "")).strip()
        version = str(request.data.get("version", "")).strip()
        os_information = request.data.get("os_information") or {}
        ip_address = request.data.get("ip_address")
        if not external_id or len(external_id) > 255:
            return Response({"detail": "Identité agent invalide."}, status=400)
        if not hostname or len(hostname) > 255:
            return Response({"detail": "Hostname agent invalide."}, status=400)
        if len(version) > 40 or not isinstance(os_information, dict):
            return Response({"detail": "Métadonnées agent invalides."}, status=400)
        if ip_address:
            try:
                validate_ipv46_address(ip_address)
            except DjangoValidationError:
                return Response({"detail": "Adresse IP invalide."}, status=400)
        try:
            agent, token = enroll_agent(
                request.data.get("enrollment_code", ""),
                external_id=external_id,
                hostname=hostname,
                ip_address=ip_address,
                os_information=os_information,
                version=version,
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
    return authenticate_agent(raw)


class AgentHeartbeatView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_ingest"

    def post(self, request):
        agent = request_agent(request)
        if not agent:
            return Response({"detail": "Token agent invalide."}, status=401)
        was_online = agent.machine.status == Machine.Status.ONLINE
        now = timezone.now()
        Agent.objects.filter(pk=agent.pk).update(
            last_heartbeat=now, version=request.data.get("version", agent.version)
        )
        Machine.objects.filter(pk=agent.machine_id).update(
            status=Machine.Status.ONLINE,
            last_seen=now,
            agent_version=request.data.get("version", agent.version),
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
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "agent_ingest"

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
        try:
            accepted = ingest_metrics(
                machine=agent.machine,
                source_type=agent.machine.source_type,
                items=request.data.get("metrics"),
            )
        except (ValueError, serializers.ValidationError, DjangoValidationError) as exc:
            return Response({"detail": str(exc)}, status=400)
        return Response({"accepted": accepted}, status=202)


class RealtimeTicketView(APIView):
    def post(self, request):
        try:
            ticket = issue_ticket(request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=403)
        return Response({"ticket": ticket, "expires_in": 60})


class RealtimeReplayView(APIView):
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
