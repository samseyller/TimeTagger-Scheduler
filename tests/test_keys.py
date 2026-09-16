from datetime import date

from timetagger_scheduler.keys import occurrence_key


def test_key_stability_and_identity_only():
    first = occurrence_key("work", date(2026, 9, 22))
    assert first == occurrence_key("work", date(2026, 9, 22))
    assert first != occurrence_key("other", date(2026, 9, 22))
    assert first != occurrence_key("work", date(2026, 9, 23))
    assert first.startswith("ttsched-") and len(first) < 256
