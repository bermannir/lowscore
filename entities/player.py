"""
Module: player
Purpose: Player-controlled character for LOWSCORE.
Dependencies: lowscore.core.constants, lowscore.core.types, lowscore.entities.entity
Used by: Game loop, renderer, combat, and input systems.
"""

from __future__ import annotations

import math
import random
from typing import Any, Iterable

import pygame

from core.constants import (
    AIR_DODGE_HEIGHT,
    ATTACK_MODES,
    ATTACK_RANGE,
    CHARACTER_DAMAGE,
    CHARACTER_HP,
    CHARACTER_SPEEDS,
    COLORS,
    COMBO_WINDOW,
    DEPTH_SPEED_RATIO,
    FIGHTER_SCALE,
    CRIT_CHANCE,
    CRIT_MULTIPLIER,
    DEFAULT_DIFFICULTY,
    DIFFICULTY_DAMAGE_TAKEN,
    DIFFICULTY_HP_REGEN,
    FURY_COOLDOWN_SCALE,
    FURY_CRIT_CHANCE,
    FURY_DAMAGE_BONUS,
    FURY_DURATION,
    FURY_MAX,
    FURY_PER_CRIT,
    FURY_PER_HIT,
    HIT_CHAIN_WINDOW,
    HITSTOP,
    HITSTUN,
    HP_REGEN_DELAY,
    AIR_HIT_HOVER,
    JUMP_SPEED,
    JUMP_SQUAT,
    LANE_DEPTH,
    PLAYER_DEFAULT_DAMAGE,
    PLAYER_DEFAULT_HP,
    PLAYER_DEFAULT_SPEED,
    PLAYER_HEIGHT,
    PLAYER_WIDTH,
    SHIELD_CHARGES,
    SHIELD_DAMAGE_MULTIPLIER,
    SHIELD_DURATION,
    SPECIALS,
    STRAFE_COOLDOWN,
    SCORE_COMBO_BONUS,
    SCORE_PER_DAMAGE,
    THROW_REACH,
)
from core.types import Position, Vector2
from entities.entity import Entity
from systems import feel
from systems.audio import audio
from ui import art

HURT_FLASH_DURATION = 0.15
ATTACK_BUFFER = 0.25  # an R press during a swing is remembered this long
AIR_COMBO = ("air1", "air2", "jump")
COMBO_MODES = ("slash", "slash2", "finisher", "throw")
# Which synthesized sound each attack mode uses.
# Which body animation each special ability plays.
SPECIAL_POSES = {
    "charge": "dash", "arrow": "finisher", "shadow_step": "finisher",
    "holy_light": "heavy", "war_cry": "heavy", "earthquake": "heavy",
}
SHADOW_STEP_GAP = 48  # how far behind the target the rogue reappears
ATTACK_SOUNDS = {"air1": "slash", "air2": "slash", "slash2": "slash", "finisher": "heavy", "jump": "slash", "dash": "heavy"}


class Player(Entity):
    """
    A playable character controlled by keyboard input.

    Attributes:
        character_name: Selected character identifier.
        speed: Movement speed in pixels per second.
        damage: Base attack damage.
        cooldowns: Seconds remaining before each attack mode can be used again.
        attack_mode: Mode of the current or last attack (see ATTACK_MODES).
        combo_step: Position in the R chain (1 slash, 2 back-swing, 3 finisher/throw).
        hit_chain: Consecutive hits landed, for the on-screen counter and score bonus.
        score: Points earned this level (banked by the game).
        attack_timer: Seconds remaining in the current attack visual state.
        fury: Fury meter, 0..FURY_MAX, filled by landing hits.
        fury_timer: Seconds of Fury buff remaining.
        shield_charges: Remaining defensive charges.
        special: This hero's special ability (see SPECIALS), used with the W key.
        special_cooldown: Seconds until the special can be used again.
        rage_timer: Seconds of the Barbarian's war-cry damage boost remaining.
        special_events: Visual events (kind, data) for the renderer to turn into effects.
        is_attacking: Whether the player is currently in an attack window.
        is_shielding: Whether the player is currently shielding.
    """

    def __init__(
        self,
        position: Position,
        character_name: str = "ran",
        difficulty: str = DEFAULT_DIFFICULTY,
    ) -> None:
        """Initialize the player using character and difficulty defaults when available."""
        self.character_name = character_name
        self.difficulty = difficulty
        self.damage_taken_multiplier = DIFFICULTY_DAMAGE_TAKEN.get(difficulty, 1.0)
        self.hp_regen = DIFFICULTY_HP_REGEN.get(difficulty, 0.0)
        self.look = art.CHARACTER_LOOKS.get(character_name, art.PLAYER_LOOK)
        self.speed = CHARACTER_SPEEDS.get(character_name, PLAYER_DEFAULT_SPEED)
        self.damage = CHARACTER_DAMAGE.get(character_name, PLAYER_DEFAULT_DAMAGE)
        hp = CHARACTER_HP.get(character_name, PLAYER_DEFAULT_HP)

        super().__init__(
            position=position,
            width=PLAYER_WIDTH,
            height=PLAYER_HEIGHT,
            hp=hp,
            color=COLORS["player"],
        )

        self.cooldowns = {mode: 0.0 for mode in ATTACK_MODES}
        self.cooldown_totals = {mode: spec["cooldown"] for mode, spec in ATTACK_MODES.items()}
        self.attack_mode = "slash"
        self.attack_duration = ATTACK_MODES["slash"]["duration"]
        self.attack_timer = 0.0
        self.fury = 0.0
        self.fury_timer = 0.0
        self.last_hit_crit = False  # set by a boss crit, read by the renderer
        self.shield_charges = SHIELD_CHARGES
        self.special = SPECIALS.get(character_name, SPECIALS["ran"])
        self.special_cooldown = 0.0
        self.special_total = self.special["cooldown"]
        self.rage_timer = 0.0
        self.special_events: list[tuple[str, dict]] = []
        self.sound_volume = 1.0  # helpers (auto-played allies) play their sounds quieter
        self.freezes_on_hit = True  # helpers' hits don't freeze the whole fight
        self.shield_timer = 0.0
        self.is_attacking = False
        self.is_shielding = False
        self.hurt_flash = 0.0
        self.regen_delay = 0.0
        self._regen_progress = 0.0
        self.combo_step = 0
        self.combo_timer = 0.0
        self.air_step = 0
        self.jump_squat = 0.0
        self.buffered_attack = 0.0
        self.hit_chain = 0
        self.chain_timer = 0.0
        self.score = 0

    def update(self, dt: float, input_state: Any | None = None) -> None:
        """
        Update player movement and action timers.

        The input_state object is expected to expose move_vector, is_attacking,
        and is_shielding attributes once systems.input_handler is implemented.
        """
        self._update_timers(dt)

        if not self.can_act:
            self.target_velocity = Vector2()
        elif input_state is not None:
            self._apply_input(input_state)

        super().update(dt)

    @property
    def attack_cooldown(self) -> float:
        """Seconds until the basic slash is ready (kept for HUD/compat)."""
        return self.cooldowns["slash"]

    @property
    def is_fury_active(self) -> bool:
        """Return True while the Fury buff is running."""
        return self.fury_timer > 0

    def light_attack(self, enemies: Iterable[Entity]) -> list[Entity]:
        """
        The R button, Golden Axe style.

        In the air it's the next hit of the air combo (slash, back-slash, then a
        knockdown plunge), while strafing a dash attack, otherwise the next hit of
        the ground chain: slash, back-swing, then a knockdown finisher, which
        becomes a throw when hugging an enemy.
        """
        enemies = list(enemies)
        if self.attack_timer > 0 or not self.can_act:
            self.buffer_attack()  # fire as soon as this swing ends or the hero recovers from a hit
            return []
        step = 0
        if self.is_airborne:
            mode = AIR_COMBO[self.air_step] if self.air_step < len(AIR_COMBO) else None
        elif self.is_strafing:
            mode = "dash"
        else:
            step = self.combo_step + 1 if self.combo_timer > 0 else 1
            if step >= 3:
                mode = "throw" if self._grab_target(enemies) is not None else "finisher"
            else:
                mode = "slash" if step == 1 else "slash2"

        if mode is None or not self.can_attack(mode):
            return []  # keep any buffered press so it fires once the move is ready
        self.buffered_attack = 0.0
        hits = self.attack(enemies, mode)
        if mode in COMBO_MODES:
            self.combo_step = 0 if step >= 3 else step
            self.combo_timer = COMBO_WINDOW + ATTACK_MODES[mode]["duration"]
        if mode in AIR_COMBO:
            self.air_step = AIR_COMBO.index(mode) + 1
            if mode != "jump":
                self.vz = max(self.vz, AIR_HIT_HOVER)  # each swing holds the hero up a moment
        return hits

    def heavy_attack(self, enemies: Iterable[Entity]) -> list[Entity]:
        """E: a heavy swing on the ground, or straight into the downward plunge in the air."""
        if self.is_airborne:
            if self.air_step >= len(AIR_COMBO):
                return []
            hits = self.attack(enemies, "jump")
            if self.attack_mode == "jump":
                self.air_step = len(AIR_COMBO)
            return hits
        return self.attack(enemies, "heavy")

    def attack(self, enemies: Iterable[Entity] | None = None, mode: str = "slash") -> list[Entity]:
        """
        Start an attack of the given mode if it is ready.

        Hits only land on enemies in the same depth lane and in front (unless the
        mode hits all around). Each hit rolls for a critical, stuns or knocks the
        target down, builds the hit chain and Fury, and freezes the action for a beat.

        Args:
            enemies: Optional iterable of entities to check against attack range.
            mode: One of the ATTACK_MODES keys.

        Returns:
            Entities that were damaged.
        """
        if not self.can_act or not self.can_attack(mode):
            return []

        spec = ATTACK_MODES[mode]
        cooldown = spec["cooldown"] * (FURY_COOLDOWN_SCALE if self.is_fury_active else 1.0)
        self.is_attacking = True
        self._sfx(ATTACK_SOUNDS.get(mode, mode))
        self.attack_mode = mode
        self.attack_duration = spec["duration"]
        self.attack_timer = spec["duration"]
        self.cooldowns[mode] = cooldown
        self.cooldown_totals[mode] = cooldown

        if enemies is None:
            return []

        if mode == "throw":
            target = self._grab_target(list(enemies))
            targets = [target] if target is not None else []
        else:
            targets = [
                enemy for enemy in enemies
                if self.is_in_attack_range(enemy, spec["range"], spec["full_circle"], spec.get("depth"))
            ]

        landed: list[Entity] = []
        any_crit = False
        for enemy in targets:
            damage, is_crit = self.roll_damage(spec["damage"])
            enemy.last_hit_crit = is_crit
            dealt = enemy.take_damage(damage)
            if not dealt:
                continue
            landed.append(enemy)
            any_crit = any_crit or is_crit
            self._register_hit(dealt)
            if mode == "throw":
                enemy.position.x = self.position.x - self.face_sign * 30
                enemy.knock_down(-self.face_sign)
            elif spec["knockdown"]:
                away = enemy.position.x - self.position.x if spec["full_circle"] else self.face_sign
                enemy.knock_down(away)
            if not self.is_fury_active:
                self.fury = min(FURY_MAX, self.fury + (FURY_PER_CRIT if is_crit else FURY_PER_HIT))

        if landed:
            self._hitstop(HITSTOP["crit"] if any_crit else HITSTOP["knockdown"] if spec["knockdown"] else HITSTOP["hit"])
        return landed

    # ------------------------------------------------------------------
    # Special abilities (W): one per hero, by trade
    # ------------------------------------------------------------------

    @property
    def special_ready(self) -> bool:
        """Return True when the special can be used right now."""
        return self.special_cooldown <= 0 and self.can_act and self.attack_timer <= 0 and not self.is_airborne

    def use_special(self, enemies: Iterable[Entity]) -> list[Entity]:
        """
        Use this hero's special ability if it's ready.

        Returns:
            Enemies that were damaged (empty if nothing was hit or the move couldn't start).
        """
        if not self.special_ready:
            return []
        spec = self.special
        foes = [enemy for enemy in enemies if enemy.is_alive()]
        landed = getattr(self, f"_special_{spec['kind']}")(foes, spec)
        if landed is None:  # nothing to use it on (e.g. no foe to step behind): no cooldown spent
            return []

        cooldown = spec["cooldown"] * (FURY_COOLDOWN_SCALE if self.is_fury_active else 1.0)
        self.special_cooldown = self.special_total = cooldown
        self.combo_step = 0
        self.buffered_attack = 0.0
        self.is_attacking = True
        self.attack_mode = SPECIAL_POSES[spec["kind"]]
        self.attack_duration = self.attack_timer = spec["duration"]
        if landed:
            self._hitstop(HITSTOP["knockdown"])
        return landed

    def _special_charge(self, foes: list[Entity], spec: dict) -> list[Entity]:
        """Knight: shield charge. Dash forward (dodging hits) and bowl over everyone in the path."""
        targets = [foe for foe in foes if self._in_special_zone(foe, spec, forward=True)]
        self.strafe_cooldown = 0.0
        self.strafe(Vector2(self.face_sign, 0), STRAFE_COOLDOWN, spec["range"], spec["duration"])
        self._sfx("heavy")
        self._emit("charge", face=self.face_sign)
        return self._strike_all(targets, spec["damage"], knock=lambda foe: self.face_sign)

    def _special_arrow(self, foes: list[Entity], spec: dict) -> list[Entity]:
        """Ranger: a piercing arrow along her lane that hits every foe in line."""
        targets = [foe for foe in foes if self._in_special_zone(foe, spec, forward=True) and foe.z <= AIR_DODGE_HEIGHT]
        self._sfx("strafe")
        self._emit("arrow", face=self.face_sign, reach=spec["range"])
        return self._strike_all(targets, spec["damage"], knock=lambda foe: self.face_sign)

    def _special_shadow_step(self, foes: list[Entity], spec: dict) -> list[Entity] | None:
        """Rogue: vanish, reappear behind the nearest foe, and backstab (always a critical)."""
        candidates = [
            foe for foe in foes
            if self._in_special_zone(foe, spec, forward=False) and not foe.is_lying and not foe.is_airborne
        ]
        if not candidates:
            return None
        target = min(candidates, key=lambda foe: abs(foe.position.x - self.position.x) + abs(foe.position.y - self.position.y))
        self._emit("smoke")
        side = 1 if target.position.x >= self.position.x else -1
        self.position.x = target.position.x + side * SHADOW_STEP_GAP
        self.position.y = target.position.y
        self.face_sign = -side
        self.velocity = Vector2()
        self.target_velocity = Vector2()
        self._sfx("strafe")
        self._emit("smoke")
        landed = self._strike_all([target], spec["damage"], force_crit=True)
        if landed and not getattr(target, "has_super_armor", False):
            target.windup_mode = None
            target.stun(spec["stun"])
        return landed

    def _special_holy_light(self, foes: list[Entity], spec: dict) -> list[Entity]:
        """Paladin: holy light heals the hero and knocks back foes close by."""
        healed = self.heal(spec["heal"])
        targets = [foe for foe in foes if self._in_special_zone(foe, spec, forward=False)]
        self._sfx("shield")
        self._emit("holy", reach=spec["range"], healed=healed)
        return self._strike_all(targets, spec["damage"], knock=self._away)

    def _special_war_cry(self, foes: list[Entity], spec: dict) -> list[Entity]:
        """Barbarian: a war cry stuns the foes around him, then rage boosts his damage."""
        for foe in foes:
            if self._in_special_zone(foe, spec, forward=False) and not foe.is_lying and not getattr(foe, "has_super_armor", False):
                foe.windup_mode = None
                foe.stun(spec["stun"])
                self._emit("dazed", x=foe.position.x, y=foe.position.y - foe.height / 2, life=spec["stun"])
        self.rage_timer = spec["rage"]
        self._sfx("boss_fury")
        self._emit("roar", reach=spec["range"])
        return []

    def _special_earthquake(self, foes: list[Entity], spec: dict) -> list[Entity]:
        """Warlord: slam the ground; the quake knocks down every foe standing nearby."""
        targets = [foe for foe in foes if self._in_special_zone(foe, spec, forward=False) and foe.z <= AIR_DODGE_HEIGHT]
        self._sfx("knockdown")
        self._emit("quake", reach=spec["range"])
        return self._strike_all(targets, spec["damage"], knock=self._away)

    def _in_special_zone(self, foe: Entity, spec: dict, forward: bool) -> bool:
        """Is the foe within the special's reach: in front for line attacks, all around for bursts."""
        dx = foe.position.x - self.position.x
        if abs(foe.position.y - self.position.y) > LANE_DEPTH * spec["depth"]:
            return False
        if forward:
            return -10 <= dx * self.face_sign <= spec["range"]
        return abs(dx) <= spec["range"]

    def _away(self, foe: Entity) -> int:
        """Direction that knocks a foe away from the hero."""
        dx = foe.position.x - self.position.x
        return self.face_sign if abs(dx) < 1 else (1 if dx > 0 else -1)

    def _strike_all(self, targets: list[Entity], multiplier: float, knock=None, force_crit: bool = False) -> list[Entity]:
        """Damage each target (optionally knocking it down); builds the hit chain and Fury like normal hits."""
        landed: list[Entity] = []
        for foe in targets:
            damage, is_crit = self.roll_damage(multiplier)
            if force_crit and not is_crit:
                damage, is_crit = round(damage * CRIT_MULTIPLIER), True
            foe.last_hit_crit = is_crit
            dealt = foe.take_damage(damage)
            if not dealt:
                continue
            landed.append(foe)
            self._register_hit(dealt)
            if knock is not None:
                foe.knock_down(knock(foe))
            if not self.is_fury_active:
                self.fury = min(FURY_MAX, self.fury + (FURY_PER_CRIT if is_crit else FURY_PER_HIT))
        return landed

    def _emit(self, kind: str, **data: object) -> None:
        """Queue a visual effect at the hero's feet (unless x/y are given) for the renderer."""
        data.setdefault("x", self.position.x)
        data.setdefault("y", self.position.y + self.height / 2)
        self.special_events.append((kind, data))

    def _sfx(self, name: str, volume: float = 1.0) -> None:
        audio.play(name, volume * self.sound_volume)

    def _hitstop(self, seconds: float) -> None:
        if self.freezes_on_hit:
            feel.freeze(seconds)

    def buffer_attack(self) -> None:
        """Remember an R press to fire as soon as the hero is free to swing."""
        self.buffered_attack = ATTACK_BUFFER

    def has_buffered_attack(self) -> bool:
        """Return True when a remembered R press can fire now."""
        return self.buffered_attack > 0 and self.attack_timer <= 0 and self.can_act

    def jump(self) -> bool:
        """
        Leap into the air; ground swings pass underneath a high jump.

        Returns:
            True if the jump started.
        """
        if not self.can_act or self.is_airborne or self.is_strafing or self.jump_squat > 0:
            return False
        self.jump_squat = JUMP_SQUAT  # crouch first; take-off happens when the squat ends
        return True

    def _take_off(self) -> None:
        self.vz = JUMP_SPEED
        self.z = 1.0
        self.air_step = 0
        self._sfx("jump")

    @property
    def crouch(self) -> float:
        """Knee bend: the squat before a jump, or the landing."""
        if self.jump_squat > 0:
            return 1.0
        return super().crouch

    @property
    def air_phase(self) -> float | None:
        """Jump progress for the art: 1 at take-off, 0 at the top, negative while falling."""
        if not self.is_airborne or self.knocked:
            return None
        return max(-1.0, min(1.0, self.vz / JUMP_SPEED))

    def on_land(self) -> None:
        """Thud on landing; a knockdown landing is handled by the base class."""
        super().on_land()
        if not self.knocked:
            self._sfx("land", 0.5)

    def roll_damage(self, multiplier: float = 1.0) -> tuple[int, bool]:
        """Return (damage, is_crit) for one hit, including Fury bonuses."""
        damage = self.damage * multiplier
        if self.is_fury_active:
            damage *= FURY_DAMAGE_BONUS
        if self.rage_timer > 0:
            damage *= self.special.get("rage_bonus", 1.0)
        is_crit = random.random() < (FURY_CRIT_CHANCE if self.is_fury_active else CRIT_CHANCE)
        if is_crit:
            damage *= CRIT_MULTIPLIER
        return max(1, round(damage)), is_crit

    def activate_fury(self) -> bool:
        """
        Spend a full Fury meter to start the Fury buff.

        Returns:
            True if Fury was activated.
        """
        if self.fury < FURY_MAX or self.is_fury_active:
            return False

        self.fury = 0.0
        self.fury_timer = FURY_DURATION
        self._sfx("fury")
        return True

    def activate_shield(self) -> bool:
        """
        Activate shield if a charge is available.

        Returns:
            True if the shield was activated.
        """
        if self.shield_charges <= 0 or self.is_shielding:
            return False

        self.shield_charges -= 1
        self.shield_timer = SHIELD_DURATION
        self.is_shielding = True
        self._sfx("shield")
        return True

    def take_damage(self, amount: int) -> int:
        """Scale incoming damage by difficulty, and reduce it further while shielding."""
        amount = max(1, round(amount * self.damage_taken_multiplier)) if amount > 0 else amount
        if self.is_shielding:
            amount = max(1, round(amount * SHIELD_DAMAGE_MULTIPLIER))
        damage = super().take_damage(amount)
        if damage:
            self.stun(HITSTUN * 0.7)
            self.combo_step = 0
            self._hitstop(HITSTOP["hit"])
            self.hurt_flash = HURT_FLASH_DURATION
            self.regen_delay = HP_REGEN_DELAY
            self._regen_progress = 0.0
        return damage

    def can_attack(self, mode: str = "slash") -> bool:
        """Return True when no swing is playing and this mode's cooldown has elapsed."""
        return self.attack_timer <= 0 and self.cooldowns[mode] <= 0

    def is_in_attack_range(
        self, target: Entity, reach: float = ATTACK_RANGE, full_circle: bool = False, depth: float | None = None
    ) -> bool:
        """
        Return True when target can be hit: within the attack's depth band (up/down),
        within reach, in front (unless full_circle), and not jumping clear over a ground swing.
        """
        dx = target.position.x - self.position.x
        dy = target.position.y - self.position.y
        lane = LANE_DEPTH * (depth if depth is not None else 1.4 if full_circle else 1.0)
        if abs(dy) > lane or abs(dx) > reach:
            return False
        if target.z > AIR_DODGE_HEIGHT and self.z <= AIR_DODGE_HEIGHT:
            return False
        return full_circle or dx * self.face_sign >= -10

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the hero with their fighting style's blow animation, recoil, strafe trail, and buffs."""
        now = pygame.time.get_ticks() / 1000.0
        feet_y = self.position.y + self.height / 2
        swing = 1 - self.attack_timer / self.attack_duration if self.is_attacking else None

        flash, flash_color = self.hurt_flash / HURT_FLASH_DURATION, (200, 40, 30)
        if not flash and self.is_fury_active:
            flash, flash_color = 0.18 + 0.1 * math.sin(now * 10), (255, 140, 40)
        elif not flash and self.rage_timer > 0:
            flash, flash_color = 0.16 + 0.08 * math.sin(now * 12), (230, 40, 30)

        if self.is_fury_active:
            art.draw_fury_aura(surface, self.position.x, feet_y, now)
        if self.is_attacking and self.attack_mode == "spin":
            spec = ATTACK_MODES["spin"]
            art.draw_spin_ring(surface, self.position.x, feet_y, swing, spec["range"], LANE_DEPTH * spec["depth"])
        if self.is_shielding:
            art.draw_ward(surface, self.position.x, feet_y, now, self.shield_timer / SHIELD_DURATION)

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
            shielding=self.is_shielding,
            mode=self.attack_mode,
            fury=self.is_fury_active,
            recoil=self.hurt_flash / HURT_FLASH_DURATION,
            ghosts=self.strafe_ghosts(),
            tilt=self.pose_tilt(),
            lift=self.z,
            tuck=self.is_airborne and not self.knocked,
            visible=not self.is_blinking(now),
            gait=self.walk_phase,
            stride_amount=self.stride_amount,
            crouch=self.crouch,
            scale=FIGHTER_SCALE,
            posture=self.posture(),
            air=self.air_phase,
        )

    def _apply_input(self, input_state: Any) -> None:
        """Apply movement and edge-triggered actions from the input state."""
        move_vector = getattr(input_state, "move_vector", Vector2())

        if not isinstance(move_vector, Vector2):
            move_vector = Vector2()

        strafe_direction = getattr(input_state, "strafe_direction", None)
        if strafe_direction is not None:
            if self.strafe(strafe_direction):
                self._sfx("strafe")

        if self.is_strafing:
            pass
        elif move_vector.is_zero():
            self.target_velocity = Vector2()
        else:
            direction = move_vector.normalized()
            self.target_velocity = Vector2(direction.x * self.speed, direction.y * self.speed * DEPTH_SPEED_RATIO)
            if direction.x and not self.is_attacking:
                self.face_sign = 1 if direction.x > 0 else -1  # turn on the spot, even mid-skid

        if getattr(input_state, "is_shielding", False):
            self.activate_shield()
        if getattr(input_state, "is_jumping", False):
            self.jump()

    def _update_timers(self, dt: float) -> None:
        """Update cooldown and action timers."""
        for mode in self.cooldowns:
            self.cooldowns[mode] = max(0.0, self.cooldowns[mode] - dt)
        self.fury_timer = max(0.0, self.fury_timer - dt)
        self.special_cooldown = max(0.0, self.special_cooldown - dt)
        self.rage_timer = max(0.0, self.rage_timer - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.shield_timer = max(0.0, self.shield_timer - dt)
        self.hurt_flash = max(0.0, self.hurt_flash - dt)
        self.combo_timer = max(0.0, self.combo_timer - dt)
        self.buffered_attack = max(0.0, self.buffered_attack - dt)
        if self.jump_squat > 0:
            self.jump_squat = max(0.0, self.jump_squat - dt)
            if self.jump_squat == 0 and self.can_act:
                self._take_off()
        if self.combo_timer == 0:
            self.combo_step = 0
        self.chain_timer = max(0.0, self.chain_timer - dt)
        if self.chain_timer == 0:
            self.hit_chain = 0
        self._regenerate(dt)

        if self.attack_timer == 0:
            self.is_attacking = False

        if self.shield_timer == 0:
            self.is_shielding = False

    def _regenerate(self, dt: float) -> None:
        """Heal slowly over time once the hero hasn't been hit for a moment."""
        if self.regen_delay > 0:
            self.regen_delay = max(0.0, self.regen_delay - dt)
            return
        if self.hp >= self.max_hp or not self.is_alive():
            self._regen_progress = 0.0
            return

        self._regen_progress += self.hp_regen * dt
        whole = int(self._regen_progress)
        if whole:
            self.heal(whole)
            self._regen_progress -= whole

    def _register_hit(self, dealt: int) -> None:
        """Extend the hit chain and add score (chains past 2 hits earn a bonus)."""
        self.hit_chain += 1
        self.chain_timer = HIT_CHAIN_WINDOW
        self.score += dealt * SCORE_PER_DAMAGE
        if self.hit_chain > 2:
            self.score += SCORE_COMBO_BONUS

    def _grab_target(self, enemies: list[Entity]) -> Entity | None:
        """Return an enemy close enough to grab for a throw, if any."""
        for enemy in enemies:
            if not enemy.is_alive() or enemy.is_invulnerable or enemy.is_airborne:
                continue
            dx = enemy.position.x - self.position.x
            if abs(enemy.position.y - self.position.y) <= LANE_DEPTH and abs(dx) <= THROW_REACH and dx * self.face_sign >= -6:
                return enemy
        return None
