from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APITestCase

from accounts.models import Customer, User
from inventory.models import Environment, Machine


TEST_PASSWORD = "CorrectHorse12!"


class TenantAPITestCase(APITestCase):
    """Fixtures minimales partagées par les tests API multi-tenant."""

    @classmethod
    def setUpTestData(cls):
        cls.customer_a = Customer.objects.create(name="Alpha", slug="alpha")
        cls.customer_b = Customer.objects.create(name="Beta", slug="beta")
        cls.environment_a = Environment.objects.create(
            customer=cls.customer_a,
            name="Windows Alpha",
            kind=Environment.Kind.WINDOWS,
        )
        cls.environment_b = Environment.objects.create(
            customer=cls.customer_b,
            name="Windows Beta",
            kind=Environment.Kind.WINDOWS,
        )
        cls.users_by_role = {}
        for role in User.Role.values:
            user = User.objects.create_user(
                username=f"{role.lower()}-alpha",
                email=f"{role.lower()}@alpha.test",
                password=TEST_PASSWORD,
                customer=cls.customer_a,
                role=role,
            )
            cls.users_by_role[role] = user
        cls.admin_a = cls.users_by_role[User.Role.ADMIN]
        cls.admin_b = User.objects.create_user(
            username="admin-beta",
            email="admin@beta.test",
            password=TEST_PASSWORD,
            customer=cls.customer_b,
            role=User.Role.ADMIN,
        )

    def setUp(self):
        super().setUp()
        cache.clear()

    def authenticate(self, user=None):
        self.client.force_authenticate(user or self.admin_a)

    def create_machine(
        self,
        *,
        customer=None,
        environment=None,
        source_type=Environment.Kind.WINDOWS,
        external_id="machine-1",
        hostname="host-1",
        status=Machine.Status.UNKNOWN,
    ):
        customer = customer or self.customer_a
        environment = environment or self.environment_a
        return Machine.objects.create(
            customer=customer,
            environment=environment,
            source_type=source_type,
            external_id=external_id,
            hostname=hostname,
            status=status,
            last_seen=timezone.now(),
        )
