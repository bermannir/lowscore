"""
Module: renderer
Purpose: Main rendering system: lit dungeon arena, actors, combat effects, and HUD.
Dependencies: pygame, lowscore.core.constants, lowscore.ui.art, lowscore.ui.effects
Used by: Main game loop.
"""

from __future__ import annotations

import math
from typing import Iterable, Protocol

import pygame

from core.constants import (
    ATTACK_COOLDOWN,
    FIGHTER_SCALE,
    CHARACTER_DAMAGE,
    CHARACTER_HP,
    CHARACTER_SPEEDS,
    COLORS,
    DEBUG_MODE,
    DIFFICULTIES,
    DIFFICULTY_DAMAGE_TAKEN,
    DIFFICULTY_HP_REGEN,
    FURY_DURATION,
    FURY_MAX,
    SPECIALS,
    HUD_PADDING,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    SHIELD_DURATION,
    SHOW_FPS,
)
from core import i18n
from core.i18n import t
from core.story import chapter_title, scene
from core.types import Position, Vector2
from systems.audio import VOLUME_LEVELS, audio
from ui import art
from ui.effects import Effects

SERIF_FONTS = "baskerville,georgia,palatino,timesnewroman,serif"
SANS_FONTS = "avenirnext,avenir,helveticaneue,helvetica,arial"
# Baskerville, Georgia and Avenir have no Hebrew letters; these have Hebrew and Latin.
HEBREW_SERIF_FONTS = "timesnewroman,arial"
HEBREW_SANS_FONTS = "arial,lucidagrande"

GOLD = (232, 190, 105)
PARCHMENT = (226, 208, 170)
MUTED = (168, 156, 140)
MENU_TEXT = (250, 238, 210)
MENU_HINT = (222, 212, 192)
TEXT_CACHE_LIMIT = 400  # rendered labels kept before the cache is flushed


class Drawable(Protocol):
    """Protocol for actors the renderer can draw and track."""

    position: Position
    velocity: Vector2
    height: int
    face_sign: int
    hp: int
    max_hp: int
    shield_charges: int
    attack_cooldown: float
    shield_timer: float
    is_shielding: bool

    def draw(self, surface: pygame.Surface) -> None:
        """Draw the object to the given surface."""
        ...


class Renderer:
    """
    Draws the current game state to the screen.

    The world is composed on an offscreen surface (so the camera can shake),
    then the HUD is drawn on top in screen space. Hits and deaths are detected
    by watching actor HP between frames, so gameplay code stays untouched.
    """

    def __init__(self, screen: pygame.Surface, clock: pygame.time.Clock) -> None:
        """Initialize the renderer with the active screen and game clock."""
        self.display = screen
        # Everything is drawn to this opaque frame, then copied to the window in flip_display.
        self.screen = art.opaque_surface(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.clock = clock
        self._text_cache: dict[tuple, pygame.Surface] = {}
        self.freeze_frame: pygame.Surface | None = None
        self.load_fonts()

        self.backdrop = art.build_backdrop(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.vignette = art.vignette(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.menu_world = art.opaque_surface(SCREEN_WIDTH, SCREEN_HEIGHT)
        # The level is one long strip; world holds the whole of it and the camera shows a window.
        self.level_backdrop = self.backdrop
        self.fixtures = art.DEFAULT_FIXTURES
        self.world = art.opaque_surface(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.view = pygame.Rect(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        self.effects = Effects((SCREEN_WIDTH, SCREEN_HEIGHT))

        self._tracked: dict[int, tuple[Drawable, int]] = {}
        self._player_id: int | None = None
        self._shown_hp = 0.0
        self._last_step = 0
        self._panels: dict[tuple[int, int, int], pygame.Surface] = {}
        self._portraits: dict[str, pygame.Surface] = {}
        self._difficulty_label = ""
        self._boss: Drawable | None = None
        self._intro_id: int | None = None
        self._intro_started = -10.0
        self._banner: tuple[str, str, float] | None = None
        self._toasts: list[tuple[str, tuple[int, int, int], float]] = []

    def load_fonts(self) -> None:
        """(Re)create the fonts for the active language; Hebrew needs fonts that contain Hebrew letters."""
        specs = {
            "font_small": ("sans", 14, True), "font_medium": ("sans", 17, True), "font_banner": ("serif", 26, True),
            "font_title": ("serif", 86, True), "font_prompt": ("serif", 32, True), "font_hint": ("sans", 19, True),
            "font_heading": ("serif", 40, True), "font_name": ("serif", 22, True), "font_story": ("serif", 26, False),
            "font_hits": ("serif", 48, True), "font_tiny": ("sans", 11, True),
        }
        rtl = i18n.is_rtl()
        # Pure-English text (the game title, numbers, key names) keeps the original Latin fonts in Hebrew mode.
        self._latin_twin: dict[int, pygame.font.Font] = {}
        for attribute, (kind, size, bold) in specs.items():
            latin = pygame.font.SysFont(SERIF_FONTS if kind == "serif" else SANS_FONTS, size, bold=bold)
            font = pygame.font.SysFont(HEBREW_SERIF_FONTS if kind == "serif" else HEBREW_SANS_FONTS, size, bold=bold) if rtl else latin
            setattr(self, attribute, font)
            self._latin_twin[id(font)] = latin
        self._text_cache.clear()
        if hasattr(self, "effects"):
            self.effects.load_fonts()

    def capture_freeze(self) -> None:
        """Keep the current frame to show behind the pause and settings menus."""
        self.freeze_frame = self.screen.copy()

    # ------------------------------------------------------------------
    # Frames
    # ------------------------------------------------------------------

    def set_level(self, level: int, sections: int) -> None:
        """Build the scrolling scenery strip for a level (one themed section per wave)."""
        themes = art.themes_for_level(level, sections)
        self.level_backdrop, self.fixtures = art.build_level_backdrop(themes, SCREEN_HEIGHT, seed=level * 101)
        size = self.level_backdrop.get_size()
        self.world = art.opaque_surface(*size)
        self.effects.resize(size)

    def render_world(
        self,
        player: Drawable,
        entities: Iterable[Drawable] | None = None,
        level_name: str = "Phase 1",
        enemy_count: int = 0,
        max_level: int = 1,
        pickups: Iterable = (),
        score: int = 0,
        camera_x: float = 0.0,
        wave_label: str = "",
        show_go: bool = False,
        show_swap: bool = False,
        allies: Iterable[Drawable] = (),
        bonus: dict | None = None,
    ) -> None:
        """Render one full gameplay frame through the camera window at camera_x."""
        dt = min(0.05, self.clock.get_time() / 1000.0)
        now = pygame.time.get_ticks() / 1000.0
        actors = list(entities) if entities is not None else []

        allies = list(allies)
        self._sync_effects(player, actors, now)
        for ally in allies:  # helpers' specials and arrivals; they aren't tracked for hits or deaths
            for kind, data in ally.special_events:
                self.effects.spawn_special(kind, data)
            ally.special_events.clear()
        self._spawn_ambient(player, dt, actors)
        self._boss = next((actor for actor in actors if getattr(actor, "shows_boss_bar", False) and actor.is_alive()), None)
        if self._boss is not None and id(self._boss) != self._intro_id:
            self._intro_id, self._intro_started = id(self._boss), now  # a new boss enters: show its name
        self.effects.update(dt)

        view = self.view = pygame.Rect(round(camera_x), 0, SCREEN_WIDTH, SCREEN_HEIGHT)
        self.world.set_clip(view)
        self.world.blit(self.level_backdrop, view.topleft, view)
        self.effects.draw_ground(self.world)
        art.draw_fixtures(self.world, now, self.fixtures, view)
        self.render_entities(sorted([*pickups, *actors, *allies, player], key=lambda thing: thing.position.y))
        self.effects.draw_air(self.world)
        art.draw_light_glow(self.world, now, self.fixtures, view)
        self.world.set_clip(None)

        self.screen.fill(COLORS["black"])
        self.screen.blit(self.world, self.effects.shake_offset(), view)
        self.screen.blit(self.vignette, (0, 0))
        self.render_hud(player, level_name, enemy_count, max_level, wave_label)
        self._draw_score(score, player)
        if show_go:
            self._draw_go_arrow(now)
        self._draw_boss_intro(now)
        self._draw_banner(now)
        self._draw_toasts(now)
        if bonus is not None:
            self._draw_bonus_panel(bonus, now)
        if show_swap:
            self._draw_swap_hint()

        if DEBUG_MODE:
            self.render_debug_overlay()

        self.flip_display()

    def render_entities(self, entities: Iterable[Drawable]) -> None:
        """Draw all provided entities."""
        for entity in entities:
            entity.draw(self.world)

    def render_message_screen(
        self,
        title: str,
        prompt: str,
        hint: str,
        color: tuple[int, int, int],
        menu: tuple[list[str], int] | None = None,
    ) -> None:
        """Render a cinematic title, win, or failure screen; menu=(options, selected) shows a menu instead of the prompt."""
        now = self._begin_menu_frame()
        figures = (
            (art.PLAYER_LOOK, 330, 560, 1, 2.2, 0.0),
            (art.ENEMY_LOOKS[0], 870, 560, -1, 2.2, 1.3),
        )
        self._draw_menu_backdrop(now, dim=figures)
        self._draw_text_band(110, 470 if menu is not None else 380)

        heading = self._metal_text(title, self.font_title, color)
        # Blur on an opaque black base so transparent pixels don't add light.
        glow = pygame.Surface(heading.get_size())
        glow.blit(heading, (0, 0))
        glow = pygame.transform.smoothscale(
            pygame.transform.smoothscale(glow, (heading.get_width() // 8, heading.get_height() // 8)),
            heading.get_size(),
        )
        center = (SCREEN_WIDTH // 2, 180)
        self.screen.blit(glow, glow.get_rect(center=center), special_flags=pygame.BLEND_RGB_ADD)
        self.screen.blit(heading, heading.get_rect(center=center))

        self._draw_divider(SCREEN_WIDTH // 2, 246, 220, color)

        if menu is not None:
            self._draw_menu_list(menu[0], menu[1], 300)
            hint_y = 300 + len(menu[0]) * 44
        else:
            # Gentle pulse that never drops low enough to lose readability.
            pulse = 0.88 + 0.12 * math.sin(now * 3.0)
            prompt_image = art.faded(self._metal_text(prompt, self.font_prompt, MENU_TEXT), 255 * pulse)
            self.screen.blit(prompt_image, prompt_image.get_rect(center=(SCREEN_WIDTH // 2, 302)))
            hint_y = 348
        hint_image = self._metal_text(hint, self.font_hint, MENU_HINT)
        self.screen.blit(hint_image, hint_image.get_rect(center=(SCREEN_WIDTH // 2, hint_y)))

        self.flip_display()

    def render_settings(self, rows: list[tuple[str, str]], index: int, notes: list[str], in_game: bool) -> None:
        """
        Render the settings menu: one row per option with its current value
        (LEFT/RIGHT changes it), a final Back row, and explanatory notes.
        """
        self._draw_overlay_background(in_game)
        heading = self._metal_text(t("settings_title"), self.font_heading, GOLD)
        self.screen.blit(heading, heading.get_rect(center=(SCREEN_WIDTH // 2, 70)))
        self._draw_divider(SCREEN_WIDTH // 2, 108, 180, GOLD)

        row_h = 52
        panel = pygame.Rect(0, 0, 720, row_h * len(rows) + 28)
        panel.midtop = (SCREEN_WIDTH // 2, 132)
        self._draw_panel(panel)
        rtl = i18n.is_rtl()
        for i, (label, value) in enumerate(rows):
            y = panel.top + 14 + i * row_h + row_h // 2
            selected = i == index
            row = pygame.Rect(panel.left + 12, y - row_h // 2 + 4, panel.width - 24, row_h - 8)
            if selected:
                pygame.draw.rect(self.screen, (64, 50, 38), row, border_radius=8)
                pygame.draw.rect(self.screen, GOLD, row, 1, border_radius=8)
            label_image = self._metal_text(label, self.font_hint, GOLD if selected else PARCHMENT)
            if not value:  # the Back row
                self.screen.blit(label_image, label_image.get_rect(center=row.center))
                continue
            value_image = self._metal_text(value, self.font_hint, MENU_TEXT if selected else MUTED)
            label_side, value_side = (row.right - 24, row.left + 24) if rtl else (row.left + 24, row.right - 24)
            if rtl:
                self.screen.blit(label_image, label_image.get_rect(midright=(label_side, y)))
                value_rect = value_image.get_rect(midleft=(value_side + 22, y))
            else:
                self.screen.blit(label_image, label_image.get_rect(midleft=(label_side, y)))
                value_rect = value_image.get_rect(midright=(value_side - 22, y))
            self.screen.blit(value_image, value_rect)
            arrow_color = GOLD if selected else (110, 98, 84)
            for direction, x in ((-1, value_rect.left - 14), (1, value_rect.right + 14)):
                tip = x + direction * 6
                pygame.draw.polygon(self.screen, arrow_color, [(tip, y), (x - direction * 4, y - 7), (x - direction * 4, y + 7)])

        y = panel.bottom + 26
        for note in notes:
            self._blit_text(note, self.font_small, MUTED, center=(SCREEN_WIDTH // 2, y))
            y += 22
        hint = self._metal_text(t("settings_hint"), self.font_hint, MENU_HINT)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT - 60)))
        self.flip_display()

    def render_pause(self, options: list[str], index: int) -> None:
        """Render the pause menu over the frozen battle."""
        self._draw_overlay_background(in_game=True)
        heading = self._metal_text(t("paused"), self.font_title, GOLD)
        self.screen.blit(heading, heading.get_rect(center=(SCREEN_WIDTH // 2, 190)))
        self._draw_divider(SCREEN_WIDTH // 2, 252, 200, GOLD)
        self._draw_menu_list(options, index, 310)
        self.flip_display()

    def _draw_overlay_background(self, in_game: bool) -> None:
        """The frozen battle (dimmed) when paused in a level, otherwise the torch-lit menu hall."""
        if in_game and self.freeze_frame is not None:
            self.screen.blit(self.freeze_frame, (0, 0))
            shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            shade.fill((0, 0, 0, 170))
            self.screen.blit(shade, (0, 0))
        else:
            now = self._begin_menu_frame()
            self._draw_menu_backdrop(now, darkness=160)

    def _draw_menu_list(self, options: list[str], index: int, top: int) -> None:
        """Vertical menu: the selected option is gold and flanked by diamonds."""
        for i, option in enumerate(options):
            y = top + i * 44
            selected = i == index
            image = self._metal_text(option, self.font_prompt, GOLD if selected else MENU_HINT)
            rect = image.get_rect(center=(SCREEN_WIDTH // 2, y))
            self.screen.blit(image, rect)
            if selected:
                art.draw_diamond(self.screen, (rect.left - 22, y), 7, GOLD)
                art.draw_diamond(self.screen, (rect.right + 22, y), 7, GOLD)

    def render_character_select(self, names: list[str], index: int, difficulty: str = "medium", swap: bool = False) -> None:
        """
        Render the hero select screen: a row of cards, the chosen hero's stats, and difficulty.

        swap: opened between levels to change heroes (difficulty is fixed, ESC goes back).
        """
        now = self._begin_menu_frame()
        self._draw_menu_backdrop(now, darkness=150)

        heading = self._metal_text(t("change_hero" if swap else "choose_hero"), self.font_heading, GOLD)
        self.screen.blit(heading, heading.get_rect(center=(SCREEN_WIDTH // 2, 58)))
        self._draw_divider(SCREEN_WIDTH // 2, 96, 180, GOLD)

        card_w, card_h, gap = 160, 236, 18
        left = (SCREEN_WIDTH - (card_w * len(names) + gap * (len(names) - 1))) // 2
        for i, name in enumerate(names):
            look = art.CHARACTER_LOOKS.get(name, art.PLAYER_LOOK)
            selected = i == index
            card = pygame.Rect(left + i * (card_w + gap), 120 - (8 if selected else 0), card_w, card_h)
            self._draw_panel(card)
            art.draw_fighter(self.screen, look, card.centerx, card.bottom - 54, now + i * 0.7, face_sign=1, scale=1.7)
            name_image = self._metal_text(i18n.hero_name(name).upper(), self.font_name, GOLD if selected else PARCHMENT)
            self.screen.blit(name_image, name_image.get_rect(center=(card.centerx, card.bottom - 32)))
            self._blit_text(i18n.class_title(look["title"]), self.font_small, MUTED, center=(card.centerx, card.bottom - 12))
            if selected:
                pygame.draw.rect(self.screen, GOLD, card.inflate(6, 6), 3, border_radius=12)
            else:
                dim = pygame.Surface(card.size, pygame.SRCALPHA)
                pygame.draw.rect(dim, (0, 0, 0, 120), dim.get_rect(), border_radius=10)
                self.screen.blit(dim, card)

        name = names[index]
        stats = (
            (t("stat_health"), CHARACTER_HP, (224, 72, 60)),
            (t("stat_speed"), CHARACTER_SPEEDS, (96, 186, 230)),
            (t("stat_power"), CHARACTER_DAMAGE, (236, 184, 80)),
        )
        info = pygame.Rect(170, 382, 520, 128)
        self._draw_panel(info)
        for row, (label, table, color) in enumerate(stats):
            y = info.top + 28 + row * 36
            self._blit_text(label, self.font_medium, PARCHMENT, topleft=(info.left + 28, y - 10))
            bar = pygame.Rect(info.left + 130, y - 7, 300, 14)
            ratio = table[name] / max(table.values())
            pygame.draw.rect(self.screen, (20, 14, 14), bar.inflate(4, 4), border_radius=5)
            fill = bar.copy()
            fill.width = round(bar.width * ratio)
            self.screen.blit(art.vertical_gradient(bar.width, bar.height, (*art.mix(color, (255, 255, 255), 0.3), 255), (*art.shade(color, 0.6), 255)), fill, (0, 0, fill.width, fill.height))
            self._blit_text(str(table[name]), self.font_medium, MENU_TEXT, topleft=(bar.right + 16, y - 10))

        self._draw_difficulty_picker(pygame.Rect(info.right + 20, info.top, 320, info.height), difficulty)
        self._draw_special_line(name, info.bottom + 14)

        hint = self._metal_text(t("swap_select_hint" if swap else "select_hint"), self.font_hint, MENU_HINT)
        self.screen.blit(hint, hint.get_rect(center=(SCREEN_WIDTH // 2, 560)))
        self.flip_display()

    def _draw_special_line(self, name: str, y: int) -> None:
        """Under the stats on hero select: the hero's special ability icon, name, and what it does."""
        kind = SPECIALS[name]["kind"]
        label = f"{t('ctl_special')} (W):  {t('special_' + kind)}  ·  {t('special_desc_' + kind)}"
        width = self._font_for(self.font_small, label).size(i18n.visual(label))[0]
        icon_x = SCREEN_WIDTH // 2 - (width + 34) // 2 + 13
        art.draw_special_icon(self.screen, (icon_x, y + 2), 26, kind, art.CHARACTER_LOOKS[name])
        self._blit_text(label, self.font_small, GOLD, topleft=(icon_x + 21, y - 7))

    def _draw_difficulty_picker(self, panel: pygame.Rect, difficulty: str) -> None:
        self._draw_panel(panel)
        colors = {"easy": (120, 210, 130), "medium": (236, 196, 100), "hard": (232, 92, 72)}
        for row, level in enumerate(DIFFICULTIES):
            y = panel.top + 28 + row * 36
            chosen = level == difficulty
            if chosen:
                pygame.draw.rect(self.screen, (60, 48, 36), (panel.left + 10, y - 15, panel.width - 20, 30), border_radius=6)
                pygame.draw.rect(self.screen, colors[level], (panel.left + 10, y - 15, panel.width - 20, 30), 1, border_radius=6)
                art.draw_diamond(self.screen, (panel.left + 26, y), 5, colors[level])
            name = self._metal_text(t(f"diff_{level}"), self.font_medium, colors[level] if chosen else MUTED)
            self.screen.blit(name, name.get_rect(midleft=(panel.left + 40, y)))
            detail = t("diff_detail", dmg=round(DIFFICULTY_DAMAGE_TAKEN[level] * 100), regen=f"{DIFFICULTY_HP_REGEN[level]:g}")
            self._blit_text(detail, self.font_small, MENU_TEXT if chosen else MUTED, topleft=(panel.left + 140, y - 8))

    def render_story(self, key: int | str, line_index: int, revealed: int, hero_name: str) -> None:
        """Render one line of a story scene with speaker figures and a typewriter dialogue box."""
        now = self._begin_menu_frame()
        hero_look = art.CHARACTER_LOOKS.get(hero_name, art.PLAYER_LOOK)
        level = key if isinstance(key, int) else len(art.ENEMY_LOOKS)
        foe_look = art.ENEMY_LOOKS[(level - 1) % len(art.ENEMY_LOOKS)]
        lines = scene(key)
        speaker, text = lines[min(line_index, len(lines) - 1)]
        display_name = i18n.hero_name(hero_name)
        text = text.replace("{hero}", display_name)

        hero = (hero_look, 300, 400, 1, 2.6, 0.0)
        foe = (foe_look, 900, 400, -1, 2.6, 1.3)
        has_foe = key != "ending"
        cast = [hero, foe] if has_foe else [hero]
        lit = [figure for figure, who in zip(cast, ("hero", "foe")) if who == speaker]
        dim = [figure for figure in cast if figure not in lit]
        self._draw_menu_backdrop(now, dim=dim, lit=lit, darkness=140)

        chapter = self._metal_text(chapter_title(key), self.font_heading, GOLD)
        self.screen.blit(chapter, chapter.get_rect(center=(SCREEN_WIDTH // 2, 54)))
        self._draw_divider(SCREEN_WIDTH // 2, 92, 200, GOLD)

        box = pygame.Rect(90, 418, SCREEN_WIDTH - 180, 156)
        self._draw_panel(box)
        if speaker != "narrator":
            label = display_name if speaker == "hero" else self._foe_name(level)
            tab = pygame.Rect(box.left + 24, box.top - 20, self.font_name.size(label)[0] + 36, 36)
            if i18n.is_rtl():
                tab.right = box.right - 24
            self._draw_panel(tab, radius=8)
            name_image = self._metal_text(label, self.font_name, GOLD)
            self.screen.blit(name_image, name_image.get_rect(center=tab.center))

        color = MENU_HINT if speaker == "narrator" else MENU_TEXT
        y = box.top + 28
        for row in self._wrap(text[:max(0, revealed)], self.font_story, box.width - 64):
            image = self._metal_text(row, self.font_story, color) if row else None
            if image:
                x = box.right - 32 - image.get_width() if i18n.is_rtl() else box.left + 32  # Hebrew aligns right
                self.screen.blit(image, (x, y))
            y += self.font_story.get_linesize() + 4

        if revealed >= len(text) and int(now * 2) % 2 == 0:
            more = t("story_next") if line_index < len(lines) - 1 else t("story_begin") if has_foe else t("story_finish")
            more_x = box.left + 70 if i18n.is_rtl() else box.right - 70
            self._blit_text(more, self.font_small, GOLD, center=(more_x, box.bottom - 20))
        count_x = box.right - 50 if i18n.is_rtl() else box.left + 50
        self._blit_text(f"{line_index + 1} / {len(lines)}", self.font_small, MUTED, center=(count_x, box.bottom - 20))
        self.flip_display()

    def flip_display(self) -> None:
        """Draw the volume indicator over whatever screen is showing, then present the frame."""
        self._draw_volume_indicator()
        width, height = self.display.get_size()
        if (width, height) == (SCREEN_WIDTH, SCREEN_HEIGHT):
            self.display.blit(self.screen, (0, 0))
        else:
            # Scale the 1200x600 picture to the window/screen, keeping its shape (black bars if needed).
            scale = min(width / SCREEN_WIDTH, height / SCREEN_HEIGHT)
            size = (round(SCREEN_WIDTH * scale), round(SCREEN_HEIGHT * scale))
            self.display.fill(COLORS["black"])
            self.display.blit(pygame.transform.smoothscale(self.screen, size), ((width - size[0]) // 2, (height - size[1]) // 2))
        pygame.display.flip()

    def _draw_volume_indicator(self) -> None:
        """Speaker with level bars in the bottom-left; a larger toast briefly after a change."""
        x, y = HUD_PADDING, SCREEN_HEIGHT - 32
        backing = pygame.Surface((118, 26), pygame.SRCALPHA)
        pygame.draw.rect(backing, (8, 6, 8, 150), backing.get_rect(), border_radius=13)
        self.screen.blit(backing, (x, y - 4))

        color = MUTED if audio.muted else PARCHMENT
        pygame.draw.rect(self.screen, color, (x + 10, y + 5, 5, 8))
        pygame.draw.polygon(self.screen, color, [(x + 15, y + 5), (x + 21, y), (x + 21, y + 18), (x + 15, y + 13)])
        if audio.muted:
            pygame.draw.line(self.screen, (220, 90, 70), (x + 25, y + 4), (x + 33, y + 14), 2)
            pygame.draw.line(self.screen, (220, 90, 70), (x + 33, y + 4), (x + 25, y + 14), 2)
        else:
            for i in range(len(VOLUME_LEVELS)):
                height = 5 + i * 3
                lit = i <= audio.volume_index
                pygame.draw.rect(self.screen, GOLD if lit else (60, 52, 46), (x + 26 + i * 6, y + 15 - height, 4, height))
        self._draw_keycap("M", (x + 56, y + 20))
        self._blit_text("-/+", self.font_small, MUTED, topleft=(x + 82, y + 1))

        age = pygame.time.get_ticks() / 1000.0 - audio.changed_at
        if 0 <= age < 1.2:
            label = t("sound_off") if audio.muted else t("volume", n=round(audio.volume * 100))
            toast = self._metal_text(label, self.font_name, GOLD)
            if age > 0.9:
                toast = art.faded(toast, 255 * (1.2 - age) / 0.3)
            box = toast.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 90)).inflate(36, 16)
            self._draw_panel(box, radius=8)
            self.screen.blit(toast, toast.get_rect(center=box.center))

    def render_debug_overlay(self) -> None:
        """Draw debug information such as FPS."""
        if not SHOW_FPS:
            return

        fps = int(self.clock.get_fps())
        self._blit_text(f"FPS {fps}", self.font_small, MUTED, topleft=(SCREEN_WIDTH - 70, SCREEN_HEIGHT - 26))

    # ------------------------------------------------------------------
    # HUD
    # ------------------------------------------------------------------

    def render_hud(
        self,
        player: Drawable,
        level_name: str = "Phase 1",
        enemy_count: int = 0,
        max_level: int = 1,
        wave_label: str = "",
    ) -> None:
        """Draw the player plate, level banner, ability slots, and control hints."""
        dt = min(0.05, self.clock.get_time() / 1000.0)
        if self._shown_hp > player.hp:
            self._shown_hp = max(float(player.hp), self._shown_hp - dt * 45)
        else:
            self._shown_hp = float(player.hp)

        difficulty = getattr(player, "difficulty", "")
        self._difficulty_label = t(f"diff_{difficulty}") if difficulty else ""
        self._draw_player_plate(player)
        self._draw_level_banner(level_name, enemy_count, max_level, wave_label)
        self._draw_ability_slots(player)
        self._draw_boss_bar()
        self._draw_controls_hint()

    def _draw_player_plate(self, player: Drawable) -> None:
        plate = pygame.Rect(HUD_PADDING, 12, 330, 66)
        self._draw_panel(plate)

        medallion = (plate.left + 34, plate.centery)
        look = getattr(player, "look", art.PLAYER_LOOK)
        portrait = self._portrait_surface(look, 25)
        self.screen.blit(portrait, portrait.get_rect(center=medallion))
        pygame.draw.circle(self.screen, (10, 8, 8), medallion, 27, 3)
        pygame.draw.circle(self.screen, GOLD, medallion, 27, 1)

        name = i18n.hero_name(getattr(player, "character_name", "ran")).upper()
        self._blit_text(f"{name}  ·  {i18n.class_title(look['title'])}", self.font_small, PARCHMENT, topleft=(plate.left + 70, plate.top + 9))
        regen = getattr(player, "hp_regen", 0.0)
        if regen:
            healing = getattr(player, "regen_delay", 0.0) <= 0 and 0 < player.hp < player.max_hp
            self._blit_text(f"+{regen:g}/s", self.font_small, (130, 220, 140) if healing else MUTED, topleft=(plate.right - 58, plate.top + 9))
        bar = pygame.Rect(plate.left + 70, plate.top + 31, 244, 20)
        self._draw_health_bar(bar, player.hp, player.max_hp)

    def _draw_level_banner(self, level_name: str, enemy_count: int, max_level: int, wave_label: str = "") -> None:
        banner = pygame.Rect(0, 0, 360, 62)
        banner.midtop = (SCREEN_WIDTH // 2, 12)
        self._draw_panel(banner)
        art.draw_diamond(self.screen, (banner.left, banner.centery), 7, GOLD)
        art.draw_diamond(self.screen, (banner.right, banner.centery), 7, GOLD)

        title = self._metal_text(level_name, self.font_banner, GOLD)
        self.screen.blit(title, title.get_rect(center=(banner.centerx, banner.top + 22)))

        label = t("foe_one") if enemy_count == 1 else t("foes", n=enemy_count)
        if wave_label:
            label = f"{label}  ·  {wave_label}"
        if self._difficulty_label:
            label = f"{label}  ·  {self._difficulty_label}"
        text = self.font_small.render(i18n.visual(label), True, MUTED)
        x = banner.centerx - (text.get_width() + 18) // 2
        art.draw_skull(self.screen, (x + 6, banner.top + 46), 6)
        self.screen.blit(text, (x + 18, banner.top + 46 - text.get_height() // 2))

    def _draw_ability_slots(self, player: Drawable) -> None:
        size, gap = 56, 10
        right = SCREEN_WIDTH - HUD_PADDING
        slots = ("slash", "heavy", "spin", "special", "shield", "fury")
        rects = {
            name: pygame.Rect(right - size - (len(slots) - 1 - i) * (size + gap), 14, size, size)
            for i, name in enumerate(slots)
        }
        now = pygame.time.get_ticks() / 1000.0
        cooldowns = getattr(player, "cooldowns", {"slash": player.attack_cooldown})
        totals = getattr(player, "cooldown_totals", {"slash": ATTACK_COOLDOWN})

        icons = {
            "slash": lambda c: art.draw_sword_icon(self.screen, c, 34),
            "heavy": lambda c: art.draw_heavy_icon(self.screen, c, 34),
            "spin": lambda c: art.draw_spin_icon(self.screen, c, 36),
        }
        for mode, key in (("slash", "R"), ("heavy", "E"), ("spin", "Q")):
            rect = rects[mode]
            self._draw_panel(rect, radius=8)
            icons[mode](rect.center)
            remaining = cooldowns.get(mode, 0.0)
            if remaining > 0:
                self._draw_cooldown_pie(rect.inflate(-6, -6), remaining / max(0.01, totals.get(mode, 1.0)))
            self._draw_keycap(key, (rect.left + 2, rect.bottom - 2))

        self._draw_special_slot(rects["special"], player, now)

        shield = rects["shield"]
        self._draw_panel(shield, radius=8)
        art.draw_shield_icon(self.screen, shield.center, 32, getattr(player, "look", art.PLAYER_LOOK))
        if player.shield_charges <= 0 and not player.is_shielding:
            self._draw_cooldown_pie(shield.inflate(-6, -6), 1.0)
        if player.is_shielding:
            ratio = player.shield_timer / SHIELD_DURATION
            pygame.draw.arc(self.screen, (150, 215, 255), shield.inflate(8, 8), math.pi / 2, math.pi / 2 + 2 * math.pi * ratio, 3)
        self._draw_keycap("A", (shield.left + 2, shield.bottom - 2))
        badge = (shield.right - 4, shield.top + 4)
        pygame.draw.circle(self.screen, (12, 10, 10), badge, 11)
        pygame.draw.circle(self.screen, GOLD, badge, 11, 1)
        self._blit_text(str(player.shield_charges), self.font_small, PARCHMENT, center=badge)

        self._draw_fury_slot(rects["fury"], player, now)

    def adopt_player(self, old: Drawable, new: Drawable) -> None:
        """
        The hero was swapped mid-level: follow the new one without treating the old
        one as fallen (no death effect) and without clearing the level's effects.
        """
        self._tracked.pop(id(old), None)
        self._tracked[id(new)] = (new, new.hp)
        self._player_id = id(new)
        self._shown_hp = float(new.hp)

    def _draw_swap_hint(self) -> None:
        """Between waves: a pill under the GO arrow saying C changes the hero."""
        label = self.font_small.render(i18n.visual(t("swap_hint")), True, PARCHMENT)
        width = label.get_width() + 8 + self._keycap_width("C")
        pill = pygame.Rect(0, 0, width + 28, 30)
        pill.center = (SCREEN_WIDTH - 150, SCREEN_HEIGHT // 2 + 30)
        backing = pygame.Surface(pill.size, pygame.SRCALPHA)
        pygame.draw.rect(backing, (8, 6, 8, 170), backing.get_rect(), border_radius=15)
        self.screen.blit(backing, pill)
        self._draw_keycap("C", (pill.left + 14, pill.centery + 10))
        self.screen.blit(label, (pill.left + 14 + self._keycap_width("C") + 8, pill.centery - label.get_height() // 2))

    def _draw_go_arrow(self, now: float) -> None:
        """Golden Axe's blinking 'GO' prompt: the wave is clear, push forward."""
        if int(now * 3) % 2:
            return
        cx, cy = SCREEN_WIDTH - 150, SCREEN_HEIGHT // 2 - 40
        text = self._metal_text(t("go"), self.font_title, GOLD)
        self.screen.blit(text, text.get_rect(midright=(cx + 10, cy)))
        nudge = 8 * math.sin(now * 8)
        arrow = [(cx + 24 + nudge, cy - 30), (cx + 74 + nudge, cy), (cx + 24 + nudge, cy + 30)]
        pygame.draw.polygon(self.screen, (8, 6, 8), [(x + 3, y + 4) for x, y in arrow])
        pygame.draw.polygon(self.screen, GOLD, arrow)
        pygame.draw.polygon(self.screen, art.shade(GOLD, 0.55), arrow, 3)

    def _draw_score(self, score: int, player: Drawable) -> None:
        """Arcade score under the player plate, plus a big hit counter while a chain is going."""
        label = self._metal_text(t("score", n=f"{score:07d}"), self.font_medium, PARCHMENT)
        self.screen.blit(label, (HUD_PADDING + 6, 84))

        chain = getattr(player, "hit_chain", 0)
        if chain < 2:
            return
        timer = getattr(player, "chain_timer", 0.0)
        number = self._metal_text(str(chain), self.font_hits, (255, 200, 80))
        word = self._metal_text(t("hits"), self.font_banner, GOLD)
        group = pygame.Surface((number.get_width() + word.get_width() + 10, number.get_height()), pygame.SRCALPHA)
        word_y = number.get_height() - word.get_height() - 6
        if i18n.is_rtl():  # Hebrew reads the number first, from the right
            group.blit(word, (0, word_y))
            group.blit(number, (word.get_width() + 10, 0))
        else:
            group.blit(number, (0, 0))
            group.blit(word, (number.get_width() + 8, word_y))
        if timer < 0.4:
            group = art.faded(group, 255 * timer / 0.4)
        self.screen.blit(group, (HUD_PADDING + 4, 108))

    def _draw_boss_bar(self) -> None:
        """Long health bar for the boss, above the controls bar."""
        boss = self._boss
        if boss is None:
            return
        frame = pygame.Rect(0, 0, 520, 46)
        frame.midbottom = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 52)
        self._draw_panel(frame, radius=8)
        raging = getattr(boss, "is_fury_active", False) or getattr(boss, "enraged", False)
        tag = t("fury_tag") if getattr(boss, "is_fury_active", False) else t("enraged_tag")
        title = t(getattr(boss, "name_key", "boss_name")) + (f"  ·  {tag}" if raging else "")
        name = self._metal_text(title, self.font_name, (255, 150, 70) if raging else GOLD)
        self.screen.blit(name, name.get_rect(midleft=(frame.left + 16, frame.top + 14)))
        bar = pygame.Rect(frame.left + 16, frame.top + 27, frame.width - 32, 10)
        ratio = boss.hp / max(1, boss.max_hp)
        pygame.draw.rect(self.screen, (30, 10, 10), bar, border_radius=4)
        fill = round(bar.width * ratio)
        if fill:
            self.screen.blit(art.vertical_gradient(bar.width, bar.height, (255, 120, 60, 255), (150, 24, 16, 255)), bar.topleft, pygame.Rect(0, 0, fill, bar.height))
        fury = getattr(boss, "fury", 0.0) / FURY_MAX
        if fury and not getattr(boss, "is_fury_active", False):
            pygame.draw.line(self.screen, (255, 170, 60), (bar.left, bar.bottom + 3), (bar.left + round(bar.width * fury), bar.bottom + 3), 2)

    @property
    def intro_showing(self) -> bool:
        """True while a boss's name banner is on screen."""
        return pygame.time.get_ticks() / 1000.0 - self._intro_started < 2.6

    def toast(self, text: str, color: tuple[int, int, int]) -> None:
        """A short announcement under the level banner (stacked, fades after a few seconds)."""
        self._toasts.append((text, color, pygame.time.get_ticks() / 1000.0))
        self._toasts = self._toasts[-3:]

    def _draw_toasts(self, now: float) -> None:
        self._toasts = [toast for toast in self._toasts if now - toast[2] < 2.6]
        for row, (text, color, started) in enumerate(self._toasts):
            age = now - started
            alpha = min(1.0, age / 0.12, (2.6 - age) / 0.5)
            image = self._metal_text(text, self.font_hint, color)
            pill = pygame.Surface((image.get_width() + 36, image.get_height() + 10), pygame.SRCALPHA)
            pygame.draw.rect(pill, (12, 8, 4, 190), pill.get_rect(), border_radius=pill.get_height() // 2)
            pygame.draw.rect(pill, (*color, 200), pill.get_rect(), 1, border_radius=pill.get_height() // 2)
            pill.blit(image, image.get_rect(center=pill.get_rect().center))
            self.screen.blit(art.faded(pill, 255 * alpha), pill.get_rect(midtop=(SCREEN_WIDTH // 2, 84 + row * 34 - round(6 * max(0.0, 1 - age / 0.12)))))

    def show_banner(self, title: str, subtitle: str) -> None:
        """Slam a big announcement across the screen for a few seconds (e.g. Heroes' Rally)."""
        self._banner = (title, subtitle, pygame.time.get_ticks() / 1000.0)

    def _draw_banner(self, now: float) -> None:
        if self._banner is None:
            return
        title, subtitle, started = self._banner
        age = now - started
        if age > 3.4:
            self._banner = None
            return
        alpha = min(1.0, age / 0.15, (3.4 - age) / 0.5)
        grow = 1.0 + 0.3 * max(0.0, 1 - age / 0.18)
        band = pygame.Surface((SCREEN_WIDTH, 120), pygame.SRCALPHA)
        band.fill((24, 16, 4, 170))
        pygame.draw.line(band, (240, 200, 90, 230), (0, 1), (SCREEN_WIDTH, 1), 2)
        pygame.draw.line(band, (240, 200, 90, 230), (0, 118), (SCREEN_WIDTH, 118), 2)
        name = self._metal_text(title, self.font_heading, (255, 226, 140))
        if grow != 1.0:
            name = pygame.transform.smoothscale(name, (round(name.get_width() * grow), round(name.get_height() * grow)))
        band.blit(name, name.get_rect(center=(SCREEN_WIDTH // 2, 46)))
        sub = self._metal_text(subtitle, self.font_hint, PARCHMENT)
        band.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 92)))
        self.screen.blit(art.faded(band, 255 * alpha), (0, 150))

    def _draw_bonus_panel(self, bonus: dict, now: float) -> None:
        """
        Under the ability slots: Ally Call (X) with saved calls and progress to the next,
        and Heroes' Rally with its two conditions (combo and points) as bars.
        """
        panel = pygame.Rect(0, 0, 250, 66)
        panel.topright = (SCREEN_WIDTH - HUD_PADDING, 98)
        self._draw_panel(panel, radius=8)
        gold, pale = (240, 200, 90), (255, 236, 170)

        # Row 1: [X] ALLY  ●●  [progress]
        y1 = panel.top + 16
        self._draw_keycap("X", (panel.left + 10, y1 + 10))
        self._blit_text(t("ally_label"), self.font_small, gold if bonus["calls"] else MUTED, topleft=(panel.left + 36, y1 - 8))
        for i in range(bonus["max_calls"]):
            center = (panel.left + 104 + i * 14, y1)
            pygame.draw.circle(self.screen, (20, 14, 10), center, 5)
            if i < bonus["calls"]:
                pygame.draw.circle(self.screen, gold, center, 4)
        bar = pygame.Rect(panel.left + 136, y1 - 4, 100, 8)
        if bonus["ally_active"]:
            self._blit_text(t("ally_active"), self.font_small, pale, center=(bar.centerx, y1 - 1))
        else:
            self._draw_meter(bar, bonus["call_progress"], gold)

        # Row 2: RALLY  combo [bar]  pts [bar]   (glows when earned)
        y2 = panel.top + 42
        ready = bonus["rally_ready"] or bonus["rally_active"]
        label_color = art.mix(gold, pale, 0.5 + 0.5 * math.sin(now * 6)) if ready else MUTED
        self._blit_text(t("rally_label"), self.font_small, label_color, topleft=(panel.left + 10, y2 - 8))
        combo = pygame.Rect(panel.left + 80, y2 - 4, 72, 8)
        points = pygame.Rect(panel.left + 164, y2 - 4, 72, 8)
        if ready:
            self._blit_text(t("rally_active") if bonus["rally_active"] else t("rally_ready"), self.font_small, pale, center=(panel.left + 158, y2 + 3))
        else:
            self._draw_meter(combo, bonus["rally_combo"], (230, 120, 70))
            self._draw_meter(points, bonus["rally_points"], gold)
            for rect, label in ((combo, t("rally_combo_label")), (points, t("rally_points_label"))):
                image = self.font_tiny.render(i18n.visual(label), True, MUTED)
                self.screen.blit(image, image.get_rect(midtop=(rect.centerx, rect.bottom + 2)))

    def _draw_meter(self, rect: pygame.Rect, ratio: float, color: tuple[int, int, int]) -> None:
        pygame.draw.rect(self.screen, (20, 14, 10), rect.inflate(2, 2), border_radius=3)
        fill = round(rect.width * max(0.0, min(1.0, ratio)))
        if fill:
            pygame.draw.rect(self.screen, color, (rect.left, rect.top, fill, rect.height), border_radius=3)

    def _draw_boss_intro(self, now: float) -> None:
        """When a boss walks in, its name slams onto the screen for a couple of seconds."""
        age = now - self._intro_started
        if self._boss is None or age > 2.6:
            return
        alpha = min(1.0, age / 0.15, (2.6 - age) / 0.5)
        grow = 1.0 + 0.25 * max(0.0, 1 - age / 0.15)
        final = not getattr(self._boss, "is_mid_boss", False)
        sub = self._metal_text(t("boss_title" if final else "midboss_title"), self.font_hint, (240, 120, 90))
        name = self._metal_text(t(getattr(self._boss, "name_key", "boss_name")), self.font_heading, (255, 196, 110))
        if grow != 1.0:
            name = pygame.transform.smoothscale(name, (round(name.get_width() * grow), round(name.get_height() * grow)))
        band = pygame.Surface((SCREEN_WIDTH, 110), pygame.SRCALPHA)
        band.fill((10, 4, 4, 150))
        pygame.draw.line(band, (200, 80, 50, 220), (0, 1), (SCREEN_WIDTH, 1), 2)
        pygame.draw.line(band, (200, 80, 50, 220), (0, 108), (SCREEN_WIDTH, 108), 2)
        band.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, 26)))
        band.blit(name, name.get_rect(center=(SCREEN_WIDTH // 2, 68)))
        self.screen.blit(art.faded(band, 255 * alpha), (0, 150))

    def _draw_special_slot(self, rect: pygame.Rect, player: Drawable, now: float) -> None:
        """The hero's special ability (W): cooldown pie, a glow when ready, red ring while raging."""
        special = getattr(player, "special", None)
        if special is None:
            return
        self._draw_panel(rect, radius=8)
        art.draw_special_icon(self.screen, rect.center, 34, special["kind"], getattr(player, "look", art.PLAYER_LOOK))
        remaining = getattr(player, "special_cooldown", 0.0)
        if remaining > 0:
            self._draw_cooldown_pie(rect.inflate(-6, -6), remaining / max(0.01, getattr(player, "special_total", 1.0)))
        else:
            pulse = 0.5 + 0.5 * math.sin(now * 5)
            pygame.draw.rect(self.screen, art.mix((120, 90, 40), (236, 196, 100), pulse), rect.inflate(4, 4), 2, border_radius=10)
        rage = getattr(player, "rage_timer", 0.0)
        if rage > 0:
            ratio = rage / max(0.01, special.get("rage", 1.0))
            pygame.draw.arc(self.screen, (230, 60, 40), rect.inflate(8, 8), math.pi / 2, math.pi / 2 + 2 * math.pi * ratio, 3)
        self._draw_keycap("W", (rect.left + 2, rect.bottom - 2))

    def _draw_fury_slot(self, rect: pygame.Rect, player: Drawable, now: float) -> None:
        """Fury slot: fills bottom-up as hits land, pulses when ready, drains while active."""
        self._draw_panel(rect, radius=8)
        fury = getattr(player, "fury", 0.0)
        fury_timer = getattr(player, "fury_timer", 0.0)
        inner = rect.inflate(-6, -6)

        if fury_timer <= 0 and fury < FURY_MAX:
            level = round(inner.height * fury / FURY_MAX)
            if level:
                fill = art.vertical_gradient(inner.width, inner.height, (255, 170, 60, 150), (170, 40, 10, 150))
                self.screen.blit(fill, (inner.left, inner.bottom - level), pygame.Rect(0, inner.height - level, inner.width, level))
        art.draw_fury_icon(self.screen, rect.center, 34, now)
        if fury_timer <= 0 and fury < FURY_MAX:
            dim = pygame.Surface(inner.size, pygame.SRCALPHA)
            dim.fill((0, 0, 0, 90))
            self.screen.blit(dim, inner)

        if fury_timer > 0:
            ratio = fury_timer / FURY_DURATION
            pygame.draw.arc(self.screen, (255, 140, 50), rect.inflate(8, 8), math.pi / 2, math.pi / 2 + 2 * math.pi * ratio, 3)
        elif fury >= FURY_MAX:
            pulse = 0.5 + 0.5 * math.sin(now * 8)
            pygame.draw.rect(self.screen, art.mix((180, 90, 20), (255, 220, 120), pulse), rect.inflate(6, 6), 3, border_radius=10)
            self._blit_text(t("ready"), self.font_small, (255, 220, 140), center=(rect.centerx, rect.bottom + 12))
        self._draw_keycap("F", (rect.left + 2, rect.bottom - 2))

    def _draw_controls_hint(self) -> None:
        items = (
            (t("ctl_move"), t("key_arrows")), (t("ctl_strafe"), t("key_double")), (t("ctl_combo"), "R"), (t("ctl_jump"), t("key_space")),
            (t("ctl_heavy"), "E"), (t("ctl_spin"), "Q"), (t("ctl_special"), "W"), (t("ctl_shield"), "A"), (t("ctl_fury"), "F"),
        )
        rendered = [(self.font_small.render(i18n.visual(label), True, MUTED), key) for label, key in items]
        widths = [label.get_width() + 8 + self._keycap_width(key) for label, key in rendered]
        gap = 16
        total = sum(widths) + gap * (len(widths) - 1)

        pill = pygame.Rect(0, 0, total + 36, 32)
        pill.midbottom = (SCREEN_WIDTH // 2, SCREEN_HEIGHT - 10)
        backing = pygame.Surface(pill.size, pygame.SRCALPHA)
        pygame.draw.rect(backing, (8, 6, 8, 150), backing.get_rect(), border_radius=16)
        self.screen.blit(backing, pill)

        x = pill.left + 18
        for (label, key), width in zip(rendered, widths):
            self.screen.blit(label, (x, pill.centery - label.get_height() // 2))
            self._draw_keycap(key, (x + label.get_width() + 8, pill.centery + 10))
            x += width + gap

    # ------------------------------------------------------------------
    # Effects bookkeeping
    # ------------------------------------------------------------------

    def _sync_effects(self, player: Drawable, actors: list[Drawable], now: float) -> None:
        """Turn HP changes and disappearances into hit and death effects."""
        if id(player) != self._player_id:
            self._player_id = id(player)
            self._tracked = {}
            self._shown_hp = float(player.hp)
            self.effects.reset()

        for actor in (player, *actors):
            events = getattr(actor, "special_events", None)
            if events:
                for kind, data in events:
                    self.effects.spawn_special(kind, data)
                events.clear()

        for actor in (player, *actors):
            previous = self._tracked.get(id(actor))
            if previous is not None and actor.hp < previous[1]:
                self._on_hit(actor, previous[1] - actor.hp, player)
            self._tracked[id(actor)] = (actor, actor.hp)

        present = {id(player), *(id(actor) for actor in actors)}
        for key in [key for key in self._tracked if key not in present]:
            fallen, last_hp = self._tracked.pop(key)
            if last_hp > 0:
                self._on_hit(fallen, last_hp, player)
            feet_y = fallen.position.y + fallen.height / 2
            if hasattr(fallen, "render_corpse"):  # beasts are drawn lying on their side already
                canvas, lift = fallen.render_corpse(now)
                self.effects.spawn_death(canvas, fallen.position.x, feet_y, fallen.face_sign, (96, 18, 14), rotate=0.0, lift=lift)
                self.effects.add_shake(3)
                continue
            look = getattr(fallen, "look", art.ENEMY_LOOKS[0])
            canvas = art.render_fighter(look, now, False, fallen.face_sign, posture="limp")
            size = FIGHTER_SCALE * getattr(fallen, "draw_scale", 1.0)
            w, h = canvas.get_size()
            canvas = pygame.transform.smoothscale(canvas, (round(w * size), round(h * size)))
            self.effects.spawn_death(canvas, fallen.position.x, feet_y, fallen.face_sign, (96, 18, 14))
            self.effects.add_shake(4)

    def _on_hit(self, actor: Drawable, damage: int, player: Drawable) -> None:
        x, y = actor.position.x, actor.position.y - 8
        if actor is player:
            crit = getattr(player, "last_hit_crit", False)
            player.last_hit_crit = False
            self.effects.spawn_hit(x, y, None, damage, (140, 14, 18), None, (255, 96, 80), crit=crit)
            audio.play("block" if player.is_shielding else "hurt")
            if crit:
                audio.play("crit")
            self.effects.add_shake(3 if player.is_shielding else 7)
        else:
            direction = (actor.position.x - player.position.x, actor.position.y - player.position.y)
            crit = getattr(actor, "last_hit_crit", False)
            actor.last_hit_crit = False
            text_color = (255, 196, 60) if crit else (255, 236, 170)
            self.effects.spawn_hit(x, y, direction, damage, (96, 18, 14), (255, 214, 120), text_color, crit=crit)
            audio.play("crit" if crit else "hit")
            self.effects.add_shake(7 if crit else 3)

    def _spawn_ambient(self, player: Drawable | None, dt: float, actors: Iterable[Drawable] = ()) -> None:
        fixtures = self.fixtures if player is not None else art.DEFAULT_FIXTURES
        for x, y, _ in art.flame_points(fixtures, self.view if player is not None else None):
            if self.effects._rng.random() < dt * 5:
                self.effects.spawn_ember(x, y - 10)

        for actor in (player, *actors) if player is not None else ():
            if getattr(actor, "is_strafing", False):
                self.effects.spawn_dust(actor.position.x, actor.position.y + actor.height / 2)

        if player is None:
            return
        step = int(getattr(player, "walk_phase", 0.0) // math.pi)  # one count per footfall
        if step != self._last_step and player.velocity.length() > 60 and not player.is_airborne:
            self.effects.spawn_dust(player.position.x, player.position.y + player.height / 2)
        self._last_step = step

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------

    def _draw_panel(self, rect: pygame.Rect, radius: int = 10) -> None:
        """Draw a dark leather-and-gold panel with a soft drop shadow."""
        shadow = art.soft_shadow(rect.width, rect.height, 150)
        self.screen.blit(shadow, shadow.get_rect(center=(rect.centerx, rect.centery + 5)))

        key = (rect.width, rect.height, radius)
        panel = self._panels.get(key)
        if panel is None:
            w, h = rect.size
            panel = pygame.Surface(rect.size, pygame.SRCALPHA)
            panel.blit(art.vertical_gradient(w, h, (46, 38, 34, 236), (14, 12, 14, 236)), (0, 0))
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, (255, 255, 255, 255), mask.get_rect(), border_radius=radius)
            panel.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            pygame.draw.rect(panel, (8, 6, 8, 255), panel.get_rect(), 3, border_radius=radius)
            pygame.draw.rect(panel, (164, 128, 70, 255), panel.get_rect().inflate(-2, -2), 1, border_radius=radius - 1)
            pygame.draw.line(panel, (255, 226, 170, 50), (radius, 3), (w - radius, 3))
            self._panels[key] = panel
        self.screen.blit(panel, rect)

    def _draw_health_bar(self, rect: pygame.Rect, hp: int, max_hp: int) -> None:
        ratio = max(0.0, min(1.0, hp / max(1, max_hp)))
        trail = max(0.0, min(1.0, self._shown_hp / max(1, max_hp)))

        pygame.draw.rect(self.screen, (8, 6, 8), rect.inflate(6, 6), border_radius=6)
        pygame.draw.rect(self.screen, (40, 14, 16), rect, border_radius=4)
        if trail > ratio:
            pygame.draw.rect(self.screen, (236, 200, 128), (rect.left, rect.top, round(rect.width * trail), rect.height), border_radius=4)
        fill_width = round(rect.width * ratio)
        if fill_width > 0:
            area = pygame.Rect(0, 0, fill_width, rect.height)
            self.screen.blit(art.vertical_gradient(rect.width, rect.height, (240, 82, 62, 255), (118, 16, 22, 255)), rect.topleft, area)
            gloss = art.vertical_gradient(rect.width, rect.height // 2, (255, 255, 255, 80), (255, 255, 255, 12))
            self.screen.blit(gloss, rect.topleft, pygame.Rect(0, 0, fill_width, rect.height // 2))

        notch = pygame.Surface((1, rect.height), pygame.SRCALPHA)
        notch.fill((0, 0, 0, 90))
        for i in range(1, 4):
            self.screen.blit(notch, (rect.left + rect.width * i // 4, rect.top))
        pygame.draw.rect(self.screen, (164, 128, 70), rect.inflate(6, 6), 1, border_radius=6)

        label = f"{hp} / {max_hp}"
        self._blit_text(label, self.font_small, (0, 0, 0), center=(rect.centerx + 1, rect.centery + 1))
        self._blit_text(label, self.font_small, (255, 246, 230), center=rect.center)

    def _draw_cooldown_pie(self, rect: pygame.Rect, ratio: float) -> None:
        ratio = max(0.0, min(1.0, ratio))
        overlay = pygame.Surface(rect.size, pygame.SRCALPHA)
        cx, cy = rect.width / 2, rect.height / 2
        radius = rect.width
        steps = max(2, int(40 * ratio))
        points = [(cx, cy)]
        for i in range(steps + 1):
            angle = -math.pi / 2 + 2 * math.pi * ratio * i / steps
            points.append((cx + math.cos(angle) * radius, cy + math.sin(angle) * radius))
        pygame.draw.polygon(overlay, (0, 0, 0, 175), points)
        self.screen.blit(overlay, rect)

    def _keycap_width(self, key: str) -> int:
        return max(20, self.font_small.size(key)[0] + 10)

    def _draw_keycap(self, key: str, bottomleft: tuple[int, int]) -> None:
        cap = pygame.Rect(0, 0, self._keycap_width(key), 20)
        cap.bottomleft = bottomleft
        pygame.draw.rect(self.screen, (8, 6, 8), cap.move(0, 2), border_radius=4)
        self.screen.blit(art.vertical_gradient(cap.width, cap.height, (74, 66, 60, 255), (34, 30, 30, 255)), cap)
        pygame.draw.rect(self.screen, (120, 100, 72), cap, 1, border_radius=4)
        self._blit_text(key, self.font_small, PARCHMENT, center=cap.center)

    def _begin_menu_frame(self) -> float:
        """Advance ambient effects for a non-gameplay screen and return the current time."""
        dt = min(0.05, self.clock.get_time() / 1000.0)
        if self._player_id is not None:
            # Leaving gameplay: drop combat leftovers so only ambient embers remain.
            self._player_id = None
            self.effects.reset()
        self._spawn_ambient(None, dt)
        self.effects.update(dt)
        return pygame.time.get_ticks() / 1000.0

    def _draw_menu_backdrop(self, now: float, dim: Iterable[tuple] = (), lit: Iterable[tuple] = (), darkness: int = 120) -> None:
        """
        Draw the torch-lit arena behind a menu.

        Figures are (look, x, feet_y, face_sign, scale, time_offset); dim ones sit
        under the darkening layer, lit ones (e.g. the current speaker) on top of it.
        """
        stage = self.menu_world
        stage.blit(self.backdrop, (0, 0))
        art.draw_fixtures(stage, now)
        for look, x, feet_y, face, scale, offset in dim:
            art.draw_fighter(stage, look, x, feet_y, now + offset, face_sign=face, scale=scale)
        self.effects.draw_air(stage)
        art.draw_light_glow(stage, now)

        shade = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        shade.fill((0, 0, 0, darkness))
        stage.blit(shade, (0, 0))
        for look, x, feet_y, face, scale, offset in lit:
            art.draw_fighter(stage, look, x, feet_y, now + offset, face_sign=face, scale=scale)
        stage.blit(self.vignette, (0, 0))
        self.screen.blit(stage, (0, 0))

    @staticmethod
    def _foe_name(level: int) -> str:
        return t(f"foe_{(level - 1) % 4 + 1}")

    @staticmethod
    def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
        rows: list[str] = []
        current = ""
        for word in text.split(" "):
            candidate = f"{current} {word}".strip()
            if current and font.size(candidate)[0] > width:
                rows.append(current)
                current = word
            else:
                current = candidate
        rows.append(current)
        return rows

    def _draw_text_band(self, top: int, bottom: int) -> None:
        """Darken a soft-edged horizontal band so menu text never sits on bare bricks."""
        fade = 50
        dark = (6, 4, 6, 185)
        clear = (6, 4, 6, 0)
        self.screen.blit(art.vertical_gradient(SCREEN_WIDTH, fade, clear, dark), (0, top))
        band = pygame.Surface((SCREEN_WIDTH, bottom - top - 2 * fade), pygame.SRCALPHA)
        band.fill(dark)
        self.screen.blit(band, (0, top + fade))
        self.screen.blit(art.vertical_gradient(SCREEN_WIDTH, fade, dark, clear), (0, bottom - fade))

    def _draw_divider(self, cx: int, y: int, half_width: int, color: tuple[int, int, int]) -> None:
        tint = art.mix(color, GOLD, 0.5)
        for direction in (-1, 1):
            start = (cx + direction * 14, y)
            end = (cx + direction * half_width, y)
            pygame.draw.line(self.screen, art.shade(tint, 0.8), start, end, 2)
            art.draw_diamond(self.screen, end, 4, tint)
        art.draw_diamond(self.screen, (cx, y), 8, tint)

    def _portrait_surface(self, look: dict, radius: int) -> pygame.Surface:
        key = look["title"]
        if key not in self._portraits:
            canvas = art.render_fighter(look, 0.0, False, 1)
            fx, fy = art.CANVAS_ANCHOR
            crop = canvas.subsurface(pygame.Rect(fx - 17, fy - 92, 42, 42)).copy()
            size = radius * 2
            disc = pygame.Surface((size, size), pygame.SRCALPHA)
            disc.blit(art.vertical_gradient(size, size, (86, 72, 64, 255), (24, 20, 22, 255)), (0, 0))
            disc.blit(pygame.transform.smoothscale(crop, (size, size)), (0, 0))
            mask = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(mask, (255, 255, 255, 255), (radius, radius), radius)
            disc.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self._portraits[key] = disc
        return self._portraits[key]

    def _metal_text(self, text: str, font: pygame.font.Font, tint: tuple[int, int, int]) -> pygame.Surface:
        """Render text with a metallic vertical gradient, a dark outline, and a drop shadow."""
        key = (text, id(font), tint)
        cached = self._text_cache.get(key)
        if cached is not None:
            return cached
        font = self._font_for(font, text)
        text = i18n.visual(text)  # Hebrew into the left-to-right order pygame draws

        face = font.render(text, True, (255, 255, 255))
        w, h = face.get_size()
        light = art.mix(tint, (255, 255, 255), 0.55)
        dark = art.shade(tint, 0.78)
        face.blit(art.vertical_gradient(w, h, (*light, 255), (*dark, 255)), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

        outline = font.render(text, True, (8, 5, 6))
        shadow = art.faded(outline, 170)
        image = pygame.Surface((w + 6, h + 7), pygame.SRCALPHA)
        image.blit(shadow, (4, 5))
        for ox in (0, 1, 2, 3, 4):
            for oy in (0, 1, 2, 3, 4):
                if (ox - 2) ** 2 + (oy - 2) ** 2 <= 5:
                    image.blit(outline, (ox, oy))
        image.blit(face, (2, 2))
        if len(self._text_cache) >= TEXT_CACHE_LIMIT:
            self._text_cache.clear()  # scores and typewriter text change constantly; don't grow forever
        self._text_cache[key] = image
        return image

    def _font_for(self, font: pygame.font.Font, text: str) -> pygame.font.Font:
        """Use the Latin twin of a Hebrew font for text with no Hebrew in it (nicer, and always has the glyphs)."""
        if i18n.has_hebrew(text):
            return font
        return self._latin_twin.get(id(font), font)

    def _blit_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        *,
        topleft: tuple[int, int] | None = None,
        center: tuple[int, int] | None = None,
    ) -> None:
        surface = self._font_for(font, text).render(i18n.visual(text), True, color)
        rect = surface.get_rect(center=center) if center is not None else surface.get_rect(topleft=topleft)
        self.screen.blit(surface, rect)
