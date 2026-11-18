"""
Module: input_handler
Purpose: Keyboard input polling and edge-triggered action detection.
Dependencies: pygame, lowscore.core.types
Used by: Main game loop and player update logic.
"""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from core.constants import DOUBLE_TAP_WINDOW
from core.types import Direction, Vector2

# Every key whose press (not hold) triggers something in a fight.
EDGE_KEYS = (
    pygame.KSCAN_R, pygame.KSCAN_A, pygame.KSCAN_E, pygame.KSCAN_Q, pygame.KSCAN_F, pygame.KSCAN_W, pygame.KSCAN_SPACE,
    pygame.KSCAN_LEFT, pygame.KSCAN_RIGHT, pygame.KSCAN_UP, pygame.KSCAN_DOWN,
)


def is_down(keys: pygame.key.ScancodeWrapper, scancode: int) -> bool:
    """
    Return True if the physical key with this scancode is held.

    Controls are read by physical position (pygame.KSCAN_*), not by the letter a
    key types: with a Hebrew (or any non-Latin) layout active, the R key types
    "ר", so looking up pygame.K_r would never see it pressed. Indexing the raw
    tuple bypasses ScancodeWrapper's letter-to-key translation.
    """
    return bool(tuple.__getitem__(keys, scancode))


@dataclass
class InputState:
    """
    Snapshot of player input for one frame.

    Attributes:
        move_vector: Directional movement vector, not yet scaled by speed.
        move_direction: Cardinal direction for simple facing/animation logic.
        is_attacking: True only on the frame the attack key is pressed.
        is_shielding: True only on the frame the shield key is pressed.
        is_heavy: True only on the frame the heavy attack key is pressed.
        is_spin: True only on the frame the spin attack key is pressed.
        is_fury: True only on the frame the fury key is pressed.
        is_special: True only on the frame the special-ability key (W) is pressed.
        strafe_direction: Set on the frame a direction key is double-tapped.
        is_jumping: True only on the frame the jump key (Space) is pressed.
        wants_quit: True when the player requests closing the game.
    """

    move_vector: Vector2
    move_direction: Direction
    is_attacking: bool
    is_shielding: bool
    wants_quit: bool = False
    is_heavy: bool = False
    is_spin: bool = False
    is_fury: bool = False
    is_special: bool = False
    strafe_direction: Vector2 | None = None
    is_jumping: bool = False


class InputHandler:
    """
    Polls pygame keyboard state and returns a frame-level InputState.

    Attack and shield are edge-triggered: holding a key down only emits the
    action on the first pressed frame.
    """

    def __init__(self) -> None:
        """Initialize previous key state tracking."""
        self._previous_pressed: dict[int, bool] = {}
        self._last_tap: dict[int, float] = {}

    def handle_input(self) -> InputState:
        """Poll keyboard state and return input for the current frame."""
        keys = pygame.key.get_pressed()

        move_vector = self._get_movement_vector(keys)
        move_direction = self.get_movement_direction(move_vector)

        return InputState(
            move_vector=move_vector,
            move_direction=move_direction,
            is_attacking=self._just_pressed(keys, pygame.KSCAN_R),
            is_shielding=self._just_pressed(keys, pygame.KSCAN_A),
            wants_quit=is_down(keys, pygame.KSCAN_ESCAPE),
            is_heavy=self._just_pressed(keys, pygame.KSCAN_E),
            is_spin=self._just_pressed(keys, pygame.KSCAN_Q),
            is_fury=self._just_pressed(keys, pygame.KSCAN_F),
            is_special=self._just_pressed(keys, pygame.KSCAN_W),
            strafe_direction=self._double_tap_direction(keys),
            is_jumping=self._just_pressed(keys, pygame.KSCAN_SPACE),
        )

    def sync(self) -> None:
        """
        Record which keys are held without emitting any actions.

        Call this while gameplay isn't polling (menus, story, pause) so a key still
        held from confirming a menu (e.g. SPACE) isn't seen as a fresh press on the
        first frame of the fight.
        """
        keys = pygame.key.get_pressed()
        for scancode in EDGE_KEYS:
            self._previous_pressed[scancode] = is_down(keys, scancode)
        self._last_tap.clear()

    def _double_tap_direction(self, keys: pygame.key.ScancodeWrapper) -> Vector2 | None:
        """Return the direction of an arrow key pressed twice within DOUBLE_TAP_WINDOW."""
        now = pygame.time.get_ticks() / 1000.0
        result = None
        for key, vector in (
            (pygame.KSCAN_LEFT, Vector2(-1, 0)),
            (pygame.KSCAN_RIGHT, Vector2(1, 0)),
            (pygame.KSCAN_UP, Vector2(0, -1)),
            (pygame.KSCAN_DOWN, Vector2(0, 1)),
        ):
            if not self._just_pressed(keys, key):
                continue
            if now - self._last_tap.get(key, -1.0) <= DOUBLE_TAP_WINDOW:
                result = vector
                self._last_tap[key] = -1.0
            else:
                self._last_tap[key] = now
        return result

    def _just_pressed(self, keys: pygame.key.ScancodeWrapper, scancode: int) -> bool:
        """Return True only on the first frame a physical key is held."""
        pressed = is_down(keys, scancode)
        fresh = pressed and not self._previous_pressed.get(scancode, False)
        self._previous_pressed[scancode] = pressed
        return fresh

    def get_movement_direction(self, move_vector: Vector2) -> Direction:
        """
        Convert a movement vector into one cardinal direction.

        Horizontal movement wins ties so left/right facing feels stable during
        diagonal movement.
        """
        if move_vector.is_zero():
            return Direction.NONE

        if abs(move_vector.x) >= abs(move_vector.y):
            return Direction.RIGHT if move_vector.x > 0 else Direction.LEFT

        return Direction.DOWN if move_vector.y > 0 else Direction.UP

    def _get_movement_vector(self, keys: pygame.key.ScancodeWrapper) -> Vector2:
        """Build a movement vector from arrow keys."""
        x = 0.0
        y = 0.0

        if is_down(keys, pygame.KSCAN_LEFT):
            x -= 1.0
        if is_down(keys, pygame.KSCAN_RIGHT):
            x += 1.0
        if is_down(keys, pygame.KSCAN_UP):
            y -= 1.0
        if is_down(keys, pygame.KSCAN_DOWN):
            y += 1.0

        return Vector2(x, y)

