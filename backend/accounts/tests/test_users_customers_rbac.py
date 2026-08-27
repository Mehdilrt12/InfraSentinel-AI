from django.contrib.auth import get_user_model

from accounts.models import Customer, User
from common.testing import TEST_PASSWORD, TenantAPITestCase


class UserAndCustomerCRUDTests(TenantAPITestCase):
    def test_admin_can_create_read_update_and_delete_user_in_own_customer(self):
        self.authenticate()
        created = self.client.post(
            "/api/users/",
            {
                "email": "operator@alpha.test",
                "username": "operator-alpha",
                "password": "OperatorHorse12!",
                "role": User.Role.TECHNICIAN,
            },
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        user = get_user_model().objects.get(pk=created.data["id"])
        self.assertEqual(user.customer, self.customer_a)
        self.assertTrue(user.check_password("OperatorHorse12!"))
        self.assertNotIn("password", created.data)

        read = self.client.get(f"/api/users/{user.pk}/")
        self.assertEqual(read.status_code, 200)
        updated = self.client.patch(
            f"/api/users/{user.pk}/",
            {"role": User.Role.SUPERVISOR, "first_name": "Ops"},
            format="json",
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.data["role"], User.Role.SUPERVISOR)
        self.assertEqual(self.client.delete(f"/api/users/{user.pk}/").status_code, 204)
        self.assertFalse(get_user_model().objects.filter(pk=user.pk).exists())

    def test_user_validation_and_duplicate_email_are_rejected(self):
        self.authenticate()
        missing_password = self.client.post(
            "/api/users/",
            {
                "email": "nopassword@alpha.test",
                "username": "no-password",
                "role": User.Role.VIEWER,
            },
            format="json",
        )
        self.assertEqual(missing_password.status_code, 400)
        duplicate = self.client.post(
            "/api/users/",
            {
                "email": self.admin_a.email.upper(),
                "username": "duplicate-admin",
                "password": "OperatorHorse12!",
                "role": User.Role.VIEWER,
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)

    def test_customer_a_cannot_read_update_or_delete_customer_b_user(self):
        self.authenticate()
        path = f"/api/users/{self.admin_b.pk}/"
        self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(
            self.client.patch(path, {"first_name": "intrusion"}, format="json").status_code,
            404,
        )
        self.assertEqual(self.client.delete(path).status_code, 404)
        self.admin_b.refresh_from_db()
        self.assertNotEqual(self.admin_b.first_name, "intrusion")

    def test_tenant_admin_reads_but_cannot_mutate_customer_records(self):
        self.authenticate()
        own = self.client.get(f"/api/customers/{self.customer_a.pk}/")
        self.assertEqual(own.status_code, 200)
        updated = self.client.patch(
            f"/api/customers/{self.customer_a.pk}/",
            {"name": "Alpha Updated", "active": False},
            format="json",
        )
        self.assertEqual(updated.status_code, 403)
        self.customer_a.refresh_from_db()
        self.assertTrue(self.customer_a.active)
        foreign = f"/api/customers/{self.customer_b.pk}/"
        self.assertEqual(self.client.get(foreign).status_code, 404)
        self.assertEqual(
            self.client.patch(foreign, {"name": "Stolen"}, format="json").status_code,
            403,
        )
        self.assertEqual(self.client.delete(foreign).status_code, 403)
        created = self.client.post(
            "/api/customers/",
            {"name": "Escalation", "slug": "escalation"},
            format="json",
        )
        self.assertEqual(created.status_code, 403)

    def test_superuser_can_manage_customer_records(self):
        superuser = User.objects.create_superuser(
            username="root", email="root@global.test", password=TEST_PASSWORD
        )
        self.authenticate(superuser)
        created = self.client.post(
            "/api/customers/",
            {"name": "Global Customer", "slug": "global-customer"},
            format="json",
        )
        self.assertEqual(created.status_code, 201)
        customer_id = created.data["id"]
        self.assertEqual(
            self.client.patch(
                f"/api/customers/{customer_id}/", {"active": False}, format="json"
            ).status_code,
            200,
        )
        self.assertEqual(self.client.delete(f"/api/customers/{customer_id}/").status_code, 204)
        self.assertFalse(Customer.objects.filter(pk=customer_id).exists())


class RolePermissionMatrixTests(TenantAPITestCase):
    def test_all_authenticated_roles_can_read_tenant_resources(self):
        paths = (
            "/api/environments/",
            "/api/machines/",
            "/api/rules/",
            "/api/alerts/",
            "/api/anomalies/",
            "/api/notifications/preferences/",
        )
        for role, user in self.users_by_role.items():
            self.authenticate(user)
            for path in paths:
                with self.subTest(role=role, path=path):
                    self.assertEqual(self.client.get(path).status_code, 200)

    def test_write_permissions_match_admin_and_supervisor_roles(self):
        writable = {User.Role.ADMIN, User.Role.SUPERVISOR}
        for index, (role, user) in enumerate(self.users_by_role.items()):
            self.authenticate(user)
            response = self.client.post(
                "/api/environments/",
                {"name": f"Role Environment {index}", "kind": "WINDOWS"},
                format="json",
            )
            with self.subTest(role=role):
                self.assertEqual(response.status_code, 201 if role in writable else 403)

    def test_user_and_customer_management_is_admin_only(self):
        for role, user in self.users_by_role.items():
            self.authenticate(user)
            expected = 200 if role == User.Role.ADMIN else 403
            for path in ("/api/users/", "/api/customers/"):
                with self.subTest(role=role, path=path):
                    self.assertEqual(self.client.get(path).status_code, expected)

    def test_non_managers_cannot_patch_or_delete_resources(self):
        machine = self.create_machine()
        for role in (User.Role.TECHNICIAN, User.Role.CLIENT, User.Role.VIEWER):
            self.authenticate(self.users_by_role[role])
            with self.subTest(role=role, method="PATCH"):
                self.assertEqual(
                    self.client.patch(
                        f"/api/machines/{machine.pk}/",
                        {"hostname": "forbidden"},
                        format="json",
                    ).status_code,
                    403,
                )
            with self.subTest(role=role, method="DELETE"):
                self.assertEqual(
                    self.client.delete(f"/api/machines/{machine.pk}/").status_code,
                    403,
                )
