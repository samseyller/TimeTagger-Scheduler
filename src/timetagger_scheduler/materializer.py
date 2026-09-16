from __future__ import annotations

import time
from datetime import datetime

from .client import TimeTaggerClient
from .models import MaterializationResult, SchedulerConfig
from .recurrence import generate_occurrences


class MaterializationError(RuntimeError):
    """One or more records could not be created safely."""


def materialize(
    config: SchedulerConfig,
    client: TimeTaggerClient,
    now: datetime,
    *,
    dry_run: bool = False,
) -> MaterializationResult:
    existing_keys = {record.key for record in client.get_all_records()}
    occurrences, excluded = generate_occurrences(config, now)
    missing = [occurrence for occurrence in occurrences if occurrence.key not in existing_keys]
    skipped = len(occurrences) - len(missing)
    if dry_run:
        return MaterializationResult(
            len(occurrences), excluded, skipped, len(missing), 0, 0, tuple(missing)
        )
    created = failed = 0
    records = [occurrence.to_record(int(time.time())) for occurrence in missing]
    size = config.settings.put_batch_size
    for offset in range(0, len(records), size):
        batch = records[offset : offset + size]
        result = client.create_records(batch)
        created += len(result.accepted)
        failed += len(result.failed)
        if result.failed or result.errors:
            details = "; ".join((*result.failed, *result.errors))
            raise MaterializationError(f"TimeTagger rejected records: {details}")
        submitted = {record.key for record in batch}
        if set(result.accepted) != submitted:
            raise MaterializationError("TimeTagger did not acknowledge every submitted record")
    return MaterializationResult(
        len(occurrences), excluded, skipped, len(missing), created, failed, tuple(missing)
    )
