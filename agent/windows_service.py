import os
import threading

if os.name != "nt":
    raise SystemExit("Ce module nécessite Windows.")

import servicemanager
import win32event
import win32service
import win32serviceutil
from agent import build_runtime, default_data_dir


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
        data_dir = default_data_dir()
        runtime = build_runtime(data_dir / "config.json", data_dir, self.runtime_stop)
        runtime.run()
        servicemanager.LogInfoMsg("InfraSentinel agent stopped")


if __name__ == "__main__":
    win32serviceutil.HandleCommandLine(InfraSentinelService)
