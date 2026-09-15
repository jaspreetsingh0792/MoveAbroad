from __future__ import annotations


def records(payload: object, *keys: str) -> list[dict]:
    """Pull a list of record objects out of a payload of uncertain shape.

    These are public APIs we do not control: a field can go null, change type,
    or be renamed between runs. Anything that is not a list of objects yields
    nothing rather than raising halfway through a mapping loop.
    """
    if isinstance(payload, list):
        candidate: object = payload
    elif isinstance(payload, dict):
        candidate = next(
            (payload[key] for key in keys if isinstance(payload.get(key), list)),
            [],
        )
    else:
        candidate = []
    if not isinstance(candidate, list):
        return []
    return [item for item in candidate if isinstance(item, dict)]
