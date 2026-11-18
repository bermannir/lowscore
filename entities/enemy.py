"""
Module: enemy
Purpose: Enemy actors: telegraphed slash/heavy/spin attacks, strafing, and the Fury-capable boss.
Dependencies: pygame, lowscore core/entities modules
Used by: core.game and renderer.
"""

from __future__ import annotations

import math
import random

import pygame

from core.constants import (
    AIR_DODGE_HEIGHT,
    BOSS_DAMAGE_BONUS,
    BOSS_FURY_PER_DAMAGE,
    BOSS_FURY_PER_HIT,
    BOSS_HP_MULTIPLIER,
    BOSS_SCALE,
    COLORS,
    ENEMY_ATTACK_MODES,
    DEPTH_SPEED_RATIO,
    ENEMY_ACCELERATION,
    ENEMY_ATTACK_RECOVERY,
    ENEMY_CIRCLE_RATE,
    ENEMY_DEFAULT_DAMAGE,
    ENEMY_DEFAULT_HP,
    ENEMY_DEFAULT_SPEED,
    ENEMY_DODGE_CHANCE,
    ENEMY_HEIGHT,
    ENEMY_STRAFE_COOLDOWN,
    ENEMY_WIDTH,
    FURY_COOLDOWN_SCALE,
    FURY_CRIT_CHANCE,
    FURY_DAMAGE_BONUS,
    FURY_DURATION,
    FIGHTER_SCALE,
    FURY_MAX,
    HITSTOP,
    HITSTUN,
    LANE_DEPTH,
    CRIT_MULTIPLIER,
)
from core.types import Position, Vector2
from entities.entity import Entity
from entities.player import Player
from systems.physics import calculate_direction, clamp_to_bounds
from systems import feel
from systems.audio import audio
from ui import art

ENEMY_VOLUME = 0.55

HIT_FLASH_DURATION = 0.12


class Enemy(Entity):
    """
    A brawler that lines up in the hero's depth lane, winds up, then strikes
    with one of three attack modes. Hits interrupt it; big hits knock it down.

    Attributes:
        cooldowns: Seconds until each attack mode is ready again.
        windup_mode: Mode being telegraphed, or None.
        windup_timer: Seconds left before the telegraphed strike lands.
        attack_mode: Mode of the current or last swing (for animation).
        attack_timer: Seconds left in the current swing animation.
        is_boss: Bosses are larger, tougher, and can enter Fury.
    """

    def __init__(self, position: Position, level: int = 1, is_boss: bool = False) -> None:
        hp = ENEMY_DEFAULT_HP + level * 7
        width, height = ENEMY_WIDTH, ENEMY_HEIGHT
        if is_boss:
            hp = round(hp * BOSS_HP_MULTIPLIER)
            width, height = round(width * BOSS_SCALE), round(height * BOSS_SCALE)
        super().__init__(
            position=position,
            width=width,
            height=height,
            hp=hp,
            color=COLORS["boss"] if is_boss else COLORS["enemy"],
        )
        self.level = level
        self.is_boss = is_boss
        self.speed = ENEMY_DEFAULT_SPEED + min(level - 1, 4) * 10 - (20 if is_boss else 0)
        self.damage = ENEMY_DEFAULT_DAMAGE + level + (BOSS_DAMAGE_BONUS if is_boss else 0)
        self.cooldowns = {mode: 0.0 for mode in ENEMY_ATTACK_MODES}
        self.recovery = 0.0
        self.windup_mode: str | None = None
        self.windup_timer = 0.0
        self.windup_total = 1.0
        self.attack_mode = "slash"
        self.attack_timer = 0.0
        self.hit_flash = 0.0
        self.last_hit_crit = False  # set by the player's attack, read by the renderer
        self.fury = 0.0
        self.fury_timer = 0.0
        self.look = art.BOSS_LOOK if is_boss else art.ENEMY_LOOKS[(level - 1) % len(art.ENEMY_LOOKS)]
        self.anim_offset = (id(self) % 97) / 9.7
        self.draw_scale = BOSS_SCALE if is_boss else 1.0  # drawn this much bigger than a regular foe
        self.reach_scale = 1.0  # big foes reach further with their normal attacks
        self.shows_boss_bar = is_boss  # bosses get the long bar at the bottom instead of a mini bar
        self.special_events: list[tuple[str, dict]] = []  # visual effects for the renderer
        self.acceleration = ENEMY_ACCELERATION
        self._dodged_swing = False

    @property
    def attack_cooldown(self) -> float:
        """Seconds until the basic slash is ready (kept for compatibility)."""
        return self.cooldowns["slash"]

    @property
    def is_fury_active(self) -> bool:
        """Return True while this (boss) enemy is in Fury."""
        return self.fury_timer > 0

    def update(self, dt: float, player: Player, world_width: float, world_height: float, min_x: float = 0) -> None:
        """Line up with the player, wind up and strike, dodge, and recover from hits."""
        if not self.is_alive():
            return

        self._tick_timers(dt)
        if not self.can_act:
            self.target_velocity = Vector2()
            self.windup_mode = None
            super().update(dt)
            clamp_to_bounds(self, world_width, world_height, min_x)
            return

        dx = player.position.x - self.position.x
        dy = player.position.y - self.position.y
        if abs(dx) > 4:
            self.face_sign = 1 if dx > 0 else -1
            self.facing = Vector2(self.face_sign, 0)

        if self.windup_mode is not None:
            self.target_velocity = Vector2()
            if self.windup_timer <= 0:
                self._strike(player)
        elif self.attack_timer > 0:
            self.target_velocity = Vector2()
        else:
            self._maybe_dodge(player, dx, dy)
            targetable = player.is_alive() and not player.is_lying
            mode = self._choose_attack(dx, dy) if targetable else None
            if mode is not None:
                self._start_windup(mode)
                self.target_velocity = Vector2()
            else:
                self._approach(player, dx)

        super().update(dt)
        clamp_to_bounds(self, world_width, world_height, min_x)
        if not self.target_velocity.is_zero() and abs(dx) > 4:
            self.face_sign = 1 if dx > 0 else -1  # keep facing the hero while walking

    def take_damage(self, amount: int) -> int:
        """Apply damage, interrupt the enemy (bosses in Fury shrug it off), and build boss Fury."""
        damage = super().take_damage(amount)
        if damage:
            self.hit_flash = HIT_FLASH_DURATION
            if not self.has_super_armor:
                self.windup_mode = None
                self.stun(HITSTUN)
            if self.is_boss:
                self._gain_fury(damage * BOSS_FURY_PER_DAMAGE)
        return damage

    @property
    def has_super_armor(self) -> bool:
        """A raging boss can't be interrupted or knocked down."""
        return self.is_boss and self.is_fury_active

    def knock_down(self, direction_x: float) -> None:
        """Knock down unless the boss is in Fury."""
        if self.has_super_armor:
            return
        self.windup_mode = None
        super().knock_down(direction_x)

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the monster: wind-up tell, styled swing, recoil, strafe trail, and health bar."""
        now = pygame.time.get_ticks() / 1000.0 + self.anim_offset
        feet_y = self.position.y + self.height / 2
        scale = FIGHTER_SCALE * self.draw_scale

        windup = None
        if self.windup_mode is not None:
            windup = 1 - self.windup_timer / max(1e-6, self.windup_total)
        swing = None
        if self.attack_timer > 0:
            swing = 1 - self.attack_timer / ENEMY_ATTACK_MODES[self.attack_mode]["duration"]

        if self.is_fury_active:
            art.draw_fury_aura(surface, self.position.x, feet_y, now)

        flash, flash_color = self.hit_flash / HIT_FLASH_DURATION, (255, 255, 255)
        if not flash and self.is_fury_active:
            flash, flash_color = 0.2 + 0.1 * math.sin(now * 10), (255, 120, 30)

        art.draw_fighter(
            surface,
            self.look,
            self.position.x,
            feet_y,
            now,
            moving=self.stride_amount > 0.05 or self.is_strafing,
            face_sign=self.face_sign,
            swing=swing,
            flash=flash,
            flash_color=flash_color,
            scale=scale,
            mode=self.windup_mode or self.attack_mode,
            fury=self.is_fury_active,
            windup=windup,
            recoil=self.hit_flash / HIT_FLASH_DURATION,
            ghosts=self.strafe_ghosts(),
            tilt=self.pose_tilt(),
            lift=self.z,
            visible=not self.is_blinking(now),
            gait=self.walk_phase + self.anim_offset,
            stride_amount=self.stride_amount,
            crouch=self.crouch,
            posture=self.posture(),
        )

        if self.hp < self.max_hp and not self.shows_boss_bar and not self.knocked:
            art.draw_mini_health(surface, self.position.x, feet_y - 94 * scale, self.hp / max(1, self.max_hp))

    def _tick_timers(self, dt: float) -> None:
        for mode in self.cooldowns:
            self.cooldowns[mode] = max(0.0, self.cooldowns[mode] - dt)
        self.recovery = max(0.0, self.recovery - dt)
        self.windup_timer = max(0.0, self.windup_timer - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.hit_flash = max(0.0, self.hit_flash - dt)
        self.fury_timer = max(0.0, self.fury_timer - dt)

    def _choose_attack(self, dx: float, dy: float) -> str | None:
        """Pick a ready attack whose reach covers the player in this lane, weighted by preference."""
        if self.recovery > 0 or abs(dy) > LANE_DEPTH:
            return None
        ready = [
            mode for mode, spec in ENEMY_ATTACK_MODES.items()
            if self.cooldowns[mode] <= 0 and abs(dx) <= spec["range"] * self.reach_scale
        ]
        if not ready:
            return None
        weights = [ENEMY_ATTACK_MODES[mode]["weight"] for mode in ready]
        return random.choices(ready, weights)[0]

    def _approach(self, player: Player, dx: float) -> None:
        """Walk to a striking spot beside the hero in their lane, Golden Axe style."""
        side = -1 if dx > 0 else 1  # stay on the side we're already on
        spot = Position(player.position.x + side * 56 * self.reach_scale, player.position.y)
        offset = Vector2(spot.x - self.position.x, spot.y - self.position.y)
        if offset.length() < 6:
            self.target_velocity = Vector2()
            return
        self._maybe_circle(calculate_direction(self.position, player.position), abs(dx))
        direction = offset.normalized()
        self.target_velocity = Vector2(direction.x * self.speed, direction.y * self.speed * DEPTH_SPEED_RATIO)

    def _start_windup(self, mode: str) -> None:
        self.windup_mode = mode
        if mode != "slash":
            audio.play("windup", ENEMY_VOLUME)
        self.windup_total = ENEMY_ATTACK_MODES[mode]["windup"] * (FURY_COOLDOWN_SCALE if self.is_fury_active else 1.0)
        self.windup_timer = self.windup_total

    def _strike(self, player: Player) -> None:
        """Land the telegraphed blow if the hero is still in lane and reach (they may have dodged)."""
        mode = self.windup_mode
        spec = ENEMY_ATTACK_MODES[mode]
        self.windup_mode = None
        self.attack_mode = mode
        self.attack_timer = spec["duration"]
        audio.play(mode, ENEMY_VOLUME)
        cooldown_scale = FURY_COOLDOWN_SCALE if self.is_fury_active else 1.0
        self.cooldowns[mode] = spec["cooldown"] * cooldown_scale
        self.recovery = ENEMY_ATTACK_RECOVERY * cooldown_scale

        dx = player.position.x - self.position.x
        dy = player.position.y - self.position.y
        lane = LANE_DEPTH * (1.4 if spec["full_circle"] else 1.0) + 6
        if not player.is_alive() or abs(dy) > lane or abs(dx) > spec["range"] * self.reach_scale + 8:
            return
        if player.z > AIR_DODGE_HEIGHT:
            return  # jumped over it
        if not spec["full_circle"] and dx * self.face_sign < -10:
            return

        damage = self.damage * spec["damage"]
        is_crit = False
        if self.is_fury_active:
            damage *= FURY_DAMAGE_BONUS
            is_crit = random.random() < FURY_CRIT_CHANCE
            if is_crit:
                damage *= CRIT_MULTIPLIER
        player.last_hit_crit = is_crit
        dealt = player.take_damage(max(1, round(damage)))
        if not dealt:
            return
        if spec["knockdown"] and player.is_alive():
            player.knock_down(1 if dx >= 0 else -1)
        feel.freeze(HITSTOP["crit"] if is_crit else HITSTOP["knockdown"] if spec["knockdown"] else HITSTOP["hit"])
        if self.is_boss:
            self._gain_fury(BOSS_FURY_PER_HIT)

    def _maybe_dodge(self, player: Player, dx: float, dy: float) -> None:
        """Sometimes sidestep out of the lane when the hero swings close by."""
        if not player.is_attacking:
            self._dodged_swing = False
            return
        if self._dodged_swing or abs(dx) > 95 or abs(dy) > LANE_DEPTH * 1.5:
            return
        self._dodged_swing = True
        if random.random() < ENEMY_DODGE_CHANCE + 0.05 * (self.level - 1):
            out_of_lane = Vector2(0, -1 if dy > 0 or (dy == 0 and random.random() < 0.5) else 1)
            if self.strafe(out_of_lane, ENEMY_STRAFE_COOLDOWN):
                audio.play("strafe", ENEMY_VOLUME)

    def _maybe_circle(self, to_player: Vector2, distance: float) -> None:
        """Occasionally sidestep while closing in, so enemies flank instead of beelining."""
        if 80 < distance < 240 and random.random() < ENEMY_CIRCLE_RATE / 60:
            if self.strafe(self._sideways(to_player), ENEMY_STRAFE_COOLDOWN):
                audio.play("strafe", ENEMY_VOLUME * 0.6)

    @staticmethod
    def _sideways(direction: Vector2) -> Vector2:
        side = Vector2(-direction.y, direction.x)
        return side if random.random() < 0.5 else side * -1

    def _face(self, direction: Vector2) -> None:
        if direction.is_zero():
            return
        self.facing = direction
        if abs(direction.x) > 0.2:
            self.face_sign = 1 if direction.x > 0 else -1

    def _gain_fury(self, amount: float) -> None:
        """Bosses only: fill the meter and erupt into Fury when it is full."""
        if not self.is_boss or self.is_fury_active:
            return
        self.fury = min(FURY_MAX, self.fury + amount)
        if self.fury >= FURY_MAX:
            self.fury = 0.0
            self.fury_timer = FURY_DURATION
            audio.play("boss_fury")
