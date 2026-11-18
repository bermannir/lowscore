"""
Module: entity
Purpose: Base entity class for all visible gameplay objects.
Dependencies: lowscore.core.constants, lowscore.core.types
Used by: Player, Enemy, Boss, Projectile, combat, physics, and renderer.
"""

from __future__ import annotations

import math
from typing import Tuple

import pygame

from core.constants import (
    ACCELERATION,
    AIR_CONTROL,
    APEX_BAND,
    APEX_GRAVITY,
    COLORS,
    DECELERATION,
    DOWN_TIME,
    GETUP_INVULNERABLE,
    GETUP_TIME,
    GRAVITY,
    KNOCKDOWN_LAUNCH,
    KNOCKDOWN_SPEED,
    LAND_CROUCH,
    STRAFE_COOLDOWN,
    STRAFE_DISTANCE,
    STRAFE_DURATION,
    STRIDE_LENGTH,
)
from core.types import Position, Rectangle, Vector2
from systems.audio import audio


class Entity:
    """
    Base class for all game objects that have position, size, and health.

    Attributes:
        position: Center position in world/screen pixels.
        velocity: Movement vector in pixels per second.
        width: Entity width in pixels.
        height: Entity height in pixels.
        hp: Current hit points.
        max_hp: Maximum hit points.
        color: RGB color used for placeholder rendering.
        is_active: Whether the entity should update and render.
        target_velocity: Desired velocity; the actual velocity accelerates toward it.
        walk_phase: Walk-cycle phase in radians, advanced by distance travelled.
        stride_amount: 0 standing .. 1 full stride, eased from the current speed.
        z: Height above the ground (jumps and knockdown flights).
        knocked: True from a knockdown hit until the fighter starts getting up.
        stun_timer: Hitstun; the fighter can't act while it runs.
        invulnerable_timer: Blinking grace period after getting up.
    """

    def __init__(
        self,
        position: Position,
        width: int,
        height: int,
        hp: int,
        color: Tuple[int, int, int] = COLORS["white"],
    ) -> None:
        """Initialize the entity with position, dimensions, health, and color."""
        self.position = position
        self.velocity = Vector2()
        self.width = width
        self.height = height
        self.hp = hp
        self.max_hp = hp
        self.color = color
        self.is_active = True
        self.facing = Vector2(1.0, 0.0)
        self.face_sign = 1
        self.strafe_timer = 0.0
        self.strafe_cooldown = 0.0
        self.strafe_direction = Vector2()
        self.strafe_speed = STRAFE_DISTANCE / STRAFE_DURATION
        self.z = 0.0
        self.vz = 0.0
        self.knocked = False
        self.knock_vx = 0.0
        self.knock_age = 0.0
        self.down_timer = 0.0
        self.getup_timer = 0.0
        self.invulnerable_timer = 0.0
        self.stun_timer = 0.0
        self.target_velocity = Vector2()
        self.acceleration = ACCELERATION
        self.deceleration = DECELERATION
        self.walk_phase = 0.0
        self.stride_amount = 0.0
        self.land_timer = 0.0

    @property
    def crouch(self) -> float:
        """Knee bend from 0..1 right after landing."""
        return self.land_timer / LAND_CROUCH if self.land_timer > 0 else 0.0

    @property
    def is_airborne(self) -> bool:
        """Return True while off the ground."""
        return self.z > 0 or self.vz > 0

    @property
    def is_lying(self) -> bool:
        """Return True while knocked flat on the ground."""
        return self.knocked and not self.is_airborne

    @property
    def can_act(self) -> bool:
        """Return True when not knocked down, getting up, or in hitstun."""
        return not self.knocked and self.getup_timer <= 0 and self.stun_timer <= 0

    @property
    def is_invulnerable(self) -> bool:
        """Return True when hits should pass through (dodging, lying down, getting up)."""
        return self.is_strafing or self.invulnerable_timer > 0 or self.is_lying or self.getup_timer > 0

    def knock_down(self, direction_x: float) -> None:
        """Launch the fighter into the air and away, to land flat on their back."""
        self.knocked = True
        self.knock_age = 0.0
        self.vz = KNOCKDOWN_LAUNCH
        self.z = max(self.z, 1.0)
        self.knock_vx = KNOCKDOWN_SPEED if direction_x >= 0 else -KNOCKDOWN_SPEED
        self.strafe_timer = 0.0
        self.stun_timer = 0.0
        self.velocity = Vector2()
        self.target_velocity = Vector2()

    def stun(self, seconds: float) -> None:
        """Interrupt the fighter for a moment."""
        self.stun_timer = max(self.stun_timer, seconds)

    def posture(self) -> str | None:
        """Knockdown stance for the art: flailing in the air, limp on the floor, or kneeling up."""
        if self.knocked:
            return "flail" if self.is_airborne else "limp"
        if self.getup_timer > 0:
            return "kneel"
        return None

    def pose_tilt(self) -> float:
        """Degrees the body is tipped over: leaning back in flight, 90 flat on the floor, upright when kneeling."""
        if self.knocked:
            return 70.0 * min(1.0, self.knock_age / 0.3) if self.is_airborne else 90.0
        return 0.0

    def is_blinking(self, now: float) -> bool:
        """Arcade-style flicker during post-getup invulnerability."""
        return self.invulnerable_timer > 0 and int(now * 20) % 2 == 0

    @property
    def is_strafing(self) -> bool:
        """Return True during a strafe dash (which also dodges damage)."""
        return self.strafe_timer > 0

    def strafe(
        self, direction: Vector2, cooldown: float = STRAFE_COOLDOWN, distance: float = STRAFE_DISTANCE, duration: float = STRAFE_DURATION
    ) -> bool:
        """
        Dash a short distance in a direction without changing facing (special moves may dash further).

        Returns:
            True if the strafe started.
        """
        if self.strafe_cooldown > 0 or direction.is_zero() or not self.is_alive():
            return False
        self.strafe_direction = direction.normalized()
        self.strafe_timer = duration
        self.strafe_speed = distance / duration
        self.strafe_cooldown = cooldown
        return True

    def update(self, dt: float) -> None:
        """Update jump/knockdown physics, then the active strafe or normal movement."""
        self.strafe_cooldown = max(0.0, self.strafe_cooldown - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.stun_timer = max(0.0, self.stun_timer - dt)
        self.land_timer = max(0.0, self.land_timer - dt)
        self._update_vertical(dt)

        if self.knocked or self.getup_timer > 0 or self.strafe_timer > 0:
            self._advance_gait(dt, 0.0)
        if self.knocked:
            self.knock_age += dt
            if self.is_airborne:
                self.position.x += self.knock_vx * dt
            else:
                self.down_timer -= dt
                if self.down_timer <= 0 and self.is_alive():  # the fallen stay down
                    self.knocked = False
                    self.getup_timer = GETUP_TIME
            return
        if self.getup_timer > 0:
            self.getup_timer = max(0.0, self.getup_timer - dt)
            if self.getup_timer == 0:
                self.invulnerable_timer = GETUP_INVULNERABLE
            return

        if self.strafe_timer > 0:
            self.strafe_timer = max(0.0, self.strafe_timer - dt)
            speed = self.strafe_speed
            self.position.x += self.strafe_direction.x * speed * dt
            self.position.y += self.strafe_direction.y * speed * dt
            return

        self._steer(dt)
        self.position.x += self.velocity.x * dt
        self.position.y += self.velocity.y * dt
        self._advance_gait(dt, self.velocity.length())

        heading = self.target_velocity if not self.target_velocity.is_zero() else self.velocity
        if heading.length() > 1:
            self.facing = heading.normalized()
            if abs(self.facing.x) > 0.2:
                self.face_sign = 1 if self.facing.x > 0 else -1

    def _steer(self, dt: float) -> None:
        """Accelerate toward target_velocity (weaker in the air) for weight and momentum."""
        diff = self.target_velocity - self.velocity
        gap = diff.length()
        if gap == 0:
            return
        speeding_up = self.target_velocity.length() >= self.velocity.length()
        rate = self.acceleration if speeding_up else self.deceleration
        if self.is_airborne:
            rate *= AIR_CONTROL
        step = rate * dt
        self.velocity = self.target_velocity if gap <= step else self.velocity + diff * (step / gap)

    def _advance_gait(self, dt: float, speed: float) -> None:
        """Advance the walk cycle by distance travelled and ease the stride size toward the speed."""
        self.walk_phase += speed * dt * math.pi / STRIDE_LENGTH
        top_speed = max(1.0, getattr(self, "speed", speed or 1.0))
        target = min(1.0, speed / top_speed) if not self.is_airborne else 0.0
        self.stride_amount += (target - self.stride_amount) * min(1.0, dt * 12)

    def _update_vertical(self, dt: float) -> None:
        if self.z <= 0 and self.vz <= 0:
            return
        hang = APEX_GRAVITY if abs(self.vz) < APEX_BAND and not self.knocked else 1.0  # float at the top of a jump
        self.vz -= GRAVITY * hang * dt
        self.z += self.vz * dt
        if self.z <= 0:
            self.z = 0.0
            self.vz = 0.0
            self.on_land()

    def on_land(self) -> None:
        """Called when touching down after a jump or knockdown flight."""
        if self.knocked:
            self.down_timer = DOWN_TIME
            audio.play("knockdown", 0.8)
        else:
            self.land_timer = LAND_CROUCH

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the entity as a placeholder rectangle."""
        pygame.draw.rect(surface, self.color, self.get_pygame_rect())

    def take_damage(self, amount: int) -> int:
        """
        Reduce current hit points by the given amount.

        Returns:
            The actual damage applied after clamping.
        """
        if amount <= 0 or not self.is_alive() or self.is_invulnerable:
            return 0

        previous_hp = self.hp
        self.hp = max(0, self.hp - amount)

        if self.hp == 0:
            self.is_active = False

        return previous_hp - self.hp

    def heal(self, amount: int) -> int:
        """
        Restore hit points up to max_hp.

        Returns:
            The actual amount healed.
        """
        if amount <= 0 or not self.is_alive():
            return 0

        previous_hp = self.hp
        self.hp = min(self.max_hp, self.hp + amount)
        return self.hp - previous_hp

    def is_alive(self) -> bool:
        """Return True if the entity has hit points and is active."""
        return self.is_active and self.hp > 0

    def strafe_ghosts(self) -> tuple[tuple[float, float], ...]:
        """Afterimage offsets trailing a strafe, for the renderer."""
        if not self.is_strafing:
            return ()
        d = self.strafe_direction
        return tuple((-d.x * step, -d.y * step) for step in (14, 28, 42))

    def get_rect(self) -> Rectangle:
        """Return a lightweight rectangle representing the entity bounds."""
        return Rectangle(
            self.position.x - self.width / 2,
            self.position.y - self.height / 2,
            self.width,
            self.height,
        )

    def get_pygame_rect(self) -> pygame.Rect:
        """Return a pygame.Rect representing the entity bounds."""
        rect = self.get_rect()
        return pygame.Rect(
            int(rect.x),
            int(rect.y),
            int(rect.width),
            int(rect.height),
        )
