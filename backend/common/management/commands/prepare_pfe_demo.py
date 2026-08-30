import hashlib
import json
import math
import os
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from accounts.models import Customer, User
from inventory.models import Agent, Environment, IntegrationEndpoint, Machine, VirtualAsset
from metrics.models import NormalizedMetric
from ml_engine.models import MLModelVersion
from ml_engine.pipeline import MODEL_DIR, infer_customer, train_customer_model
from ml_engine.predictive import analyze_machine_trends
from monitoring.engine import evaluate_metric, evaluate_offline_machines
from monitoring.models import Alert, Anomaly, MonitoringRule
from notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)
from notifications.services import deliver_notification


DEMO_SUITE = "PFE25"
DEMO_PREFIX = "[PFE DEMO]"
DEMO_USER_PREFIX = "pfe25_"
ISOLATED_CUSTOMER_SLUG = "pfe-demo-isolated"
DEMO_EMAIL_DOMAIN = "demo.invalid"
DEMO_DATA_CLASSIFICATION = "SYNTHETIC_DEMO"
CONSOLE_EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
ML_FEATURES = (
    "system.cpu.utilization",
    "system.memory.utilization",
    "system.disk.utilization",
    "system.network.in",
    "system.network.out",
    "system.network.latency",
)


class Command(BaseCommand):
    help = "Prépare et vérifie les scénarios synthétiques de démonstration PFE."

    def add_arguments(self, parser):
        parser.add_argument(
            "--customer-slug",
            required=True,
            help="Tenant existant dans lequel afficher les scénarios.",
        )
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Supprime uniquement les objets PFE25 du tenant avant de les recréer.",
        )
        parser.add_argument(
            "--verify-only",
            action="store_true",
            help="N'écrit rien et affiche uniquement l'état des scénarios préparés.",
        )

    def handle(self, *args, **options):
        try:
            customer = Customer.objects.get(slug=options["customer_slug"])
        except Customer.DoesNotExist as exc:
            raise CommandError("Le customer demandé n'existe pas.") from exc

        if options["verify_only"]:
            self.stdout.write(json.dumps(self._summary(customer), indent=2, default=str))
            return

        password = os.getenv("PFE_DEMO_PASSWORD")
        if not password or len(password) < 12:
            raise CommandError(
                "PFE_DEMO_PASSWORD (12 caractères minimum) est requis pour les comptes locaux."
            )
        foreign_active_model = (
            MLModelVersion.objects.filter(customer=customer, active=True)
            .exclude(dataset__demo_suite=DEMO_SUITE)
            .exists()
        )
        if foreign_active_model:
            raise CommandError(
                "Ce tenant possède un modèle actif non PFE. Utilisez un tenant de démonstration dédié."
            )
        if options["reset"]:
            self._reset(customer)
        elif Machine.objects.filter(
            customer=customer, metadata__demo_suite=DEMO_SUITE
        ).exists():
            raise CommandError(
                "Les scénarios existent déjà. Utilisez --verify-only ou --reset."
            )

        isolated_customer = Customer.objects.create(
            name="PFE Client isolé", slug=ISOLATED_CUSTOMER_SLUG
        )
        self._create_users(customer, isolated_customer, password)
        environments = self._create_environments(customer)
        machines = self._create_machines(customer, environments)
        self._create_isolated_machine(isolated_customer)
        self._create_agent(customer, machines["normal"])
        self._create_virtual_inventory(customer, environments, machines)
        self._create_training_history(machines["normal"])

        training = train_customer_model(
            customer.pk,
            days=2,
            dataset_metadata={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "purpose": "jury_demonstration_only",
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
            include_controlled=True,
        )
        self._create_monitoring_scenarios(customer, machines)
        inference = infer_customer(
            customer.pk,
            days=1,
            machine_ids=[machines["ml"].pk],
            include_controlled=True,
        )
        notification_status = self._create_notification_scenario(customer, machines)
        summary = self._summary(customer)
        summary.update(
            training=training,
            inference=inference,
            notification_execution=notification_status,
        )
        self.stdout.write(self.style.SUCCESS("Scénarios PFE25 préparés."))
        self.stdout.write(json.dumps(summary, indent=2, default=str))
        self.stdout.write(
            self.style.WARNING(
                "Toutes les données VMware, Hyper-V et ML créées par cette commande sont synthétiques."
            )
        )

    def _reset(self, customer):
        artifact_names = list(
            MLModelVersion.objects.filter(
                customer=customer, dataset__demo_suite=DEMO_SUITE
            ).values_list("artifact_path", flat=True)
        )
        MLModelVersion.objects.filter(
            customer=customer, dataset__demo_suite=DEMO_SUITE
        ).delete()
        model_root = MODEL_DIR.resolve()
        for name in artifact_names:
            candidate = (MODEL_DIR / Path(name).name).resolve()
            if candidate.parent == model_root:
                candidate.unlink(missing_ok=True)
        NotificationPreference.objects.filter(
            customer=customer, destination=f"jury-demo@{DEMO_EMAIL_DOMAIN}"
        ).delete()
        MonitoringRule.objects.filter(
            customer=customer, name__startswith=DEMO_PREFIX
        ).delete()
        Machine.objects.filter(
            customer=customer, metadata__demo_suite=DEMO_SUITE
        ).delete()
        Environment.objects.filter(
            customer=customer, metadata__demo_suite=DEMO_SUITE
        ).delete()
        User.objects.filter(
            customer=customer, username__startswith=DEMO_USER_PREFIX
        ).delete()
        isolated_customer = Customer.objects.filter(
            slug=ISOLATED_CUSTOMER_SLUG
        ).first()
        if isolated_customer:
            Machine.objects.filter(customer=isolated_customer).delete()
            Environment.objects.filter(customer=isolated_customer).delete()
            User.objects.filter(customer=isolated_customer).delete()
            isolated_customer.delete()

    def _create_users(self, customer, isolated_customer, password):
        for role in User.Role.values:
            local_role = role.lower()
            user, _ = User.objects.update_or_create(
                email=f"pfe25.{local_role}.{customer.slug}@{DEMO_EMAIL_DOMAIN}",
                defaults={
                    "username": f"{DEMO_USER_PREFIX}{local_role}_{customer.slug}"[:150],
                    "customer": customer,
                    "role": role,
                    "is_active": True,
                },
            )
            user.set_password(password)
            user.save(update_fields=["password"])
        isolated, _ = User.objects.update_or_create(
            email=f"pfe25.viewer.isolated@{DEMO_EMAIL_DOMAIN}",
            defaults={
                "username": f"{DEMO_USER_PREFIX}viewer_isolated",
                "customer": isolated_customer,
                "role": User.Role.VIEWER,
                "is_active": True,
            },
        )
        isolated.set_password(password)
        isolated.save(update_fields=["password"])

    def _create_environments(self, customer):
        result = {}
        for key, name, kind in (
            ("windows", "Windows", Environment.Kind.WINDOWS),
            ("vmware", "VMware synthétique", Environment.Kind.VMWARE),
            ("hyperv", "Hyper-V synthétique", Environment.Kind.HYPERV),
        ):
            result[key] = Environment.objects.create(
                customer=customer,
                name=f"{DEMO_PREFIX} {name}",
                kind=kind,
                metadata={
                    "synthetic": True,
                    "demo_suite": DEMO_SUITE,
                    "data_classification": DEMO_DATA_CLASSIFICATION,
                },
            )
        return result

    def _machine(
        self,
        customer,
        environment,
        external_id,
        hostname,
        source_type,
        status=Machine.Status.ONLINE,
        last_seen=None,
        ip_address=None,
    ):
        return Machine.objects.create(
            customer=customer,
            environment=environment,
            source_type=source_type,
            external_id=external_id,
            hostname=hostname,
            ip_address=ip_address,
            status=status,
            last_seen=last_seen or timezone.now(),
            agent_version="2.0.0-demo" if source_type == Environment.Kind.WINDOWS else "",
            os_information={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
                "platform": "Windows Server 2022" if source_type == "WINDOWS" else source_type,
            },
            metadata={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
        )

    def _create_machines(self, customer, environments):
        now = timezone.now()
        specs = {
            "normal": ("pfe-demo-win-normal", "[DEMO] WIN-NORMAL", "windows", "10.25.0.10"),
            "cpu": ("pfe-demo-win-cpu", "[DEMO] WIN-CPU", "windows", "10.25.0.11"),
            "ram": ("pfe-demo-win-ram", "[DEMO] WIN-RAM", "windows", "10.25.0.12"),
            "disk": ("pfe-demo-win-disk", "[DEMO] WIN-DISK", "windows", "10.25.0.13"),
            "offline": ("pfe-demo-win-offline", "[DEMO] WIN-OFFLINE", "windows", "10.25.0.14"),
            "trend": ("pfe-demo-win-trend", "[DEMO] WIN-TREND", "windows", "10.25.0.15"),
            "ml": ("pfe-demo-win-ml", "[DEMO] WIN-ML-ANOMALY", "windows", "10.25.0.16"),
            "vmware_host": ("pfe-demo-esxi-01", "[DEMO SYNTHÉTIQUE] ESXI-01", "vmware", None),
            "vmware_vm": ("pfe-demo-vm-app-01", "[DEMO SYNTHÉTIQUE] VM-APP-01", "vmware", None),
            "hyperv_host": ("pfe-demo-hv-01", "[DEMO SYNTHÉTIQUE] HV-01", "hyperv", None),
            "hyperv_vm": ("pfe-demo-hv-vm-01", "[DEMO SYNTHÉTIQUE] HV-VM-01", "hyperv", None),
        }
        machines = {}
        for key, (external_id, hostname, environment_key, ip_address) in specs.items():
            environment = environments[environment_key]
            machines[key] = self._machine(
                customer,
                environment,
                external_id,
                hostname,
                environment.kind,
                status=(
                    Machine.Status.OFFLINE if key == "offline" else Machine.Status.ONLINE
                ),
                last_seen=(now - timedelta(minutes=15) if key == "offline" else now),
                ip_address=ip_address,
            )
        return machines

    def _create_isolated_machine(self, customer):
        environment = Environment.objects.create(
            customer=customer,
            name=f"{DEMO_PREFIX} Tenant isolé",
            kind=Environment.Kind.WINDOWS,
            metadata={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
        )
        self._machine(
            customer,
            environment,
            "pfe-demo-secret-isolated",
            "[DEMO] CLIENT-B-SECRET",
            Environment.Kind.WINDOWS,
            ip_address="10.26.0.10",
        )

    def _create_agent(self, customer, machine):
        Agent.objects.create(
            customer=customer,
            machine=machine,
            token_hash=hashlib.sha256(
                f"{DEMO_SUITE}:{customer.pk}:{machine.pk}".encode()
            ).hexdigest(),
            enabled=True,
            version="2.0.0-demo",
            last_heartbeat=timezone.now(),
        )

    def _create_virtual_inventory(self, customer, environments, machines):
        vmware = IntegrationEndpoint.objects.create(
            customer=customer,
            environment=environments["vmware"],
            kind=IntegrationEndpoint.Kind.VMWARE,
            name="[DÉMO SYNTHÉTIQUE — NON CONNECTÉ] vCenter",
            endpoint="https://vcenter.demo.invalid/sdk",
            secret_ref="PFE_DEMO_VMWARE_SECRET_NOT_USED",
            enabled=False,
            config={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
            last_error="Mode démonstration synthétique : aucune connexion vCenter.",
        )
        hyperv = IntegrationEndpoint.objects.create(
            customer=customer,
            environment=environments["hyperv"],
            kind=IntegrationEndpoint.Kind.HYPERV,
            name="[DÉMO SYNTHÉTIQUE — NON CONNECTÉ] Hyper-V",
            endpoint="hyperv.demo.invalid",
            secret_ref="PFE_DEMO_HYPERV_SECRET_NOT_USED",
            enabled=False,
            config={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
            last_error="Mode démonstration synthétique : aucune connexion Hyper-V.",
        )
        now = timezone.now()
        for connector, machine, external_id, parent, kind, state in (
            (vmware, machines["vmware_host"], "host-01", "", "HOST", "connected"),
            (vmware, machines["vmware_vm"], "vm-01", "host-01", "VM", "poweredOn"),
            (hyperv, machines["hyperv_host"], "hv-host-01", "", "HOST", "Running"),
            (hyperv, machines["hyperv_vm"], "hv-vm-01", "hv-host-01", "VM", "Running"),
        ):
            VirtualAsset.objects.create(
                customer=customer,
                connector=connector,
                machine=machine,
                external_id=external_id,
                parent_external_id=parent,
                kind=kind,
                name=machine.hostname,
                state=state,
                metadata={
                    "synthetic": True,
                    "demo_suite": DEMO_SUITE,
                    "data_classification": DEMO_DATA_CLASSIFICATION,
                },
                last_seen=now,
            )
        VirtualAsset.objects.create(
            customer=customer,
            connector=vmware,
            external_id="datastore-01",
            parent_external_id="host-01",
            kind=VirtualAsset.Kind.DATASTORE,
            name="[DEMO SYNTHÉTIQUE] DATASTORE-01",
            state="available",
            metadata={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
                "capacity_bytes": 2 * 1024**4,
            },
            last_seen=now,
        )

    def _metric(self, machine, name, value, unit, timestamp, key, metadata=None):
        return NormalizedMetric.objects.create(
            timestamp=timestamp,
            customer=machine.customer,
            environment=machine.environment,
            machine=machine,
            source_type=machine.source_type,
            metric_name=name,
            metric_value=float(value),
            unit=unit,
            status="ok",
            metadata={
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
                **(metadata or {}),
            },
            idempotency_key=f"pfe25:{machine.external_id}:{key}:{name}"[:128],
        )

    def _create_training_history(self, machine):
        start = timezone.now().replace(second=0, microsecond=0) - timedelta(minutes=201)
        for bucket in range(200):
            wave = math.sin(bucket / 4)
            values = {
                "system.cpu.utilization": (38 + 5 * wave, "%"),
                "system.memory.utilization": (55 + 3 * wave, "%"),
                "system.disk.utilization": (61 + bucket * 0.05, "%"),
                "system.network.in": (2_000_000 + abs(wave) * 500_000, "bytes/s"),
                "system.network.out": (1_000_000 + abs(wave) * 250_000, "bytes/s"),
                "system.network.latency": (12 + abs(wave) * 4, "ms"),
            }
            timestamp = start + timedelta(minutes=bucket)
            for name, (value, unit) in values.items():
                self._metric(machine, name, value, unit, timestamp, f"baseline-{bucket}")

    def _rule(self, customer, machine, suffix, metric, threshold, severity):
        return MonitoringRule.objects.create(
            customer=customer,
            environment=machine.environment,
            machine=machine,
            name=f"{DEMO_PREFIX} {suffix}",
            metric=metric,
            operator=">",
            threshold=threshold,
            duration_seconds=60,
            severity=severity,
            enabled=True,
            cooldown_seconds=300,
        )

    def _trigger_rule(self, machine, metric_name, value, unit, key):
        now = timezone.now()
        first = self._metric(
            machine, metric_name, value, unit, now - timedelta(seconds=90), f"{key}-1"
        )
        second = self._metric(
            machine, metric_name, value + 1, unit, now - timedelta(seconds=10), f"{key}-2"
        )
        evaluate_metric(first)
        evaluate_metric(second)

    def _create_monitoring_scenarios(self, customer, machines):
        self._rule(customer, machines["cpu"], "CPU critique", "system.cpu.utilization", 90, "CRITICAL")
        self._rule(customer, machines["ram"], "RAM élevée", "system.memory.utilization", 90, "HIGH")
        self._rule(customer, machines["disk"], "Disque saturé", "system.disk.utilization", 90, "HIGH")
        self._trigger_rule(machines["cpu"], "system.cpu.utilization", 94, "%", "cpu")
        self._trigger_rule(machines["ram"], "system.memory.utilization", 93, "%", "ram")
        self._trigger_rule(machines["disk"], "system.disk.utilization", 95, "%", "disk")

        MonitoringRule.objects.create(
            customer=customer,
            environment=machines["offline"].environment,
            machine=machines["offline"],
            name=f"{DEMO_PREFIX} Machine hors ligne",
            metric="machine.online",
            operator="<",
            threshold=1,
            duration_seconds=300,
            severity="CRITICAL",
            enabled=True,
            cooldown_seconds=300,
        )
        evaluate_offline_machines()

        self._rule(customer, machines["trend"], "Tendance CPU", "system.cpu.utilization", 85, "HIGH")
        start = timezone.now() - timedelta(hours=6)
        for index in range(13):
            self._metric(
                machines["trend"],
                "system.cpu.utilization",
                50 + index * 2,
                "%",
                start + timedelta(minutes=index * 30),
                f"trend-{index}",
            )

        now = timezone.now()
        source_metrics = (
            ("vmware_host", "system.cpu.utilization", 72, "%", "HOST"),
            ("vmware_host", "system.memory.utilization", 68, "%", "HOST"),
            ("vmware_vm", "system.cpu.utilization", 44, "%", "VM"),
            ("vmware_vm", "system.memory.utilization", 57, "%", "VM"),
            ("hyperv_host", "system.cpu.utilization", 63, "%", "HOST"),
            ("hyperv_host", "system.memory.utilization", 71, "%", "HOST"),
            ("hyperv_vm", "system.cpu.utilization", 39, "%", "VM"),
            ("hyperv_vm", "system.memory.utilization", 52, "%", "VM"),
        )
        for index, (machine_key, metric, value, unit, kind) in enumerate(source_metrics):
            self._metric(
                machines[machine_key],
                metric,
                value,
                unit,
                now - timedelta(minutes=index),
                f"source-{index}",
                {"resource_kind": kind},
            )
        self._metric(
            machines["hyperv_vm"],
            "hyperv.vm.state",
            1,
            "state",
            now,
            "hyperv-state",
            {"resource_kind": "VM", "state": "Running"},
        )

        extreme_values = {
            "system.cpu.utilization": (84.8033, "%"),
            "system.memory.utilization": (45.4717, "%"),
            "system.disk.utilization": (66.2769, "%"),
            "system.network.in": (64_170_446, "bytes/s"),
            "system.network.out": (47_771_676, "bytes/s"),
            "system.network.latency": (10.6787, "ms"),
        }
        latest_completed_minute = now.replace(second=0, microsecond=0) - timedelta(
            minutes=1
        )
        for window in range(5):
            timestamp = latest_completed_minute - timedelta(minutes=4 - window)
            for name, (value, unit) in extreme_values.items():
                # Cinq fenêtres complètes fournissent la preuve temporelle 3/5 requise
                # par le pipeline, sans présenter ces mesures synthétiques comme réelles.
                self._metric(
                    machines["ml"],
                    name,
                    value * (1 + window / 100),
                    unit,
                    timestamp,
                    f"ml-extreme-{window}",
                )

    def _create_notification_scenario(self, customer, machines):
        preference = NotificationPreference.objects.create(
            customer=customer,
            channel=NotificationPreference.Channel.EMAIL,
            destination=f"jury-demo@{DEMO_EMAIL_DOMAIN}",
            minimum_severity="CRITICAL",
            enabled=True,
            cooldown_seconds=300,
        )
        alert = Alert.objects.filter(
            customer=customer, machine=machines["cpu"], severity="CRITICAL"
        ).first()
        if not alert:
            return "NO_CRITICAL_ALERT"
        event = NotificationEvent.objects.create(
            customer=customer,
            alert=alert,
            event_type="pfe.demo.notification",
            severity=alert.severity,
            payload={
                "alert_id": str(alert.pk),
                "machine": alert.machine.hostname,
                "message": alert.message,
                "synthetic": True,
                "demo_suite": DEMO_SUITE,
                "data_classification": DEMO_DATA_CLASSIFICATION,
            },
            dedup_key=f"pfe25:notification:{alert.pk}",
        )
        delivery = NotificationDelivery.objects.create(
            event=event,
            preference=preference,
            next_attempt_at=timezone.now(),
        )
        if settings.EMAIL_BACKEND != CONSOLE_EMAIL_BACKEND:
            return "PENDING_EXTERNAL_EMAIL_DISABLED_FOR_DEMO"
        return deliver_notification(delivery.pk)

    def _summary(self, customer):
        demo_machines = Machine.objects.filter(
            customer=customer, metadata__demo_suite=DEMO_SUITE
        )
        trend_machine = demo_machines.filter(external_id="pfe-demo-win-trend").first()
        trends = analyze_machine_trends(trend_machine, hours=24) if trend_machine else []
        alerts = Alert.objects.filter(customer=customer, machine__in=demo_machines)
        return {
            "customer": customer.slug,
            "synthetic": True,
            "data_classification": DEMO_DATA_CLASSIFICATION,
            "demo_users": User.objects.filter(
                customer=customer, username__startswith=DEMO_USER_PREFIX
            ).count(),
            "demo_machines": demo_machines.count(),
            "online_machines": demo_machines.filter(status=Machine.Status.ONLINE).count(),
            "offline_machines": demo_machines.filter(status=Machine.Status.OFFLINE).count(),
            "vmware_assets": VirtualAsset.objects.filter(
                customer=customer,
                connector__kind=IntegrationEndpoint.Kind.VMWARE,
                metadata__demo_suite=DEMO_SUITE,
            ).count(),
            "hyperv_assets": VirtualAsset.objects.filter(
                customer=customer,
                connector__kind=IntegrationEndpoint.Kind.HYPERV,
                metadata__demo_suite=DEMO_SUITE,
            ).count(),
            "metrics": NormalizedMetric.objects.filter(
                customer=customer, metadata__demo_suite=DEMO_SUITE
            ).count(),
            "rules": MonitoringRule.objects.filter(
                customer=customer, name__startswith=DEMO_PREFIX
            ).count(),
            "alerts": alerts.count(),
            "recommendations": alerts.filter(
                structured_recommendation__isnull=False
            ).count(),
            "anomalies": Anomaly.objects.filter(
                customer=customer, explanation__synthetic=True
            ).count(),
            "active_synthetic_models": MLModelVersion.objects.filter(
                customer=customer,
                active=True,
                dataset__demo_suite=DEMO_SUITE,
                dataset__synthetic=True,
            ).count(),
            "predictive_trends": len(trends),
            "predictive_risk_max": max(
                (item["risk_score"] for item in trends), default=0
            ),
            "notification_deliveries": list(
                NotificationDelivery.objects.filter(
                    event__customer=customer,
                    event__payload__demo_suite=DEMO_SUITE,
                )
                .values_list("status", flat=True)
                .order_by("status")
            ),
            "isolated_customer_present": Customer.objects.filter(
                slug=ISOLATED_CUSTOMER_SLUG
            ).exists(),
        }
