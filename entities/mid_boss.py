"""
Module: mid_boss
Purpose: Mid-level bosses (one per level) with a telegraphed signature move each.
Dependencies: pygame, lowscore core/entities/ui modules
Used by: core.game (spawned in each level's middle wave) and the renderer (boss bar, intro).

Every signature is announced on the ground before it lands, so it can be read and dodged:
    ground_pound  (Grukk the Ogre)       a red circle fills, then a shockwave knocks down anyone standing in it
    summon        (The Gravewarden)      raises ghouls from the floor around him
    bull_rush     (Warchief Gorrak)      a red lane flashes, then he charges across it; he is winded afterwards
    fire_pillars  (Brannoc the Pyre Ogre) glowing rings appear under and around the hero, then erupt
While performing a signature they can't be staggered or knocked down. At half HP they enrage.
"""

from __future__ import annotations

import math
import random

import pygame

from core.constants import (
    AIR_DODGE_HEIGHT,
    ENEMY_DEFAULT_DAMAGE,
    ENEMY_DEFAULT_HP,
    ENEMY_DEFAULT_SPEED,
    ENEMY_HEIGHT,
    ENEMY_WIDTH,
    FIGHTER_SCALE,
    HITSTOP,
    LANE_DEPTH,
    MID_BOSS_ENRAGE,
    MID_BOSS_ENRAGED_COOLDOWN,
    MID_BOSS_ENRAGED_SPEED,
    MID_BOSSES,
)
from core.types import Position, Vector2
from entities.enemy import Enemy
from entities.entity import Entity
from entities.player import Player
from systems import feel
from systems.audio import audio
from systems.physics import clamp_to_bounds
from ui import art

FIRST_SIGNATURE_DELAY = 2.5  # seconds after arriving before the first signature
RUSH_HIT_REACH = 56  # how close (x) the charging warchief must pass to hit the hero
SUMMON_SPREAD = 110  # summoned ghouls rise this far around the Gravewarden
PILLAR_SCATTER = 95  # extra fire pillars land within this distance of the hero


class MidBoss(Enemy):
    """
    A big, tough foe with normal attacks plus one signature move (see module docstring).

    Attributes:
        name_key: i18n key of the boss's name.
        move: Signature move name.
        phase: None, "windup" (telegraphing), or "active" (charging).
        enraged: Below half HP: faster signature and movement.
        spawn_requests: Foes this boss summoned, for the game to add to the fight.
        hazards: Fire pillars waiting to erupt: [x, y, time_left, total, radius, power].
    """

    is_mid_boss = True

    def __init__(self, position: Position, level: int, spec: dict | None = None, is_boss: bool = False) -> None:
        super().__init__(position, level, is_boss=is_boss)
        spec = spec if spec is not None else MID_BOSSES[level]
        self.spec = spec
        self.name_key = f"midboss_{spec['key']}"
        self.move = spec.get("move", "")
        self.look = art.MID_BOSS_LOOKS[spec["key"]]
        self.draw_scale = spec["scale"]
        self.reach_scale = spec["scale"] * 0.85
        self.shows_boss_bar = True
        self.width = round(ENEMY_WIDTH * spec["scale"])
        self.height = round(ENEMY_HEIGHT * spec["scale"])
        self.max_hp = self.hp = round((ENEMY_DEFAULT_HP + level * 7) * spec["hp"])
        self.damage = ENEMY_DEFAULT_DAMAGE + level + spec["damage"]
        self.speed = ENEMY_DEFAULT_SPEED + min(level - 1, 4) * 10 + spec["speed"]
        self.signature_cooldown = FIRST_SIGNATURE_DELAY
        self.phase: str | None = None
        self.phase_timer = 0.0
        self.phase_total = 1.0
        self.enraged = False
        self.rush_hit = False
        self.spawn_requests: list[Enemy] = []
        self.minions: list[Enemy] = []
        self.hazards: list[list[float]] = []

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def has_super_armor(self) -> bool:
        """Can't be staggered or knocked down mid-signature (or, for the final boss, in Fury)."""
        return self.phase is not None or super().has_super_armor

    def take_damage(self, amount: int) -> int:
        damage = super().take_damage(amount)
        if damage and not self.enraged and self.is_alive() and self.hp <= self.max_hp * MID_BOSS_ENRAGE:
            self._enrage()
        return damage

    def _enrage(self) -> None:
        self.enraged = True
        self.speed = round(self.speed * MID_BOSS_ENRAGED_SPEED)
        self.signature_cooldown = min(self.signature_cooldown, 1.0)
        audio.play("boss_fury")
        self._emit("roar", reach=220, y=self.position.y)

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, dt: float, player: Player, world_width: float, world_height: float, min_x: float = 0) -> None:
        if not self.is_alive():
            return
        self._update_hazards(dt, player)
        self.minions = [minion for minion in self.minions if minion.is_alive()]
        self.signature_cooldown = max(0.0, self.signature_cooldown - dt)

        if self.phase is not None:
            self._tick_timers(dt)
            self.phase_timer = max(0.0, self.phase_timer - dt)
            self.target_velocity = Vector2()
            self._update_signature(player)
            Entity.update(self, dt)
            clamp_to_bounds(self, world_width, world_height, min_x)
            return

        if self._signature_ready(player):
            self._begin_signature(player)
            Entity.update(self, dt)
            return
        super().update(dt, player, world_width, world_height, min_x)

    def _signature_ready(self, player: Player) -> bool:
        if self.signature_cooldown > 0 or not self.can_act or self.windup_mode is not None or self.attack_timer > 0:
            return False
        if not player.is_alive() or player.is_lying:
            return False
        dx = abs(player.position.x - self.position.x)
        dy = abs(player.position.y - self.position.y)
        if self.move == "ground_pound":
            return dx < self.spec["radius"] * 0.8 and dy < self.spec["radius"] * 0.3
        if self.move == "summon":
            return len(self.minions) < self.spec["max_minions"]
        if self.move == "bull_rush":
            return dy < LANE_DEPTH * 1.5 and 140 < dx < 700
        return dx < 650  # fire_pillars: anywhere on screen

    def _begin_signature(self, player: Player) -> None:
        self.phase = "windup"
        self.phase_total = self.phase_timer = self.spec["windup"] * (0.8 if self.enraged else 1.0)
        self.face_sign = 1 if player.position.x >= self.position.x else -1
        self.windup_mode = "heavy" if self.move != "summon" else "spin"  # raise the weapon: the pose telegraphs too
        self.windup_total = self.windup_timer = self.phase_total
        self.target_velocity = Vector2()
        self.velocity = Vector2()
        audio.play("windup", 0.8)
        prepare = getattr(self, f"_prepare_{self.move}", None)
        if prepare is not None:
            prepare(player)  # e.g. mark where the fire pillars or summoning circles will appear

    def _update_signature(self, player: Player) -> None:
        if self.phase == "windup":
            self.windup_timer = self.phase_timer
            if self.phase_timer > 0:
                return
            self.windup_mode = None
            getattr(self, f"_fire_{self.move}")(player)
        elif self.phase == "active":  # the warchief's charge
            self._check_rush_hit(player)
            if not self.is_strafing:
                self._end_signature()
                self.stun(self.spec["winded"])  # winded after the charge: the moment to punish him
                self._emit("dazed", y=self.position.y - self.height / 2, life=self.spec["winded"])

    def _end_signature(self) -> None:
        self.phase = None
        cooldown = self.spec["cooldown"] * (MID_BOSS_ENRAGED_COOLDOWN if self.enraged else 1.0)
        self.signature_cooldown = cooldown * random.uniform(0.85, 1.15)
        self.recovery = 0.6

    # ------------------------------------------------------------------
    # Signature moves
    # ------------------------------------------------------------------

    def _fire_ground_pound(self, player: Player) -> None:
        radius = self.spec["radius"]
        self._swing("heavy")
        audio.play("knockdown")
        self._emit("quake", reach=radius)
        # A floor shockwave: any hero off the ground (mid-jump) is safe, so the jump is easy to time.
        if self._in_ellipse(player, self.position.x, self.position.y, radius) and not player.is_airborne:
            self._hurt(player, self.spec["power"], 1 if player.position.x >= self.position.x else -1)
        self._end_signature()

    def _fire_summon(self, player: Player) -> None:
        self._swing("spin")
        audio.play("boss_fury", 0.6)
        room = self.spec["max_minions"] - len(self.minions)
        for i in range(min(self.spec["minions"], room)):
            side = -1 if i % 2 == 0 else 1
            x = self.position.x + side * SUMMON_SPREAD + random.uniform(-25, 25)
            y = self.position.y + random.uniform(-50, 50)
            ghoul = Enemy(Position(x, y), self.level)
            ghoul.invulnerable_timer = 0.6  # rising out of the ground
            ghoul.recovery = 0.8
            self.minions.append(ghoul)
            self.spawn_requests.append(ghoul)
            self._emit("grave", x=x, y=y + ghoul.height / 2)
        self._end_signature()

    def _fire_bull_rush(self, player: Player) -> None:
        self.phase = "active"
        self.rush_hit = False
        self.strafe_cooldown = 0.0
        self.strafe(Vector2(self.face_sign, 0), 0.0, self.spec["rush_distance"], self.spec["rush_time"])
        self.attack_mode = "heavy"
        audio.play("heavy")
        audio.play("strafe")

    def _check_rush_hit(self, player: Player) -> None:
        if self.rush_hit:
            return
        if abs(player.position.x - self.position.x) > RUSH_HIT_REACH or abs(player.position.y - self.position.y) > LANE_DEPTH * 1.3:
            return
        if player.z > AIR_DODGE_HEIGHT:
            return
        if self._hurt(player, self.spec["power"], self.face_sign):
            self.rush_hit = True
            self._emit("charge", face=self.face_sign)

    def _prepare_fire_pillars(self, player: Player) -> None:
        delay = self.spec["delay"] + self.phase_total
        spots = [(player.position.x, player.position.y)]
        for _ in range(self.spec["pillars"] - 1 + (1 if self.enraged else 0)):
            angle = random.uniform(0, 2 * math.pi)
            spots.append((player.position.x + math.cos(angle) * PILLAR_SCATTER, player.position.y + math.sin(angle) * PILLAR_SCATTER * 0.45))
        for x, y in spots:
            self.hazards.append([x, y + player.height / 2, delay, delay, self.spec["radius"], self.spec["power"]])

    def _fire_fire_pillars(self, player: Player) -> None:
        self._swing("heavy")
        self._end_signature()

    def _update_hazards(self, dt: float, player: Player) -> None:
        """Fire pillars count down, then erupt: anyone standing on one gets burned."""
        remaining = []
        for hazard in self.hazards:
            hazard[2] -= dt
            if hazard[2] > 0:
                remaining.append(hazard)
                continue
            x, feet_y, _, _, radius, power = hazard
            audio.play("fury", 0.5)
            self._emit("fire", x=x, y=feet_y)
            player_feet = player.position.y + player.height / 2
            if abs(player.position.x - x) <= radius and abs(player_feet - feet_y) <= radius * 0.45 and player.z <= AIR_DODGE_HEIGHT * 2:
                self._hurt(player, power, 1 if player.position.x >= x else -1)
        self.hazards = remaining

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _swing(self, mode: str) -> None:
        """Play the blow animation for a signature."""
        self.attack_mode = mode
        self.attack_timer = {"heavy": 0.3, "spin": 0.36}[mode]

    def _hurt(self, player: Player, power: float, direction: int) -> int:
        dealt = player.take_damage(max(1, round(self.damage * power)))
        if dealt:
            player.last_hit_crit = False
            if player.is_alive():
                player.knock_down(direction)
            feel.freeze(HITSTOP["knockdown"])
        return dealt

    @staticmethod
    def _in_ellipse(target: Entity, cx: float, cy: float, radius: float) -> bool:
        """Inside a floor circle (seen at an angle, so squashed vertically)."""
        dx = (target.position.x - cx) / radius
        dy = (target.position.y - cy) / (radius * 0.3)
        return dx * dx + dy * dy <= 1.0

    def _emit(self, kind: str, **data: object) -> None:
        data.setdefault("x", self.position.x)
        data.setdefault("y", self.position.y + self.height / 2)
        self.special_events.append((kind, data))

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the floor telegraphs first (so they sit under the fighters), then the boss."""
        now = pygame.time.get_ticks() / 1000.0
        feet_y = self.position.y + self.height / 2
        if self.phase == "windup":
            progress = 1 - self.phase_timer / max(0.01, self.phase_total)
            if self.move == "ground_pound":
                art.draw_danger_ellipse(surface, self.position.x, feet_y, self.spec["radius"], progress, now)
            elif self.move == "bull_rush":
                art.draw_danger_lane(surface, self.position.x, feet_y, self.face_sign, self.spec["rush_distance"], LANE_DEPTH * 1.3, progress, now)
        for x, y, left, total, radius, _ in self.hazards:
            art.draw_danger_ellipse(surface, x, y, radius, 1 - left / total, now, color=(255, 140, 40))
        if self.enraged and not self.knocked:
            art.draw_fury_aura(surface, self.position.x, feet_y, now)
        super().draw(surface)
