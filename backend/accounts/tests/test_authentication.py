from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from rest_framework_simplejwt.tokens import AccessToken

from accounts.models import Customer, User
from common.testing import TEST_PASSWORD, TenantAPITestCase


@override_settings(PUBLIC_REGISTRATION_ENABLED=True)
class AuthenticationAPITests(TenantAPITestCase):
    def test_valid_login_issues_jwt_and_access_authenticates_me(self):
        response = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {response.data['access']}")
        me = self.client.get("/api/auth/me/")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.data["email"], self.admin_a.email)
        self.assertFalse(me.data["is_superuser"])
        self.assertNotIn("password", me.data)

    def test_invalid_password_is_rejected(self):
        response = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": "wrong-password"},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_disabled_user_cannot_login(self):
        self.admin_a.is_active = False
        self.admin_a.save(update_fields=["is_active"])
        response = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 401)

    def test_refresh_rotation_blacklists_previous_refresh(self):
        login = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        original = login.data["refresh"]
        refreshed = self.client.post(
            "/api/auth/refresh/", {"refresh": original}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200)
        self.assertIn("access", refreshed.data)
        self.assertIn("refresh", refreshed.data)
        replay = self.client.post(
            "/api/auth/refresh/", {"refresh": original}, format="json"
        )
        self.assertEqual(replay.status_code, 401)

    def test_logout_blacklists_refresh_token(self):
        login = self.client.post(
            "/api/auth/token/",
            {"email": self.admin_a.email, "password": TEST_PASSWORD},
            format="json",
        )
        refresh = login.data["refresh"]
        logout = self.client.post(
            "/api/auth/logout/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(logout.status_code, 200)
        replay = self.client.post(
            "/api/auth/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(replay.status_code, 401)

    def test_invalid_and_expired_access_tokens_are_rejected(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid.jwt.token")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

        expired = AccessToken.for_user(self.admin_a)
        expired.set_exp(
            from_time=timezone.now() - timedelta(hours=1),
            lifetime=timedelta(seconds=1),
        )
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {expired}")
        self.assertEqual(self.client.get("/api/auth/me/").status_code, 401)

    def test_protected_endpoint_requires_authentication(self):
        self.client.force_authenticate(user=None)
        self.client.credentials()
        for path in ("/api/auth/me/", "/api/machines/", "/api/alerts/"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 401)

    def test_registration_creates_isolated_admin_and_default_environment(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "organization": "Gamma Operations",
                "email": "owner@gamma.test",
                "password": "AnEvenStrongerHorse12!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 201)
        customer = Customer.objects.get(pk=response.data["customer_id"])
        user = User.objects.get(pk=response.data["user_id"])
        self.assertEqual(user.customer, customer)
        self.assertEqual(user.role, User.Role.ADMIN)
        self.assertTrue(user.check_password("AnEvenStrongerHorse12!"))
        self.assertEqual(customer.environments.count(), 1)

    def test_registration_validation_and_duplicate_email_are_rejected(self):
        invalid = self.client.post(
            "/api/auth/register/",
            {"organization": "", "email": "bad", "password": "short"},
            format="json",
        )
        self.assertEqual(invalid.status_code, 400)
        duplicate = self.client.post(
            "/api/auth/register/",
            {
                "organization": "Duplicate",
                "email": self.admin_a.email,
                "password": "AnEvenStrongerHorse12!",
            },
            format="json",
        )
        self.assertEqual(duplicate.status_code, 400)
