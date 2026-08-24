import argparse
import logging
import os
import signal
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

from infrasentinel_agent import __version__
from infrasentinel_agent.collector import WindowsCollector
from infrasentinel_agent.config import AgentConfig
from infrasentinel_agent.credentials import CredentialStore
from infrasentinel_agent.runtime import AgentRuntime
from infrasentinel_agent.spool import Spool


def default_data_dir():
    return Path(os.getenv("PROGRAMDATA", Path.home())) / "InfraSentinel"


def configure_logging(data_dir, config):
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        log_dir / "agent.log",
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    console = logging.StreamHandler()
    console.setFormatter(handler.formatter)
    logging.basicConfig(level=logging.INFO, handlers=[handler, console])


def build_runtime(config_path, data_dir, stop_event=None):
    config = AgentConfig.load(config_path)
    configure_logging(data_dir, config)
    return AgentRuntime(
        config,
        CredentialStore(data_dir / "credentials.dat"),
        Spool(data_dir / "spool.sqlite3", config.spool_max_items),
        stop_event,
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="InfraSentinel Windows Agent")
    parser.add_argument("--config", default=str(default_data_dir() / "config.json"))
    parser.add_argument("--data-dir", default=str(default_data_dir()))
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--collect-once", action="store_true")
    args = parser.parse_args(argv)
    if args.version:
        print(__version__)
        return 0
    config = AgentConfig.load(args.config)
    if args.collect_once:
        print(WindowsCollector(config).collect())
        return 0
    stop = threading.Event()
    runtime = build_runtime(args.config, Path(args.data_dir), stop)
    for signal_name in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_name, lambda *_: stop.set())
    runtime.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
