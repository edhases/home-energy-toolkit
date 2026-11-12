"""Shared helpers for the Device Watchdog integration."""

from __future__ import annotations

import re
from typing import Any

_ENTITY_SEPARATORS = re.compile(r"[,;\s]+")


def split_entity_list(value: Any) -> list[str]:
    """Split a multi-line/comma separated value into unique entity ids.

    The configuration stores the entity list as a list of strings, but the
    config flow asks the user for a free-form text block.  Accept both, plus
    tolerate semicolons and arbitrary whitespace between entries.
    """
    if value is None:
        return []

    if isinstance(value, str):
        tokens: list[str] = _ENTITY_SEPARATORS.split(value)
    elif isinstance(value, (list, tuple, set, frozenset)):
        tokens = [str(token) for token in value]
    else:
        tokens = _ENTITY_SEPARATORS.split(str(value))

    result: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        token = token.strip()
        if not token or token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result
