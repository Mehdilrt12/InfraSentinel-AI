from django.urls import path
from .consumers import TenantEventConsumer

websocket_urlpatterns = [path("ws/events/", TenantEventConsumer.as_asgi())]
