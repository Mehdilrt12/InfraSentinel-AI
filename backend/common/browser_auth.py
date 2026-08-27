from django.conf import settings
from django.middleware.csrf import get_token
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError

from .auth_api import (
    SecureTokenBlacklistSerializer,
    SecureTokenObtainPairSerializer,
    SecureTokenRefreshSerializer,
    user_from_refresh,
)
from .throttles import LoginAccountThrottle, LoginIPThrottle
from .openapi import ErrorResponseSerializer
from monitoring.audit import record_audit
from monitoring.models import AuditLog


class CSRFResponseSerializer(serializers.Serializer):
    csrf_token = serializers.CharField()


class BrowserLoginResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    expires_in = serializers.IntegerField()


BROWSER_ERRORS = {
    400: OpenApiResponse(ErrorResponseSerializer, "Corps de requête invalide."),
    401: OpenApiResponse(ErrorResponseSerializer, "Identifiants ou cookie invalides."),
    403: OpenApiResponse(ErrorResponseSerializer, "Jeton CSRF absent ou invalide."),
    429: OpenApiResponse(ErrorResponseSerializer, "Limite de requêtes dépassée."),
}


def _set_refresh_cookie(response, refresh):
    response.set_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        refresh,
        max_age=int(settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"].total_seconds()),
        path=settings.JWT_REFRESH_COOKIE_PATH,
        secure=settings.JWT_REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


def _delete_refresh_cookie(response):
    response.delete_cookie(
        settings.JWT_REFRESH_COOKIE_NAME,
        path=settings.JWT_REFRESH_COOKIE_PATH,
        samesite=settings.JWT_REFRESH_COOKIE_SAMESITE,
    )


@method_decorator(ensure_csrf_cookie, name="dispatch")
class BrowserCSRFView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Authentication"],
        summary="Initialiser la protection CSRF navigateur",
        description="Retourne un jeton CSRF et pose le cookie associé. Permissions: public.",
        auth=[],
        responses={200: CSRFResponseSerializer, 429: BROWSER_ERRORS[429]},
        extensions={"x-permissions": ["PUBLIC"]},
    )
    def get(self, request):
        return Response({"csrf_token": get_token(request)})


@method_decorator(csrf_protect, name="dispatch")
class BrowserLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle]

    @extend_schema(
        tags=["Authentication"],
        summary="Ouvrir une session navigateur sécurisée",
        description="Valide les identifiants, renvoie l'accès en mémoire et pose le refresh en cookie HttpOnly.",
        auth=[],
        request=SecureTokenObtainPairSerializer,
        responses={200: BrowserLoginResponseSerializer, **BROWSER_ERRORS},
        extensions={"x-permissions": ["PUBLIC_WITH_CSRF"]},
    )
    def post(self, request):
        serializer = SecureTokenObtainPairSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        response = Response(
            {
                "access": serializer.validated_data["access"],
                "expires_in": int(
                    settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
                ),
            }
        )
        _set_refresh_cookie(response, serializer.validated_data["refresh"])
        return response


@method_decorator(csrf_protect, name="dispatch")
class BrowserRefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Authentication"],
        summary="Rafraîchir une session navigateur",
        description="Utilise et fait tourner le refresh HttpOnly; le corps ne contient jamais ce secret.",
        auth=[],
        request=None,
        responses={200: BrowserLoginResponseSerializer, **BROWSER_ERRORS},
        extensions={"x-permissions": ["REFRESH_COOKIE_WITH_CSRF"]},
    )
    def post(self, request):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, "")
        serializer = SecureTokenRefreshSerializer(data={"refresh": refresh})
        try:
            serializer.is_valid(raise_exception=True)
        except (InvalidToken, TokenError):
            return Response(
                {"detail": "Cookie de rafraîchissement invalide."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        response = Response(
            {
                "access": serializer.validated_data["access"],
                "expires_in": int(
                    settings.SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"].total_seconds()
                ),
            }
        )
        _set_refresh_cookie(
            response, serializer.validated_data.get("refresh", refresh)
        )
        return response


@method_decorator(csrf_protect, name="dispatch")
class BrowserLogoutView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(
        tags=["Authentication"],
        summary="Fermer une session navigateur",
        description="Révoque le refresh HttpOnly puis supprime le cookie. Requiert le jeton CSRF.",
        auth=[],
        request=None,
        responses={204: OpenApiResponse(description="Session fermée."), **BROWSER_ERRORS},
        extensions={"x-permissions": ["REFRESH_COOKIE_WITH_CSRF"]},
    )
    def post(self, request):
        refresh = request.COOKIES.get(settings.JWT_REFRESH_COOKIE_NAME, "")
        user = user_from_refresh(refresh)
        if refresh:
            serializer = SecureTokenBlacklistSerializer(data={"refresh": refresh})
            try:
                serializer.is_valid(raise_exception=True)
            except (serializers.ValidationError, TokenError):
                pass
        response = Response(status=204)
        _delete_refresh_cookie(response)
        if user:
            record_audit(
                AuditLog.Action.USER_LOGOUT,
                customer=user.customer,
                actor=user,
                target=user,
                request=request,
                metadata={"authentication": "browser_cookie"},
            )
        return response
