from datetime import date
from uuid import UUID, uuid5

# Fixed forever: changing this would make every occurrence appear new.
NAMESPACE = UUID("abf12d9d-7be0-5c04-9071-a2dbe0b53153")


def occurrence_key(event_id: str, occurrence_date: date) -> str:
    """Return a stable identity independent of time and description."""
    return "ttsched-" + uuid5(NAMESPACE, f"{event_id}|{occurrence_date.isoformat()}").hex
