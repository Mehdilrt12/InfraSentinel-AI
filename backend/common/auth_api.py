from drf_spectacular.utils import OpenApiResponse, extend_schema, extend_schema_view
from rest_framework import serializers
from rest_framework_simplejwt.serializers import (
    PasswordField,
    TokenBlacklistSerializer,
    TokenObtainPairSerializer,
    TokenRefreshSerializer,
)
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import (
    TokenBlacklistView,
    TokenObtainPairView,
    TokenRefreshView,
)

from .openapi import ErrorResponseSerializer
from .throttles import LoginAccountThrottle, LoginIPThrottle
from accounts.models import User
from monitoring.audit import record_audit
from monitoring.models import AuditLog


MAX_PASSWORD_LENGTH = 128


def active_user_authentication_rule(user):
    if not user or not user.is_active:
        return False
    if user.is_superuser:
        return True
    return bool(user.customer_id and user.customer and user.customer.active)


class SecureTokenObtainPairSerializer(TokenObtainPairSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[self.username_field] = serializers.EmailField(
            max_length=254, write_only=True
        )
        self.fields["password"] = PasswordField(max_length=MAX_PASSWORD_LENGTH)

    def validate(self, attrs):
        data = super().validate(attrs)
        request = self.context.get("request")
        record_audit(
            AuditLog.Action.USER_LOGIN,
            customer=self.user.customer,
            actor=self.user,
            target=self.user,
            request=request,
            metadata={
                "authentication": (
                    "browser_cookie" if request and "/browser/" in request.path else "jwt"
                )
            },
        )
        return data


class SecureTokenRefreshSerializer(TokenRefreshSerializer):
    refresh = serializers.CharField(max_length=4096)


class SecureTokenBlacklistSerializer(TokenBlacklistSerializer):
    refresh = serializers.CharField(max_length=4096)


def user_from_refresh(raw_refresh):
    if not raw_refresh:
        return None
    try:
        user_id = RefreshToken(raw_refresh).get("user_id")
    except TokenError:
        return None
    return User.objects.select_related("customer").filter(pk=user_id).first()


class TokenPairResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="JWT d'accès, durée de vie 15 minutes.")
    refresh = serializers.CharField(
        help_text="JWT de rafraîchissement, durée de vie 1 jour."
    )


class TokenRefreshResponseSerializer(serializers.Serializer):
    access = serializers.CharField(help_text="Nouveau JWT d'accès.")
    refresh = serializers.CharField(
        required=False,
        help_text="Nouveau refresh token lorsque la rotation est activée.",
    )


AUTH_ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, "Corps de requête invalide."),
    401: OpenApiResponse(ErrorResponseSerializer, "Identifiants ou jeton invalides."),
    429: OpenApiResponse(ErrorResponseSerializer, "Limite de requêtes dépassée."),
}


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Obtenir une paire de JWT",
        description=(
            "Authentifie un utilisateur avec son email et son mot de passe. "
            "Aucune authentification préalable. Permissions: public."
        ),
        auth=[],
        request=SecureTokenObtainPairSerializer,
        responses={200: TokenPairResponseSerializer, **AUTH_ERRORS},
        extensions={"x-permissions": ["PUBLIC"]},
    )
)
class DocumentedTokenObtainPairView(TokenObtainPairView):
    serializer_class = SecureTokenObtainPairSerializer
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle]


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Rafraîchir les JWT",
        description=(
            "Valide le refresh token, le met en liste noire après rotation et renvoie "
            "un nouveau jeton. Aucune authentification préalable. Permissions: public."
        ),
        auth=[],
        request=SecureTokenRefreshSerializer,
        responses={200: TokenRefreshResponseSerializer, **AUTH_ERRORS},
        extensions={"x-permissions": ["PUBLIC"]},
    )
)
class DocumentedTokenRefreshView(TokenRefreshView):
    serializer_class = SecureTokenRefreshSerializer


@extend_schema_view(
    post=extend_schema(
        tags=["Authentication"],
        summary="Révoquer un refresh token",
        description=(
            "Place le refresh token dans la liste noire. Aucune authentification "
            "préalable n'est nécessaire, mais le jeton fourni doit être valide."
        ),
        auth=[],
        request=SecureTokenBlacklistSerializer,
        responses={
            200: OpenApiResponse(description="Jeton révoqué; réponse vide."),
            **AUTH_ERRORS,
        },
        extensions={"x-permissions": ["TOKEN_HOLDER"]},
    )
)
class DocumentedTokenBlacklistView(TokenBlacklistView):
    serializer_class = SecureTokenBlacklistSerializer

    def post(self, request, *args, **kwargs):
        user = user_from_refresh(request.data.get("refresh", ""))
        response = super().post(request, *args, **kwargs)
        if user and response.status_code < 400:
            record_audit(
                AuditLog.Action.USER_LOGOUT,
                customer=user.customer,
                actor=user,
                target=user,
                request=request,
                metadata={"authentication": "jwt"},
            )
        return response
