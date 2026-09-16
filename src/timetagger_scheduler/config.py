from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from .models import (
    EffectiveRange,
    EventDefinition,
    RecurrenceDefinition,
    SchedulerConfig,
    SchedulerSettings,
)


class ConfigError(ValueError):
    """Configuration is invalid."""


WEEKDAYS = {
    name: i
    for i, name in enumerate(
        ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
    )
}
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def _mapping(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a mapping")
    return value


def _only(data: dict[str, Any], allowed: set[str], where: str) -> None:
    unknown = set(data) - allowed
    if unknown:
        raise ConfigError(f"{where} has unknown field(s): {', '.join(sorted(unknown))}")


def _date(value: Any, where: str, *, nullable: bool = False) -> date | None:
    if value is None and nullable:
        return None
    if isinstance(value, date) and not hasattr(value, "hour"):
        return value
    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    raise ConfigError(f"{where} must be an ISO date (YYYY-MM-DD)")


def _dates(value: Any, where: str) -> frozenset[date]:
    if value is None:
        return frozenset()
    if not isinstance(value, list):
        raise ConfigError(f"{where} must be a list")
    return frozenset(_date(v, f"{where} item") for v in value)  # type: ignore[arg-type]


def _time(value: Any, where: str) -> time:
    if not isinstance(value, str) or not re.fullmatch(r"\d{2}:\d{2}", value):
        raise ConfigError(f"{where} must use HH:MM")
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ConfigError(f"{where} is not a valid time") from exc


def _positive_int(value: Any, where: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{where} must be an integer >= 1")
    return value


def _parse_recurrence(raw: Any, effective: EffectiveRange, where: str) -> RecurrenceDefinition:
    data = _mapping(raw, where)
    _only(data, {"type", "every", "weekdays", "day", "weekday", "occurrence"}, where)
    kind = data.get("type")
    if kind not in {"daily", "weekly", "monthly"}:
        raise ConfigError(f"{where}.type must be daily, weekly, or monthly")
    every = _positive_int(data.get("every", 1), f"{where}.every")
    if every > 1 and effective.from_date is None:
        raise ConfigError(f"{where}.every > 1 requires effective.from")
    if kind == "daily":
        _only(data, {"type", "every"}, where)
        return RecurrenceDefinition("daily", every)
    if kind == "weekly":
        _only(data, {"type", "every", "weekdays"}, where)
        names = data.get("weekdays")
        if not isinstance(names, list) or not names:
            raise ConfigError(f"{where}.weekdays must be a non-empty list")
        try:
            days = tuple(WEEKDAYS[str(v).lower()] for v in names)
        except KeyError as exc:
            raise ConfigError(f"{where} contains invalid weekday {exc.args[0]!r}") from exc
        return RecurrenceDefinition("weekly", every, weekdays=days)
    has_day = "day" in data
    has_nth = "weekday" in data or "occurrence" in data
    if has_day == has_nth:
        raise ConfigError(f"{where} must specify day OR weekday + occurrence")
    if has_day:
        _only(data, {"type", "every", "day"}, where)
        day = data["day"]
        if isinstance(day, bool) or not isinstance(day, int) or not 1 <= day <= 31:
            raise ConfigError(f"{where}.day must be between 1 and 31")
        return RecurrenceDefinition("monthly", every, day=day)
    _only(data, {"type", "every", "weekday", "occurrence"}, where)
    if "weekday" not in data or "occurrence" not in data:
        raise ConfigError(f"{where} requires both weekday and occurrence")
    weekday_name = str(data["weekday"]).lower()
    if weekday_name not in WEEKDAYS:
        raise ConfigError(f"{where}.weekday is invalid")
    occurrence = data["occurrence"]
    if occurrence != "last" and (isinstance(occurrence, bool) or occurrence not in range(1, 6)):
        raise ConfigError(f"{where}.occurrence must be 1-5 or last")
    return RecurrenceDefinition(
        "monthly", every, weekday=WEEKDAYS[weekday_name], occurrence=occurrence
    )


def load_config(path: str | Path) -> SchedulerConfig:
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ConfigError(f"Could not read YAML: {exc}") from exc
    root = _mapping(raw, "configuration")
    _only(root, {"version", "settings", "calendar", "events"}, "configuration")
    if root.get("version") != 1:
        raise ConfigError("version must be 1")
    settings_raw = _mapping(root.get("settings"), "settings")
    _only(
        settings_raw,
        {"timezone", "generate_days_ahead", "api_timeout_seconds", "put_batch_size"},
        "settings",
    )
    tz_name = settings_raw.get("timezone")
    if not isinstance(tz_name, str):
        raise ConfigError("settings.timezone must be a string")
    try:
        timezone = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise ConfigError(f"Unknown timezone: {tz_name}") from exc
    days = _positive_int(
        settings_raw.get("generate_days_ahead", 14), "settings.generate_days_ahead"
    )
    timeout = settings_raw.get("api_timeout_seconds", 10)
    if isinstance(timeout, bool) or not isinstance(timeout, int | float) or timeout <= 0:
        raise ConfigError("settings.api_timeout_seconds must be > 0")
    batch = _positive_int(settings_raw.get("put_batch_size", 100), "settings.put_batch_size")
    calendar_raw = _mapping(root.get("calendar", {}), "calendar")
    _only(calendar_raw, {"exclude_dates"}, "calendar")
    events_raw = root.get("events")
    if not isinstance(events_raw, list):
        raise ConfigError("events must be a list")
    events: list[EventDefinition] = []
    ids: set[str] = set()
    for index, item in enumerate(events_raw):
        where = f"events[{index}]"
        data = _mapping(item, where)
        _only(
            data,
            {
                "id",
                "enabled",
                "description",
                "start",
                "end",
                "recurrence",
                "effective",
                "exclude_dates",
            },
            where,
        )
        event_id = data.get("id")
        if not isinstance(event_id, str) or not ID_RE.fullmatch(event_id):
            raise ConfigError(f"{where}.id must match {ID_RE.pattern}")
        if event_id in ids:
            raise ConfigError(f"Duplicate event id: {event_id}")
        ids.add(event_id)
        enabled = data.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ConfigError(f"{where}.enabled must be boolean")
        description = data.get("description")
        if not isinstance(description, str):
            raise ConfigError(f"{where}.description must be a string")
        start, end = (
            _time(data.get("start"), f"{where}.start"),
            _time(data.get("end"), f"{where}.end"),
        )
        if end <= start:
            raise ConfigError(f"{where}.end must be after start; overnight events are unsupported")
        effective_raw = _mapping(data.get("effective", {}), f"{where}.effective")
        _only(effective_raw, {"from", "until"}, f"{where}.effective")
        effective = EffectiveRange(
            _date(effective_raw.get("from"), f"{where}.effective.from", nullable=True),
            _date(effective_raw.get("until"), f"{where}.effective.until", nullable=True),
        )
        if (
            effective.from_date
            and effective.until_date
            and effective.from_date > effective.until_date
        ):
            raise ConfigError(f"{where}.effective.from must not be after until")
        recurrence = _parse_recurrence(data.get("recurrence"), effective, f"{where}.recurrence")
        events.append(
            EventDefinition(
                event_id,
                enabled,
                description,
                start,
                end,
                recurrence,
                effective,
                _dates(data.get("exclude_dates", []), f"{where}.exclude_dates"),
            )
        )
    return SchedulerConfig(
        1,
        SchedulerSettings(timezone, days, float(timeout), batch),
        tuple(events),
        _dates(calendar_raw.get("exclude_dates", []), "calendar.exclude_dates"),
    )
