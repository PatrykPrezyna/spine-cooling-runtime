from datetime import datetime, timezone


def utc_iso_timestamp() -> str:
    """Return a timezone-aware ISO 8601 timestamp in local time."""
    return datetime.now(timezone.utc).astimezone().isoformat()
