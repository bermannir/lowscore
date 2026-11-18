"""
Module: feel
Purpose: Hit-stop (freeze frames) requested by combat code and consumed by the game loop.
Dependencies: None
Used by: Player and Enemy (request) and core.game (consume).
"""

from __future__ import annotations

_freeze = 0.0


def freeze(seconds: float) -> None:
    """Pause gameplay for a moment so an impact lands with weight."""
    global _freeze
    _freeze = max(_freeze, seconds)


def consume(dt: float) -> bool:
    """Advance the freeze timer; return True while gameplay should stay paused."""
    global _freeze
    if _freeze <= 0:
        return False
    _freeze = max(0.0, _freeze - dt)
    return True


def reset() -> None:
    """Clear any pending freeze (e.g. on level start)."""
    global _freeze
    _freeze = 0.0
