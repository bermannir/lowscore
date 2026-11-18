"""
Module: game
Purpose: Main game class: flow between title, hero select, story scenes, and levels.
Dependencies: pygame, lowscore core/entities/systems/ui modules
Used by: main.py entry point.
"""

from __future__ import annotations

import os
import random

import pygame

from core.constants import (
    CHARACTER_HP,
    COLORS,
    DEFAULT_DIFFICULTY,
    DIFFICULTIES,
    FPS,
    ENEMY_OFFSCREEN,
    GO_SCROLL_SPEED,
    LEVEL_SAFE_TOP,
    LEVEL_WAVES,
    MID_BOSSES,
    ALLY_DURATION,
    ALLY_COST_STEP,
    ALLY_FIRST_COST,
    ALLY_MAX_CALLS,
    ELIXIR_FURY,
    RALLY_COMBO,
    RALLY_DELAY,
    RALLY_POINTS,
    PELT_SHIELD_CAP,
    RIDER_DENSITY,
    RIDER_GROUP_LEVEL_STEP,
    RIDER_GROUP_MAX,
    RIDER_SHARE_PER_LEVEL,
    MAX_LEVEL,
    MEAT_DROP_CHANCE,
    MEAT_HEAL,
    PICKUP_RADIUS,
    POTION_DROP_CHANCE,
    POTION_FURY,
    FURY_MAX,
    SCORE_PER_BOSS,
    SCORE_PER_MID_BOSS,
    SCORE_PER_KILL,
    PLAYER_START_X,
    PLAYER_START_Y,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    WINDOW_TITLE,
)
from core import i18n
from core.i18n import t
from core.settings import VOLUME_STEPS, Settings
from core.story import scene
from core.types import GameState, Position
from entities.enemy import Enemy
from entities.ally import Ally
from entities.beast import BEAST_TYPES
from entities.ember_demon import EmberDemon
from entities.mid_boss import MidBoss
from entities.pickup import Pickup
from entities.player import Player
from systems import feel
from systems.audio import audio
from systems.input_handler import InputHandler
from systems.physics import clamp_to_bounds
from ui.renderer import Renderer

CHARACTER_NAMES = list(CHARACTER_HP)
STORY_TYPE_SPEED = 45  # characters revealed per second
OUTRO_DELAY = 1.4  # let the final blow (or the hero's fall) play out before switching screens
HOME_OPTIONS = ("menu_start", "menu_settings", "menu_quit")
PAUSE_OPTIONS = ("resume", "menu_settings", "quit_title")
SETTINGS_ROWS = ("language", "sfx", "music", "back")
# The window is opened once, at the biggest of these sizes that fits the screen, and never resized.
# (Switching window modes while running crashed pygame 2.6.1 on macOS, so there is no display option.)
WINDOW_SIZES = ((1920, 960), (1680, 840), (1440, 720), (1200, 600))


class Game:
    """
    Owns the main game loop and coordinates game flow.

    Attributes:
        state: Current high-level game state.
        running: Whether the loop should continue.
        screen: Active pygame display surface.
        clock: Pygame clock for FPS and delta time.
        player: The current player entity.
        selected_index: Highlighted hero on the select screen.
        difficulty_index: Chosen difficulty (index into DIFFICULTIES).
        story_key: Scene being shown (a level number or "ending").
        story_line: Index of the current line in that scene.
        settings: Saved player options (language, volumes, display).
        settings_return: Screen to go back to when leaving the settings menu.
        input_handler: Keyboard input reader.
        renderer: Rendering system.
    """

    def __init__(self) -> None:
        """Initialize pygame, core systems, and the player."""
        audio.init()
        pygame.init()
        pygame.font.init()

        self.settings = Settings.load()
        i18n.set_language(self.settings.language)
        audio.set_sfx_level(self.settings.sfx_level)
        audio.set_music_level(self.settings.music_level)

        self.state = GameState.HOME
        self._last_update_state = self.state
        self.running = True
        self.screen = self._open_display()
        pygame.display.set_caption(WINDOW_TITLE)
        self.home_index = 0
        self.pause_index = 0
        self.settings_index = 0
        self.settings_return = GameState.HOME
        self.swap_mode = False  # hero select opened from "level complete" to change heroes mid-run
        self.allies: list[Ally] = []
        self._reset_bonuses()

        self.clock = pygame.time.Clock()
        self.level = 1
        self.selected_index = 0
        self.difficulty_index = DIFFICULTIES.index(DEFAULT_DIFFICULTY)
        self.player = self._new_player()
        self.enemies: list[Enemy] = []
        self.pickups: list[Pickup] = []
        self.banked_score = 0
        self.outro_timer: float | None = None
        self.wave = 0
        self.wave_count = 1
        self.camera_x = 0.0
        self.advancing = False
        self.story_key: int | str = 1
        self.story_line = 0
        self.story_line_started = 0.0
        self.input_handler = InputHandler()
        self.renderer = Renderer(self.screen, self.clock)

    @property
    def character_name(self) -> str:
        """Return the currently selected hero's name."""
        return CHARACTER_NAMES[self.selected_index]

    @property
    def difficulty(self) -> str:
        """Return the currently selected difficulty."""
        return DIFFICULTIES[self.difficulty_index]

    def start_level(self, level: int) -> None:
        """Reset actors and begin the requested level."""
        self.level = level
        self.banked_score += self.player.score
        self.player = self._new_player()
        self.wave = 0
        self.wave_count = LEVEL_WAVES.get(level, 3)
        self.camera_x = 0.0
        self.advancing = False
        self.renderer.set_level(level, self.wave_count)
        self.enemies = self._spawn_wave(level, 0)
        self.pickups = []
        self.outro_timer: float | None = None
        self.allies = []
        self.rally_timer = None
        feel.reset()
        self.state = GameState.LEVEL

    @property
    def score(self) -> int:
        """Total arcade score for this run."""
        return self.banked_score + self.player.score

    def start_story(self, key: int | str) -> None:
        """Show the story scene for a level number or the ending."""
        self.story_key = key
        self.story_line = 0
        self.story_line_started = self._now()
        self.state = GameState.STORY

    def run(self) -> None:
        """Run the main game loop until the user quits."""
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events()
            self.update(dt)
            self._update_music()
            self.render()

        self.shutdown()

    def handle_events(self) -> None:
        """Process pygame window events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
                self.state = GameState.QUIT
            elif event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key, getattr(event, "scancode", None))

    def update(self, dt: float) -> None:
        """Update gameplay systems for the current frame."""
        # Keys held from confirming a menu (SPACE, R...) must not fire as fresh presses in the fight.
        entering_fight = self._last_update_state != GameState.LEVEL
        self._last_update_state = self.state
        if self.state != GameState.LEVEL or entering_fight:
            self.input_handler.sync()
        if self.state != GameState.LEVEL:
            return
        input_state = self.input_handler.handle_input()

        if feel.consume(dt):
            # Hit-stop: the fight freezes for a beat on impact; remember attack presses.
            if input_state.is_attacking:
                self.player.buffer_attack()
            return

        self.player.update(dt, input_state)
        if input_state.is_attacking or self.player.has_buffered_attack():
            self.player.light_attack(self.enemies)
        elif input_state.is_heavy:
            self.player.heavy_attack(self.enemies)
        elif input_state.is_spin:
            self.player.attack(self.enemies, "spin")
        elif input_state.is_special:
            self.player.use_special(self.enemies)
        if input_state.is_fury:
            self.player.activate_fury()

        clamp_to_bounds(self.player, self.camera_x + SCREEN_WIDTH, SCREEN_HEIGHT, self.camera_x)
        self._update_bonuses(dt)

        for enemy in self.enemies:
            enemy.update(
                dt, self.player, self.camera_x + SCREEN_WIDTH + ENEMY_OFFSCREEN, SCREEN_HEIGHT, self.camera_x - ENEMY_OFFSCREEN
            )

        for enemy in list(self.enemies):  # foes a boss summoned join the fight
            summoned = getattr(enemy, "spawn_requests", None)
            if summoned:
                self.enemies.extend(summoned)
                summoned.clear()

        for enemy in [enemy for enemy in self.enemies if not enemy.is_alive()]:
            self._on_enemy_defeated(enemy)
        self.enemies = [enemy for enemy in self.enemies if enemy.is_alive()]
        self._update_pickups(dt)

        if self.player.is_alive() and self.enemies:
            return
        if self.player.is_alive() and self.wave < self.wave_count - 1:
            self._advance(dt)  # wave cleared: scroll forward to the next section
            return
        if self.outro_timer is None:
            self.outro_timer = OUTRO_DELAY
            if not self.player.is_alive() and not self.player.knocked:
                self.player.knock_down(-self.player.face_sign)
        self.outro_timer -= dt
        if self.outro_timer > 0:
            return

        if not self.player.is_alive():
            self.state = GameState.GAME_OVER
            audio.play("game_over")
        else:
            if self.level < MAX_LEVEL:
                self.state = GameState.LEVEL_COMPLETE
                audio.play("level_complete")
            else:
                self.state = GameState.FINAL_VICTORY
                audio.play("victory")

    def render(self) -> None:
        """Render the current game state."""
        if self.state == GameState.LEVEL:
            self.renderer.render_world(
                self.player,
                entities=self.enemies,
                level_name=t("level_of", n=self.level, total=MAX_LEVEL),
                enemy_count=len(self.enemies),
                max_level=MAX_LEVEL,
                pickups=self.pickups,
                score=self.score,
                camera_x=self.camera_x,
                wave_label=t("wave", n=self.wave + 1, total=self.wave_count),
                show_go=self.advancing,
                show_swap=self.can_swap_hero,
                allies=self.allies,
                bonus=self.bonus_status,
            )
        elif self.state == GameState.HOME:
            self.renderer.render_message_screen(
                "LOWSCORE",
                "",
                t("controls_hint"),
                COLORS["gold"],
                menu=([t(option) for option in HOME_OPTIONS], self.home_index),
            )
        elif self.state == GameState.PAUSED:
            self.renderer.render_pause([t(option) for option in PAUSE_OPTIONS], self.pause_index)
        elif self.state == GameState.SETTINGS:
            self.renderer.render_settings(
                self._settings_rows(), self.settings_index, self._settings_notes(), self.settings_return == GameState.PAUSED
            )
        elif self.state == GameState.CHARACTER_SELECT:
            self.renderer.render_character_select(CHARACTER_NAMES, self.selected_index, self.difficulty, swap=self.swap_mode)
        elif self.state == GameState.STORY:
            revealed = int((self._now() - self.story_line_started) * STORY_TYPE_SPEED)
            self.renderer.render_story(self.story_key, self.story_line, revealed, self.character_name)
        elif self.state == GameState.LEVEL_COMPLETE:
            self.renderer.render_message_screen(
                t("level_complete"),
                t("prompt_continue_swap"),
                t("next_level", n=self.level + 1),
                COLORS["green"],
            )
        elif self.state == GameState.FINAL_VICTORY:
            self.renderer.render_message_screen(
                t("victory"),
                t("prompt_epilogue"),
                t("all_cleared"),
                COLORS["gold"],
            )
        elif self.state == GameState.GAME_OVER:
            self.renderer.render_message_screen(
                t("game_over"),
                t("prompt_retry"),
                t("tip"),
                COLORS["red"],
            )
        else:
            self.screen.fill(COLORS["background"])
            pygame.display.flip()

    def shutdown(self) -> None:
        """Cleanly stop pygame."""
        pygame.quit()

    def _handle_keydown(self, key: int, scancode: int | None = None) -> None:
        """
        Handle state-changing key presses.

        Letter keys are matched by physical scancode too, so M and R work with any
        keyboard layout (e.g. Hebrew), not only when the layout types Latin letters.
        """
        confirm = key in (pygame.K_RETURN, pygame.K_SPACE)
        vertical = -1 if key == pygame.K_UP else 1 if key == pygame.K_DOWN else 0
        horizontal = -1 if key == pygame.K_LEFT else 1 if key == pygame.K_RIGHT else 0

        if key == pygame.K_ESCAPE:
            self._on_escape()
        elif key == pygame.K_m or scancode == pygame.KSCAN_M:
            audio.toggle_mute()
            self._save_sfx_level()
        elif key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            audio.change_volume(-1)
            self._save_sfx_level()
        elif key in (pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
            audio.change_volume(1)
            self._save_sfx_level()
        elif self.state == GameState.HOME:
            if vertical:
                audio.play("ui_move")
                self.home_index = (self.home_index + vertical) % len(HOME_OPTIONS)
            elif confirm:
                audio.play("ui_confirm")
                choice = HOME_OPTIONS[self.home_index]
                if choice == "menu_start":
                    self.state = GameState.CHARACTER_SELECT
                elif choice == "menu_settings":
                    self._open_settings(GameState.HOME)
                else:
                    self.running = False
        elif self.state == GameState.PAUSED:
            if vertical:
                audio.play("ui_move")
                self.pause_index = (self.pause_index + vertical) % len(PAUSE_OPTIONS)
            elif confirm:
                audio.play("ui_confirm")
                choice = PAUSE_OPTIONS[self.pause_index]
                if choice == "resume":
                    self.state = GameState.LEVEL
                elif choice == "menu_settings":
                    self._open_settings(GameState.PAUSED)
                else:
                    self._return_home()
        elif self.state == GameState.SETTINGS:
            row = SETTINGS_ROWS[self.settings_index]
            if vertical:
                audio.play("ui_move")
                self.settings_index = (self.settings_index + vertical) % len(SETTINGS_ROWS)
            elif horizontal and row != "back":
                self._change_setting(row, horizontal)
            elif confirm:
                if row == "back":
                    self._close_settings()
                else:
                    self._change_setting(row, 1)
        elif self.state == GameState.CHARACTER_SELECT:
            if key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                audio.play("ui_move")
            if key == pygame.K_LEFT:
                self.selected_index = (self.selected_index - 1) % len(CHARACTER_NAMES)
            elif key == pygame.K_RIGHT:
                self.selected_index = (self.selected_index + 1) % len(CHARACTER_NAMES)
            elif key == pygame.K_UP and not self.swap_mode:  # difficulty is fixed once a run has started
                self.difficulty_index = max(0, self.difficulty_index - 1)
            elif key == pygame.K_DOWN and not self.swap_mode:
                self.difficulty_index = min(len(DIFFICULTIES) - 1, self.difficulty_index + 1)
            elif confirm and self.swap_mode:
                # Changing heroes between levels: keep the run's score and go on to the next level.
                audio.play("ui_confirm")
                self.swap_mode = False
                self.start_story(self.level + 1)
            elif confirm:
                audio.play("ui_confirm")
                self.banked_score = 0
                self._reset_bonuses()
                self.player = self._new_player()
                self.start_story(1)
        elif self.state == GameState.STORY and confirm:
            audio.play("ui_tick")
            self._advance_story()
        elif self.state == GameState.LEVEL_COMPLETE and confirm:
            audio.play("ui_confirm")
            self.start_story(self.level + 1)
        elif self.state == GameState.LEVEL_COMPLETE and (key == pygame.K_c or scancode == pygame.KSCAN_C):
            audio.play("ui_confirm")
            self.swap_mode = True
            self.state = GameState.CHARACTER_SELECT
        elif self.state == GameState.LEVEL and (key == pygame.K_c or scancode == pygame.KSCAN_C):
            self._swap_hero_between_waves()
        elif self.state == GameState.LEVEL and (key == pygame.K_x or scancode == pygame.KSCAN_X):
            self._call_ally()
        elif self.state == GameState.FINAL_VICTORY and confirm:
            audio.play("ui_confirm")
            self.start_story("ending")
        elif self.state == GameState.GAME_OVER and confirm:
            audio.play("ui_confirm")
            self.start_level(self.level)
        elif (key == pygame.K_r or scancode == pygame.KSCAN_R) and self.state == GameState.GAME_OVER:
            audio.play("ui_confirm")
            self._return_home()

    def _on_escape(self) -> None:
        """ESC backs out: pauses a fight, closes menus, returns to the title, or quits from the title."""
        if self.state == GameState.LEVEL:
            self.renderer.capture_freeze()
            self.pause_index = 0
            self.state = GameState.PAUSED
        elif self.state == GameState.PAUSED:
            self.state = GameState.LEVEL
        elif self.state == GameState.SETTINGS:
            self._close_settings()
        elif self.state == GameState.HOME:
            self.running = False
            self.state = GameState.QUIT
        elif self.state == GameState.CHARACTER_SELECT and self.swap_mode:
            self.swap_mode = False
            self.state = GameState.LEVEL_COMPLETE
        else:
            self._return_home()

    # ------------------------------------------------------------------
    # Settings
    # ------------------------------------------------------------------

    def _open_settings(self, return_to: GameState) -> None:
        self.settings_return = return_to
        self.settings_index = 0
        self.state = GameState.SETTINGS

    def _close_settings(self) -> None:
        audio.play("ui_confirm")
        self.settings.save()
        self.state = self.settings_return

    def _settings_rows(self) -> list[tuple[str, str]]:
        """(label, value) for each row of the settings menu, in the active language."""
        def volume(level: int) -> str:
            return t("off") if level == 0 else f"{level * 100 // (VOLUME_STEPS - 1)}%"

        values = {
            "language": i18n.LANGUAGE_NAMES[self.settings.language],
            "sfx": volume(self.settings.sfx_level),
            "music": volume(self.settings.music_level),
            "back": "",
        }
        labels = {
            "language": "set_language", "sfx": "set_sfx", "music": "set_music", "back": "set_back",
        }
        return [(t(labels[row]), values[row]) for row in SETTINGS_ROWS]

    def _settings_notes(self) -> list[str]:
        notes = []
        if not audio.has_music():
            notes.append(t("music_missing"))
        return notes

    def _change_setting(self, row: str, step: int) -> None:
        """Change one setting by a step, apply it immediately, and save."""
        settings = self.settings
        if row == "language":
            languages = i18n.LANGUAGES
            settings.language = languages[(languages.index(settings.language) + step) % len(languages)]
            i18n.set_language(settings.language)
            self.renderer.load_fonts()
        elif row == "sfx":
            settings.sfx_level = max(0, min(VOLUME_STEPS - 1, settings.sfx_level + step))
            audio.set_sfx_level(settings.sfx_level)
        elif row == "music":
            settings.music_level = max(0, min(VOLUME_STEPS - 1, settings.music_level + step))
            audio.set_music_level(settings.music_level)
        audio.play("ui_tick")
        settings.save()

    def _save_sfx_level(self) -> None:
        """Keep the saved effects volume in step with the M and -/+ shortcuts."""
        self.settings.sfx_level = audio.sfx_level
        self.settings.save()

    def _open_display(self) -> pygame.Surface:
        """Open the game window once, as large as fits the screen; the picture is scaled to fit."""
        os.environ.setdefault("SDL_VIDEO_CENTERED", "1")
        size = _window_size()
        try:
            return pygame.display.set_mode(size)
        except pygame.error:
            return pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))

    def _update_music(self) -> None:
        """Pick the music for what's on screen (files in assets/music; silent if none)."""
        in_fight = self.state in (GameState.LEVEL, GameState.PAUSED) or (
            self.state == GameState.SETTINGS and self.settings_return == GameState.PAUSED
        )
        if not in_fight:
            audio.play_music("menu")
        elif any(enemy.is_boss or getattr(enemy, "is_mid_boss", False) for enemy in self.enemies):
            audio.play_music("boss")
        else:
            audio.play_music(f"level{self.level}")

    def _advance_story(self) -> None:
        """Finish typing the current line, or move to the next line or out of the scene."""
        text = scene(self.story_key)[self.story_line][1].replace("{hero}", i18n.hero_name(self.character_name))
        typed = (self._now() - self.story_line_started) * STORY_TYPE_SPEED
        if typed < len(text):
            self.story_line_started = self._now() - len(text) / STORY_TYPE_SPEED
            return

        self.story_line += 1
        self.story_line_started = self._now()
        if self.story_line < len(scene(self.story_key)):
            return

        if self.story_key == "ending":
            self._return_home()
        else:
            self.start_level(int(self.story_key))

    def _new_player(self) -> Player:
        return Player(Position(PLAYER_START_X, PLAYER_START_Y), self.character_name, self.difficulty)

    def _on_enemy_defeated(self, enemy: Enemy) -> None:
        """Score the kill and maybe drop a magic pot or food, Golden Axe style."""
        reward = getattr(enemy, "reward", None)
        if reward is not None:  # a goblin rider: its own reward, no random drop
            self.banked_score += enemy.reward_score
            audio.play("death", 0.6)
            feet = enemy.position.y + enemy.height / 2
            self.pickups.append(Pickup(reward, Position(enemy.position.x, feet)))
            return
        mid_boss = getattr(enemy, "is_mid_boss", False)
        self.banked_score += SCORE_PER_BOSS if enemy.is_boss else SCORE_PER_MID_BOSS if mid_boss else SCORE_PER_KILL
        audio.play("death")
        if enemy.is_boss:
            return
        if mid_boss:  # a mid-boss always leaves a feast and a magic pot
            feet = enemy.position.y + enemy.height / 2
            self.pickups.append(Pickup("meat", Position(enemy.position.x - 24, feet)))
            self.pickups.append(Pickup("potion", Position(enemy.position.x + 24, feet)))
            return
        roll = random.random()
        kind = "potion" if roll < POTION_DROP_CHANCE else "meat" if roll < POTION_DROP_CHANCE + MEAT_DROP_CHANCE else None
        if kind:
            self.pickups.append(Pickup(kind, Position(enemy.position.x, enemy.position.y + enemy.height / 2)))

    def _update_pickups(self, dt: float) -> None:
        """Bounce drops, collect the ones the hero walks over, and expire old ones."""
        feet = Position(self.player.position.x, self.player.position.y + self.player.height / 2)
        kept: list[Pickup] = []
        for pickup in self.pickups:
            pickup.update(dt)
            if pickup.z <= 0 and self.player.z < 20 and feet.distance_to(pickup.position) <= PICKUP_RADIUS:
                self._collect(pickup.kind)
                audio.play("pickup")
                continue
            if not pickup.expired:
                kept.append(pickup)
        self.pickups = kept

    # ------------------------------------------------------------------
    # Bonuses: Ally Call and Heroes' Rally
    # ------------------------------------------------------------------

    def _reset_bonuses(self) -> None:
        """A fresh run: no calls saved, Rally progress empty, and the first-boss showcase still to come."""
        self.ally_calls = 0
        self.ally_points_mark = 0  # score at which the last call was earned
        self.ally_cost = ALLY_FIRST_COST  # points needed for the next call (rises with each one earned)
        self.rally_points_mark = 0
        self.rally_best_chain = 0
        self.rally_earned = False
        self.rally_showcased = False
        self.rally_timer: float | None = None

    @property
    def bonus_status(self) -> dict:
        """What the HUD shows about both bonuses."""
        return {
            "calls": self.ally_calls,
            "max_calls": ALLY_MAX_CALLS,
            "call_progress": 1.0 if self.ally_calls >= ALLY_MAX_CALLS else (self.score - self.ally_points_mark) / self.ally_cost,
            "ally_active": any(not ally.rally for ally in self.allies),
            "rally_combo": min(1.0, self.rally_best_chain / RALLY_COMBO),
            "rally_combo_count": self.rally_best_chain,
            "rally_points": min(1.0, (self.score - self.rally_points_mark) / RALLY_POINTS),
            "rally_ready": self.rally_earned,
            "rally_active": any(ally.rally for ally in self.allies),
        }

    def _update_bonuses(self, dt: float) -> None:
        """Earn calls and Rally progress, run the helpers, and bring in a scheduled Rally."""
        # Earn: each call costs more points than the last; Rally needs a big combo and lots of points.
        if self.ally_calls < ALLY_MAX_CALLS and self.score - self.ally_points_mark >= self.ally_cost:
            self.ally_points_mark += self.ally_cost
            self.ally_cost += ALLY_COST_STEP
            self.ally_calls += 1
            self._announce(t("ally_call_earned"), (240, 200, 90))
        if self.ally_calls >= ALLY_MAX_CALLS:
            self.ally_points_mark = self.score  # full: points don't bank toward a call you can't hold
        self.rally_best_chain = max(self.rally_best_chain, self.player.hit_chain)
        if not self.rally_earned and self.rally_best_chain >= RALLY_COMBO and self.score - self.rally_points_mark >= RALLY_POINTS:
            self.rally_earned = True
            self._announce(t("rally_earned"), (255, 236, 170))

        if self.rally_timer is not None:
            self.rally_timer -= dt
            if self.rally_timer <= 0 and not self.renderer.intro_showing:  # let the boss's name banner finish first
                self.rally_timer = None
                self._start_rally()

        # Helpers fight, score for the team, and leave when their time is up (or the boss wave is won).
        boss_wave_won = not self.enemies
        for ally in self.allies:
            ally.update_ai(dt, self.enemies, self.player)
            clamp_to_bounds(ally, self.camera_x + SCREEN_WIDTH, SCREEN_HEIGHT, self.camera_x)
            self.banked_score += ally.score
            ally.score = 0
        leaving = [ally for ally in self.allies if ally.expired or (ally.rally and boss_wave_won)]
        for ally in leaving:
            self.player.special_events.append(("smoke", {"x": ally.position.x, "y": ally.position.y + ally.height / 2}))
        if leaving:
            audio.play("strafe", 0.6)
            self.allies = [ally for ally in self.allies if ally not in leaving]

    def _call_ally(self) -> None:
        """X: spend a call to bring a random other hero for ALLY_DURATION seconds."""
        if self.ally_calls <= 0 or any(not ally.rally for ally in self.allies) or not self.player.is_alive():
            if self.ally_calls <= 0:
                audio.play("ui_tick")
            return
        busy = {self.character_name, *(ally.character_name for ally in self.allies)}
        choices = [name for name in CHARACTER_NAMES if name not in busy]
        if not choices:
            return
        self.ally_calls -= 1
        name = random.choice(choices)
        self._summon(name, ALLY_DURATION, rally=False, slot=len(self.allies))
        self._announce(t("ally_joins", name=i18n.hero_name(name).upper()), (240, 200, 90))
        audio.play("level_complete", 0.5)

    def _on_wave_start(self) -> None:
        """A boss or mid-boss arrives: bring in the Rally if it's earned (or for the first-boss showcase)."""
        boss_here = any(enemy.is_boss or getattr(enemy, "is_mid_boss", False) for enemy in self.enemies)
        if boss_here and (self.rally_earned or not self.rally_showcased):
            self.rally_timer = RALLY_DELAY

    def _start_rally(self) -> None:
        if not self.enemies or not self.player.is_alive():
            return
        showcase = not self.rally_showcased
        self.rally_showcased = True
        self.rally_earned = False
        self.rally_best_chain = 0
        self.rally_points_mark = self.score
        names = [name for name in CHARACTER_NAMES if name != self.character_name and name not in {a.character_name for a in self.allies}]
        for slot, name in enumerate(names):
            self._summon(name, None, rally=True, slot=slot)
        self.renderer.show_banner(t("rally_title"), t("rally_showcase", combo=RALLY_COMBO, points=RALLY_POINTS) if showcase else t("rally_sub"))
        audio.play("victory", 0.6)

    def _summon(self, name: str, seconds: float | None, rally: bool, slot: int) -> None:
        side = -1 if slot % 2 == 0 else 1
        x = self.player.position.x + side * (80 + 30 * (slot // 2))
        y = max(LEVEL_SAFE_TOP + 60, min(SCREEN_HEIGHT - 50, self.player.position.y + ((slot % 3) - 1) * 40))
        ally = Ally(Position(x, y), name, self.difficulty, seconds, rally, slot)
        ally.face_sign = 1
        self.allies.append(ally)
        self.player.special_events.append(("smoke", {"x": x, "y": y + ally.height / 2}))
        self.player.special_events.append(("holy", {"x": x, "y": y + ally.height / 2, "reach": 60, "healed": 0}))

    def _announce(self, text: str, color: tuple[int, int, int]) -> None:
        self.renderer.toast(text, color)

    def _collect(self, kind: str) -> None:
        """Apply a picked-up drop. Rider rewards also announce themselves over the hero."""
        player = self.player
        if kind == "potion":
            player.fury = min(FURY_MAX, player.fury + POTION_FURY)
        elif kind == "meat":
            player.heal(MEAT_HEAL)
        elif kind == "elixir":  # bat rider: special ready now, plus some Fury
            player.special_cooldown = 0.0
            player.fury = min(FURY_MAX, player.fury + ELIXIR_FURY)
            player.special_events.append(("text", {"x": player.position.x, "y": player.position.y, "text": t("reward_elixir"), "color": (210, 150, 255)}))
        elif kind == "pelt":  # wolf rider: one more shield charge
            player.shield_charges = min(PELT_SHIELD_CAP, player.shield_charges + 1)
            player.special_events.append(("text", {"x": player.position.x, "y": player.position.y, "text": t("reward_pelt"), "color": (150, 210, 255)}))

    @property
    def can_swap_hero(self) -> bool:
        """Between waves (the GO arrow is up and the field is clear), the hero can be changed with C."""
        player = self.player
        return (
            self.state == GameState.LEVEL and self.advancing and not self.enemies
            and player.is_alive() and player.can_act and not player.is_attacking and not player.is_airborne
        )

    def _swap_hero_between_waves(self) -> None:
        """
        Swap to the next hero on the spot, between waves.

        The newcomer takes over the same health share (so swapping never heals),
        Fury, shield charges, and this level's score.
        """
        if not self.can_swap_hero:
            return
        old = self.player
        self.selected_index = (self.selected_index + 1) % len(CHARACTER_NAMES)
        new = self._new_player()
        new.position = Position(old.position.x, old.position.y)
        new.face_sign = old.face_sign
        new.hp = max(1, round(new.max_hp * old.hp / old.max_hp))
        new.fury = old.fury
        new.fury_timer = old.fury_timer
        new.shield_charges = old.shield_charges
        new.score = old.score
        self.player = new
        self.renderer.adopt_player(old, new)
        new.special_events.append(("smoke", {"x": new.position.x, "y": new.position.y + new.height / 2}))
        audio.play("strafe")
        audio.play("shield")

    def _return_home(self) -> None:
        self.swap_mode = False
        self.state = GameState.HOME
        self.home_index = 0
        self.level = 1
        self.enemies = []

    @staticmethod
    def _now() -> float:
        return pygame.time.get_ticks() / 1000.0

    def _advance(self, dt: float) -> None:
        """
        Golden Axe-style scrolling: once a wave falls, a GO prompt appears and the
        camera follows the hero rightward until the next section, where the next
        wave arrives and the camera locks again.
        """
        if not self.advancing:
            self.advancing = True
            audio.play("ui_confirm")
        target = (self.wave + 1) * SCREEN_WIDTH
        follow = self.player.position.x - SCREEN_WIDTH * 0.45
        step = min(follow, self.camera_x + GO_SCROLL_SPEED * dt)
        self.camera_x = min(target, max(self.camera_x, step))
        if self.camera_x >= target:
            self.camera_x = float(target)
            self.advancing = False
            self.wave += 1
            self.enemies = self._spawn_wave(self.level, self.wave)
            self._on_wave_start()

    def _spawn_wave(self, level: int, wave: int) -> list[Enemy]:
        """
        Enemies for one wave, entering from off-screen (mostly from ahead, some from
        behind on later waves). The middle wave of every level brings that level's
        mid-boss with a few escorts; the last wave of the final level brings the boss.
        """
        left = self.camera_x
        boss_wave = level >= MAX_LEVEL and wave == self.wave_count - 1
        mid_boss_wave = wave == self.wave_count // 2 and level in MID_BOSSES
        count = 3 if boss_wave else 1 + level // 2 if mid_boss_wave else 2 + level // 2 + wave // 2
        top, bottom = LEVEL_SAFE_TOP + 60, SCREEN_HEIGHT - 50
        enemies: list[Enemy] = []
        for index in range(count):
            y = top + (bottom - top) * (index + 0.5) / count
            from_behind = wave > 0 and index % 3 == 2
            if from_behind:
                x = left - 60 - index * 25
            else:
                x = left + SCREEN_WIDTH + 60 + (index // 2) * 70
            enemies.append(Enemy(Position(x, y), level))
        if boss_wave:
            enemies.append(EmberDemon(Position(left + SCREEN_WIDTH + 130, SCREEN_HEIGHT / 2 + 30), level))
        if mid_boss_wave:
            enemies.append(MidBoss(Position(left + SCREEN_WIDTH + 120, SCREEN_HEIGHT / 2 + 40), level))
        if not boss_wave:
            enemies.extend(self._spawn_beasts(level, wave, mid_boss_wave))
        return enemies

    def _spawn_beasts(self, level: int, wave: int, mid_boss_wave: bool) -> list:
        """
        The goblin riders joining a wave (see RIDER_DENSITY).

        Only some waves bring riders: their number and group size grow with the
        difficulty and the level. Groups alternate wolf-rider packs and bat-rider
        flocks (the crypt level starts with bats); on hard, a bat rider escorts the mid-boss.
        """
        left = self.camera_x
        density = RIDER_DENSITY.get(self.difficulty, RIDER_DENSITY["medium"])
        if mid_boss_wave:
            group = ["bat_rider"] * density["escort"]
        else:
            rider_waves = self._rider_waves(level)
            if wave not in rider_waves:
                return []
            size = min(RIDER_GROUP_MAX, density["group"] + (level - 1) // RIDER_GROUP_LEVEL_STEP)
            kind = "wolf_rider" if (rider_waves.index(wave) + (1 if level == 2 else 0)) % 2 == 0 else "bat_rider"
            group = [kind] * size
        beasts = []
        top, bottom = LEVEL_SAFE_TOP + 60, SCREEN_HEIGHT - 50
        for index, kind in enumerate(group):
            y = top + (bottom - top) * (index + 0.5) / len(group)
            behind = kind == "wolf_rider" and index % 2 == 1  # packs flank from both sides
            x = left - 80 - index * 40 if behind else left + SCREEN_WIDTH + 90 + index * 60
            beasts.append(BEAST_TYPES[kind](Position(x, y), level))
        return beasts

    def _rider_waves(self, level: int) -> list[int]:
        """
        Which ordinary waves of a level bring riders: a share of them set by difficulty
        and level (at least one), spread evenly, leaning toward the later waves.
        """
        density = RIDER_DENSITY.get(self.difficulty, RIDER_DENSITY["medium"])
        mid_wave = self.wave_count // 2
        last = self.wave_count - 1
        ordinary = [w for w in range(self.wave_count) if w != mid_wave and not (level >= MAX_LEVEL and w == last)]
        share = min(1.0, density["share"] + RIDER_SHARE_PER_LEVEL * (level - 1))
        count = max(1, min(len(ordinary), round(len(ordinary) * share)))
        step = len(ordinary) / count
        return [ordinary[min(len(ordinary) - 1, int(len(ordinary) - step * (i + 0.5)))] for i in reversed(range(count))]


def _window_size() -> tuple[int, int]:
    """
    The biggest of WINDOW_SIZES that fits comfortably on the screen (room left for
    the menu bar, title bar and dock).

    Uses pygame.display.Info() before the window exists; get_desktop_sizes() is
    avoided because it corrupts memory (segfault) in pygame 2.6.1 on Python 3.13.
    """
    info = pygame.display.Info()
    screen_w, screen_h = info.current_w, info.current_h
    if screen_w <= 0 or screen_h <= 0:
        return WINDOW_SIZES[-1]
    for width, height in WINDOW_SIZES:
        if width <= screen_w * 0.92 and height <= screen_h * 0.82:
            return width, height
    return WINDOW_SIZES[-1]
