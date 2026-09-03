"""Audit-oriented renderers for frozen YGO-Bench runtime states."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "build_public_site",
    "load_ydk_sections",
    "parse_puzzle",
    "render_audit_board",
    "render_deck_board",
    "render_pilot_review_bundle",
    "validate_public_site",
]

_EXPORTS = {
    "build_public_site": (".public_site", "build_public_site"),
    "load_ydk_sections": (".deck_board", "load_ydk_sections"),
    "parse_puzzle": (".pilot_review", "parse_puzzle"),
    "render_audit_board": (".audit_board", "render_audit_board"),
    "render_deck_board": (".deck_board", "render_deck_board"),
    "render_pilot_review_bundle": (".pilot_review", "render_pilot_review_bundle"),
    "validate_public_site": (".public_site", "validate_public_site"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from error
    value = getattr(import_module(module_name, __name__), attribute_name)
    globals()[name] = value
    return value
