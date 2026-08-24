import base64
import os
from pathlib import Path


class CredentialStore:
    def __init__(self, path):
        self.path = Path(path)

    def save(self, token):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if os.name != "nt":
            if os.getenv("INFRASENTINEL_ALLOW_PLAINTEXT_TEST_TOKEN") != "1":
                raise RuntimeError("Le stockage du token nécessite Windows DPAPI.")
            payload = token.encode()
        else:
            import win32crypt

            payload = win32crypt.CryptProtectData(
                token.encode(), "InfraSentinel agent token", None, None, None, 0
            )
        self.path.write_bytes(base64.b64encode(payload))

    def load(self):
        if not self.path.exists():
            return None
        payload = base64.b64decode(self.path.read_bytes())
        if os.name != "nt":
            if os.getenv("INFRASENTINEL_ALLOW_PLAINTEXT_TEST_TOKEN") != "1":
                raise RuntimeError("Le token de test en clair est désactivé.")
            return payload.decode()
        import win32crypt

        return win32crypt.CryptUnprotectData(payload, None, None, None, 0)[1].decode()
