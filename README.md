# TimeTagger Scheduler

TimeTagger Scheduler is a recurring schedule materializer for TimeTagger. It reads recurring schedules from YAML and creates future TimeTagger records while leaving existing records under user control.

It is intentionally small: Python's standard library handles dates, timezones, recurrence, UUIDs, the CLI, and the periodic loop. The only runtime dependencies are `requests` and `PyYAML`.

## Safety model

```text
CREATE missing occurrences
NEVER UPDATE existing occurrences
NEVER RECREATE hidden occurrences
```

Each occurrence gets a deterministic UUIDv5 key derived only from `event ID + local calendar date`, prefixed with `ttsched-`. Time, duration, and description are deliberately absent from the identity. Before every run, the scheduler obtains a full record inventory with `GET /updates?since=0`, including moved and `HIDDEN` records. If a key exists anywhere, the scheduler does not PUT it.

Event IDs are immutable deployment identifiers. Renaming an ID intentionally creates a new schedule identity and can produce new records for dates materialized under the old ID.

Records with unrelated keys are never claimed, even when date, time, and description match. This can create a visual duplicate, which is safer than treating a user's record as scheduler-owned.

### Edit lifecycle

```text
YAML:       work = 08:00-17:00
Scheduler:  creates Sep 22 08:00-17:00
User:       changes Sep 22 to 08:00-17:45
Next run:   sees the generated Sep 22 key and does nothing
Result:     the user's 17:45 edit remains
```

Deletion behaves the same way:

```text
Scheduler creates record
        |
User deletes it (TimeTagger retains a HIDDEN record/key)
        |
Scheduler sees the key in the full inventory
        |
Does not recreate it
```

GET requests retry selected transient failures. PUT requests are never automatically retried: a timeout or disconnect may mean the server committed the write. The process exits non-zero, and the next run safely resolves the outcome through a fresh complete inventory.

## Supported schedules

- Daily, including every N days
- Weekly weekdays, including every N weeks (weeks start Monday)
- Monthly calendar day (missing dates such as February 31 are skipped)
- Monthly first through fifth weekday, or last weekday
- Inclusive `effective.from` / `effective.until` bounds
- Global and per-event excluded dates

Intervals greater than one require `effective.from`, which anchors the day, Monday-based week, or month interval. Unknown fields are rejected.

The materialization window is `[local now, local today + generate_days_ahead calendar days)`. Recurrence is calculated in the configured `zoneinfo` timezone. An event today is included if it has not ended; arbitrary history is not backfilled. Wall-clock times remain local across DST changes. Times directly inside a DST gap or ambiguous repeated hour are not specially resolved in this POC; avoid scheduling in those transition hours.

## Setup and local use

Python 3.11 or later is required. On Windows, installation also brings in the
IANA `tzdata` database needed by Python's standard-library `zoneinfo` module.

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Then:

1. Obtain a TimeTagger API token (not a temporary web token).
2. Copy `.env.example` to `.env` and replace its placeholders.
3. Copy `config/schedule.example.yaml` to `config/schedule.yaml`.
4. Edit the schedules; keep event IDs stable once deployed.
5. Export/load the `.env` values into the process environment. The application does not parse `.env` itself.
6. Check connectivity and configuration:

```bash
timetagger-scheduler --config config/schedule.yaml --check
```

7. Always preview the first run:

```bash
timetagger-scheduler --config config/schedule.yaml --dry-run
```

8. Run once:

```bash
timetagger-scheduler --config config/schedule.yaml
# Equivalent:
python -m timetagger_scheduler --config config/schedule.yaml
```

Required environment variables are `TIMETAGGER_URL` (normally ending in `/timetagger/api/v2`) and `TIMETAGGER_TOKEN`. `TIMETAGGER_TIMEOUT` optionally overrides the YAML timeout. Tokens are never included in log/error messages.

Exit codes are `0` success, `2` configuration, `3` API/auth/connectivity, and `4` write/materialization failure.

## Docker

Build:

```bash
docker build -t timetagger-scheduler .
```

Dry-run with the example copied to `config/schedule.yaml`:

```bash
docker run --rm --env-file .env \
  -v "${PWD}/config/schedule.yaml:/config/schedule.yaml:ro" \
  timetagger-scheduler --config /config/schedule.yaml --dry-run
```

One-shot Compose dry-run:

```bash
docker compose run --rm timetagger-scheduler --config /config/schedule.yaml --dry-run
```

Periodic deployment (runs immediately, then every six hours):

```bash
docker compose up -d --build
docker compose logs -f timetagger-scheduler
```

The image uses a slim Debian-based Python image and a non-root user. Compose mounts configuration read-only, makes the container filesystem read-only, and exposes no ports. SIGTERM interrupts the periodic wait cleanly. The one-shot materializer remains the underlying operation.

## Development

```bash
python -m pytest -q
python -m ruff check .
```

The tests cover strict validation, recurrence boundaries and DST, stable keys, API behavior, partial failures, dry-run, and the critical edit/delete/move idempotency cases.

## First real-server test

Use `--check`, then `--dry-run`. For the first write, enable only a temporary event with a short effective range. After creation, manually edit one record and hide another, rerun, and confirm neither is changed or recreated before enabling normal schedules.

## Limitations

This POC has no UI, database/cache, holiday provider, calendar integration, multi-user mode, distributed lock, cron parser, or two-way sync. It does not modify or clean up materialized records. Full `/updates?since=0` inventory is intentionally safe but may become expensive for very large accounts; a future persistent cache could use incremental updates while correctly honoring TimeTagger's `reset` indicator.

Run only one scheduler instance per TimeTagger account/configuration. Distributed locking is out of scope, so two instances that inventory simultaneously could race to PUT the same missing key.

## API references

The implementation follows the official [TimeTagger Web API documentation](https://timetagger.readthedocs.io/en/stable/webapi/) and current [TimeTagger server API implementation](https://github.com/almarklein/timetagger/blob/main/timetagger/server/_apiserver.py).
