"""
Module: ember_demon
Purpose: The final boss: a winged demon that spits fire, summons imps, and calls down fire rain.
Dependencies: pygame, lowscore core/entities/ui modules
Used by: core.game (last wave of the last level) and the renderer (boss bar, intro).

Three phases (see FINAL_BOSS in core.constants):
    1  fire spit (one fireball) and summoning magic
    2  (below 65% HP) roars; fire spit becomes a 3-fireball spread, fire rain joins in
    3  (below 30% HP) enraged: 5-fireball spreads, faster, casts more often
He keeps the old boss's Fury: hitting him fills it, and in Fury he can't be staggered.
When he falls, every imp he summoned burns away with him.
"""

from __future__ import annotations

import math
import random

import pygame

from core.constants import (
    AIR_DODGE_HEIGHT,
    FINAL_BOSS,
    FIREBALL_HEIGHT,
    FIREBALL_HIT_REACH,
    LANE_DEPTH,
)
from core.types import Position
from entities.enemy import Enemy
from entities.mid_boss import MidBoss
from entities.player import Player
from systems.audio import audio
from ui import art

SUMMON_SPOTS = ((-150, -70), (-130, 80), (150, -70), (130, 80))  # where imps appear around him
IMP_HP_SHARE = 0.6
IMP_SPEED_BONUS = 50
IMP_SCALE = 0.85
FIREBALLS_PER_PHASE = (1, 3, 5)
EMBER_INTERVAL = 0.08


class EmberDemon(MidBoss):
    """The final boss. Attributes beyond MidBoss: stage (1..3), fireballs in flight, summon spots."""

    is_mid_boss = False

    def __init__(self, position: Position, level: int) -> None:
        super().__init__(position, level, spec={**FINAL_BOSS}, is_boss=True)
        self.name_key = "boss_name"
        self.stage = 1
        self.move_cooldowns = {move: 0.0 for move in FINAL_BOSS["moves"]}
        self.move_cooldowns["summon_magic"] = 4.0  # opens with fire before calling help
        self.fireballs: list[dict] = []
        self.summon_spots: list[tuple[float, float]] = []
        self._ember_clock = 0.0

    # ------------------------------------------------------------------
    # Phases
    # ------------------------------------------------------------------

    def take_damage(self, amount: int) -> int:
        damage = super().take_damage(amount)
        if not self.is_alive():
            self._burn_minions()
            return damage
        share = self.hp / self.max_hp
        phase_2, phase_3 = FINAL_BOSS["phases"]
        if self.stage == 1 and share <= phase_2:
            self._enter_stage(2)
        if self.stage == 2 and share <= phase_3:
            self._enter_stage(3)
        return damage

    def _enrage(self) -> None:
        """The mid-boss half-HP enrage is replaced by the demon's own phases."""

    def _enter_stage(self, stage: int) -> None:
        self.stage = stage
        self.signature_cooldown = min(self.signature_cooldown, 0.6)
        audio.play("boss_fury")
        self._emit("roar", reach=280, y=self.position.y)
        if stage == 3:
            self.enraged = True
            self.speed = round(self.speed * 1.25)

    def _burn_minions(self) -> None:
        for imp in self.minions:
            if imp.is_alive():
                self._emit("fire", x=imp.position.x, y=imp.position.y + imp.height / 2)
                imp.hp = 0
                imp.is_active = False
        self.fireballs.clear()
        self.hazards.clear()

    # ------------------------------------------------------------------
    # Choosing a move
    # ------------------------------------------------------------------

    def update(self, dt: float, player: Player, world_width: float, world_height: float, min_x: float = 0) -> None:
        if not self.is_alive():
            return
        for move in self.move_cooldowns:
            self.move_cooldowns[move] = max(0.0, self.move_cooldowns[move] - dt)
        self._update_fireballs(dt, player, min_x, world_width)
        self._ember_clock += dt
        if self._ember_clock >= EMBER_INTERVAL:
            self._ember_clock = 0.0
            self._emit("embers", count=2 if self.stage < 3 else 4)
        super().update(dt, player, world_width, world_height, min_x)

    def _signature_ready(self, player: Player) -> bool:
        if self.signature_cooldown > 0 or not self.can_act or self.windup_mode is not None or self.attack_timer > 0:
            return False
        if not player.is_alive() or player.is_lying:
            return False
        dx = abs(player.position.x - self.position.x)
        dy = abs(player.position.y - self.position.y)
        options = []
        for move, spec in FINAL_BOSS["moves"].items():
            if self.move_cooldowns[move] > 0 or spec["phase"] > self.stage:
                continue
            if move == "fire_spit" and not (110 < dx < 900 and dy < 260):
                continue
            if move == "summon_magic" and len(self.minions) >= spec["max_minions"]:
                continue
            options.append(move)
        if not options:
            return False
        # Prefer calling imps when alone, and spitting fire when the hero keeps their distance.
        weights = [3 if (m == "summon_magic" and not self.minions) or (m == "fire_spit" and dx > 260) else 1 for m in options]
        self.move = random.choices(options, weights)[0]
        self.spec = {**FINAL_BOSS, **FINAL_BOSS["moves"][self.move]}
        return True

    def _end_signature(self) -> None:
        self.phase = None
        speedup = (1.0, 0.85, 0.65)[self.stage - 1]
        self.move_cooldowns[self.move] = self.spec["cooldown"] * speedup
        self.signature_cooldown = FINAL_BOSS["move_gap"] * speedup * random.uniform(0.85, 1.15)
        self.recovery = 0.4

    # ------------------------------------------------------------------
    # Fire spit
    # ------------------------------------------------------------------

    def _fire_fire_spit(self, player: Player) -> None:
        """Spit a volley: one fireball at the hero, or a fan of them across nearby lanes."""
        self._swing("heavy")
        audio.play("fury", 0.7)
        count = FIREBALLS_PER_PHASE[self.stage - 1]
        mouth_x = self.position.x + self.face_sign * 30 * self.draw_scale
        floor_y = self.position.y + self.height / 2
        target_feet = player.position.y + player.height / 2
        travel = max(120.0, abs(player.position.x - mouth_x))
        speed = self.spec["speed"] * (1.15 if self.stage == 3 else 1.0)
        for i in range(count):
            offset = (i - (count - 1) / 2) * self.spec["spread"]
            vy = (target_feet + offset - floor_y) / (travel / speed)
            self.fireballs.append({"x": mouth_x, "floor": floor_y, "vx": self.face_sign * speed, "vy": vy, "life": 2.6})
        self._end_signature()

    def _update_fireballs(self, dt: float, player: Player, min_x: float, max_x: float) -> None:
        player_feet = player.position.y + player.height / 2
        flying = []
        for ball in self.fireballs:
            ball["x"] += ball["vx"] * dt
            ball["floor"] += ball["vy"] * dt
            ball["life"] -= dt
            if ball["life"] <= 0 or not (min_x - 50 < ball["x"] < max_x + 50):
                continue
            close = abs(player.position.x - ball["x"]) <= FIREBALL_HIT_REACH and abs(player_feet - ball["floor"]) <= LANE_DEPTH * 1.1
            if close and player.z <= AIR_DODGE_HEIGHT and player.is_alive():
                if self._hurt(player, self.spec_for("fire_spit")["power"], 1 if ball["vx"] > 0 else -1):
                    self._emit("burst", x=ball["x"], y=ball["floor"] - FIREBALL_HEIGHT)
                    continue
            flying.append(ball)
        self.fireballs = flying

    @staticmethod
    def spec_for(move: str) -> dict:
        return {**FINAL_BOSS, **FINAL_BOSS["moves"][move]}

    # ------------------------------------------------------------------
    # Summoning magic
    # ------------------------------------------------------------------

    def _prepare_summon_magic(self, player: Player) -> None:
        room = self.spec["max_minions"] - len(self.minions)
        count = min(room, self.spec["minions"] + (1 if self.stage == 3 else 0))
        feet = self.position.y + self.height / 2
        spots = random.sample(SUMMON_SPOTS, k=min(count, len(SUMMON_SPOTS)))
        self.summon_spots = [(self.position.x + dx, feet + dy) for dx, dy in spots]
        audio.play("shield", 0.6)

    def _fire_summon_magic(self, player: Player) -> None:
        self._swing("spin")
        audio.play("boss_fury", 0.6)
        for x, feet_y in self.summon_spots:
            imp = Enemy(Position(x, feet_y), self.level)
            imp.position.y -= imp.height / 2
            imp.max_hp = imp.hp = max(1, round(imp.max_hp * IMP_HP_SHARE))
            imp.speed += IMP_SPEED_BONUS
            imp.draw_scale = IMP_SCALE
            imp.invulnerable_timer = 0.4
            imp.recovery = 0.6
            self.minions.append(imp)
            self.spawn_requests.append(imp)
            self._emit("summon", x=x, y=feet_y)
        self.summon_spots = []
        self._end_signature()

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------

    def draw(self, surface: pygame.Surface) -> None:
        now = pygame.time.get_ticks() / 1000.0
        if self.phase == "windup":
            progress = 1 - self.phase_timer / max(0.01, self.phase_total)
            if self.move == "summon_magic":
                for x, y in self.summon_spots:
                    art.draw_magic_circle(surface, x, y, 60, progress, now)
            elif self.move == "fire_spit":  # flames gather in his mouth
                mouth = (self.position.x + self.face_sign * 28 * self.draw_scale, self.position.y - self.height * 0.62)
                glow = art.radial_glow(round(16 + 20 * progress), (255, 150, 50))
                surface.blit(glow, glow.get_rect(center=(round(mouth[0]), round(mouth[1]))), special_flags=pygame.BLEND_RGB_ADD)
        super().draw(surface)
        for ball in self.fireballs:
            art.draw_fireball(surface, ball["x"], ball["floor"] - FIREBALL_HEIGHT, ball["floor"], ball["vx"], ball["vy"], now)
