import uuid
from django.db import models
from accounts.models import Customer


class Environment(models.Model):
    class Kind(models.TextChoices):
        WINDOWS = "WINDOWS", "Windows"
        VMWARE = "VMWARE", "VMware"
        HYPERV = "HYPERV", "Hyper-V"
        MIXED = "MIXED", "Mixte"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="environments"
    )
    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "name"], name="uniq_environment_customer_name"
            )
        ]


class Machine(models.Model):
    class Status(models.TextChoices):
        ONLINE = "ONLINE", "En ligne"
        OFFLINE = "OFFLINE", "Hors ligne"
        UNKNOWN = "UNKNOWN", "Inconnu"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="machines"
    )
    environment = models.ForeignKey(
        Environment, on_delete=models.PROTECT, related_name="machines"
    )
    source_type = models.CharField(max_length=16, choices=Environment.Kind.choices)
    external_id = models.CharField(max_length=255)
    hostname = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    os_information = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.UNKNOWN, db_index=True
    )
    last_seen = models.DateTimeField(null=True, blank=True, db_index=True)
    agent_version = models.CharField(max_length=40, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "source_type", "external_id"],
                name="uniq_machine_source_external",
            )
        ]
        indexes = [
            models.Index(fields=["customer", "status"]),
            models.Index(fields=["environment", "hostname"]),
        ]


class EnrollmentCode(models.Model):
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="enrollment_codes"
    )
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name="enrollment_codes"
    )
    code_hash = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class Agent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="agents"
    )
    machine = models.OneToOneField(
        Machine, on_delete=models.CASCADE, related_name="agent"
    )
    token_hash = models.CharField(max_length=64, unique=True)
    enabled = models.BooleanField(default=True)
    version = models.CharField(max_length=40, blank=True)
    last_heartbeat = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class IntegrationEndpoint(models.Model):
    class Kind(models.TextChoices):
        VMWARE = "VMWARE", "VMware/vCenter"
        HYPERV = "HYPERV", "Microsoft Hyper-V"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="connectors"
    )
    environment = models.ForeignKey(
        Environment, on_delete=models.CASCADE, related_name="connectors"
    )
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=160)
    endpoint = models.CharField(max_length=500)
    username = models.CharField(max_length=255, blank=True)
    secret_ref = models.CharField(
        max_length=255, help_text="Variable d'environnement ou référence de coffre"
    )
    verify_tls = models.BooleanField(default=True)
    timeout_seconds = models.PositiveIntegerField(default=30)
    enabled = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    last_sync_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "kind", "name"],
                name="uniq_connector_customer_kind_name",
            )
        ]


class VirtualAsset(models.Model):
    class Kind(models.TextChoices):
        HOST = "HOST", "Hôte"
        VM = "VM", "Machine virtuelle"
        DATASTORE = "DATASTORE", "Datastore"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="virtual_assets"
    )
    connector = models.ForeignKey(
        IntegrationEndpoint, on_delete=models.CASCADE, related_name="assets"
    )
    machine = models.OneToOneField(
        Machine,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="virtual_asset",
    )
    external_id = models.CharField(max_length=255)
    parent_external_id = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    name = models.CharField(max_length=255)
    state = models.CharField(max_length=80, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    last_seen = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["connector", "external_id"],
                name="uniq_asset_connector_external",
            )
        ]
        indexes = [models.Index(fields=["customer", "kind"])]
