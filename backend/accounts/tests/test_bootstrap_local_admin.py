import os
from io import StringIO
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.test import TestCase

from accounts.models import Customer, User
from inventory.models import Environment
from monitoring.models import AuditLog


class BootstrapLocalAdminCommandTests(TestCase):
    password = "PortableLaptopBootstrap42!"

    def run_command(self, **options):
        output = StringIO()
        with patch.dict(
            os.environ,
            {"INFRASENTINEL_BOOTSTRAP_PASSWORD": self.password},
            clear=False,
        ):
            call_command(
                "bootstrap_local_admin",
                organization="Portable Operations",
                email="owner@portable.test",
                stdout=output,
                **options,
            )
        return output.getvalue()

    def test_creates_tenant_admin_environment_and_audit_logs(self):
        output = self.run_command()
        user = User.objects.select_related("customer").get(email="owner@portable.test")
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertEqual(user.customer.slug, "portable-operations")
        self.assertTrue(user.check_password(self.password))
        self.assertTrue(
            Environment.objects.filter(
                customer=user.customer,
                name="Windows",
                kind=Environment.Kind.WINDOWS,
            ).exists()
        )
        self.assertEqual(AuditLog.objects.filter(customer=user.customer).count(), 2)
        self.assertNotIn(self.password, output)

    def test_is_idempotent_and_does_not_reset_existing_password(self):
        self.run_command()
        with patch.dict(
            os.environ,
            {"INFRASENTINEL_BOOTSTRAP_PASSWORD": "DifferentPassword99!"},
            clear=False,
        ):
            output = StringIO()
            call_command(
                "bootstrap_local_admin",
                organization="Portable Operations",
                email="owner@portable.test",
                stdout=output,
            )
        user = User.objects.get(email="owner@portable.test")
        self.assertTrue(user.check_password(self.password))
        self.assertEqual(User.objects.count(), 1)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertIn("already exists", output.getvalue())

    def test_check_mode_is_read_only(self):
        missing = self.run_command(check=True)
        self.assertIn("MISSING", missing)
        self.assertEqual(Customer.objects.count(), 0)
        self.run_command()
        existing = self.run_command(check=True)
        self.assertIn("EXISTS", existing)

    def test_rejects_weak_password_without_partial_records(self):
        with patch.dict(
            os.environ,
            {"INFRASENTINEL_BOOTSTRAP_PASSWORD": "weak"},
            clear=False,
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "bootstrap_local_admin",
                    organization="Portable Operations",
                    email="owner@portable.test",
                )
        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(User.objects.count(), 0)

    def test_rejects_existing_email_from_another_tenant(self):
        customer = Customer.objects.create(name="Other", slug="other")
        User.objects.create_user(
            username="owner@portable.test",
            email="owner@portable.test",
            password=self.password,
            customer=customer,
            role=User.Role.ADMIN,
        )
        with self.assertRaises(CommandError):
            self.run_command()
