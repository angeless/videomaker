#!/usr/bin/env python3
"""Shared parameter parsing utilities for API route handlers."""

from __future__ import annotations

from typing import Any


def parse_int_param(
    value: Any,
    default: int,
    min_val: int = 0,
    max_val: int = 10000,
) -> int:
    """Parse an integer from a request parameter with bounds clamping.

    Safely converts *value* to int and clamps to [min_val, max_val].
    Returns *default* if conversion fails (None, empty string, non-numeric).

    >>> parse_int_param("42", default=10, min_val=1, max_val=100)
    42
    >>> parse_int_param(None, default=10, min_val=1, max_val=100)
    10
    >>> parse_int_param("abc", default=10, min_val=1, max_val=100)
    10
    >>> parse_int_param("-5", default=10, min_val=1, max_val=100)
    1
    >>> parse_int_param("999", default=10, min_val=1, max_val=100)
    100
    """
    try:
        v = int(value)
    except (TypeError, ValueError):
        return max(min_val, min(default, max_val))
    return max(min_val, min(v, max_val))


def parse_float_param(
    value: Any,
    default: float,
    min_val: float = 0.0,
    max_val: float = 1e9,
) -> float:
    """Parse a float from a request parameter with bounds clamping.

    >>> parse_float_param("3.14", default=1.0, min_val=0.0, max_val=10.0)
    3.14
    >>> parse_float_param(None, default=1.0, min_val=0.0, max_val=10.0)
    1.0
    """
    try:
        v = float(value)
    except (TypeError, ValueError):
        return max(min_val, min(default, max_val))
    return max(min_val, min(v, max_val))
