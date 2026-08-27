import base64
import os
from pathlib import Path


# CRYPTPROTECT_LOCAL_MACHINE is deliberately specified here because pywin32 does
# not expose the constant on every supported release.  Machine scope is needed
# when setup performs enrollment and the Windows service later runs as LocalSystem.
CRYPTPROTECT_LOCAL_MACHINE = 0x4


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
                token.encode(),
                "InfraSentinel agent token",
                None,
                None,
                None,
                CRYPTPROTECT_LOCAL_MACHINE,
            )
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            temporary.write_bytes(base64.b64encode(payload))
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

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
