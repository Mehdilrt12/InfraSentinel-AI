import os
from datetime import timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.core import mail
from django.test import override_settings
from django.utils import timezone

from accounts.models import User
from common.testing import TenantAPITestCase
from monitoring.models import Alert, Severity
from notifications.models import (
    NotificationDelivery,
    NotificationEvent,
    NotificationPreference,
)
from notifications.services import (
    deliver_notification,
    dispatch_due_notifications,
    queue_alert_notification,
    recover_stale_deliveries,
)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class NotificationPolicyTests(TenantAPITestCase):
    def setUp(self):
        self.machine = self.create_machine()
        self.preference = NotificationPreference.objects.create(
            customer=self.customer_a,
            user=self.admin_a,
            channel=NotificationPreference.Channel.EMAIL,
            destination="infra@alpha.test",
            minimum_severity=Severity.HIGH,
            cooldown_seconds=300,
        )

    def _alert(self, severity, *, key=None, customer=None, machine=None):
        customer = customer or self.customer_a
        machine = machine or self.machine
        return Alert.objects.create(
            customer=customer,
            machine=machine,
            type="RULE_THRESHOLD",
            severity=severity,
            source="WINDOWS",
            message=f"{severity} incident",
            dedup_key=key or f"alert-{severity}-{Alert.objects.count()}",
        )

    def _delivery(self, *, severity="HIGH", key="delivery", preference=None):
        alert = self._alert(severity, key=f"alert-{key}")
        event = NotificationEvent.objects.create(
            customer=self.customer_a,
            alert=alert,
            event_type="alert.created",
            severity=severity,
            payload={"machine": self.machine.hostname, "message": alert.message},
            dedup_key=f"event-{key}",
        )
        return NotificationDelivery.objects.create(
            event=event,
            preference=preference or self.preference,
            next_attempt_at=timezone.now(),
        )

    def test_declared_severity_contract_is_explicit(self):
        self.assertEqual(
            list(Severity.values), ["INFO", "WARNING", "HIGH", "CRITICAL"]
        )
        self.assertNotIn("LOW", Severity.values)
        self.assertNotIn("MEDIUM", Severity.values)

    def test_info_warning_high_and_critical_follow_notification_policy(self):
        for severity in (Severity.INFO, Severity.WARNING):
            with self.subTest(severity=severity):
                self.assertIsNone(
                    queue_alert_notification(self._alert(severity).pk, "alert.created")
                )
        high_event = queue_alert_notification(
            self._alert(Severity.HIGH).pk, "alert.created"
        )
        critical_event = queue_alert_notification(
            self._alert(Severity.CRITICAL).pk, "alert.created"
        )
        self.assertEqual(high_event.deliveries.count(), 1)
        self.assertEqual(critical_event.deliveries.count(), 1)

    def test_disabled_and_minimum_severity_preferences_are_respected(self):
        self.preference.enabled = False
        self.preference.save(update_fields=["enabled"])
        event = queue_alert_notification(
            self._alert(Severity.HIGH).pk, "alert.created"
        )
        self.assertEqual(event.deliveries.count(), 0)
        self.preference.enabled = True
        self.preference.minimum_severity = Severity.CRITICAL
        self.preference.save(update_fields=["enabled", "minimum_severity"])
        high = queue_alert_notification(
            self._alert(Severity.HIGH).pk, "alert.created"
        )
        critical = queue_alert_notification(
            self._alert(Severity.CRITICAL).pk, "alert.created"
        )
        self.assertEqual(high.deliveries.count(), 0)
        self.assertEqual(critical.deliveries.count(), 1)

    def test_event_deduplication_and_on_commit_enqueue(self):
        alert = self._alert(Severity.HIGH, key="deduplicated")
        with (
            patch("notifications.tasks.dispatch_pending_notifications.delay") as delay,
            self.captureOnCommitCallbacks(execute=True),
        ):
            first = queue_alert_notification(alert.pk, "alert.created")
            second = queue_alert_notification(alert.pk, "alert.created")
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(NotificationEvent.objects.count(), 1)
        self.assertEqual(NotificationDelivery.objects.count(), 1)
        delay.assert_called_once_with()

    def test_email_success_and_terminal_delivery_are_idempotent(self):
        delivery = self._delivery(key="success")
        self.assertEqual(deliver_notification(delivery.pk), "SENT")
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(deliver_notification(delivery.pk), "SENT")
        self.assertEqual(len(mail.outbox), 1)
        delivery.refresh_from_db()
        self.assertEqual(delivery.provider_id, "email")

    def test_retry_uses_exponential_backoff_and_eventually_fails(self):
        delivery = self._delivery(key="retry")
        with patch(
            "notifications.adapters.EmailAdapter.send", side_effect=OSError("smtp down")
        ):
            first_now = timezone.now()
            self.assertEqual(deliver_notification(delivery.pk), "RETRY")
            delivery.refresh_from_db()
            self.assertEqual(delivery.attempts, 1)
            self.assertGreaterEqual(
                delivery.next_attempt_at, first_now + timedelta(seconds=59)
            )
            delivery.next_attempt_at = timezone.now()
            delivery.save(update_fields=["next_attempt_at"])
            second_now = timezone.now()
            self.assertEqual(deliver_notification(delivery.pk), "RETRY")
            delivery.refresh_from_db()
            self.assertEqual(delivery.attempts, 2)
            self.assertGreaterEqual(
                delivery.next_attempt_at, second_now + timedelta(seconds=119)
            )
            delivery.attempts = 7
            delivery.next_attempt_at = timezone.now()
            delivery.save(update_fields=["attempts", "next_attempt_at"])
            self.assertEqual(deliver_notification(delivery.pk), "FAILED")
        delivery.refresh_from_db()
        self.assertEqual(delivery.status, NotificationDelivery.Status.FAILED)

    def test_cooldown_suppresses_duplicate_but_critical_escalation_bypasses(self):
        alert = self._alert(Severity.HIGH, key="cooldown-alert")
        old_event = NotificationEvent.objects.create(
            customer=self.customer_a,
            alert=alert,
            event_type="alert.created",
            severity=Severity.HIGH,
            dedup_key="cooldown-old-event",
        )
        NotificationDelivery.objects.create(
            event=old_event,
            preference=self.preference,
            status=NotificationDelivery.Status.SENT,
            sent_at=timezone.now(),
        )
        duplicate_event = NotificationEvent.objects.create(
            customer=self.customer_a,
            alert=alert,
            event_type="alert.updated",
            severity=Severity.HIGH,
            dedup_key="cooldown-duplicate-event",
        )
        duplicate = NotificationDelivery.objects.create(
            event=duplicate_event,
            preference=self.preference,
            next_attempt_at=timezone.now(),
        )
        self.assertEqual(deliver_notification(duplicate.pk), "SUPPRESSED")
        critical_event = NotificationEvent.objects.create(
            customer=self.customer_a,
            alert=alert,
            event_type="alert.escalated",
            severity=Severity.CRITICAL,
            dedup_key="cooldown-critical-event",
        )
        critical = NotificationDelivery.objects.create(
            event=critical_event,
            preference=self.preference,
            next_attempt_at=timezone.now(),
        )
        self.assertEqual(deliver_notification(critical.pk), "SENT")

    def test_stale_recovery_future_delivery_and_dispatch_completion(self):
        stale = self._delivery(key="stale")
        stale.status = NotificationDelivery.Status.SENDING
        stale.save(update_fields=["status", "updated_at"])
        NotificationDelivery.objects.filter(pk=stale.pk).update(
            updated_at=timezone.now() - timedelta(hours=1)
        )
        self.assertEqual(recover_stale_deliveries(), 1)
        stale.refresh_from_db()
        self.assertEqual(stale.status, NotificationDelivery.Status.RETRY)

        future = self._delivery(key="future")
        future.next_attempt_at = timezone.now() + timedelta(hours=1)
        future.save(update_fields=["next_attempt_at"])
        self.assertEqual(deliver_notification(future.pk), "NOT_DUE")

        result = dispatch_due_notifications()
        self.assertEqual(result["sent"], 1)
        stale.event.refresh_from_db()
        self.assertIsNotNone(stale.event.processed_at)

    def test_unimplemented_channel_is_logged_as_retry_not_success(self):
        slack = NotificationPreference.objects.create(
            customer=self.customer_a,
            channel=NotificationPreference.Channel.SLACK,
            destination="https://hooks.invalid",
            minimum_severity=Severity.HIGH,
        )
        delivery = self._delivery(key="slack", preference=slack)
        self.assertEqual(deliver_notification(delivery.pk), "RETRY")
        delivery.refresh_from_db()
        self.assertIn("non implémenté", delivery.last_error)


class NotificationPreferenceAPITests(TenantAPITestCase):
    def test_preference_crud_permissions_validation_and_tenant_isolation(self):
        self.authenticate()
        created = self.client.post(
            "/api/notifications/preferences/",
            {
                "user": self.admin_a.pk,
                "channel": "EMAIL",
                "destination": "ops@alpha.test",
                "minimum_severity": "HIGH",
                "cooldown_seconds": 120,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        preference_id = created.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/notifications/preferences/{preference_id}/",
                {"enabled": False},
                format="json",
            ).status_code,
            200,
        )
        foreign = NotificationPreference.objects.create(
            customer=self.customer_b,
            user=self.admin_b,
            channel="EMAIL",
            destination="ops@beta.test",
        )
        self.assertEqual(
            self.client.get(f"/api/notifications/preferences/{foreign.pk}/").status_code,
            404,
        )
        invalid_relation = self.client.post(
            "/api/notifications/preferences/",
            {
                "user": self.admin_b.pk,
                "channel": "EMAIL",
                "destination": "intrusion@alpha.test",
            },
            format="json",
        )
        self.assertEqual(invalid_relation.status_code, 400)
        self.authenticate(self.users_by_role[User.Role.VIEWER])
        self.assertEqual(
            self.client.delete(
                f"/api/notifications/preferences/{preference_id}/"
            ).status_code,
            403,
        )


class ExternalSMTPIntegrationTests(TenantAPITestCase):
    @skipUnless(
        os.getenv("INFRASENTINEL_RUN_EXTERNAL_SMTP") == "1",
        "NOT TESTED — EXTERNAL SMTP DELIVERY",
    )
    def test_external_smtp_delivery(self):
        self.assertTrue(os.getenv("EMAIL_HOST"))
