"""
Module: ally
Purpose: Auto-played helper heroes for the two bonuses: Ally Call (one hero, 30 s) and Heroes' Rally
         (every other hero, until the boss wave is cleared).
Dependencies: pygame, lowscore core/entities/ui modules
Used by: core.game (summons, updates, dismisses) and the renderer (draws, effects).

An ally is a full Player (same moves, combos, and specials) driven by a small brain instead of the
keyboard. Enemies keep hunting the real hero, so allies never get hurt; their hits score for the
team, and they don't freeze the fight on impact (only the real hero's hits do).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import pygame

from core.constants import AIR_DODGE_HEIGHT, LANE_DEPTH
from core.types import Direction, Position, Vector2
from entities.entity import Entity
from entities.player import Player
from ui import art

ALLY_VOLUME = 0.35
THINK_INTERVAL = (0.1, 0.22)  # seconds between decisions, varied so allies don't move in lockstep
STRIKE_GAP = 58  # how far beside a foe an ally stands to strike
REACH_X = 88
SPREAD = 46  # allies line up at different depths around their target instead of stacking


@dataclass
class AllyInput:
    """What the ally's brain 'presses' this frame (the same fields the keyboard input has)."""

    move_vector: Vector2 = field(default_factory=Vector2)
    move_direction: Direction = Direction.NONE
    is_attacking: bool = False
    is_shielding: bool = False
    is_jumping: bool = False
    strafe_direction: Vector2 | None = None


class Ally(Player):
    """
    A helper hero played by the computer.

    Attributes:
        time_left: Seconds until it leaves (None: stays until the boss wave is cleared).
        rally: True for Heroes' Rally helpers.
        slot: Its place in the formation (spreads allies around a foe).
    """

    def __init__(self, position: Position, character_name: str, difficulty: str, time_left: float | None, rally: bool, slot: int) -> None:
        super().__init__(position, character_name, difficulty)
        self.time_left = time_left
        self.total_time = time_left
        self.rally = rally
        self.slot = slot
        self.sound_volume = ALLY_VOLUME
        self.freezes_on_hit = False
        self.think_timer = random.uniform(*THINK_INTERVAL)
        self.plan = AllyInput()
        self.special_cooldown = random.uniform(1.0, 4.0)  # don't all fire their specials at once

    @property
    def expired(self) -> bool:
        return self.time_left is not None and self.time_left <= 0

    def take_damage(self, amount: int) -> int:
        """Allies fight on untouched (enemies keep hunting the real hero)."""
        return 0

    def update_ai(self, dt: float, enemies: list[Entity], leader: Player) -> None:
        """Pick a foe, walk to a striking spot beside it, and fight with combos, heavies, and specials."""
        if self.time_left is not None:
            self.time_left -= dt
        self.think_timer -= dt
        foes = [foe for foe in enemies if foe.is_alive() and not foe.is_lying]
        if self.think_timer <= 0:
            self.think_timer = random.uniform(*THINK_INTERVAL)
            self.plan = self._decide(foes, enemies, leader)
        self.update(dt, self.plan)
        self.plan.is_jumping = False  # jumps and dodges are one-shot presses

    def _decide(self, foes: list[Entity], enemies: list[Entity], leader: Player) -> AllyInput:
        plan = AllyInput()
        if not foes:  # nothing to fight: stay close to the hero
            side = -1 if self.slot % 2 == 0 else 1
            return self._walk_to(plan, leader.position.x + side * (70 + 25 * self.slot), leader.position.y + (self.slot - 2) * 18)

        target = min(foes, key=lambda foe: abs(foe.position.x - self.position.x) + 2 * abs(foe.position.y - self.position.y))
        dx = target.position.x - self.position.x
        dy = target.position.y - self.position.y
        side = -1 if dx > 0 else 1
        lane_offset = ((self.slot % 3) - 1) * (LANE_DEPTH * 0.5)
        flying = target.z > AIR_DODGE_HEIGHT

        in_reach = abs(dx) <= REACH_X and abs(dy) <= LANE_DEPTH * 0.8
        if in_reach:
            self.face_sign = 1 if dx > 0 else -1
            if flying and not self.is_airborne:
                plan.is_jumping = True  # bat riders: leap up to them
            elif self.special_ready and random.random() < 0.25:
                self.use_special(enemies)
            elif random.random() < 0.15 and self.can_attack("heavy"):
                self.heavy_attack(enemies)
            else:
                self.light_attack(enemies)
            return plan
        return self._walk_to(plan, target.position.x + side * STRIKE_GAP, target.position.y + lane_offset * (0 if abs(dx) < 120 else 1))

    def _walk_to(self, plan: AllyInput, x: float, y: float) -> AllyInput:
        offset = Vector2(x - self.position.x, y - self.position.y)
        if offset.length() > 8:
            plan.move_vector = offset.normalized()
        return plan

    def draw(self, surface: pygame.Surface) -> None:
        """A golden ring marks a helper; a timed ally also shows how long it stays."""
        feet_y = self.position.y + self.height / 2
        now = pygame.time.get_ticks() / 1000.0
        art.draw_ally_ring(surface, self.position.x, feet_y, now, rally=self.rally)
        super().draw(surface)
        if self.time_left is not None and self.total_time:
            ratio = max(0.0, self.time_left / self.total_time)
            top = feet_y - self.z - 118
            pygame.draw.rect(surface, (20, 14, 10), (self.position.x - 22, top, 44, 5), border_radius=2)
            pygame.draw.rect(surface, (240, 200, 90), (self.position.x - 21, top + 1, round(42 * ratio), 3), border_radius=2)
