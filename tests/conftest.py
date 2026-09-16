from __future__ import annotations

from datetime import date, time
from zoneinfo import ZoneInfo

import pytest

from timetagger_scheduler.models import (
    EffectiveRange,
    EventDefinition,
    RecurrenceDefinition,
    SchedulerConfig,
    SchedulerSettings,
)


@pytest.fixture
def weekly_config():
    event = EventDefinition(
        "work",
        True,
        "#work Work",
        time(8),
        time(17),
        RecurrenceDefinition("weekly", weekdays=(0, 1, 2)),
        EffectiveRange(date(2026, 9, 1)),
    )
    return SchedulerConfig(1, SchedulerSettings(ZoneInfo("America/Chicago"), 3), (event,))
