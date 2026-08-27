from drf_spectacular.utils import (
    OpenApiParameter,
    OpenApiResponse,
    extend_schema,
    extend_schema_view,
)
from rest_framework import serializers


class ErrorResponseSerializer(serializers.Serializer):
    detail = serializers.JSONField(
        help_text="Message ou objet de validation renvoyé par Django REST Framework."
    )


class HealthResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    version = serializers.CharField()
    time = serializers.DateTimeField()
    components = serializers.DictField(child=serializers.CharField())


class RegistrationRequestSerializer(serializers.Serializer):
    organization = serializers.CharField(max_length=160)
    email = serializers.EmailField()
    password = serializers.CharField(
        min_length=10, max_length=128, write_only=True, trim_whitespace=False
    )


class RegistrationResponseSerializer(serializers.Serializer):
    user_id = serializers.IntegerField()
    customer_id = serializers.UUIDField()
    environment_id = serializers.UUIDField()


class DashboardResponseSerializer(serializers.Serializer):
    total_assets = serializers.IntegerField()
    online = serializers.IntegerField()
    offline = serializers.IntegerField()
    critical = serializers.IntegerField()
    warning = serializers.IntegerField()
    anomalies = serializers.IntegerField()
    vmware_hosts = serializers.IntegerField()
    hyperv_hosts = serializers.IntegerField()
    active_alerts = serializers.IntegerField()


class EnrollmentCodeRequestSerializer(serializers.Serializer):
    ttl_minutes = serializers.IntegerField(min_value=1, max_value=1440, default=30)


class EnrollmentCodeResponseSerializer(serializers.Serializer):
    enrollment_code = serializers.CharField(
        help_text="Secret à transmettre à l'agent; il n'est plus affiché ensuite."
    )
    expires_in_minutes = serializers.IntegerField()


class AgentEnrollmentRequestSerializer(serializers.Serializer):
    enrollment_code = serializers.CharField(max_length=128, write_only=True)
    external_id = serializers.CharField(max_length=255)
    hostname = serializers.CharField(max_length=255)
    ip_address = serializers.IPAddressField(required=False, allow_null=True)
    os_information = serializers.JSONField(required=False, default=dict)
    version = serializers.CharField(max_length=40, required=False, allow_blank=True)


class AgentEnrollmentResponseSerializer(serializers.Serializer):
    agent_id = serializers.UUIDField()
    machine_id = serializers.UUIDField()
    token = serializers.CharField(
        help_text="Jeton opaque affiché une seule fois; à stocker comme secret."
    )


class AgentHeartbeatRequestSerializer(serializers.Serializer):
    version = serializers.CharField(max_length=40, required=False, allow_blank=True)


class AgentHeartbeatResponseSerializer(serializers.Serializer):
    status = serializers.CharField()
    server_time = serializers.DateTimeField()
    agent_id = serializers.UUIDField()
    machine_id = serializers.UUIDField()


class AgentMetricItemSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField(required=False)
    metric_name = serializers.CharField(max_length=120, required=False)
    name = serializers.CharField(max_length=120, required=False)
    metric_value = serializers.FloatField(required=False, allow_null=True)
    value = serializers.FloatField(required=False, allow_null=True)
    unit = serializers.CharField(max_length=32, required=False, allow_blank=True)
    status = serializers.CharField(max_length=32, required=False, allow_blank=True)
    metadata = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=128)


class AgentMetricBatchSerializer(serializers.Serializer):
    machine_id = serializers.UUIDField(required=False)
    metrics = AgentMetricItemSerializer(many=True, min_length=1, max_length=5000)


class AgentMetricAcceptedSerializer(serializers.Serializer):
    accepted = serializers.IntegerField(min_value=0)


class TaskRequestSerializer(serializers.Serializer):
    days = serializers.IntegerField(min_value=1, max_value=3650, default=30)
    idempotency_key = serializers.CharField(max_length=255, required=False)


class ReportRequestSerializer(serializers.Serializer):
    kind = serializers.CharField(max_length=80, default="summary")
    idempotency_key = serializers.CharField(max_length=255, required=False)


class TaskQueuedResponseSerializer(serializers.Serializer):
    task_id = serializers.CharField()
    status = serializers.ChoiceField(choices=["queued"])


class PredictionSerializer(serializers.Serializer):
    metric_name = serializers.CharField()
    unit = serializers.CharField(allow_blank=True)
    sample_count = serializers.IntegerField()
    window_hours = serializers.IntegerField()
    last_value = serializers.FloatField()
    rolling_average = serializers.FloatField()
    rate_of_change_per_hour = serializers.FloatField()
    trend = serializers.ChoiceField(choices=["INCREASING", "DECREASING", "STABLE"])
    risk_score = serializers.IntegerField(min_value=0, max_value=100)
    rule_id = serializers.UUIDField(allow_null=True)
    threshold = serializers.FloatField(allow_null=True)
    estimated_threshold_breach_at = serializers.DateTimeField(allow_null=True)
    already_breached = serializers.BooleanField()
    confidence = serializers.ChoiceField(choices=["LOW", "MEDIUM", "HIGH"])
    is_estimate = serializers.BooleanField()
    disclaimer = serializers.CharField()


class RealtimeTicketResponseSerializer(serializers.Serializer):
    ticket = serializers.CharField(
        help_text="Ticket opaque à usage unique; ne doit pas être journalisé."
    )
    expires_in = serializers.IntegerField()


class RealtimeEventSerializer(serializers.Serializer):
    sequence = serializers.IntegerField()
    event_type = serializers.CharField()
    aggregate_id = serializers.CharField(allow_blank=True)
    payload = serializers.JSONField()
    created_at = serializers.DateTimeField()


class IntegrationOverviewResponseSerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=["VMWARE", "HYPERV"])
    connectors = serializers.ListField(child=serializers.DictField())
    hosts = serializers.ListField(child=serializers.DictField())
    vms = serializers.ListField(child=serializers.DictField())
    datastores = serializers.ListField(child=serializers.DictField())
    partial = serializers.BooleanField()


TENANT_FILTER = OpenApiParameter(
    "customer",
    type={"type": "string", "format": "uuid"},
    location=OpenApiParameter.QUERY,
    required=False,
    description="Filtre réservé au superutilisateur; ignoré pour les autres comptes.",
)


def _response(code, description):
    return OpenApiResponse(ErrorResponseSerializer, description)


AUTH_ERRORS = {
    401: _response(401, "JWT/session absent ou invalide."),
    403: _response(403, "Rôle insuffisant ou ressource hors tenant."),
    429: _response(429, "Limite de requêtes dépassée."),
}
VALIDATION_ERRORS = {400: _response(400, "Corps ou paramètres invalides.")}
NOT_FOUND_ERROR = {404: _response(404, "Ressource inexistante dans le tenant courant.")}


def crud_schema(
    tag,
    resource,
    serializer,
    *,
    permissions,
    read_permissions=None,
    tenant=True,
    tenant_filter=True,
    list_parameters=None,
):
    read_permissions = read_permissions or ["AUTHENTICATED"]
    read_extension = {
        "x-permissions": read_permissions,
        "x-tenant-scope": "customer" if tenant else "global",
    }
    write_extension = {
        "x-permissions": permissions,
        "x-tenant-scope": "customer" if tenant else "global",
    }
    auth = "JWT Bearer ou session Django requis."
    write = ", ".join(permissions)
    return extend_schema_view(
        list=extend_schema(
            tags=[tag],
            summary=f"Lister les {resource}",
            description=f"{auth} Lecture: utilisateur authentifié; écritures: {write}.",
            parameters=(
                ([TENANT_FILTER] if tenant and tenant_filter else [])
                + list(list_parameters or [])
            ),
            responses={200: serializer, **AUTH_ERRORS},
            extensions=read_extension,
        ),
        retrieve=extend_schema(
            tags=[tag],
            summary=f"Consulter un élément de {resource}",
            description=f"{auth} Isolation par client appliquée côté serveur.",
            responses={200: serializer, **AUTH_ERRORS, **NOT_FOUND_ERROR},
            extensions=read_extension,
        ),
        create=extend_schema(
            tags=[tag],
            summary=f"Créer un élément de {resource}",
            description=f"{auth} Rôles autorisés: {write}.",
            request=serializer,
            responses={201: serializer, **VALIDATION_ERRORS, **AUTH_ERRORS},
            extensions=write_extension,
        ),
        update=extend_schema(
            tags=[tag],
            summary=f"Remplacer un élément de {resource}",
            description=f"{auth} Rôles autorisés: {write}.",
            request=serializer,
            responses={
                200: serializer,
                **VALIDATION_ERRORS,
                **AUTH_ERRORS,
                **NOT_FOUND_ERROR,
            },
            extensions=write_extension,
        ),
        partial_update=extend_schema(
            tags=[tag],
            summary=f"Modifier un élément de {resource}",
            description=f"{auth} Rôles autorisés: {write}.",
            request=serializer,
            responses={
                200: serializer,
                **VALIDATION_ERRORS,
                **AUTH_ERRORS,
                **NOT_FOUND_ERROR,
            },
            extensions=write_extension,
        ),
        destroy=extend_schema(
            tags=[tag],
            summary=f"Supprimer un élément de {resource}",
            description=f"{auth} Rôles autorisés: {write}.",
            responses={204: None, **AUTH_ERRORS, **NOT_FOUND_ERROR},
            extensions=write_extension,
        ),
    )


def readonly_schema(
    tag,
    resource,
    serializer,
    *,
    permissions=None,
    tenant=True,
    tenant_filter=True,
    list_parameters=None,
    list_validation=False,
):
    permissions = permissions or ["AUTHENTICATED"]
    extension = {
        "x-permissions": permissions,
        "x-tenant-scope": "customer" if tenant else "global",
    }
    return extend_schema_view(
        list=extend_schema(
            tags=[tag],
            summary=f"Lister les {resource}",
            description="JWT Bearer ou session Django requis. Endpoint en lecture seule.",
            parameters=(
                ([TENANT_FILTER] if tenant and tenant_filter else [])
                + list(list_parameters or [])
            ),
            responses={
                200: serializer,
                **(VALIDATION_ERRORS if list_validation else {}),
                **AUTH_ERRORS,
            },
            extensions=extension,
        ),
        retrieve=extend_schema(
            tags=[tag],
            summary=f"Consulter un élément de {resource}",
            description="JWT Bearer ou session Django requis. Endpoint en lecture seule.",
            responses={200: serializer, **AUTH_ERRORS, **NOT_FOUND_ERROR},
            extensions=extension,
        ),
    )


def read_patch_schema(tag, resource, serializer, *, permissions, list_parameters=None):
    read_extension = {
        "x-permissions": ["AUTHENTICATED"],
        "x-tenant-scope": "customer",
    }
    write_extension = {
        "x-permissions": permissions,
        "x-tenant-scope": "customer",
    }
    write = ", ".join(permissions)
    return extend_schema_view(
        list=extend_schema(
            tags=[tag],
            summary=f"Lister les {resource}",
            description="JWT Bearer ou session Django requis. Données limitées au client courant.",
            parameters=[TENANT_FILTER] + list(list_parameters or []),
            responses={200: serializer, **AUTH_ERRORS},
            extensions=read_extension,
        ),
        retrieve=extend_schema(
            tags=[tag],
            summary=f"Consulter un élément de {resource}",
            description=(
                "JWT Bearer ou session Django requis. La ressource doit appartenir "
                "au client courant."
            ),
            responses={200: serializer, **AUTH_ERRORS, **NOT_FOUND_ERROR},
            extensions=read_extension,
        ),
        partial_update=extend_schema(
            tags=[tag],
            summary=f"Modifier l'état d'un élément de {resource}",
            description=f"JWT Bearer ou session requis. Rôles autorisés: {write}.",
            request=serializer,
            responses={
                200: serializer,
                **VALIDATION_ERRORS,
                **AUTH_ERRORS,
                **NOT_FOUND_ERROR,
            },
            extensions=write_extension,
        ),
    )
