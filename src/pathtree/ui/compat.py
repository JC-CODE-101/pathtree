import uuid

from textual.widgets import Select

_MISSING = object()
SELECT_BLANK = getattr(Select, "BLANK", _MISSING)
SELECT_NULL = getattr(Select, "NULL", _MISSING)

# Clean, version-safe sentinel detection (blank sentinel is never a boolean)
_BLANK_SENTINEL = (
    SELECT_BLANK
    if (SELECT_BLANK is not _MISSING and not isinstance(SELECT_BLANK, bool))
    else (SELECT_NULL if SELECT_NULL is not _MISSING else None)
)


def resolve_optional_uuid(value) -> uuid.UUID | None:
    """Compatibility helper to resolve parent values.

    Maps both Select.BLANK and Select.NULL blank sentinels explicitly to None,
    maintains valid UUID parent values intact, and does not rely on truthiness.
    """
    if value is None:
        return None
    # Use explicitly resolved sentinels to avoid matching False if SELECT_BLANK is bool
    if (
        SELECT_BLANK is not _MISSING
        and not isinstance(SELECT_BLANK, bool)
        and value is SELECT_BLANK
    ):
        return None
    if SELECT_NULL is not _MISSING and value is SELECT_NULL:
        return None
    if isinstance(value, uuid.UUID):
        return value
    return None
