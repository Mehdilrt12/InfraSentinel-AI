from rest_framework.permissions import BasePermission, SAFE_METHODS


def active_principal(user):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(user.customer_id and user.customer and user.customer.active)


class IsActiveTenant(BasePermission):
    def has_permission(self, request, _view):
        return active_principal(request.user)


class ReadOnlyUnlessManager(BasePermission):
    def has_permission(self, request, _view):
        if request.method in SAFE_METHODS:
            return active_principal(request.user)
        return bool(
            active_principal(request.user)
            and (
                request.user.is_superuser
                or request.user.role in {"ADMIN", "SUPERVISOR"}
            )
        )


class IsAdmin(BasePermission):
    def has_permission(self, request, _view):
        return bool(
            active_principal(request.user)
            and (request.user.is_superuser or request.user.role == "ADMIN")
        )


class IsAuditReader(BasePermission):
    def has_permission(self, request, _view):
        return bool(
            active_principal(request.user)
            and (
                request.user.is_superuser
                or request.user.role in {"ADMIN", "SUPERVISOR"}
            )
        )


class IsPlatformAdminForWrite(BasePermission):
    """Tenant admins may inspect their customer; only superusers mutate tenants."""

    def has_permission(self, request, _view):
        if request.method in SAFE_METHODS:
            return bool(
                active_principal(request.user)
                and (request.user.is_superuser or request.user.role == "ADMIN")
            )
        return bool(active_principal(request.user) and request.user.is_superuser)
