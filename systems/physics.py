"""
Module: physics
Purpose: Movement, bounds clamping, and vector helpers for entities.
Dependencies: lowscore.core.constants, lowscore.core.types
Used by: Player, Enemy AI, level systems, and the main game loop.
"""

from __future__ import annotations

from typing import Any

from core.constants import MAX_X, MAX_Y, MIN_X, MIN_Y
from core.types import Position, Vector2


def clamp_to_bounds(
    entity: Any,
    width: float = MAX_X,
    height: float = MAX_Y,
    min_x: float = MIN_X,
) -> None:
    """
    Keep an entity fully inside the horizontal range [min_x, width] and the floor's vertical range.

    The entity position is treated as its center point.
    """
    half_width = entity.width / 2
    half_height = entity.height / 2

    entity.position.x = clamp(entity.position.x, min_x + half_width, width - half_width)
    entity.position.y = clamp(entity.position.y, MIN_Y + half_height, height - half_height)


def calculate_direction(from_pos: Position, to_pos: Position) -> Vector2:
    """
    Return a normalized direction vector from one position to another.

    Returns a zero vector when both positions are the same.
    """
    return Vector2(to_pos.x - from_pos.x, to_pos.y - from_pos.y).normalized()


def clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a numeric value between minimum and maximum."""
    return max(minimum, min(value, maximum))

