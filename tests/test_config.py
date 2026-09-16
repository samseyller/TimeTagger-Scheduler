from pathlib import Path

import pytest

from timetagger_scheduler.config import ConfigError, load_config

BASE = """version: 1
settings: {timezone: America/Chicago, generate_days_ahead: 14}
events:
  - id: work
    enabled: true
    description: '#work Work'
    start: '08:00'
    end: '17:00'
    recurrence: {type: weekly, every: 1, weekdays: [monday]}
    effective: {from: 2026-09-01, until: null}
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "schedule.yaml"
    path.write_text(text, encoding="utf-8")
    return path


def test_valid(tmp_path):
    config = load_config(write(tmp_path, BASE))
    assert config.events[0].id == "work"


@pytest.mark.parametrize(
    "old,new",
    [
        ("    start: '08:00'", "    start: nope"),
        ("weekly, every: 1, weekdays: [monday]", "yearly, every: 1"),
        ("weekdays: [monday]", "weekdays: [funday]"),
        (
            "effective: {from: 2026-09-01, until: null}",
            "effective: {from: 2026-10-01, until: 2026-09-01}",
        ),
        ("timezone: America/Chicago", "timezone: Mars/Olympus"),
        ("every: 1", "every: 2"),
    ],
)
def test_invalid_variants(tmp_path, old, new):
    text = BASE.replace(old, new)
    if new == "every: 2":
        text = text.replace("    effective: {from: 2026-09-01, until: null}\n", "")
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, text))


def test_duplicate_ids(tmp_path):
    duplicate = BASE + BASE.split("events:\n", 1)[1]
    with pytest.raises(ConfigError, match="Duplicate"):
        load_config(write(tmp_path, duplicate))


@pytest.mark.parametrize(
    "rule",
    [
        "{type: monthly, day: 32}",
        "{type: monthly, weekday: monday, occurrence: 6}",
    ],
)
def test_invalid_monthly(tmp_path, rule):
    with pytest.raises(ConfigError):
        load_config(
            write(tmp_path, BASE.replace("{type: weekly, every: 1, weekdays: [monday]}", rule))
        )


def test_invalid_excluded_date(tmp_path):
    with pytest.raises(ConfigError):
        load_config(
            write(
                tmp_path,
                BASE.replace("events:", "calendar: {exclude_dates: [not-a-date]}\nevents:"),
            )
        )
