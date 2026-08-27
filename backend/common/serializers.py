import ipaddress
import json
import re
from urllib.parse import urlparse
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers
from accounts.models import Customer, User
from async_tasks.models import GeneratedReport, TaskRun
from integrations.models import CollectionRun
from inventory.models import (
    Agent,
    Environment,
    IntegrationEndpoint,
    Machine,
    VirtualAsset,
)
from metrics.models import MetricAggregate, NormalizedMetric
from ml_engine.models import MLModelVersion
from monitoring.models import Alert, Anomaly, AuditLog, MonitoringRule, Recommendation
from notifications.models import NotificationDelivery, NotificationPreference


class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = "__all__"
        read_only_fields = ["id", "created_at", "updated_at"]


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
        required=False,
        max_length=128,
        trim_whitespace=False,
        validators=[validate_password],
    )

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "username",
            "first_name",
            "last_name",
            "role",
            "customer",
            "is_active",
            "is_superuser",
            "password",
        ]
        read_only_fields = ["id", "customer", "is_superuser"]

    def validate_email(self, value):
        value = value.strip().lower()
        existing = User.objects.filter(email=value)
        if self.instance:
            existing = existing.exclude(pk=self.instance.pk)
        if existing.exists():
            raise serializers.ValidationError("Cette adresse email existe déjà.")
        return value

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        if not password:
            raise serializers.ValidationError({"password": "Ce champ est obligatoire."})
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        instance = super().update(instance, validated_data)
        if password:
            instance.set_password(password)
            instance.save(update_fields=["password"])
        return instance


class EnvironmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Environment
        exclude = ["customer"]
        read_only_fields = ["id", "created_at"]


class TenantRelationSerializer(serializers.ModelSerializer):
    tenant_relation_fields = ()

    def validate(self, attrs):
        attrs = super().validate(attrs)
        user = self.context["request"].user
        if user.is_superuser:
            return attrs
        for field in self.tenant_relation_fields:
            value = attrs.get(field) or getattr(self.instance, field, None)
            if value and value.customer_id != user.customer_id:
                raise serializers.ValidationError(
                    {field: "La ressource appartient à un autre client."}
                )
        return attrs


class MachineSerializer(TenantRelationSerializer):
    tenant_relation_fields = ("environment",)

    class Meta:
        model = Machine
        exclude = ["customer"]
        read_only_fields = ["id", "created_at", "updated_at", "last_seen"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        environment = attrs.get("environment") or getattr(
            self.instance, "environment", None
        )
        source_type = attrs.get("source_type") or getattr(
            self.instance, "source_type", None
        )
        if environment and environment.kind not in {
            source_type,
            Environment.Kind.MIXED,
        }:
            raise serializers.ValidationError(
                {"source_type": "La source ne correspond pas à l'environnement."}
            )
        return attrs


class AgentSerializer(serializers.ModelSerializer):
    hostname = serializers.CharField(source="machine.hostname", read_only=True)

    class Meta:
        model = Agent
        exclude = ["token_hash", "customer"]
        read_only_fields = ["id", "machine", "last_heartbeat", "created_at", "hostname"]


class ConnectorSerializer(TenantRelationSerializer):
    tenant_relation_fields = ("environment",)

    class Meta:
        model = IntegrationEndpoint
        exclude = ["customer"]
        extra_kwargs = {"secret_ref": {"write_only": True}}
        read_only_fields = ["id", "last_sync_at", "last_error", "created_at"]

    def validate_secret_ref(self, value):
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{7,254}", value):
            raise serializers.ValidationError(
                "Référence invalide; utilisez uniquement une variable d'environnement dédiée."
            )
        user = self.context["request"].user
        allowed = ("INFRASENTINEL_CONNECTOR_", "INFRASENTINEL_CUSTOMER_")
        if user.is_superuser:
            if not value.startswith(allowed):
                raise serializers.ValidationError(
                    "La variable doit utiliser un préfixe InfraSentinel dédié."
                )
        else:
            expected = f"INFRASENTINEL_CUSTOMER_{user.customer_id.hex.upper()}_"
            if not value.startswith(expected):
                raise serializers.ValidationError(
                    f"La variable doit commencer par {expected}."
                )
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        kind = attrs.get("kind") or getattr(self.instance, "kind", None)
        environment = attrs.get("environment") or getattr(
            self.instance, "environment", None
        )
        endpoint = str(
            attrs.get("endpoint") or getattr(self.instance, "endpoint", "")
        ).strip()
        timeout = attrs.get(
            "timeout_seconds", getattr(self.instance, "timeout_seconds", 30)
        )
        verify_tls = attrs.get(
            "verify_tls", getattr(self.instance, "verify_tls", True)
        )
        if environment and environment.kind not in {kind, Environment.Kind.MIXED}:
            raise serializers.ValidationError(
                {
                    "environment": "Le type d'environnement ne correspond pas au connecteur."
                }
            )
        if not 1 <= timeout <= 300:
            raise serializers.ValidationError(
                {
                    "timeout_seconds": "Le timeout doit être compris entre 1 et 300 secondes."
                }
            )
        if kind == IntegrationEndpoint.Kind.VMWARE:
            parsed = urlparse(endpoint)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise serializers.ValidationError(
                    {
                        "endpoint": "Une URL vCenter HTTPS sans identifiants, paramètres ni fragment est obligatoire."
                    }
                )
            self._validate_target(parsed.hostname)
            if not verify_tls and not settings.ALLOW_INSECURE_CONNECTOR_TLS:
                raise serializers.ValidationError(
                    {
                        "verify_tls": "La désactivation TLS doit être autorisée explicitement côté serveur."
                    }
                )
        elif kind == IntegrationEndpoint.Kind.HYPERV and (
            not endpoint
            or "://" in endpoint
            or not re.fullmatch(r"[A-Za-z0-9_.:\-\[\]]+", endpoint)
        ):
            raise serializers.ValidationError(
                {"endpoint": "Utilisez un nom DNS ou une adresse d'hôte Hyper-V."}
            )
        elif kind == IntegrationEndpoint.Kind.HYPERV:
            self._validate_target(endpoint)
        config = attrs.get("config", getattr(self.instance, "config", {}))
        self._validate_public_config(config)
        attrs["endpoint"] = endpoint
        return attrs

    @staticmethod
    def _validate_target(host):
        normalized = str(host).strip().rstrip(".").lower()
        if normalized in {"localhost", "localhost.localdomain"}:
            raise serializers.ValidationError(
                {"endpoint": "Les cibles loopback sont interdites."}
            )
        try:
            address = ipaddress.ip_address(normalized.strip("[]"))
        except ValueError:
            address = None
        if address and (
            address.is_loopback
            or address.is_link_local
            or address.is_multicast
            or address.is_unspecified
        ):
            raise serializers.ValidationError(
                {"endpoint": "Cette classe d'adresse réseau est interdite."}
            )
        allowed = settings.CONNECTOR_ALLOWED_HOSTS
        if allowed and not any(
            normalized == item.lower().rstrip(".")
            or (
                item.startswith("*.")
                and normalized.endswith(item[1:].lower().rstrip("."))
            )
            for item in allowed
        ):
            raise serializers.ValidationError(
                {"endpoint": "La cible n'appartient pas à l'allowlist des connecteurs."}
            )

    @classmethod
    def _validate_public_config(cls, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError({"config": "Un objet JSON est attendu."})
        if len(json.dumps(value, separators=(",", ":"), ensure_ascii=False)) > 16_384:
            raise serializers.ValidationError({"config": "Configuration trop volumineuse."})
        forbidden = re.compile(r"(?i)(password|passwd|secret|token|credential|api.?key)")

        def walk(item, depth=0):
            if depth > 8:
                raise serializers.ValidationError(
                    {"config": "Imbrication JSON excessive."}
                )
            if isinstance(item, dict):
                for key, nested in item.items():
                    if forbidden.search(str(key)):
                        raise serializers.ValidationError(
                            {
                                "config": "Aucun secret ne doit être stocké dans config; utilisez secret_ref."
                            }
                        )
                    walk(nested, depth + 1)
            elif isinstance(item, list):
                for nested in item:
                    walk(nested, depth + 1)

        walk(value)


class VirtualAssetSerializer(serializers.ModelSerializer):
    class Meta:
        model = VirtualAsset
        exclude = ["customer"]
        read_only_fields = [
            field.name
            for field in VirtualAsset._meta.fields
            if field.name != "customer"
        ]


class MetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = NormalizedMetric
        exclude = ["customer"]
        read_only_fields = [
            field.name
            for field in NormalizedMetric._meta.fields
            if field.name != "customer"
        ]


class MetricAggregateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetricAggregate
        fields = "__all__"
        read_only_fields = [field.name for field in MetricAggregate._meta.fields]


class RuleSerializer(TenantRelationSerializer):
    tenant_relation_fields = ("environment", "machine")

    class Meta:
        model = MonitoringRule
        exclude = ["customer"]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        environment = attrs.get("environment") or getattr(
            self.instance, "environment", None
        )
        machine = attrs.get("machine") or getattr(self.instance, "machine", None)
        metric = attrs.get("metric") or getattr(self.instance, "metric", "")
        operator = attrs.get("operator") or getattr(self.instance, "operator", "")
        threshold = attrs.get("threshold", getattr(self.instance, "threshold", None))
        if machine and environment and machine.environment_id != environment.pk:
            raise serializers.ValidationError(
                {"machine": "La machine n'appartient pas à cet environnement."}
            )
        if metric == "machine.online" and not (operator == "==" and threshold == 0):
            raise serializers.ValidationError(
                {
                    "metric": "Une règle offline doit utiliser machine.online == 0; la durée porte le délai d'indisponibilité."
                }
            )
        return attrs


class RecommendationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Recommendation
        fields = "__all__"


class AlertSerializer(serializers.ModelSerializer):
    structured_recommendation = RecommendationSerializer(read_only=True)
    hostname = serializers.CharField(source="machine.hostname", read_only=True)

    class Meta:
        model = Alert
        exclude = ["customer"]
        read_only_fields = [
            "id",
            "machine",
            "timestamp",
            "updated_at",
            "type",
            "severity",
            "source",
            "message",
            "context",
            "anomaly_score",
            "recommendation",
            "dedup_key",
            "first_seen_at",
            "last_seen_at",
            "occurrences",
            "escalation_level",
            "hostname",
        ]


class AnomalySerializer(serializers.ModelSerializer):
    hostname = serializers.CharField(source="machine.hostname", read_only=True)

    class Meta:
        model = Anomaly
        exclude = ["customer"]
        read_only_fields = [
            field.name
            for field in Anomaly._meta.fields
            if field.name not in {"acknowledged", "customer"}
        ]


class MLModelSerializer(serializers.ModelSerializer):
    class Meta:
        model = MLModelVersion
        exclude = ["customer", "artifact_path"]
        read_only_fields = [
            field.name
            for field in MLModelVersion._meta.fields
            if field.name not in {"customer", "artifact_path"}
        ]


class NotificationPreferenceSerializer(TenantRelationSerializer):
    tenant_relation_fields = ("user",)

    class Meta:
        model = NotificationPreference
        exclude = ["customer"]
        read_only_fields = ["id", "created_at", "updated_at"]


class NotificationDeliverySerializer(serializers.ModelSerializer):
    class Meta:
        model = NotificationDelivery
        fields = "__all__"
        read_only_fields = [field.name for field in NotificationDelivery._meta.fields]


class CollectionRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = CollectionRun
        fields = "__all__"
        read_only_fields = [field.name for field in CollectionRun._meta.fields]


class AuditLogSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    timestamp = serializers.DateTimeField(read_only=True)
    created_at = serializers.DateTimeField(source="timestamp", read_only=True)
    context = serializers.JSONField(source="metadata", read_only=True)
    target = serializers.SerializerMethodField()

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "customer",
            "customer_name",
            "actor",
            "actor_email",
            "action",
            "target",
            "target_type",
            "target_id",
            "target_repr",
            "timestamp",
            "created_at",
            "ip_address",
            "metadata",
            "context",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.DictField(child=serializers.CharField()))
    def get_target(self, obj):
        return {
            "type": obj.target_type,
            "id": obj.target_id,
            "repr": obj.target_repr,
        }


class TaskRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaskRun
        fields = "__all__"
        read_only_fields = [field.name for field in TaskRun._meta.fields]


class ReportSerializer(serializers.ModelSerializer):
    class Meta:
        model = GeneratedReport
        exclude = ["customer"]
        read_only_fields = [
            field.name
            for field in GeneratedReport._meta.fields
            if field.name != "customer"
        ]
