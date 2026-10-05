from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from timetagger_scheduler.models import (
    EffectiveRange,
    EventDefinition,
    RecurrenceDefinition,
    SchedulerConfig,
    SchedulerSettings,
)
from timetagger_scheduler.recurrence import generate_occurrences

TZ = ZoneInfo("America/Chicago")


def generate(rule, start, days, effective=date(2024, 1, 1), exclusions=(), event_exclusions=()):
    event = EventDefinition(
        "event",
        True,
        "test",
        time(8),
        time(9),
        rule,
        EffectiveRange(effective),
        frozenset(event_exclusions),
    )
    config = SchedulerConfig(1, SchedulerSettings(TZ, days), (event,), frozenset(exclusions))
    return generate_occurrences(config, datetime.combine(start, time(0), TZ))


def dates(result):
    return [occ.occurrence_date for occ in result[0]]


def test_daily_and_every_two_days():
    assert len(dates(generate(RecurrenceDefinition("daily"), date(2024, 2, 27), 4))) == 4
    assert dates(
        generate(RecurrenceDefinition("daily", 2), date(2024, 2, 27), 4, date(2024, 2, 27))
    ) == [date(2024, 2, 27), date(2024, 2, 29)]


def test_weekdays_and_every_two_weeks():
    rule = RecurrenceDefinition("weekly", weekdays=(0, 2, 4))
    assert dates(generate(rule, date(2024, 1, 1), 7)) == [
        date(2024, 1, 1),
        date(2024, 1, 3),
        date(2024, 1, 5),
    ]
    rule2 = RecurrenceDefinition("weekly", 2, weekdays=(0,))
    assert dates(generate(rule2, date(2024, 1, 1), 22)) == [date(2024, 1, 1), date(2024, 1, 15)]


@pytest.mark.parametrize(
    ("rule", "start", "days", "expected"),
    [
        (
            RecurrenceDefinition("monthly", day=15),
            date(2024, 1, 1),
            60,
            [date(2024, 1, 15), date(2024, 2, 15)],
        ),
        (RecurrenceDefinition("monthly", day=31), date(2024, 1, 1), 61, [date(2024, 1, 31)]),
        (
            RecurrenceDefinition("monthly", weekday=1, occurrence=2),
            date(2024, 1, 1),
            32,
            [date(2024, 1, 9)],
        ),
        (RecurrenceDefinition("monthly", weekday=0, occurrence=5), date(2024, 2, 1), 29, []),
        (
            RecurrenceDefinition("monthly", weekday=4, occurrence="last"),
            date(2024, 2, 1),
            29,
            [date(2024, 2, 23)],
        ),
        (
            RecurrenceDefinition("monthly", 2, day=1),
            date(2024, 12, 1),
            93,
            [date(2024, 12, 1), date(2025, 2, 1)],
        ),
    ],
)
def test_monthly(rule, start, days, expected):
    assert dates(generate(rule, start, days, start)) == expected


def test_effective_and_exclusions():
    result = generate(
        RecurrenceDefinition("daily"),
        date(2024, 1, 1),
        5,
        date(2024, 1, 2),
        [date(2024, 1, 3)],
        [date(2024, 1, 4)],
    )
    assert dates(result) == [date(2024, 1, 2), date(2024, 1, 5)]
    assert result[1] == 2


def test_dst_keeps_local_wall_clock():
    occurrences, _ = generate(RecurrenceDefinition("weekly", weekdays=(6,)), date(2026, 3, 1), 16)
    assert all(occ.start.hour == 8 for occ in occurrences)
    assert occurrences[0].start.utcoffset() != occurrences[-1].start.utcoffset()
    assert int(occurrences[-1].start.timestamp() - occurrences[0].start.timestamp()) != 14 * 86400


def test_full_day_entries_in_recurring_weeks():
    event = EventDefinition(
        "full-day-event", True, "#example Full-day event", time(0), time(0),
        RecurrenceDefinition("weekly", 3, weekdays=tuple(range(7))),
        EffectiveRange(date(2026, 9, 14)),
    )
    config = SchedulerConfig(1, SchedulerSettings(TZ, 28), (event,))
    occurrences, _ = generate_occurrences(config, datetime(2026, 10, 5, 12, tzinfo=TZ))
    assert [occ.occurrence_date for occ in occurrences] == [
        date(2026, 10, 5) + timedelta(days=offset)
        for offset in [*range(7), *range(21, 28)]
    ]
    assert len({occ.key for occ in occurrences}) == 14
    for occ in occurrences:
        assert occ.end.date() == occ.start.date() + timedelta(days=1)
        assert occ.start.time() == occ.end.time() == time(0)
    assert occurrences[0].to_record(0).t2 - occurrences[0].to_record(0).t1 == 86400
    # The final Sunday crosses the fall DST change and still covers the full local day.
    assert occurrences[-1].to_record(0).t2 - occurrences[-1].to_record(0).t1 == 90000
