"""
Module: types
Purpose: Shared types: positions, vectors, rectangles, and the game-flow / direction enums.
Dependencies: None
Used by: Entities, systems, and renderer modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto
from math import sqrt


@dataclass
class Position:
    """
    A two-dimensional world position.

    Attributes:
        x: Horizontal position in pixels.
        y: Vertical position in pixels.
    """

    x: float
    y: float

    def distance_to(self, other: "Position") -> float:
        """Return the Euclidean distance to another position."""
        dx = self.x - other.x
        dy = self.y - other.y
        return sqrt(dx * dx + dy * dy)

    def copy(self) -> "Position":
        """Return a copy of this position."""
        return Position(self.x, self.y)


@dataclass
class Vector2:
    """
    A two-dimensional vector for movement and direction.

    Attributes:
        x: Horizontal vector component.
        y: Vertical vector component.
    """

    x: float = 0.0
    y: float = 0.0

    def __add__(self, other: "Vector2") -> "Vector2":
        """Return the sum of two vectors."""
        return Vector2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vector2") -> "Vector2":
        """Return the difference between two vectors."""
        return Vector2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vector2":
        """Return this vector multiplied by a scalar."""
        return Vector2(self.x * scalar, self.y * scalar)

    def __truediv__(self, scalar: float) -> "Vector2":
        """Return this vector divided by a scalar."""
        if scalar == 0:
            return Vector2()
        return Vector2(self.x / scalar, self.y / scalar)

    def length(self) -> float:
        """Return the vector magnitude."""
        return sqrt(self.x * self.x + self.y * self.y)

    def normalized(self) -> "Vector2":
        """Return a unit-length copy of this vector."""
        magnitude = self.length()
        if magnitude == 0:
            return Vector2()
        return self / magnitude

    def is_zero(self) -> bool:
        """Return True when this vector has no movement."""
        return self.x == 0 and self.y == 0


@dataclass
class Rectangle:
    """
    A lightweight rectangle for bounds and collision calculations.

    Attributes:
        x: Left coordinate in pixels.
        y: Top coordinate in pixels.
        width: Rectangle width in pixels.
        height: Rectangle height in pixels.
    """

    x: float
    y: float
    width: float
    height: float

    @property
    def left(self) -> float:
        """Return the left edge."""
        return self.x

    @property
    def right(self) -> float:
        """Return the right edge."""
        return self.x + self.width

    @property
    def top(self) -> float:
        """Return the top edge."""
        return self.y

    @property
    def bottom(self) -> float:
        """Return the bottom edge."""
        return self.y + self.height

    def intersects(self, other: "Rectangle") -> bool:
        """Return True when this rectangle overlaps another rectangle."""
        return (
            self.left < other.right
            and self.right > other.left
            and self.top < other.bottom
            and self.bottom > other.top
        )


class GameState(Enum):
    """
    High-level state of the running game.

    The main Game class uses this enum to decide which update and render
    paths should run each frame.
    """

    HOME = auto()
    CHARACTER_SELECT = auto()
    STORY = auto()
    LEVEL = auto()
    PAUSED = auto()
    SETTINGS = auto()
    GAME_OVER = auto()
    LEVEL_COMPLETE = auto()
    FINAL_VICTORY = auto()
    QUIT = auto()


class Direction(Enum):
    """
    Cardinal movement directions used by the input and physics systems.

    Diagonal movement is represented by Vector2 values in the input state;
    this enum remains useful for simple facing and animation decisions.
    """

    UP = auto()
    DOWN = auto()
    LEFT = auto()
    RIGHT = auto()
    NONE = auto()
