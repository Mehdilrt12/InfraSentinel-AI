from django.contrib.auth.password_validation import validate_password
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
        write_only=True, required=False, validators=[validate_password]
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
            "password",
        ]
        read_only_fields = ["id", "customer"]

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
            if field.name not in {"active", "customer", "artifact_path"}
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
    class Meta:
        model = AuditLog
        fields = "__all__"
        read_only_fields = [field.name for field in AuditLog._meta.fields]


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
