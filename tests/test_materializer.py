from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from timetagger_scheduler.client import UncertainWriteError
from timetagger_scheduler.keys import occurrence_key
from timetagger_scheduler.materializer import materialize
from timetagger_scheduler.models import PutResult, TimeTaggerRecord

NOW = datetime(2026, 9, 21, 7, tzinfo=ZoneInfo("America/Chicago"))


def record(key, ds="changed", t1=1, t2=2):
    return TimeTaggerRecord(key, t1, t2, ds, 1)


def test_first_run_and_second_run(weekly_config):
    client = Mock()
    client.get_all_records.return_value = []
    client.create_records.side_effect = lambda records: PutResult(
        tuple(r.key for r in records), (), ()
    )
    first = materialize(weekly_config, client, NOW)
    assert first.created == 3
    client.get_all_records.return_value = [record(o.key) for o in first.occurrences]
    second = materialize(weekly_config, client, NOW)
    assert second.created == 0 and second.already_materialized == 3
    assert client.create_records.call_count == 1


@pytest.mark.parametrize(
    "changed",
    [
        {"ds": "renamed"},
        {"ds": "HIDDEN user deleted"},
        {"t1": 999},
        {"t2": 999999},
    ],
)
def test_existing_key_is_always_skipped(weekly_config, changed):
    key = occurrence_key("work", NOW.date())
    client = Mock()
    client.get_all_records.return_value = [record(key, **changed)]
    client.create_records.side_effect = lambda records: PutResult(
        tuple(r.key for r in records), (), ()
    )
    materialize(weekly_config, client, NOW)
    submitted = [r.key for call in client.create_records.call_args_list for r in call.args[0]]
    assert key not in submitted


def test_moved_outside_window_still_skipped(weekly_config):
    key = occurrence_key("work", NOW.date())
    client = Mock()
    client.get_all_records.return_value = [record(key, t1=0, t2=1)]
    client.create_records.side_effect = lambda records: PutResult(
        tuple(r.key for r in records), (), ()
    )
    materialize(weekly_config, client, NOW)
    assert key not in [r.key for call in client.create_records.call_args_list for r in call.args[0]]


def test_unrelated_identical_record_does_not_count(weekly_config):
    client = Mock()
    client.get_all_records.return_value = [record("manual", "#work Work")]
    client.create_records.side_effect = lambda records: PutResult(
        tuple(r.key for r in records), (), ()
    )
    result = materialize(weekly_config, client, NOW)
    assert result.created == 3


def test_dry_run_never_puts(weekly_config):
    client = Mock()
    client.get_all_records.return_value = []
    result = materialize(weekly_config, client, NOW, dry_run=True)
    assert result.planned == 3
    client.create_records.assert_not_called()


def test_uncertain_put_propagates_without_retry(weekly_config):
    client = Mock()
    client.get_all_records.return_value = []
    client.create_records.side_effect = UncertainWriteError("uncertain")
    with pytest.raises(UncertainWriteError):
        materialize(weekly_config, client, NOW)
    assert client.create_records.call_count == 1
