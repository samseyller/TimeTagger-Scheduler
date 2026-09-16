from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class SchedulerSettings:
    timezone: ZoneInfo
    generate_days_ahead: int = 14
    api_timeout_seconds: float = 10.0
    put_batch_size: int = 100


@dataclass(frozen=True)
class EffectiveRange:
    from_date: date | None = None
    until_date: date | None = None


@dataclass(frozen=True)
class RecurrenceDefinition:
    type: Literal["daily", "weekly", "monthly"]
    every: int = 1
    weekdays: tuple[int, ...] = ()
    day: int | None = None
    weekday: int | None = None
    occurrence: int | Literal["last"] | None = None


@dataclass(frozen=True)
class EventDefinition:
    id: str
    enabled: bool
    description: str
    start: time
    end: time
    recurrence: RecurrenceDefinition
    effective: EffectiveRange = EffectiveRange()
    exclude_dates: frozenset[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class SchedulerConfig:
    version: int
    settings: SchedulerSettings
    events: tuple[EventDefinition, ...]
    exclude_dates: frozenset[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Occurrence:
    event_id: str
    occurrence_date: date
    start: datetime
    end: datetime
    description: str
    key: str

    def to_record(self, modified_time: int) -> TimeTaggerRecord:
        return TimeTaggerRecord(
            key=self.key,
            t1=int(self.start.timestamp()),
            t2=int(self.end.timestamp()),
            ds=self.description,
            mt=modified_time,
            st=0.0,
        )


@dataclass(frozen=True)
class TimeTaggerRecord:
    key: str
    t1: int
    t2: int
    ds: str
    mt: int
    st: float = 0.0

    def as_api_dict(self) -> dict[str, str | int | float]:
        return {
            "key": self.key,
            "t1": self.t1,
            "t2": self.t2,
            "ds": self.ds,
            "mt": self.mt,
            "st": self.st,
        }


@dataclass(frozen=True)
class PutResult:
    accepted: tuple[str, ...]
    failed: tuple[str, ...]
    errors: tuple[str, ...]


@dataclass(frozen=True)
class MaterializationResult:
    calculated: int
    excluded: int
    already_materialized: int
    planned: int
    created: int
    failed: int
    occurrences: tuple[Occurrence, ...] = ()
