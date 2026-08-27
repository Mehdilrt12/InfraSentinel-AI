import hashlib

from rest_framework.throttling import AnonRateThrottle, SimpleRateThrottle


class LoginIPThrottle(AnonRateThrottle):
    scope = "auth_login_ip"


class LoginAccountThrottle(SimpleRateThrottle):
    scope = "auth_login_account"

    def get_cache_key(self, request, _view):
        try:
            identifier = str(request.data.get("email", "")).strip().lower()
        except Exception:
            identifier = ""
        digest = hashlib.sha256((identifier or "missing").encode()).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}


class RegistrationThrottle(AnonRateThrottle):
    scope = "registration"


class AgentEnrollmentThrottle(AnonRateThrottle):
    scope = "agent_enrollment"


class AgentRequestThrottle(AnonRateThrottle):
    scope = "agent_request"
