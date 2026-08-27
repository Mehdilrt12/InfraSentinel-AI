from django.conf import settings
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from rest_framework.permissions import AllowAny
from common.auth_api import (
    DocumentedTokenBlacklistView,
    DocumentedTokenObtainPairView,
    DocumentedTokenRefreshView,
)
from common.browser_auth import (
    BrowserCSRFView,
    BrowserLoginView,
    BrowserLogoutView,
    BrowserRefreshView,
)
from common.permissions import IsAdmin

docs_permissions = [AllowAny] if settings.API_DOCS_PUBLIC else [IsAdmin]

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "api/schema/",
        SpectacularAPIView.as_view(permission_classes=docs_permissions),
        name="api-schema",
    ),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(
            url_name="api-schema", permission_classes=docs_permissions
        ),
        name="api-docs",
    ),
    path(
        "api/auth/token/",
        DocumentedTokenObtainPairView.as_view(),
        name="token_obtain_pair",
    ),
    path(
        "api/auth/refresh/",
        DocumentedTokenRefreshView.as_view(),
        name="token_refresh",
    ),
    path(
        "api/auth/logout/",
        DocumentedTokenBlacklistView.as_view(),
        name="token_blacklist",
    ),
    path("api/auth/browser/csrf/", BrowserCSRFView.as_view(), name="browser_csrf"),
    path("api/auth/browser/login/", BrowserLoginView.as_view(), name="browser_login"),
    path(
        "api/auth/browser/refresh/",
        BrowserRefreshView.as_view(),
        name="browser_refresh",
    ),
    path(
        "api/auth/browser/logout/",
        BrowserLogoutView.as_view(),
        name="browser_logout",
    ),
    path("api/", include("common.urls")),
]
