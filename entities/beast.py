"""
Module: beast
Purpose: Goblin riders that join the waves (bat riders, wolf riders) and drop special rewards.
Dependencies: pygame, lowscore core/entities/ui modules
Used by: core.game (spawned with each wave; their reward is dropped on death) and the renderer.

    Bat rider   a goblin on a giant bat: hovers out of reach, screeches (eyes flare),
                then swoops down to strike. Hit it while it swoops low, or jump.   Drops a Bat Elixir.
    Wolf rider  a goblin raider on a warg: circles at a distance, crouches and snarls,
                then lunges (the leap is aimed when the snarl starts).             Drops a Wolf Pelt.
"""

from __future__ import annotations

import math
import random

import pygame

from core.constants import (
    AIR_DODGE_HEIGHT,
    BAT_HOVER_HEIGHT,
    BAT_SWOOP_TIME,
    BEASTS,
    FIGHTER_SCALE,
    HITSTOP,
    LANE_DEPTH,
    WOLF_LUNGE_DISTANCE,
    WOLF_LUNGE_TIME,
)
from core.types import Position, Vector2
from entities.enemy import Enemy
from entities.entity import Entity
from entities.player import Player
from systems import feel
from systems.audio import audio
from systems.physics import clamp_to_bounds
from ui import art

BEAST_VOLUME = 0.5


class Beast(Enemy):
    """
    Shared body of the special creatures: stats from BEASTS, a small state machine, and a reward.

    Attributes:
        kind: "bat_rider" or "wolf_rider".
        reward: Pickup kind dropped on death.
        reward_score: Bonus score for the kill.
        state: Current behaviour state; state_timer counts down within it.
    """

    def __init__(self, position: Position, level: int, kind: str) -> None:
        super().__init__(position, level)
        spec = BEASTS[kind]
        self.kind = kind
        self.reward = spec["reward"]
        self.reward_score = spec["score"]
        self.max_hp = self.hp = spec["hp"] + spec["hp_per_level"] * (level - 1)
        self.damage = spec["damage"] + level
        self.speed = spec["speed"] + random.uniform(-15, 15)
        self.width, self.height = spec["size"]
        self.state = "approach"
        self.state_timer = random.uniform(0.5, 1.5)
        self.attack_cooldown_left = random.uniform(1.0, 2.0)
        self.side = random.choice((-1, 1))  # which side of the hero it prefers
        self.bit = False

    # Behaviour shared by the ground beasts --------------------------------

    def _begin(self, state: str, seconds: float) -> None:
        self.state = state
        self.state_timer = seconds
        self.bit = False

    def _bite(self, player: Player, reach: float, depth: float, power: float = 1.0, knockdown: bool = False) -> int:
        """Land a bite if the hero is within reach, in lane, and on the ground; once per attack."""
        if self.bit or not player.is_alive():
            return 0
        if abs(player.position.x - self.position.x) > reach or abs(player.position.y - self.position.y) > depth:
            return 0
        if player.z > AIR_DODGE_HEIGHT:
            return 0
        dealt = player.take_damage(max(1, round(self.damage * power)))
        if dealt:
            self.bit = True
            player.last_hit_crit = False
            if knockdown and player.is_alive():
                player.knock_down(1 if player.position.x >= self.position.x else -1)
            feel.freeze(HITSTOP["knockdown"] if knockdown else HITSTOP["hit"])
            audio.play("hit", BEAST_VOLUME)
        return dealt

    def _move_toward(self, x: float, y: float, speed: float) -> None:
        offset = Vector2(x - self.position.x, y - self.position.y)
        if offset.length() < 6:
            self.target_velocity = Vector2()
            return
        direction = offset.normalized()
        self.target_velocity = Vector2(direction.x * speed, direction.y * speed * 0.8)

    def _face_player(self, player: Player) -> None:
        dx = player.position.x - self.position.x
        if abs(dx) > 4:
            self.face_sign = 1 if dx > 0 else -1

    # Drawing --------------------------------------------------------------

    def _pose(self) -> tuple[str, float]:
        """(pose name, telegraph charge 0..1) for the art."""
        return "stand", 0.0

    def draw(self, surface: pygame.Surface) -> None:
        now = pygame.time.get_ticks() / 1000.0 + self.anim_offset
        feet_y = self.position.y + self.height / 2
        pose, charge = self._pose()
        if self.knocked and not self.is_airborne:
            pose = "dead"
        moving = self.stride_amount > 0.05 or self.is_strafing
        canvas = art.render_beast(self.kind, now, self.walk_phase, self.stride_amount if moving else 0.0, pose, charge, self.face_sign)
        scale = FIGHTER_SCALE
        w, h = canvas.get_size()
        canvas = pygame.transform.smoothscale(canvas, (round(w * scale), round(h * scale)))
        if self.hit_flash > 0:
            canvas.fill(art.shade((255, 255, 255), self.hit_flash / 0.12), special_flags=pygame.BLEND_RGB_ADD)
        self._draw_telegraph(surface, feet_y, now)
        shadow_w = self.width * 1.6 if self.kind != "bat_rider" else 40
        shadow = art.soft_shadow(round(shadow_w), 12, 150)
        surface.blit(shadow, shadow.get_rect(center=(round(self.position.x), round(feet_y))))
        if self.is_blinking(now):
            return
        ax, ay = art.BEAST_ANCHOR
        surface.blit(canvas, (round(self.position.x - ax * scale), round(feet_y - self.z - ay * scale)))
        if self.hp < self.max_hp and not self.knocked:
            top = feet_y - self.z - (70 if self.kind == "bat_rider" else self.height * 1.9)
            art.draw_mini_health(surface, self.position.x, top, self.hp / max(1, self.max_hp))

    def _draw_telegraph(self, surface: pygame.Surface, feet_y: float, now: float) -> None:
        """Floor warnings drawn under the rider (none yet)."""

    def render_corpse(self, now: float) -> tuple[pygame.Surface, float]:
        """The bodies left behind (mount and rider), and how high the image centre sits above the floor."""
        canvas = art.render_beast(self.kind, now, 0.0, 0.0, "dead", 0.0, self.face_sign)
        scale = FIGHTER_SCALE
        w, h = canvas.get_size()
        canvas = pygame.transform.smoothscale(canvas, (round(w * scale), round(h * scale)))
        ay = art.BEAST_ANCHOR[1]
        lift = (ay - 12 - h / 2 / scale) * scale if self.kind == "bat_rider" else (ay - h / 2 / scale) * scale
        return canvas, lift


class WolfRider(Beast):
    """A goblin on a warg: circles the hero at a distance, crouches (telegraph), lunges, then backs off."""

    STALK_DISTANCE = 150
    CROUCH_TIME = 0.4

    def __init__(self, position: Position, level: int) -> None:
        super().__init__(position, level, "wolf_rider")
        self.lunge_aim = (1.0, 0.0)

    def update(self, dt: float, player: Player, world_width: float, world_height: float, min_x: float = 0) -> None:
        if not self.is_alive():
            return
        self._tick_timers(dt)
        self.state_timer -= dt
        self.attack_cooldown_left -= dt
        if not self.can_act:
            self.state = "stalk"
            self.target_velocity = Vector2()
        else:
            self._think(player)
        Entity.update(self, dt)
        clamp_to_bounds(self, world_width, world_height, min_x)

    def _think(self, player: Player) -> None:
        dx = player.position.x - self.position.x
        dy = player.position.y - self.position.y
        if self.state == "crouch":
            self.target_velocity = Vector2()
            if self.state_timer <= 0:
                self._lunge(*self.lunge_aim)
            return
        if self.state == "lunge":
            self._bite(player, 46, LANE_DEPTH * 1.2)
            if not self.is_strafing:
                self._begin("retreat", 0.6)
            return
        self._face_player(player)
        if self.state == "retreat":
            self._move_toward(self.position.x - self.face_sign * 120, self.position.y, self.speed * 0.6)
            if self.state_timer <= 0:
                self._begin("stalk", 0)
                self.side = random.choice((-1, 1)) if random.random() < 0.3 else self.side
            return
        side = -1 if dx > 0 else 1  # stay on the side it's on
        spot_x = player.position.x + side * self.STALK_DISTANCE
        self._move_toward(spot_x, player.position.y, self.speed)
        ready = self.attack_cooldown_left <= 0 and player.is_alive() and not player.is_lying
        if ready and abs(spot_x - self.position.x) < 50 and abs(dy) < LANE_DEPTH:
            self._begin("crouch", self.CROUCH_TIME)
            self.lunge_aim = (dx, dy)  # the leap is aimed when the growl starts: moving during it dodges
            self.target_velocity = Vector2()
            self.velocity = Vector2()
            audio.play("windup", BEAST_VOLUME)

    def _lunge(self, dx: float, dy: float) -> None:
        direction = Vector2(1 if dx > 0 else -1, max(-0.3, min(0.3, dy / 200)))
        self._begin("lunge", WOLF_LUNGE_TIME)
        self.strafe_cooldown = 0.0
        self.strafe(direction, 0.0, WOLF_LUNGE_DISTANCE, WOLF_LUNGE_TIME)
        self.attack_cooldown_left = random.uniform(1.6, 2.6)
        audio.play("strafe", BEAST_VOLUME)

    def _pose(self) -> tuple[str, float]:
        if self.state == "crouch":
            return "crouch", 1 - max(0.0, self.state_timer) / self.CROUCH_TIME
        if self.state == "lunge":
            return "lunge", 0.0
        return "run", 0.0


class BatRider(Beast):
    """
    A goblin on a giant bat: flies above the fight, screeches, swoops down to strike,
    hangs low beside the hero for a moment (hit it now), then climbs away.
    """

    SCREECH_TIME = 0.4
    RISE_TIME = 0.45
    LINGER_TIME = 0.6  # after a dive it hangs low beside the hero: the moment to hit back
    SWOOP_HEIGHT = 10
    SWOOP_STOP = 46  # the dive ends this far in front of the hero, not on top of them

    def __init__(self, position: Position, level: int) -> None:
        super().__init__(position, level, "bat_rider")
        self.z = BAT_HOVER_HEIGHT
        self.state = "hover"
        self.state_timer = random.uniform(1.2, 2.8)
        self.phase_offset = random.uniform(0, 6.28)
        self.swoop_from = (0.0, 0.0, 0.0)
        self.swoop_to = (0.0, 0.0)

    def knock_down(self, direction_x: float) -> None:
        """A hit bat tumbles and flutters back up instead of hitting the floor."""
        if self.is_alive():
            self.stun(0.3)
            self._begin("rise", self.RISE_TIME)

    def take_damage(self, amount: int) -> int:
        damage = super().take_damage(amount)
        if damage and self.is_alive():
            self._begin("rise", self.RISE_TIME)
        return damage

    def update(self, dt: float, player: Player, world_width: float, world_height: float, min_x: float = 0) -> None:
        if not self.is_alive():
            return
        self._tick_timers(dt)
        self.stun_timer = max(0.0, self.stun_timer - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.state_timer -= dt
        self.walk_phase += dt * 10
        t = pygame.time.get_ticks() / 1000.0 + self.phase_offset

        if self.state == "screech":
            if self.state_timer <= 0:
                self._begin("swoop", BAT_SWOOP_TIME)
                self.swoop_from = (self.position.x, self.position.y, self.z)
                approach = 1 if self.position.x < player.position.x else -1
                self.swoop_to = (player.position.x - approach * self.SWOOP_STOP, player.position.y)
                audio.play("strafe", BEAST_VOLUME)
        elif self.state == "swoop":
            k = 1 - max(0.0, self.state_timer) / BAT_SWOOP_TIME
            (sx, sy, sz), (tx, ty) = self.swoop_from, self.swoop_to
            self.position.x = sx + (tx - sx) * k
            self.position.y = sy + (ty - sy) * k
            self.z = sz + (self.SWOOP_HEIGHT - sz) * min(1.0, k * 1.4)
            if self.z < 30:
                self._bite(player, self.SWOOP_STOP + 22, LANE_DEPTH * 1.2)
            if self.state_timer <= 0:
                bit = self.bit
                self._begin("linger", self.LINGER_TIME)
                self.bit = bit
        elif self.state == "linger":
            self.z = self.SWOOP_HEIGHT + math.sin(t * 9) * 3
            if self.state_timer <= 0:
                self.side = -self.side
                self._begin("rise", self.RISE_TIME)
        elif self.state == "rise":
            self.z = min(BAT_HOVER_HEIGHT, self.z + (BAT_HOVER_HEIGHT / self.RISE_TIME) * dt)
            self._fly_toward(player.position.x + self.side * 120, player.position.y - 30, self.speed * 0.8, dt)
            if self.state_timer <= 0:
                self._begin("hover", random.uniform(1.4, 3.0))
        else:  # hover: circle near the hero, bobbing
            self.z = BAT_HOVER_HEIGHT + math.sin(t * 3) * 6
            orbit_x = player.position.x + self.side * (110 + math.sin(t * 0.9) * 30)
            orbit_y = player.position.y + math.sin(t * 0.7) * 40
            self._fly_toward(orbit_x, orbit_y, self.speed, dt)
            if self.state_timer <= 0 and self.can_act and player.is_alive() and not player.is_lying:
                self._begin("screech", self.SCREECH_TIME)
                audio.play("windup", BEAST_VOLUME)

        if self.state != "swoop":
            self._face_player(player)
        clamp_to_bounds(self, world_width, world_height, min_x)

    def _fly_toward(self, x: float, y: float, speed: float, dt: float) -> None:
        offset = Vector2(x - self.position.x, y - self.position.y)
        distance = offset.length()
        if distance < 2:
            return
        step = min(distance, speed * dt)
        self.position.x += offset.x / distance * step
        self.position.y += offset.y / distance * step

    def _pose(self) -> tuple[str, float]:
        if self.state == "screech":
            return "screech", 1 - max(0.0, self.state_timer) / self.SCREECH_TIME
        if self.state in ("swoop", "linger"):
            return "swoop", 0.6
        return "fly", 0.0


BEAST_TYPES = {"bat_rider": BatRider, "wolf_rider": WolfRider}
