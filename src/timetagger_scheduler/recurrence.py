from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

from .keys import occurrence_key
from .models import EventDefinition, Occurrence, SchedulerConfig


def _month_index(value: date) -> int:
    return value.year * 12 + value.month - 1


def _matches(event: EventDefinition, candidate: date) -> bool:
    rule = event.recurrence
    anchor = event.effective.from_date
    if rule.type == "daily":
        return rule.every == 1 or (candidate - anchor).days % rule.every == 0  # type: ignore[operator]
    if rule.type == "weekly":
        if candidate.weekday() not in rule.weekdays:
            return False
        if rule.every == 1:
            return True
        anchor_monday = anchor - timedelta(days=anchor.weekday())  # type: ignore[union-attr]
        candidate_monday = candidate - timedelta(days=candidate.weekday())
        return (candidate_monday - anchor_monday).days // 7 % rule.every == 0
    if rule.every > 1 and (_month_index(candidate) - _month_index(anchor)) % rule.every:  # type: ignore[arg-type]
        return False
    if rule.day is not None:
        return candidate.day == rule.day
    if candidate.weekday() != rule.weekday:
        return False
    month_days = calendar.monthrange(candidate.year, candidate.month)[1]
    if rule.occurrence == "last":
        return candidate.day + 7 > month_days
    return (candidate.day - 1) // 7 + 1 == rule.occurrence


def generate_occurrences(config: SchedulerConfig, now: datetime) -> tuple[list[Occurrence], int]:
    """Generate the half-open local window [now, today + N days)."""
    local_now = now.astimezone(config.settings.timezone)
    first_date = local_now.date()
    end_date = first_date + timedelta(days=config.settings.generate_days_ahead)
    output: list[Occurrence] = []
    excluded = 0
    for event in config.events:
        if not event.enabled:
            continue
        candidate = first_date
        while candidate < end_date:
            effective = event.effective
            within = (effective.from_date is None or candidate >= effective.from_date) and (
                effective.until_date is None or candidate <= effective.until_date
            )
            if within and _matches(event, candidate):
                if candidate in config.exclude_dates or candidate in event.exclude_dates:
                    excluded += 1
                else:
                    start = datetime.combine(candidate, event.start, config.settings.timezone)
                    end = datetime.combine(candidate, event.end, config.settings.timezone)
                    if event.start == event.end:
                        end += timedelta(days=1)
                    if end > local_now:
                        output.append(
                            Occurrence(
                                event.id,
                                candidate,
                                start,
                                end,
                                event.description,
                                occurrence_key(event.id, candidate),
                            )
                        )
            candidate += timedelta(days=1)
    output.sort(key=lambda occurrence: (occurrence.start, occurrence.event_id))
    return output, excluded
