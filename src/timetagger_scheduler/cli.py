from __future__ import annotations

import argparse
import logging
import os
import signal
import sys
import threading
from datetime import datetime
from pathlib import Path

from .client import TimeTaggerClient, TimeTaggerError
from .config import ConfigError, load_config
from .materializer import MaterializationError, materialize

EXIT_CONFIG, EXIT_API, EXIT_WRITE = 2, 3, 4
LOG = logging.getLogger("timetagger_scheduler")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create-only recurring TimeTagger materializer")
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--interval", type=int, metavar="SECONDS")
    parser.add_argument("--verbose", action="store_true")
    return parser


def _run_once(config, client, *, dry_run: bool) -> None:
    now = datetime.now(config.settings.timezone)
    result = materialize(config, client, now, dry_run=dry_run)
    end_date = now.date() + __import__("datetime").timedelta(
        days=config.settings.generate_days_ahead
    )
    if dry_run:
        print("DRY RUN\n")
    print(f"Window: {now.date()} -> {end_date} (exclusive)\n")
    print(f"Occurrences calculated: {result.calculated}")
    print(f"Excluded:                {result.excluded}")
    print(f"Already materialized:   {result.already_materialized}")
    action = "Would create" if dry_run else "Created"
    action_count = result.planned if dry_run else result.created
    print(f"{action}:                 {action_count}")
    print(f"Failed:                  {result.failed}")
    if dry_run:
        for occurrence in result.occurrences:
            times = f"{occurrence.start:%H:%M}-{occurrence.end:%H:%M}"
            print(f"CREATE {occurrence.occurrence_date} {times} {occurrence.description}")
    else:
        print("\nMaterialization complete.")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s"
    )
    if args.interval is not None and args.interval < 1:
        print("ERROR --interval must be >= 1", file=sys.stderr)
        return EXIT_CONFIG
    try:
        config = load_config(args.config)
        url, token = os.getenv("TIMETAGGER_URL"), os.getenv("TIMETAGGER_TOKEN")
        if not url or not token:
            raise ConfigError("TIMETAGGER_URL and TIMETAGGER_TOKEN are required")
        timeout_text = os.getenv("TIMETAGGER_TIMEOUT")
        timeout = float(timeout_text) if timeout_text else config.settings.api_timeout_seconds
        client = TimeTaggerClient(url, token, timeout)
        version = client.get_version()
        print(f"Connected to TimeTagger {version}\n")
        if args.check:
            print("Configuration and API connectivity check passed.")
            return 0
        stop = threading.Event()
        if args.interval:
            signal.signal(signal.SIGTERM, lambda *_: stop.set())
            signal.signal(signal.SIGINT, lambda *_: stop.set())
        while True:
            try:
                _run_once(config, client, dry_run=args.dry_run)
            except (TimeTaggerError, MaterializationError) as exc:
                LOG.error("%s", exc)
                if not args.interval:
                    raise
            if not args.interval or stop.wait(args.interval):
                break
        return 0
    except ConfigError as exc:
        LOG.error("Configuration error: %s", exc)
        return EXIT_CONFIG
    except TimeTaggerError as exc:
        LOG.error("%s", exc)
        return EXIT_API if "PUT" not in str(exc) and "write" not in str(exc).lower() else EXIT_WRITE
    except MaterializationError as exc:
        LOG.error("%s", exc)
        return EXIT_WRITE
    except (ValueError, OSError) as exc:
        LOG.error("Configuration error: %s", exc)
        return EXIT_CONFIG
