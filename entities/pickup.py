"""
Module: pickup
Purpose: Golden Axe-style drops: blue magic pots (fill Fury), meat (heals), and the special
rewards goblin riders leave: bat elixir and wolf pelt (see core.game for their effects).
Dependencies: pygame, lowscore core/ui modules
Used by: core.game (spawn/collect) and renderer (draw).
"""

from __future__ import annotations

import math

import pygame

from core.constants import GRAVITY
from core.types import Position
from ui import art

LIFETIME = 12.0  # seconds before an uncollected drop vanishes (blinks for the last 2)
SPECIAL_LIFETIME = 20.0  # rider rewards wait longer
SPECIAL_KINDS = ("elixir", "pelt")


class Pickup:
    """
    A collectible that pops out of a defeated enemy and waits on the floor.

    Attributes:
        kind: "potion", "meat", or a rider reward ("elixir", "pelt").
        position: Floor position (center).
        z: Height during the pop-out bounce.
        age: Seconds since it dropped.
    """

    def __init__(self, kind: str, position: Position) -> None:
        self.kind = kind
        self.position = position
        self.z = 1.0
        self.vz = 260.0
        self.age = 0.0

    @property
    def expired(self) -> bool:
        """Return True once the drop has timed out."""
        return self.age >= self.lifetime

    @property
    def lifetime(self) -> float:
        return SPECIAL_LIFETIME if self.kind in SPECIAL_KINDS else LIFETIME

    def update(self, dt: float) -> None:
        """Advance the pop-out bounce and lifetime."""
        self.age += dt
        if self.z > 0 or self.vz > 0:
            self.vz -= GRAVITY * dt
            self.z += self.vz * dt
            if self.z <= 0:
                self.z = 0.0
                self.vz = -self.vz * 0.35 if self.vz < -120 else 0.0

    def draw(self, surface: pygame.Surface) -> None:
        """Draw with a gentle hover, a shadow, and a blink before vanishing."""
        if self.lifetime - self.age < 2.0 and int(self.age * 10) % 2 == 0:
            return
        hover = 0.0 if self.z > 0 else 2.5 + 2.5 * math.sin(self.age * 4)
        x, y = self.position.x, self.position.y
        shadow = art.soft_shadow(20, 7, 140)
        surface.blit(shadow, shadow.get_rect(center=(int(x), int(y) + 1)))
        if self.kind in SPECIAL_KINDS:
            art.draw_reward(surface, self.kind, x, y - self.z - hover, self.age)
        elif self.kind == "potion":
            art.draw_potion(surface, x, y - self.z - hover, self.age)
        else:
            art.draw_meat(surface, x, y - self.z - hover)
