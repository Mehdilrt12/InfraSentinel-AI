import argparse
import os
import sys
import threading

if os.name != "nt":
    raise SystemExit("Ce module nécessite Windows.")

import servicemanager
import win32event
import win32service
import win32serviceutil
from agent import build_runtime, default_data_dir
from infrasentinel_agent import __version__
from infrasentinel_agent.installer import configure_installation


class InfraSentinelService(win32serviceutil.ServiceFramework):
    _svc_name_ = "InfraSentinelAgent"
    _svc_display_name_ = "InfraSentinel AI Agent"
    _svc_description_ = "Collecte sécurisée de métriques Windows pour InfraSentinel AI."

    def __init__(self, args):
        super().__init__(args)
        self.stop_event = win32event.CreateEvent(None, 0, 0, None)
        self.runtime_stop = threading.Event()

    def SvcStop(self):
        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        self.runtime_stop.set()
        win32event.SetEvent(self.stop_event)

    def SvcDoRun(self):
        servicemanager.LogInfoMsg("InfraSentinel agent starting")
        try:
            data_dir = default_data_dir()
            runtime = build_runtime(data_dir / "config.json", data_dir, self.runtime_stop)
            runtime.run()
            servicemanager.LogInfoMsg("InfraSentinel agent stopped")
        except Exception as exc:
            # The exception text can contain a URL or transport detail.  Keep the
            # Windows Event Log useful without risking disclosure of secrets.
            servicemanager.LogErrorMsg(
                f"InfraSentinel agent stopped unexpectedly ({type(exc).__name__})"
            )
            raise


def _configure(argv):
    parser = argparse.ArgumentParser(
        prog="InfraSentinelAgent.exe configure",
        description="Configure and enroll the InfraSentinel Windows service.",
    )
    parser.add_argument("--server-url")
    parser.add_argument("--machine-name")
    parser.add_argument("--enrollment-file")
    parser.add_argument("--data-dir", default=str(default_data_dir()))
    parser.add_argument("--allow-http-localhost", action="store_true")
    parser.add_argument("--delete-enrollment-file", action="store_true")
    args = parser.parse_args(argv)
    result = configure_installation(
        data_dir=args.data_dir,
        server_url=args.server_url,
        machine_name=args.machine_name,
        enrollment_file=args.enrollment_file,
        allow_http_localhost=args.allow_http_localhost,
        delete_enrollment_file=args.delete_enrollment_file,
    )
    print(
        f"InfraSentinel agent configured: machine={result['machine_id']} "
        f"server={result['server_url']}"
    )
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "configure":
        try:
            return _configure(argv[1:])
        except Exception as exc:
            print(
                f"InfraSentinel configuration failed ({type(exc).__name__}): {exc}",
                file=sys.stderr,
            )
            return 2
    if argv == ["--version"]:
        print(__version__)
        return 0
    if argv:
        return win32serviceutil.HandleCommandLine(InfraSentinelService)

    # The Service Control Manager invokes a frozen service executable without
    # arguments.  HandleCommandLine alone does not dispatch that execution mode.
    servicemanager.Initialize()
    servicemanager.PrepareToHostSingle(InfraSentinelService)
    servicemanager.StartServiceCtrlDispatcher()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
