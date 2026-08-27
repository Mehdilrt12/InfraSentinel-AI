import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from infrasentinel_agent.client import AgentAPIError
from infrasentinel_agent.installer import (
    InstallationConfigurationError,
    configure_installation,
)


class InstallerConfigurationTests(unittest.TestCase):
    def _mocks(self):
        client = Mock()
        store = Mock()
        return (
            client,
            store,
            patch("infrasentinel_agent.installer.AgentClient", return_value=client),
            patch(
                "infrasentinel_agent.installer.CredentialStore", return_value=store
            ),
        )

    def test_fresh_install_enrolls_before_writing_secret_free_config(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            enrollment_file = root / "enroll.secret"
            enrollment_file.write_text("one-time-code", encoding="utf-8")
            client, store, client_patch, store_patch = self._mocks()
            client.enroll.return_value = {
                "token": "server-agent-token",
                "machine_id": "machine-1",
                "agent_id": "agent-1",
            }

            with client_patch, store_patch:
                result = configure_installation(
                    root / "data",
                    "https://central.example",
                    "windows-01",
                    enrollment_file,
                )

            store.save.assert_called_once_with("server-agent-token")
            request_code, identity = client.enroll.call_args.args
            self.assertEqual(request_code, "one-time-code")
            self.assertEqual(identity["hostname"], "windows-01")
            self.assertIn("external_id", identity)
            self.assertIn("os_information", identity)
            self.assertEqual(result["machine_id"], "machine-1")
            raw_config = (root / "data" / "config.json").read_text(encoding="utf-8")
            self.assertNotIn("one-time-code", raw_config)
            self.assertNotIn("server-agent-token", raw_config)
            config = json.loads(raw_config)
            self.assertEqual(config["backend_url"], "https://central.example")
            self.assertEqual(config["latency_host"], "central.example")
            self.assertEqual(config["latency_port"], 443)

    def test_invalid_token_and_unavailable_server_leave_no_configuration(self):
        scenarios = (
            AgentAPIError("Authentification agent refusée.", 401, retryable=False),
            AgentAPIError("Serveur indisponible.", retryable=True),
        )
        for failure in scenarios:
            with self.subTest(failure=str(failure)), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                enrollment_file = root / "enroll.secret"
                enrollment_file.write_text("invalid-code", encoding="utf-8")
                client, store, client_patch, store_patch = self._mocks()
                client.enroll.side_effect = failure

                with client_patch, store_patch, self.assertRaises(AgentAPIError):
                    configure_installation(
                        root / "data",
                        "https://central.example",
                        "windows-01",
                        enrollment_file,
                        delete_enrollment_file=True,
                    )

                self.assertFalse((root / "data" / "config.json").exists())
                self.assertFalse(enrollment_file.exists())
                store.save.assert_not_called()

    def test_upgrade_validates_existing_token_and_preserves_tuning(self):
        with tempfile.TemporaryDirectory() as directory:
            data_dir = Path(directory) / "data"
            data_dir.mkdir()
            (data_dir / "config.json").write_text(
                json.dumps(
                    {
                        "backend_url": "https://old.example",
                        "machine_name": "old-name",
                        "interval_seconds": 75,
                        "critical_services": ["W32Time"],
                    }
                ),
                encoding="utf-8",
            )
            client, store, client_patch, store_patch = self._mocks()
            store.load.return_value = "existing-token"
            client.heartbeat.return_value = {
                "machine_id": "machine-1",
                "agent_id": "agent-1",
            }

            with client_patch, store_patch:
                configure_installation(
                    data_dir,
                    "https://new.example",
                    "new-name",
                )

            client.heartbeat.assert_called_once_with("2.0.0")
            client.enroll.assert_not_called()
            store.save.assert_not_called()
            config = json.loads((data_dir / "config.json").read_text(encoding="utf-8"))
            self.assertEqual(config["backend_url"], "https://new.example")
            self.assertEqual(config["machine_name"], "new-name")
            self.assertEqual(config["interval_seconds"], 75)
            self.assertEqual(config["critical_services"], ["W32Time"])

    def test_first_install_without_enrollment_file_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            client, store, client_patch, store_patch = self._mocks()
            store.load.return_value = None
            with (
                client_patch,
                store_patch,
                self.assertRaises(InstallationConfigurationError),
            ):
                configure_installation(
                    Path(directory) / "data",
                    "https://central.example",
                )


@unittest.skipUnless(os.name == "nt", "DPAPI est spécifique à Windows")
class WindowsCredentialTests(unittest.TestCase):
    def test_installer_credentials_use_machine_scope_dpapi(self):
        import win32crypt

        from infrasentinel_agent.credentials import (
            CRYPTPROTECT_LOCAL_MACHINE,
            CredentialStore,
        )

        with tempfile.TemporaryDirectory() as directory:
            store = CredentialStore(Path(directory) / "credential.bin")
            with (
                patch.object(win32crypt, "CryptProtectData", return_value=b"encrypted") as protect,
                patch.object(
                    win32crypt,
                    "CryptUnprotectData",
                    return_value=("description", b"agent-token"),
                ),
            ):
                store.save("agent-token")
                self.assertEqual(store.load(), "agent-token")
            self.assertEqual(protect.call_args.args[-1], CRYPTPROTECT_LOCAL_MACHINE)


if __name__ == "__main__":
    unittest.main()
