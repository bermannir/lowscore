"""
Module: art
Purpose: Procedural textures, lighting, and character art for a grounded, lit look.
Dependencies: pygame
Used by: ui.renderer, ui.effects, and entity draw methods.
"""

from __future__ import annotations

import math
import random
from functools import lru_cache

import pygame

Color = tuple[int, ...]

WALL_HEIGHT = 96
# Fighters are painted on this canvas with the feet at CANVAS_ANCHOR. It is wide and tall enough
# for the longest blade, lunge and slash trail (measured: 116 px forward, 131 px up), so weapon
# tips are never cut off. Keep the centre 44 px above the feet: knockdown/corpse rotation relies on it.
CANVAS_SIZE = (240, 180)
CANVAS_ANCHOR = (120, 134)
# How each fighter swings. arcs: sword (start, end) angle per mode; lunge scales the
# forward step; hop lifts the body on heavy strikes; thrust stabs instead of arcing.
FIGHTING_STYLES = {
    "balanced": {"arcs": {"slash": (-120.0, 72.0), "heavy": (-165.0, 95.0)}, "lunge": 1.0, "hop": 0.0, "thrust": False},
    "overhead": {"arcs": {"slash": (-155.0, 55.0), "heavy": (-210.0, 100.0)}, "lunge": 0.8, "hop": 0.0, "thrust": False},
    "wild": {"arcs": {"slash": (110.0, -70.0), "heavy": (-200.0, 120.0)}, "lunge": 1.3, "hop": 10.0, "thrust": False},
    "quick": {"arcs": {"slash": (-30.0, 20.0), "heavy": (-30.0, 20.0)}, "lunge": 1.7, "hop": 0.0, "thrust": True},
}
SPIN_ARC = (-90.0, 270.0)
MODE_LUNGE = {"slash": 6.0, "slash2": 6.0, "finisher": 12.0, "heavy": 10.0, "spin": 0.0, "dash": 14.0}
HEAVY_WINDUP_SHARE = 0.3  # first part of a heavy swing is the crouch/raise
TRAIL_STYLE = {
    "slash": ((255, 236, 190), 13),
    "slash2": ((255, 236, 190), 13),
    "finisher": ((255, 206, 110), 18),
    "heavy": ((255, 206, 110), 22),
    "spin": ((200, 230, 255), 16),
    "jump": ((255, 236, 190), 16),
    "air1": ((255, 236, 190), 13),
    "air2": ((255, 236, 190), 13),
    "dash": ((220, 240, 255), 10),
    "throw": ((255, 236, 190), 10),
}
JUMP_ARC = (-30.0, 95.0)
FURY_TRAIL = (255, 130, 50)

# Ready stances held while not attacking: where the sword hand sits (relative to the
# shoulder pivot) and which way the blade points.
#   two_hand: both hands on the hilt in front of the belly, blade standing up
#   shoulder: blade resting back over the shoulder
#   obi:      blade raised high behind the head pointing forward, free hand pointing at the foe
GUARDS = {
    "two_hand": {"grip": (8, 18), "blade": -78.0},
    "shoulder": {"grip": (5, 12), "blade": -145.0},
    "obi": {"grip": (-10, -26), "blade": 12.0},
}

SECTION_WIDTH = 1200  # one arena screen; a level is several sections side by side

# Scenery themes. floor tints the flagstones; wall is the brick color (None = open sky);
# ambient is the unlit light level; light is the color fires cast.
THEMES = {
    "hall": {"floor": (1.0, 0.95, 0.88), "wall": (78, 70, 64), "ledge": (92, 84, 78), "ambient": (96, 92, 108), "light": (200, 124, 60)},
    "crypt": {"floor": (0.84, 0.94, 0.92), "wall": (58, 66, 64), "ledge": (78, 88, 86), "ambient": (66, 84, 92), "light": (150, 190, 150)},
    "forge": {"floor": (1.02, 0.8, 0.7), "wall": (86, 56, 48), "ledge": (104, 70, 58), "ambient": (112, 80, 72), "light": (240, 120, 50)},
    "ruins": {"floor": (0.9, 0.98, 0.76), "wall": None, "ledge": (104, 100, 90), "ambient": (96, 106, 146), "light": (200, 124, 60)},
}
THEME_ORDER = ("hall", "crypt", "forge", "ruins")

# Fixtures: (kind, x, y). Torches hang on the wall, braziers stand on the floor, candles sit in crypt alcoves.
THEME_FIXTURES = {
    "hall": (("torch", 405, 44), ("torch", 795, 44), ("brazier", 64, 548), ("brazier", 1136, 548)),
    "crypt": (("candle", 200, 72), ("candle", 600, 72), ("candle", 1000, 72), ("brazier", 600, 560)),
    "forge": (("torch", 405, 44), ("torch", 795, 44), ("brazier", 300, 548), ("brazier", 900, 548)),
    "ruins": (("brazier", 200, 548), ("brazier", 1000, 548)),
}
DEFAULT_FIXTURES = THEME_FIXTURES["hall"]
FLAME_HEIGHT = {"torch": 10, "brazier": 32, "candle": 14}

PLAYER_LOOK = {
    "title": "Knight",
    "skin": (226, 184, 150),
    "armor": (158, 166, 180),
    "trim": (204, 164, 82),
    "cloth": (38, 66, 132),
    "leather": (82, 56, 38),
    "legs": (62, 60, 70),
    "blade": (214, 222, 232),
    "blade_len": 34,
    "blade_width": 3.0,
    "helmet": True,
    "cape": True,
    "eye": None,
    "fighting_style": "balanced",
    "guard": "two_hand",
}

# Playable heroes, keyed by the names used in core.constants.
CHARACTER_LOOKS = {
    "ran": {**PLAYER_LOOK, "title": "Knight"},
    "florella": {
        **PLAYER_LOOK, "guard": "obi", "fighting_style": "quick", "title": "Ranger", "helmet": False, "hair": (176, 84, 38),
        "skin": (236, 196, 164), "armor": (104, 114, 78), "cloth": (46, 98, 60),
        "trim": (186, 156, 96), "blade_len": 30,
    },
    "nili": {
        **PLAYER_LOOK, "guard": "obi", "fighting_style": "quick", "title": "Rogue", "helmet": False, "hair": (34, 26, 34),
        "skin": (198, 150, 116), "armor": (72, 64, 84), "cloth": (104, 48, 124),
        "trim": (176, 176, 196), "blade_len": 24, "blade_width": 2.5,
    },
    "gili": {
        **PLAYER_LOOK, "guard": "two_hand", "fighting_style": "overhead", "title": "Paladin",
        # White plate with a gold tabard: gold armour was too close to skin tone, so the
        # round pauldrons and gauntlets read as extra hands.
        "armor": (226, 228, 236), "cloth": (196, 160, 60), "trim": (222, 172, 52),
    },
    "snib": {
        **PLAYER_LOOK, "guard": "shoulder", "fighting_style": "wild", "title": "Barbarian", "helmet": False, "cape": False, "hair": (156, 44, 30),
        "skin": (212, 162, 122), "armor": (124, 84, 52), "cloth": (144, 42, 36),
        "blade": (190, 190, 198), "blade_len": 30, "blade_width": 4.5,
    },
    "hogipog": {
        **PLAYER_LOOK, "guard": "shoulder", "fighting_style": "overhead", "title": "Warlord", "armor": (98, 100, 110), "cloth": (128, 88, 30),
        "trim": (172, 132, 62), "blade_len": 38, "blade_width": 4.5,
    },
}

_ENEMY_BASE = {
    "trim": (128, 98, 64),
    "leather": (58, 40, 30),
    "legs": (70, 56, 44),
    "blade": (150, 138, 124),
    "blade_len": 22,
    "blade_width": 3.5,
    "helmet": False,
    "cape": False,
}

# One look per level: goblin, ghoul, orc, demon.
ENEMY_LOOKS = (
    {**_ENEMY_BASE, "skin": (118, 146, 86), "armor": (96, 72, 52), "cloth": (96, 34, 38), "eye": (255, 70, 40), "fighting_style": "wild", "guard": "shoulder"},
    {**_ENEMY_BASE, "skin": (150, 156, 160), "armor": (70, 70, 78), "cloth": (50, 50, 60), "eye": (120, 220, 255), "fighting_style": "quick", "guard": None},
    {**_ENEMY_BASE, "skin": (96, 112, 70), "armor": (110, 100, 96), "cloth": (60, 40, 30), "eye": (255, 200, 60), "fighting_style": "wild", "guard": "shoulder"},
    {**_ENEMY_BASE, "skin": (156, 58, 48), "armor": (50, 40, 44), "cloth": (30, 24, 28), "eye": (255, 220, 90), "fighting_style": "overhead", "guard": "two_hand"},
)

BOSS_LOOK = {
    **ENEMY_LOOKS[3], "horns": True, "blade_len": 34, "blade_width": 4.5,
    "blade": (200, 120, 90), "fighting_style": "overhead", "guard": "two_hand",
}


def shade(color: Color, factor: float) -> Color:
    """Scale a color's RGB channels, clamped to the valid range."""
    return tuple(max(0, min(255, round(c * factor))) for c in color)


def mix(a: Color, b: Color, t: float) -> Color:
    """Linearly blend two colors."""
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def opaque_surface(width: int, height: int) -> pygame.Surface:
    """
    A 32-bit surface with no alpha channel.

    Drawing targets must be opaque: on macOS the window surface carries an alpha
    channel, and blending onto it makes transparent image borders show up as boxes.
    """
    return pygame.Surface((width, height), 0, 32, (0xFF0000, 0x00FF00, 0x0000FF, 0))


def faded(surface: pygame.Surface, alpha: float) -> pygame.Surface:
    """
    Return a copy with every pixel's own alpha scaled by alpha (0..255).

    Use this instead of Surface.set_alpha on per-pixel-alpha images: on some
    displays (e.g. macOS windows) set_alpha lets the transparent background of
    the image show through as a visible rectangle.
    """
    image = surface.copy()
    image.fill((255, 255, 255, max(0, min(255, int(alpha)))), special_flags=pygame.BLEND_RGBA_MULT)
    return image


def silhouette_glow(canvas: pygame.Surface, color: Color, spread: int = 4) -> pygame.Surface:
    """
    A soft, character-shaped glow for additive blits.

    The glow is painted on opaque black (premultiplied), so the empty area
    around the figure adds nothing and never shows as a box.
    """
    w, h = canvas.get_size()
    shape = canvas.copy()
    shape.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
    shape.fill((*color, 0), special_flags=pygame.BLEND_RGBA_ADD)
    base = pygame.Surface((w, h))
    base.fill((0, 0, 0))
    base.blit(shape, (0, 0))
    small = pygame.transform.smoothscale(base, (max(1, w // spread), max(1, h // spread)))
    return pygame.transform.smoothscale(small, (w, h))


@lru_cache(maxsize=64)
def vertical_gradient(width: int, height: int, top: Color, bottom: Color) -> pygame.Surface:
    """Return a cached RGBA surface fading from top color to bottom color."""
    surf = pygame.Surface((max(1, width), max(1, height)), pygame.SRCALPHA)
    for y in range(height):
        color = mix(top, bottom, y / max(1, height - 1))
        pygame.draw.line(surf, color, (0, y), (width, y))
    return surf


@lru_cache(maxsize=32)
def radial_glow(radius: int, color: Color, falloff: float = 2.0) -> pygame.Surface:
    """Return a cached RGB surface fading from color at the center to black, for additive blits."""
    surf = pygame.Surface((radius * 2, radius * 2))
    surf.fill((0, 0, 0))
    steps = max(8, radius // 3)
    for i in range(steps, 0, -1):
        intensity = (1 - i / steps) ** falloff
        pygame.draw.circle(surf, shade(color, intensity), (radius, radius), radius * i / steps)
    return surf


@lru_cache(maxsize=32)
def soft_shadow(width: int, height: int, alpha: int) -> pygame.Surface:
    """Return a blurred ellipse shadow roughly width x height, on a 2x canvas."""
    big = pygame.Surface((width * 2, height * 2), pygame.SRCALPHA)
    ellipse = pygame.Rect(0, 0, width, height)
    ellipse.center = big.get_rect().center
    pygame.draw.ellipse(big, (0, 0, 0, alpha), ellipse)
    small = pygame.transform.smoothscale(big, (max(1, width // 3), max(1, height // 3)))
    return pygame.transform.smoothscale(small, (width * 2, height * 2))


@lru_cache(maxsize=8)
def vignette(width: int, height: int, color: Color = (0, 0, 0), strength: int = 220) -> pygame.Surface:
    """Return a full-screen overlay that darkens toward the edges."""
    sw, sh = 80, 40
    small = pygame.Surface((sw, sh), pygame.SRCALPHA)
    for y in range(sh):
        for x in range(sw):
            dx = (x + 0.5) / sw * 2 - 1
            dy = (y + 0.5) / sh * 2 - 1
            d = math.sqrt(dx * dx + dy * dy) / math.sqrt(2)
            k = max(0.0, (d - 0.38) / 0.62)
            small.set_at((x, y), (*color, int(strength * k ** 1.5)))
    return pygame.transform.smoothscale(small, (width, height))


def flame_points(fixtures=DEFAULT_FIXTURES, view: pygame.Rect | None = None) -> list[tuple[int, int, str]]:
    """Return (x, y, kind) of every fire, optionally only those near the visible view."""
    points = []
    for kind, x, y in fixtures:
        if view is not None and not (view.left - 160 <= x <= view.right + 160):
            continue
        points.append((x, y - FLAME_HEIGHT[kind], kind))
    return points


def themes_for_level(level: int, sections: int) -> list[str]:
    """Scenery for each section of a level: the theme rotates as you push forward."""
    return [THEME_ORDER[(level - 1 + i) % len(THEME_ORDER)] for i in range(sections)]


# --------------------------------------------------------------------------
# Arena backdrop
# --------------------------------------------------------------------------


def build_backdrop(width: int, height: int, seed: int = 11) -> pygame.Surface:
    """A single-screen torch-lit hall (menus and story scenes)."""
    return build_level_backdrop(["hall"], height, seed)[0]


def build_level_backdrop(themes: list[str], height: int = 600, seed: int = 11) -> tuple[pygame.Surface, list]:
    """
    Paint a whole level: one section per theme side by side, stone thresholds
    between them, baked lighting, then glowing details (lava) on top.

    Returns the backdrop and the level's fixtures in level coordinates.
    """
    rng = random.Random(seed)
    width = SECTION_WIDTH * len(themes)
    strip = opaque_surface(width, height)
    fixtures: list = []
    for i, theme in enumerate(themes):
        offset = i * SECTION_WIDTH
        strip.blit(_build_section(theme, rng, height), (offset, 0))
        fixtures += [(kind, x + offset, y) for kind, x, y in THEME_FIXTURES[theme]]
    for i in range(1, len(themes)):
        _paint_threshold(strip, i * SECTION_WIDTH, height)
    _apply_lighting(strip, themes, fixtures)
    for i, theme in enumerate(themes):
        if theme == "forge":
            _paint_lava_cracks(strip, random.Random(seed + i), i * SECTION_WIDTH, height)
    return strip, fixtures


def _build_section(theme: str, rng: random.Random, height: int) -> pygame.Surface:
    spec = THEMES[theme]
    section = opaque_surface(SECTION_WIDTH, height)
    _paint_floor(section, rng, WALL_HEIGHT, spec["floor"])
    _apply_grime(section, rng)
    if spec["wall"] is None:
        _paint_sky(section, rng, WALL_HEIGHT, spec["ledge"])
    else:
        _paint_wall(section, rng, WALL_HEIGHT, spec["wall"], spec["ledge"])
    if theme == "hall":
        for x in (200, 600, 1000):
            _paint_banner(section, x)
    elif theme == "crypt":
        for x in (200, 600, 1000):
            _paint_alcove(section, x, rng)
    elif theme == "forge":
        for x in (150, 600, 1050):
            _paint_chains(section, x)
    elif theme == "ruins":
        _paint_grass(section, rng, height)
    return section


def _paint_floor(surf: pygame.Surface, rng: random.Random, top: int, tint: tuple[float, float, float] = (1.0, 0.95, 0.88)) -> None:
    width, height = surf.get_size()
    surf.fill((34, 30, 30))
    tile_w, tile_h = 72, 48
    y = top - rng.randint(0, tile_h // 2)
    row = 0
    while y < height:
        x = -((row * 37) % tile_w)
        while x < width:
            tw = tile_w + rng.randint(-14, 14)
            stone = pygame.Rect(x + 2, y + 2, tw - 4, tile_h - 4)
            base = rng.randint(104, 130)
            color = tuple(max(0, min(255, round(base * k + rng.randint(-5, 5)))) for k in tint)
            pygame.draw.rect(surf, color, stone, border_radius=5)
            pygame.draw.line(surf, shade(color, 1.18), (stone.left + 4, stone.top + 1), (stone.right - 5, stone.top + 1), 2)
            pygame.draw.line(surf, shade(color, 0.62), (stone.left + 4, stone.bottom - 1), (stone.right - 5, stone.bottom - 1), 2)
            for _ in range(22):
                px = rng.randint(stone.left + 3, stone.right - 4)
                py = rng.randint(stone.top + 3, stone.bottom - 4)
                pygame.draw.circle(surf, shade(color, rng.uniform(0.78, 1.12)), (px, py), rng.choice((1, 1, 2)))
            if rng.random() < 0.2:
                _paint_crack(surf, rng, stone, shade(color, 0.5))
            x += tw
        y += tile_h
        row += 1


def _paint_crack(surf: pygame.Surface, rng: random.Random, stone: pygame.Rect, color: Color) -> None:
    x = rng.randint(stone.left + 8, stone.right - 8)
    y = stone.top + 3
    points = [(x, y)]
    while y < stone.bottom - 6:
        x = max(stone.left + 3, min(stone.right - 3, x + rng.randint(-7, 7)))
        y += rng.randint(5, 11)
        points.append((x, y))
    if len(points) > 1:
        pygame.draw.lines(surf, color, False, points, 1)


def _apply_grime(surf: pygame.Surface, rng: random.Random) -> None:
    width, height = surf.get_size()
    sw, sh = width // 6, height // 6
    noise = pygame.Surface((sw, sh))
    for x in range(sw):
        for y in range(sh):
            v = rng.randint(180, 255)
            noise.set_at((x, y), (v, v, v))
    surf.blit(pygame.transform.smoothscale(noise, (width, height)), (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    for _ in range(16):
        patch = soft_shadow(rng.randint(90, 240), rng.randint(40, 110), rng.randint(30, 70))
        center = (rng.randint(0, width), rng.randint(WALL_HEIGHT, height))
        surf.blit(patch, patch.get_rect(center=center))


def _paint_wall(surf: pygame.Surface, rng: random.Random, top: int, brick_color: Color = (78, 70, 64), ledge_color: Color = (92, 84, 78)) -> None:
    width = surf.get_width()
    surf.fill((24, 20, 20), pygame.Rect(0, 0, width, top))
    brick_w, brick_h = 52, 20
    for row, y in enumerate(range(-6, top - 10, brick_h)):
        offset = (row % 2) * brick_w // 2
        for x in range(-offset, width, brick_w):
            color = shade(brick_color, rng.uniform(0.86, 1.12))
            brick = pygame.Rect(x + 2, y + 2, brick_w - 3, brick_h - 3)
            pygame.draw.rect(surf, color, brick, border_radius=2)
            pygame.draw.line(surf, shade(color, 1.15), (brick.left + 2, brick.top), (brick.right - 3, brick.top))
            pygame.draw.line(surf, shade(color, 0.7), (brick.left + 2, brick.bottom - 1), (brick.right - 3, brick.bottom - 1))
    _paint_ledge(surf, top, ledge_color)
    surf.blit(vertical_gradient(width, top - 12, (0, 0, 0, 170), (0, 0, 0, 0)), (0, 0))


def _paint_ledge(surf: pygame.Surface, top: int, color: Color) -> None:
    width = surf.get_width()
    ledge = pygame.Rect(0, top - 12, width, 12)
    pygame.draw.rect(surf, color, ledge)
    pygame.draw.line(surf, shade(color, 1.42), (0, ledge.top), (width, ledge.top), 2)
    pygame.draw.line(surf, (20, 16, 16), (0, ledge.bottom - 1), (width, ledge.bottom - 1), 2)
    surf.blit(vertical_gradient(width, 34, (0, 0, 0, 150), (0, 0, 0, 0)), (0, top))


def _paint_sky(surf: pygame.Surface, rng: random.Random, top: int, ledge_color: Color) -> None:
    """Open-air ruins: night sky, moon, far hills, and a broken low wall."""
    width = surf.get_width()
    surf.blit(vertical_gradient(width, top, (14, 18, 40, 255), (64, 60, 86, 255)), (0, 0))
    for _ in range(70):
        star = (rng.randint(0, width), rng.randint(0, top - 30))
        pygame.draw.circle(surf, shade((230, 230, 255), rng.uniform(0.5, 1.0)), star, rng.choice((1, 1, 1, 2)))
    moon = (rng.randint(260, width - 260), 30)
    glow = radial_glow(70, (60, 66, 90))
    surf.blit(glow, glow.get_rect(center=moon), special_flags=pygame.BLEND_RGB_ADD)
    pygame.draw.circle(surf, (236, 232, 210), moon, 15)
    pygame.draw.circle(surf, (206, 200, 180), (moon[0] + 4, moon[1] - 3), 4)
    hills = [(0, top)]
    for x in range(0, width + 60, 60):
        hills.append((x, top - 26 - rng.randint(0, 22)))
    hills.append((width, top))
    pygame.draw.polygon(surf, (36, 38, 58), hills)
    x = 0
    while x < width:  # broken wall: uneven stone stubs
        w = rng.randint(30, 70)
        h = rng.randint(6, 30)
        color = shade(ledge_color, rng.uniform(0.6, 0.85))
        pygame.draw.rect(surf, color, (x, top - 12 - h, w - 3, h), border_radius=3)
        pygame.draw.line(surf, shade(color, 1.3), (x + 2, top - 12 - h), (x + w - 6, top - 12 - h), 2)
        x += w + rng.choice((0, 0, 20, 50))
    for cx in (160, 520, 900):  # broken columns
        h = rng.randint(40, 80)
        column = pygame.Rect(cx - 16, top - 12 - h, 32, h)
        pygame.draw.rect(surf, (130, 124, 112), column)
        for gx in (column.left + 6, column.centerx, column.right - 7):
            pygame.draw.line(surf, (96, 90, 82), (gx, column.top + 4), (gx, column.bottom), 2)
        pygame.draw.polygon(surf, (130, 124, 112), [(column.left, column.top), (column.centerx - 4, column.top - 9), (column.right, column.top + 3)])
    _paint_ledge(surf, top, ledge_color)


def _paint_banner(surf: pygame.Surface, x: int) -> None:
    """A hanging red war banner with a gold emblem (hall)."""
    pygame.draw.line(surf, (40, 34, 30), (x - 20, 10), (x + 20, 10), 4)
    cloth = [(x - 16, 12), (x + 16, 12), (x + 16, 68), (x, 80), (x - 16, 68)]
    pygame.draw.polygon(surf, (128, 30, 34), cloth)
    pygame.draw.polygon(surf, (196, 156, 74), cloth, 2)
    pygame.draw.polygon(surf, (90, 20, 24), [(x + 6, 14), (x + 14, 14), (x + 14, 67), (x + 6, 72)])
    draw_diamond(surf, (x, 38), 8, (214, 172, 86))


def _paint_alcove(surf: pygame.Surface, x: int, rng: random.Random) -> None:
    """An arched burial niche with a skull (crypt); a candle fixture sits in front."""
    arch = pygame.Rect(x - 26, 14, 52, 70)
    pygame.draw.rect(surf, (16, 18, 18), (arch.left, arch.top + 22, arch.width, arch.height - 22))
    pygame.draw.ellipse(surf, (16, 18, 18), (arch.left, arch.top, arch.width, 46))
    pygame.draw.arc(surf, (96, 106, 102), (arch.left - 3, arch.top - 3, arch.width + 6, 52), 0, math.pi, 3)
    draw_skull(surf, (x - 8, arch.bottom - 22), 7)
    for bx in range(x + 2, x + 20, 5):
        pygame.draw.line(surf, (200, 194, 172), (bx, arch.bottom - 14), (bx + rng.randint(-3, 3), arch.bottom - 26), 2)


def _paint_chains(surf: pygame.Surface, x: int) -> None:
    """Hanging iron chains with a hook (forge)."""
    for i in range(7):
        y = 6 + i * 10
        rect = pygame.Rect(x - 4, y, 8, 12) if i % 2 == 0 else pygame.Rect(x - 2, y, 4, 12)
        pygame.draw.ellipse(surf, (54, 48, 46), rect, 2)
    pygame.draw.arc(surf, (64, 58, 54), (x - 8, 76, 16, 14), math.pi, 2 * math.pi, 3)


def _paint_grass(surf: pygame.Surface, rng: random.Random, height: int) -> None:
    """Moss and grass tufts pushing up between the flagstones (ruins)."""
    width = surf.get_width()
    for _ in range(140):
        gx, gy = rng.randint(0, width), rng.randint(WALL_HEIGHT + 20, height)
        color = shade((70, 104, 52), rng.uniform(0.7, 1.15))
        for blade in range(rng.randint(3, 6)):
            pygame.draw.line(surf, color, (gx + blade * 2, gy), (gx + blade * 2 + rng.randint(-4, 4), gy - rng.randint(5, 11)), 1)


def _paint_threshold(surf: pygame.Surface, x: int, height: int) -> None:
    """A stone pillar on the wall and a band of threshold stones across the floor between two sections."""
    band = pygame.Rect(x - 22, WALL_HEIGHT, 44, height - WALL_HEIGHT)
    pygame.draw.rect(surf, (52, 46, 44), band)
    for y in range(WALL_HEIGHT, height, 46):
        stone = pygame.Rect(band.left + 3, y + 2, band.width - 6, 42)
        pygame.draw.rect(surf, (96, 88, 82), stone, border_radius=4)
        pygame.draw.line(surf, (128, 118, 110), (stone.left + 3, stone.top + 1), (stone.right - 4, stone.top + 1), 2)
    pillar = pygame.Rect(x - 26, 0, 52, WALL_HEIGHT)
    pygame.draw.rect(surf, (88, 80, 74), pillar)
    pygame.draw.rect(surf, (118, 108, 100), (pillar.left + 4, 0, 8, WALL_HEIGHT))
    pygame.draw.rect(surf, (60, 54, 50), (pillar.right - 10, 0, 8, WALL_HEIGHT))
    pygame.draw.rect(surf, (104, 96, 88), (pillar.left - 6, WALL_HEIGHT - 16, pillar.width + 12, 10), border_radius=2)


def _apply_lighting(surf: pygame.Surface, themes: list[str] | None = None, fixtures=DEFAULT_FIXTURES) -> None:
    width, height = surf.get_size()
    themes = themes or ["hall"]
    light = opaque_surface(width, height)
    for i, theme in enumerate(themes):
        left = i * SECTION_WIDTH
        light.fill(THEMES[theme]["ambient"], pygame.Rect(left, 0, SECTION_WIDTH, height))
        center_glow = radial_glow(560, (80, 76, 82))
        light.blit(center_glow, center_glow.get_rect(center=(left + SECTION_WIDTH // 2, height // 2 + 40)), special_flags=pygame.BLEND_RGB_ADD)

    for kind, x, y in fixtures:
        tint = THEMES[themes[min(len(themes) - 1, max(0, x // SECTION_WIDTH))]]["light"]
        if kind == "torch":
            glow, center = radial_glow(380, tint), (x, y + 30)
        elif kind == "brazier":
            glow, center = radial_glow(300, shade(tint, 0.9)), (x, y - 30)
        else:
            glow, center = radial_glow(200, shade(tint, 0.8)), (x, y)
        light.blit(glow, glow.get_rect(center=center), special_flags=pygame.BLEND_RGB_ADD)

    surf.blit(light, (0, 0), special_flags=pygame.BLEND_RGB_MULT)


def _paint_lava_cracks(surf: pygame.Surface, rng: random.Random, left: int, height: int) -> None:
    """Glowing magma seams across the forge floor (painted after lighting so they stay bright)."""
    for _ in range(6):
        x = left + rng.randint(80, SECTION_WIDTH - 80)
        y = rng.randint(WALL_HEIGHT + 60, height - 40)
        points = [(x, y)]
        for _ in range(rng.randint(4, 8)):
            x += rng.randint(14, 30) * rng.choice((-1, 1))
            y += rng.randint(-10, 10)
            points.append((x, max(WALL_HEIGHT + 30, min(height - 10, y))))
        for px, py in points:
            glow = radial_glow(26, (90, 30, 6))
            surf.blit(glow, glow.get_rect(center=(px, py)), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.lines(surf, (190, 60, 14), False, points, 4)
        pygame.draw.lines(surf, (255, 170, 60), False, points, 2)


# --------------------------------------------------------------------------
# Fire
# --------------------------------------------------------------------------


def draw_flame(surface: pygame.Surface, x: float, y: float, t: float, size: float, seed: float = 0.0) -> None:
    """Draw a layered, flickering flame whose base sits at (x, y)."""
    flick = math.sin(t * 11 + seed) * 0.5 + math.sin(t * 17.3 + seed * 2) * 0.5
    height = size * (1.0 + 0.16 * flick)
    sway = math.sin(t * 7 + seed) * size * 0.14
    layers = (((214, 74, 18), 1.0), ((255, 150, 40), 0.74), ((255, 222, 120), 0.48), ((255, 252, 220), 0.24))
    for color, k in layers:
        w = size * 0.5 * k
        h = height * k
        points = [
            (x - w, y),
            (x - w * 0.75, y - h * 0.5),
            (x + sway * k, y - h * 1.35),
            (x + w * 0.75, y - h * 0.5),
            (x + w, y),
        ]
        pygame.draw.polygon(surface, color, points)
        pygame.draw.ellipse(surface, color, pygame.Rect(int(x - w), int(y - w * 0.8), int(2 * w) + 1, int(1.6 * w) + 1))


def draw_fixtures(surface: pygame.Surface, t: float, fixtures=DEFAULT_FIXTURES, view: pygame.Rect | None = None) -> None:
    """Draw wall sconces, floor braziers, and crypt candles with live flames."""
    for i, (kind, x, y) in enumerate(fixtures):
        if view is not None and not (view.left - 80 <= x <= view.right + 80):
            continue
        if kind == "torch":
            pygame.draw.rect(surface, (24, 20, 20), (x - 8, y + 16, 16, 7), border_radius=2)
            pygame.draw.rect(surface, (40, 34, 32), (x - 3, y - 2, 6, 22))
            pygame.draw.polygon(surface, (56, 48, 44), [(x - 10, y - 10), (x + 10, y - 10), (x + 5, y + 1), (x - 5, y + 1)])
            pygame.draw.line(surface, (104, 90, 80), (x - 10, y - 10), (x + 10, y - 10), 2)
            draw_flame(surface, x, y - 9, t, 14, i * 1.7)
        elif kind == "brazier":
            shadow = soft_shadow(56, 14, 160)
            surface.blit(shadow, shadow.get_rect(center=(x, y + 2)))
            iron = (36, 32, 32)
            pygame.draw.line(surface, iron, (x - 15, y), (x - 6, y - 22), 3)
            pygame.draw.line(surface, iron, (x + 15, y), (x + 6, y - 22), 3)
            pygame.draw.line(surface, iron, (x, y + 3), (x, y - 22), 3)
            pygame.draw.polygon(surface, (60, 52, 48), [(x - 21, y - 31), (x + 21, y - 31), (x + 13, y - 18), (x - 13, y - 18)])
            pygame.draw.line(surface, (116, 100, 88), (x - 21, y - 31), (x + 21, y - 31), 2)
            pygame.draw.ellipse(surface, (170, 58, 22), (x - 17, y - 35, 34, 8))
            draw_flame(surface, x, y - 31, t, 22, 5 + i * 2.3)
        else:
            for dx, h in ((-6, 12), (5, 9)):
                pygame.draw.rect(surface, (226, 218, 190), (x + dx - 2, y - h, 5, h), border_radius=1)
                draw_flame(surface, x + dx + 0.5, y - h - 1, t, 6, i * 3.1 + dx)


def draw_light_glow(surface: pygame.Surface, t: float, fixtures=DEFAULT_FIXTURES, view: pygame.Rect | None = None) -> None:
    """Add flickering warm light around every flame (call after actors so they catch it)."""
    for i, (x, y, kind) in enumerate(flame_points(fixtures, view)):
        flick = 0.85 + 0.15 * math.sin(t * 9.3 + i * 2.1) * math.sin(t * 5.7 + i)
        level = round(flick * 20) / 20
        radius = {"torch": 110, "brazier": 150, "candle": 60}[kind]
        glow = radial_glow(radius, shade((120, 70, 30), level))
        surface.blit(glow, glow.get_rect(center=(x, y)), special_flags=pygame.BLEND_RGB_ADD)


# --------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------


# Mid-bosses, keyed like core.constants.MID_BOSSES. "tusks" adds lower fangs; the weapon
# colours/sizes make the club, scythe, axe, and burning maul.
MID_BOSS_LOOKS = {
    "grukk": {  # ogre: grey-tan hide, leather, a big wooden club
        **_ENEMY_BASE, "skin": (170, 152, 112), "armor": (110, 80, 54), "cloth": (92, 70, 44), "trim": (140, 110, 70),
        "eye": (255, 196, 70), "tusks": True, "blade": (126, 88, 54), "blade_len": 34, "blade_width": 8.0,
        "fighting_style": "overhead", "guard": "shoulder",
    },
    "gravewarden": {  # giant ghoul: corpse-pale, tattered dark robes, a long grave-scythe
        **_ENEMY_BASE, "skin": (176, 184, 178), "armor": (52, 56, 66), "cloth": (34, 52, 46), "trim": (110, 150, 120),
        "legs": (40, 44, 52), "eye": (130, 255, 190), "horns": True, "blade": (176, 196, 186), "blade_len": 40, "blade_width": 3.0,
        "fighting_style": "wild", "guard": "shoulder", "cape": True,
    },
    "gorrak": {  # orc warchief: green, iron-trimmed armour, a broad war-axe
        **_ENEMY_BASE, "skin": (98, 128, 64), "armor": (96, 84, 80), "cloth": (130, 30, 26), "trim": (196, 150, 60),
        "eye": (255, 70, 40), "tusks": True, "blade": (206, 208, 214), "blade_len": 32, "blade_width": 7.0,
        "fighting_style": "wild", "guard": "shoulder",
    },
    "ember_demon": {  # the final boss: horned, winged, burning blade
        **_ENEMY_BASE, "skin": (170, 52, 40), "armor": (44, 30, 32), "cloth": (28, 18, 20), "trim": (240, 150, 60),
        "legs": (40, 26, 26), "eye": (255, 236, 120), "horns": True, "tusks": True, "wings": (92, 24, 26),
        "blade": (255, 140, 60), "blade_len": 38, "blade_width": 5.0, "fighting_style": "overhead", "guard": "two_hand",
    },
    "brannoc": {  # pyre ogre: soot-red hide, charred armour, a glowing maul
        **_ENEMY_BASE, "skin": (164, 86, 62), "armor": (54, 44, 44), "cloth": (60, 30, 24), "trim": (226, 120, 50),
        "eye": (255, 220, 90), "tusks": True, "horns": True, "blade": (240, 130, 60), "blade_len": 34, "blade_width": 8.0,
        "fighting_style": "overhead", "guard": "two_hand",
    },
}


def _ease_out(p: float) -> float:
    return 1 - (1 - p) ** 3


def attack_pose(look: dict, mode: str, swing: float | None, windup: float | None, t: float) -> dict:
    """
    Work out this frame's body and sword pose for an attack.

    Returns body offset (dx, dy), sword angle and arm reach, the slash trail arc
    (or None), whether the body is mid-twirl (flip), thrust streak strength, and
    whether the blade glints (end of an enemy wind-up).
    """
    style = FIGHTING_STYLES.get(look.get("fighting_style", "balanced"), FIGHTING_STYLES["balanced"])
    idle = 48 + math.sin(t * 2.2) * 3
    pose = {"dx": 0.0, "dy": 0.0, "angle": idle, "reach": 13.0, "trail": None, "flip": False, "streak": 0.0, "glint": False}

    def raise_toward_start(k: float) -> None:
        if style["thrust"] and mode != "spin":
            pose["reach"] = 13 - 6 * k
            pose["angle"] = idle + (5 - idle) * k
        else:
            start = SPIN_ARC[0] if mode == "spin" else style["arcs"][mode][0]
            pose["angle"] = idle + (start - idle) * k

    if windup is not None:
        k = max(0.0, min(1.0, windup))
        raise_toward_start(k)
        pose["dx"] = -3 * k
        pose["dy"] = 2 * k if mode == "heavy" else 0.0
        pose["glint"] = k > 0.6
        return pose
    if swing is None:
        return pose

    p = max(0.0, min(1.0, swing))
    if mode == "spin":
        start, end = SPIN_ARC
        pose["angle"] = start + (end - start) * _ease_out(p)
        pose["trail"] = (start, pose["angle"])
        pose["dy"] = -4 * math.sin(p * math.pi)
        pose["flip"] = 0.25 < p < 0.75
        return pose

    if mode == "throw":
        # Haul the foe up and over while turning to hurl them behind.
        pose["angle"] = -40 - 100 * _ease_out(p)
        pose["dx"] = -4 * math.sin(p * math.pi)
        pose["dy"] = -3 * math.sin(p * math.pi)
        pose["flip"] = p > 0.45
        return pose
    if mode == "jump":
        if style["thrust"]:
            pose["angle"] = 60.0
            pose["reach"] = 13 + 15 * math.sin(p * math.pi)
            pose["streak"] = math.sin(p * math.pi)
            return pose
        start, end = JUMP_ARC
        pose["angle"] = start + (end - start) * _ease_out(p)
        pose["trail"] = (start, pose["angle"])
        return pose
    if mode == "dash":
        pose["dx"] = MODE_LUNGE["dash"] * style["lunge"] * math.sin(p * math.pi)
        pose["angle"] = 2.0
        pose["reach"] = 13 + 12 * math.sin(p * math.pi)
        pose["streak"] = 1 - p * 0.5
        return pose

    lunge = MODE_LUNGE.get(mode, 6.0) * style["lunge"]
    if mode == "heavy":
        if p < HEAVY_WINDUP_SHARE:
            k = p / HEAVY_WINDUP_SHARE
            raise_toward_start(k)
            pose["dx"] = -4 * k
            pose["dy"] = 3 * k
            return pose
        p = (p - HEAVY_WINDUP_SHARE) / (1 - HEAVY_WINDUP_SHARE)
        pose["dx"] = -4 + (lunge + 4) * _ease_out(p)
        pose["dy"] = 3 * (1 - p) - style["hop"] * math.sin(p * math.pi)
    elif mode == "finisher":
        pose["dx"] = lunge * _ease_out(p)
        pose["dy"] = -style["hop"] * 0.6 * math.sin(p * math.pi)
    else:
        pose["dx"] = lunge * math.sin(p * math.pi)

    if style["thrust"]:
        extend = abs(math.sin(p * math.pi * (2 if mode in ("heavy", "finisher") else 1)))
        pose["angle"] = 5.0
        pose["reach"] = 13 + 15 * extend
        pose["streak"] = extend
        return pose

    start, end = style["arcs"][{"slash2": "slash", "air1": "slash", "air2": "slash", "finisher": "heavy"}.get(mode, mode)]
    if mode in ("slash2", "air2"):
        start, end = end, start  # the return swing of the combo
    pose["angle"] = start + (end - start) * _ease_out(p)
    pose["trail"] = (start, pose["angle"])
    return pose


def render_fighter(
    look: dict,
    t: float,
    moving: bool,
    face_sign: int,
    swing: float | None = None,
    flash: float = 0.0,
    flash_color: Color = (255, 255, 255),
    shielding: bool = False,
    mode: str = "slash",
    fury: bool = False,
    windup: float | None = None,
    recoil: float = 0.0,
    tuck: bool = False,
    gait: float | None = None,
    stride_amount: float | None = None,
    crouch: float = 0.0,
    posture: str | None = None,
    air: float | None = None,
) -> pygame.Surface:
    """
    Paint a rounded, outlined fighter onto its own canvas, facing right, then mirror if needed.

    The feet sit at CANVAS_ANCHOR. swing is attack progress 0..1 (None when not
    attacking); windup is an enemy's telegraph progress; mode picks the attack;
    recoil (0..1) staggers the body back; tuck pulls the knees up mid-jump;
    crouch (0..1) bends the knees (landing). gait is the walk-cycle phase in
    radians, advanced by distance travelled so feet plant instead of sliding,
    and stride_amount (0..1) scales the walk from standing to full stride.
    posture overrides the stance after a knockdown: "flail" (flying through the
    air), "limp" (flat on the ground; drawn upright, the caller rotates it), or
    "kneel" (pushing back up onto one knee). air is jump progress (1 take-off,
    0 apex, negative falling): legs fold tight and the arms stretch, overhead
    on the way up and reaching forward on the way down.
    """
    canvas = pygame.Surface(CANVAS_SIZE, pygame.SRCALPHA)
    if posture is not None:
        swing = windup = None
        moving, stride_amount, crouch, tuck = False, 0.0, 0.0, False
    pose = attack_pose(look, mode, swing, windup, t)
    if gait is None:
        gait = t * 11.0
        stride_amount = 1.0 if moving else 0.0
    amp = stride_amount or 0.0
    if swing is not None or windup is not None:
        amp *= 0.3  # plant the feet to strike

    lean = 3.0 * amp + pose["dx"] * 0.25 - 4 * recoil
    fx = CANVAS_ANCHOR[0] + pose["dx"] - 4 * recoil
    fy = CANVAS_ANCHOR[1] + pose["dy"]
    breathe = math.sin(t * 2.2) * 0.8 * (1 - amp)
    drop = abs(math.sin(gait)) * 2.4 * amp + 9 * crouch + breathe + 2 * recoil
    if posture == "flail":
        lean -= 7  # thrown backward
    elif posture == "kneel":
        drop += 15
        lean += 3

    hip = (fx - 1, fy - 35 + drop)
    shoulder_y = fy - 61 + drop + 1.5 * recoil
    chest = (fx + 1 + lean, shoulder_y + 10)
    head = (fx + 3 + lean * 1.3 - 2 * recoil, shoulder_y - 13 + 2 * recoil)
    if posture == "flail":
        head = (head[0] - 4, head[1] + 2)  # head snapped back
    elif posture == "limp":
        head = (head[0] - 2, head[1] + 3)  # lolling
    legs = _posture_legs(posture, hip, fy)
    arms = POSTURE_ARMS.get(posture)
    stretch = air is not None and posture is None
    if stretch and swing is None:
        up = (air + 1) / 2  # 1 rising .. 0 falling
        arms = (-140 * up + 165 * (1 - up), -120 * up - 15 * (1 - up))  # overhead -> reaching out
    if look.get("wings"):
        _draw_wings(canvas, look["wings"], (chest[0] - 6, shoulder_y + 6), t)
    if look["cape"]:
        _draw_cape(canvas, look, chest, fy, amp, t, pose["dx"])

    back_leg, front_leg = gait + math.pi, gait
    pivot = (chest[0] + 6, shoulder_y + 4)
    back_shoulder = (chest[0] - 8, shoulder_y + 4)
    idle = swing is None and windup is None and posture is None and not stretch
    guard = GUARDS.get(look.get("guard")) if idle else None
    grip = blade_angle = None
    if guard is not None:
        sway = math.sin(gait) * 2.5 * amp + math.sin(t * 2.2) * 0.8  # the ready stance breathes and bobs with the walk
        grip = (pivot[0] + guard["grip"][0], pivot[1] + guard["grip"][1] + sway)
        blade_angle = guard["blade"] + math.sin(gait) * 4 * amp
    stance = look.get("guard") if guard is not None else None

    _draw_leg(canvas, look, hip, fy, back_leg, amp, 0.7, tuck, crouch, -3, legs[0] if legs else None)
    if stance == "two_hand":
        # Two-handed grip: the far arm passes BEHIND the torso to the hilt, so only one
        # arm is seen in front of the body (drawing both in front read as two right arms).
        _draw_back_arm(canvas, look, back_shoulder, gait, amp, hand_target=(grip[0] - 1, grip[1] + 4), behind=True)
    elif stance != "obi":
        _draw_back_arm(canvas, look, back_shoulder, gait, amp, arms[0] if arms else None, stretch)
    _draw_leg(canvas, look, hip, fy, front_leg, amp, 1.0, tuck, crouch, 3, legs[1] if legs else None)
    _draw_torso(canvas, look, hip, chest, shoulder_y, gait, amp)
    tip = None
    if stance == "obi":  # sword arm raised behind the head, so draw it before the head
        tip = _draw_weapon_arm(canvas, look, pivot, pose["angle"], pose["reach"], 3.0, grip, blade_angle)
    _draw_head(canvas, look, head, t)
    if stance == "obi":  # free arm stretched out in front, pointing at the foe
        point = (chest[0] + 30, shoulder_y + 4 + math.sin(t * 2.2) * 1.5 + math.sin(gait) * 2 * amp)
        _draw_back_arm(canvas, look, back_shoulder, gait, amp, hand_target=point, pointing=True, bend=1.5)

    angle = pose["angle"]
    if arms:
        angle = arms[1] + math.sin(t * 9) * (12 if posture == "flail" else 0)
    elif swing is None and windup is None:
        angle -= math.sin(gait) * 10 * amp  # arm swings with the walk
    if tip is None:
        tip = _draw_weapon_arm(
            canvas, look, pivot, angle, pose["reach"] + (3 if stretch else 0), 0.5 if stretch else 3.0, grip, blade_angle
        )
    if shielding:
        _draw_held_shield(canvas, look, (chest[0] + 13, shoulder_y + 16))

    canvas = _outline(canvas)

    trail_color, thickness = TRAIL_STYLE.get(mode, TRAIL_STYLE["slash"])
    if fury:
        trail_color = FURY_TRAIL
    if pose["trail"] is not None:
        _draw_slash(canvas, pivot, pose["trail"][0], pose["trail"][1], look["blade_len"] + 22, trail_color, thickness)
    if pose["streak"] > 0.2:
        _draw_thrust_streak(canvas, tip, pose["streak"], trail_color)
    if pose["glint"]:
        _draw_glint(canvas, tip, t)

    if flash > 0:
        canvas.fill(shade(flash_color, min(1.0, flash)), special_flags=pygame.BLEND_RGB_ADD)
    if (face_sign < 0) != pose["flip"]:
        canvas = pygame.transform.flip(canvas, True, False)
    return canvas


def draw_fighter(
    surface: pygame.Surface,
    look: dict,
    x: float,
    feet_y: float,
    t: float,
    moving: bool = False,
    face_sign: int = 1,
    swing: float | None = None,
    flash: float = 0.0,
    flash_color: Color = (255, 255, 255),
    shielding: bool = False,
    scale: float = 1.0,
    mode: str = "slash",
    fury: bool = False,
    windup: float | None = None,
    recoil: float = 0.0,
    ghosts: tuple[tuple[float, float], ...] = (),
    tilt: float = 0.0,
    lift: float = 0.0,
    tuck: bool = False,
    visible: bool = True,
    gait: float | None = None,
    stride_amount: float | None = None,
    crouch: float = 0.0,
    posture: str | None = None,
    air: float | None = None,
) -> None:
    """
    Draw a fighter with a soft contact shadow, feet at (x, feet_y).

    ghosts are (dx, dy) offsets where fading afterimages are drawn, e.g. while strafing.
    lift raises the body off its shadow (jumps, knockdown flights); tilt tips it
    over (0 standing .. 90 flat on the ground); visible=False skips the body for blinking.
    """
    shrink = max(0.5, 1 - lift / 160)
    shadow = soft_shadow(round(46 * scale * shrink), round(14 * scale * shrink), 160)
    surface.blit(shadow, shadow.get_rect(center=(int(x), int(feet_y) - 1)))
    if not visible:
        return

    canvas = render_fighter(
        look, t, moving, face_sign, swing, flash, flash_color, shielding, mode, fury, windup, recoil, tuck, gait, stride_amount, crouch, posture, air
    )
    ax, ay = CANVAS_ANCHOR
    if scale != 1.0:
        w, h = canvas.get_size()
        canvas = pygame.transform.smoothscale(canvas, (round(w * scale), round(h * scale)))
        ax, ay = ax * scale, ay * scale

    if tilt:
        k = tilt / 90
        image = pygame.transform.rotate(canvas, tilt * face_sign)
        center = (x - face_sign * 30 * k * scale, feet_y - lift - (44 - 38 * k) * scale)
        surface.blit(image, image.get_rect(center=(round(center[0]), round(center[1]))))
        return
    feet_y -= lift

    if ghosts:
        tinted = canvas.copy()
        tinted.fill((120, 170, 230, 255), special_flags=pygame.BLEND_RGBA_MULT)
        for i, (gx, gy) in enumerate(ghosts):
            ghost = faded(tinted, max(20, 120 - i * 35))
            surface.blit(ghost, (round(x + gx - ax), round(feet_y + gy - ay)))
        glow = silhouette_glow(canvas, (70, 150, 255))
        for dx, dy in ((0, 0), (-3, 0), (3, 0), (0, -3), (0, 3)):
            surface.blit(glow, (round(x - ax + dx), round(feet_y - ay + dy)), special_flags=pygame.BLEND_RGB_ADD)
    surface.blit(canvas, (round(x - ax), round(feet_y - ay)))


def draw_mini_health(surface: pygame.Surface, x: float, top: float, ratio: float) -> None:
    """Draw a compact framed health bar centered over an actor."""
    bar = pygame.Rect(0, 0, 36, 5)
    bar.midbottom = (int(x), int(top))
    pygame.draw.rect(surface, (10, 6, 6), bar.inflate(2, 2))
    pygame.draw.rect(surface, (60, 16, 16), bar)
    fill = bar.copy()
    fill.width = round(bar.width * max(0.0, min(1.0, ratio)))
    if fill.width:
        surface.blit(vertical_gradient(bar.width, bar.height, (236, 80, 60, 255), (130, 20, 20, 255)), fill, (0, 0, fill.width, fill.height))


def draw_spin_ring(surface: pygame.Surface, x: float, feet_y: float, progress: float, reach: float, depth: float) -> None:
    """An expanding ring on the floor marking the Whirlwind's reach, including its depth (up/down)."""
    k = _ease_out(max(0.0, min(1.0, progress)))
    rx, ry = max(4, reach * k), max(3, depth * k)
    layer = pygame.Surface((int(rx * 2) + 6, int(ry * 2) + 6), pygame.SRCALPHA)
    alpha = int(200 * (1 - progress))
    rect = pygame.Rect(3, 3, int(rx * 2), int(ry * 2))
    pygame.draw.ellipse(layer, (200, 230, 255, alpha // 4), rect)
    pygame.draw.ellipse(layer, (220, 240, 255, alpha), rect, 3)
    surface.blit(layer, layer.get_rect(center=(int(x), int(feet_y))))


def draw_ward(surface: pygame.Surface, x: float, feet_y: float, t: float, ratio: float) -> None:
    """Draw the shimmering protective ward around a shielding fighter."""
    pulse = 0.5 + 0.5 * math.sin(t * 8)
    strength = 0.4 + 0.6 * min(1.0, ratio * 3)
    layer = pygame.Surface((122, 150), pygame.SRCALPHA)
    rect = layer.get_rect().inflate(-6, -6)
    alpha = int((70 + 50 * pulse) * strength)
    pygame.draw.ellipse(layer, (110, 190, 255, alpha // 3), rect)
    pygame.draw.ellipse(layer, (180, 230, 255, min(255, alpha + 70)), rect, 2)
    surface.blit(layer, layer.get_rect(midbottom=(int(x), int(feet_y) + 10)))


def draw_ally_ring(surface: pygame.Surface, x: float, feet_y: float, t: float, rally: bool = False) -> None:
    """A glowing ring under a helper hero: gold for an Ally Call, white-gold and brighter for the Rally."""
    color = (255, 236, 170) if rally else (240, 190, 80)
    pulse = 0.6 + 0.4 * math.sin(t * 5)
    layer = pygame.Surface((76, 26), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, (*color, int(60 * pulse)), layer.get_rect())
    pygame.draw.ellipse(layer, (*color, int(150 + 90 * pulse)), layer.get_rect(), 2)
    surface.blit(layer, layer.get_rect(center=(round(x), round(feet_y))))


def draw_danger_ellipse(
    surface: pygame.Surface, x: float, feet_y: float, radius: float, progress: float, t: float, color: Color = (230, 50, 40)
) -> None:
    """
    A floor warning: an outlined circle (squashed, the floor is seen at an angle) that
    fills from the centre as the attack charges. When it's full, the blow lands.
    """
    outer = pygame.Rect(0, 0, radius * 2, radius * 0.6)
    layer = pygame.Surface((outer.width + 6, outer.height + 6), pygame.SRCALPHA)
    box = layer.get_rect().inflate(-6, -6)
    blink = 0.5 + 0.5 * math.sin(t * 18)
    pygame.draw.ellipse(layer, (*color, 50), box)
    inner = box.copy()
    inner.width, inner.height = max(2, round(box.width * progress)), max(2, round(box.height * progress))
    inner.center = box.center
    pygame.draw.ellipse(layer, (*color, 90 + int(60 * progress)), inner)
    pygame.draw.ellipse(layer, (*mix(color, (255, 230, 200), blink * progress), 230), box, 3)
    surface.blit(layer, layer.get_rect(center=(round(x), round(feet_y))))


def draw_magic_circle(surface: pygame.Surface, x: float, feet_y: float, radius: float, progress: float, t: float) -> None:
    """A summoning circle on the floor: a double ring with turning runes, brightening as the spell completes."""
    w, h = round(radius * 2), round(radius * 0.6)
    layer = pygame.Surface((w + 8, h + 8), pygame.SRCALPHA)
    box = layer.get_rect().inflate(-8, -8)
    glow = (190, 70, 255)
    alpha = 90 + int(150 * progress)
    pygame.draw.ellipse(layer, (*glow, 30 + int(60 * progress)), box)
    pygame.draw.ellipse(layer, (*mix(glow, (255, 200, 255), progress), alpha), box, 2)
    pygame.draw.ellipse(layer, (*glow, alpha), box.inflate(-box.width * 0.3, -box.height * 0.3), 1)
    cx, cy = layer.get_rect().center
    for i in range(6):  # runes turning around the ring, and a star joining them
        a = t * 1.6 + i * math.pi / 3
        rx, ry = cx + math.cos(a) * box.width * 0.42, cy + math.sin(a) * box.height * 0.42
        b = t * 1.6 + (i + 2) * math.pi / 3
        pygame.draw.line(layer, (*glow, alpha // 2), (rx, ry), (cx + math.cos(b) * box.width * 0.42, cy + math.sin(b) * box.height * 0.42), 1)
        pygame.draw.circle(layer, (255, 220, 255, alpha), (rx, ry), 2)
    surface.blit(layer, layer.get_rect(center=(round(x), round(feet_y))))


def draw_fireball(surface: pygame.Surface, x: float, y: float, floor_y: float, vx: float, vy: float, t: float) -> None:
    """A spat fireball: its shadow on the floor shows the lane, a flickering core, and a short flame tail."""
    shadow = soft_shadow(30, 9, 120)
    surface.blit(shadow, shadow.get_rect(center=(round(x), round(floor_y))))
    speed = math.hypot(vx, vy) or 1.0
    ux, uy = vx / speed, vy / speed
    for i in range(5, 0, -1):  # tail: fading puffs trailing behind
        r = 10 - i * 1.4
        layer = pygame.Surface((round(r * 2) + 2, round(r * 2) + 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (255, 110 + i * 12, 40, 200 - i * 34), layer.get_rect().center, r)
        surface.blit(layer, layer.get_rect(center=(round(x - ux * i * 7), round(y - uy * i * 3))))
    flicker = 1 + 0.12 * math.sin(t * 40)
    pygame.draw.circle(surface, (255, 120, 40), (x, y), 11 * flicker)
    pygame.draw.circle(surface, (255, 210, 110), (x, y), 7 * flicker)
    pygame.draw.circle(surface, (255, 252, 220), (x + ux * 2, y + uy), 3.5)


def draw_danger_lane(
    surface: pygame.Surface, x: float, feet_y: float, direction: int, length: float, half_depth: float, progress: float, t: float
) -> None:
    """A floor warning for a charge: a red band along the lane with arrows, brightening as it nears."""
    height = round(half_depth * 2)
    band = pygame.Surface((round(length), height), pygame.SRCALPHA)
    blink = 0.5 + 0.5 * math.sin(t * 16)
    band.fill((220, 40, 30, 40 + int(70 * progress)))
    pygame.draw.rect(band, (255, 90, 60, 120 + int(100 * blink * progress)), band.get_rect(), 2)
    for i in range(int(length // 70)):
        ax = 40 + i * 70 + (t * 120) % 70
        if ax > length - 20:
            continue
        cy = height // 2
        arrow = [(ax, cy - 8), (ax + 14, cy), (ax, cy + 8)] if direction > 0 else [(length - ax, cy - 8), (length - ax - 14, cy), (length - ax, cy + 8)]
        pygame.draw.polygon(band, (255, 200, 160, 90 + int(120 * progress)), arrow)
    left = x if direction > 0 else x - length
    surface.blit(band, (round(left), round(feet_y - height / 2)))


def draw_fury_aura(surface: pygame.Surface, x: float, feet_y: float, t: float) -> None:
    """Draw a flickering fiery glow and licking flames around a fighter in Fury."""
    level = round((0.8 + 0.2 * math.sin(t * 12)) * 10) / 10
    glow = radial_glow(70, shade((150, 60, 10), level))
    surface.blit(glow, glow.get_rect(center=(int(x), int(feet_y) - 32)), special_flags=pygame.BLEND_RGB_ADD)
    for i in range(5):
        offset = (i - 2) * 9
        draw_flame(surface, x + offset, feet_y + 2, t, 9 + (i % 2) * 4, seed=i * 1.9)


# Rounded, shaded body-part primitives. Light comes from the upper left.


def _capsule(canvas: pygame.Surface, a: tuple[float, float], b: tuple[float, float], ra: float, rb: float, color: Color) -> None:
    """A tapered capsule from a (radius ra) to b (radius rb)."""
    ax, ay = a
    bx, by = b
    pygame.draw.circle(canvas, color, a, ra)
    pygame.draw.circle(canvas, color, b, rb)
    length = math.hypot(bx - ax, by - ay)
    if length < 0.5:
        return
    nx, ny = -(by - ay) / length, (bx - ax) / length
    pygame.draw.polygon(canvas, color, [(ax + nx * ra, ay + ny * ra), (bx + nx * rb, by + ny * rb), (bx - nx * rb, by - ny * rb), (ax - nx * ra, ay - ny * ra)])


def _limb(canvas: pygame.Surface, a: tuple[float, float], b: tuple[float, float], ra: float, rb: float, color: Color) -> None:
    """A round, muscular limb: dark rim, body, and a highlight along the lit side."""
    _capsule(canvas, a, b, ra, rb, shade(color, 0.6))
    _capsule(canvas, (a[0] - 0.6, a[1] - 0.6), (b[0] - 0.6, b[1] - 0.6), ra - 1.3, rb - 1.3, color)
    _capsule(canvas, (a[0] - ra * 0.35, a[1] - ra * 0.4), (b[0] - rb * 0.35, b[1] - rb * 0.4), max(1.0, ra * 0.28), max(1.0, rb * 0.28), shade(color, 1.3))


def _ball(canvas: pygame.Surface, center: tuple[float, float], r: float, color: Color) -> None:
    """A shaded sphere (heads, joints, fists, pauldrons)."""
    cx, cy = center
    pygame.draw.circle(canvas, shade(color, 0.6), center, r)
    pygame.draw.circle(canvas, color, (cx - 0.7, cy - 0.7), r - 1.3)
    pygame.draw.circle(canvas, shade(color, 1.32), (cx - r * 0.38, cy - r * 0.42), max(1.0, r * 0.36))


def _blob(canvas: pygame.Surface, center: tuple[float, float], w: float, h: float, color: Color) -> None:
    """A shaded ellipse (chest, belly, boots)."""
    cx, cy = center
    pygame.draw.ellipse(canvas, shade(color, 0.6), pygame.Rect(int(cx - w / 2), int(cy - h / 2), int(w), int(h)))
    pygame.draw.ellipse(canvas, color, pygame.Rect(int(cx - w / 2 + 1), int(cy - h / 2 + 1), int(w - 2.6), int(h - 2.6)))
    pygame.draw.ellipse(canvas, shade(color, 1.28), pygame.Rect(int(cx - w * 0.3), int(cy - h * 0.36), int(w * 0.32), int(h * 0.3)))


def _outline(canvas: pygame.Surface, color: Color = (24, 14, 14)) -> pygame.Surface:
    """Wrap the figure in a 1px dark sprite outline, like classic arcade art."""
    silhouette = canvas.copy()
    silhouette.fill((0, 0, 0, 255), special_flags=pygame.BLEND_RGBA_MULT)
    silhouette.fill((*color, 0), special_flags=pygame.BLEND_RGBA_ADD)
    out = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
    for offset in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        out.blit(silhouette, offset)
    out.blit(canvas, (0, 0))
    return out


def _draw_wings(canvas: pygame.Surface, color: Color, root: tuple[float, float], t: float) -> None:
    """Two bat wings spreading up and back from the shoulders, beating slowly."""
    rx, ry = root
    beat = math.sin(t * 3.2)
    for depth, (lift, reach, shade_k) in enumerate(((10, 40, 0.65), (0, 48, 1.0))):  # far wing first
        spread = reach + beat * 6
        top = ry - 42 - lift - beat * 8
        tip = (rx - spread, top)
        bones = [(rx - spread * 0.62, top + 8), (rx - spread * 0.88, top + 26), (rx - spread * 0.72, ry + 6)]
        membrane = [(rx, ry), (rx - 6, top + 12), tip, bones[1], (rx - spread * 0.6, ry - 6), bones[2], (rx - 8, ry + 10)]
        pygame.draw.polygon(canvas, shade(color, shade_k), membrane)
        for bone in (tip, *bones):  # dark finger bones across the membrane
            pygame.draw.line(canvas, shade(color, shade_k * 0.5), (rx - 4, ry + 2), bone, 2)
        _ball(canvas, tip, 2.5, shade(color, shade_k * 0.6))


def _draw_cape(canvas: pygame.Surface, look: dict, chest: tuple[float, float], ground: float, amp: float, t: float, lunge: float) -> None:
    cx, cy = chest
    flutter = math.sin(t * 6.0) * 2.0 + 7.0 * amp + lunge * 0.5
    color = shade(look["cloth"], 0.62)
    points = [
        (cx - 9, cy - 9), (cx + 2, cy - 10), (cx - 1, cy + 8), (cx - 4, ground - 16),
        (cx - 10 - flutter * 0.5, ground - 10), (cx - 17 - flutter, ground - 12), (cx - 15 - flutter * 0.6, cy + 6),
    ]
    pygame.draw.polygon(canvas, color, points)
    pygame.draw.lines(canvas, shade(color, 1.25), False, points[3:6], 2)


def _draw_leg(
    canvas: pygame.Surface,
    look: dict,
    hip: tuple[float, float],
    ground: float,
    phase: float,
    amp: float,
    light: float,
    tuck: bool,
    crouch: float,
    offset_x: float,
    joints: tuple[tuple[float, float], tuple[float, float]] | None = None,
) -> None:
    """One leg: the foot lifts while swinging forward and plants while the body passes over it."""
    hx, hy = hip[0] + offset_x, hip[1]
    if joints is not None:
        knee, foot = joints
    elif tuck:  # folded tight: knees up to the chest, heels tucked under
        knee = (hx + 17, hy + 1)
        foot = (hx + 5, hy + 13)
    else:
        swing = math.sin(phase) * 13 * amp
        lift = max(0.0, math.cos(phase)) * 8 * amp
        foot = (hx + swing, ground - 4 - lift)
        knee = ((hx + foot[0]) / 2 + 3 + lift * 0.7 + crouch * 11, (hy + foot[1]) / 2 - lift * 0.6)
    leg = shade(look["legs"], light)
    boot = shade(look["leather"], light * 0.9)
    _limb(canvas, (hx, hy), knee, 6.5, 5.5, leg)
    _limb(canvas, knee, (foot[0], foot[1] - 4), 5.2, 4.6, boot)
    _blob(canvas, (foot[0] + 3, foot[1] - 1), 15, 9, boot)


def _posture_legs(posture: str | None, hip: tuple[float, float], ground: float) -> tuple | None:
    """(back leg, front leg) as (knee, foot) for knockdown stances, or None for normal legs."""
    hx, hy = hip
    if posture == "flail":  # legs kicked up and forward
        return (((hx + 8, hy + 7), (hx + 16, hy + 17)), ((hx + 13, hy + 2), (hx + 25, hy + 9)))
    if posture == "limp":  # straight and slightly apart
        return (((hx - 4, hy + 16), (hx - 6, ground - 4)), ((hx + 4, hy + 16), (hx + 6, ground - 4)))
    if posture == "kneel":  # back knee on the floor, front foot planted
        return (((hx - 2, ground - 5), (hx - 16, ground - 4)), ((hx + 13, hy + 2), (hx + 14, ground - 4)))
    return None


# (back arm angle, sword arm angle) in degrees for knockdown stances.
POSTURE_ARMS = {
    "flail": (-140.0, -150.0),  # arms flung up and back
    "limp": (-105.0, -95.0),  # flopped out past the head (along the floor once rotated)
    "kneel": (55.0, 80.0),  # hand on the knee, leaning on the planted sword
}


def _draw_back_arm(
    canvas: pygame.Surface,
    look: dict,
    shoulder: tuple[float, float],
    gait: float,
    amp: float,
    override: float | None = None,
    stretch: bool = False,
    hand_target: tuple[float, float] | None = None,
    pointing: bool = False,
    bend: float = 7.0,
    behind: bool = False,
) -> None:
    """
    The far arm: swings opposite the near leg, holds a fixed stance angle, reaches
    a target (the second hand on a two-handed grip), or points with an open hand.
    """
    if hand_target is not None:
        hand = hand_target
        elbow = _elbow(shoulder, hand, bend)
        light = 0.75 if behind else 1.0  # in the torso's shadow, or crossing in front fully lit
    else:
        angle = math.radians(override if override is not None else 95 - math.sin(gait) * 30 * amp)
        elbow = (shoulder[0] + math.cos(angle) * 11, shoulder[1] + math.sin(angle) * 11)
        fore = angle - math.radians(3 if stretch else 15 + 10 * amp)  # a stretched arm is nearly straight
        hand = (elbow[0] + math.cos(fore) * 10, elbow[1] + math.sin(fore) * 10)
        light = 0.75
    _limb(canvas, shoulder, elbow, 5, 4.4, shade(look["armor"], light * 0.93))
    _limb(canvas, elbow, hand, 4.4, 4, shade(look["leather"], light))
    _ball(canvas, hand, 4, shade(look["leather"], light * 1.07))
    if pointing:
        direction = math.atan2(hand[1] - elbow[1], hand[0] - elbow[0])
        finger = (hand[0] + math.cos(direction) * 6, hand[1] + math.sin(direction) * 6)
        _capsule(canvas, hand, finger, 1.6, 1.2, shade(look["skin"], 0.95))


def _elbow(shoulder: tuple[float, float], hand: tuple[float, float], bend: float) -> tuple[float, float]:
    """A natural elbow between shoulder and hand, bent downward/outward."""
    mx, my = (shoulder[0] + hand[0]) / 2, (shoulder[1] + hand[1]) / 2
    dx, dy = hand[0] - shoulder[0], hand[1] - shoulder[1]
    length = math.hypot(dx, dy) or 1.0
    nx, ny = -dy / length, dx / length
    if ny < 0:
        nx, ny = -nx, -ny
    return (mx + nx * bend, my + ny * bend)


def _draw_torso(
    canvas: pygame.Surface, look: dict, hip: tuple[float, float], chest: tuple[float, float], shoulder_y: float, gait: float, amp: float
) -> None:
    armor = look["armor"]
    hx, hy = hip
    cx, cy = chest
    _blob(canvas, ((hx + cx) / 2, hy - 8), 23, 20, shade(armor, 0.85))  # belly
    _blob(canvas, (cx, cy), 29, 25, armor)  # barrel chest
    pygame.draw.arc(canvas, shade(armor, 0.62), pygame.Rect(int(cx - 9), int(cy - 6), 18, 14), math.radians(200), math.radians(340), 2)

    sway = -math.sin(gait) * 2 * amp
    top = hy - 4
    tabard = [
        (hx - 7, top), (hx + 8, top), (hx + 8 + sway, top + 13), (hx + 4 + sway, top + 17),
        (hx - 3 + sway, top + 17), (hx - 7 + sway, top + 13),
    ]
    pygame.draw.polygon(canvas, look["cloth"], tabard)
    pygame.draw.lines(canvas, look["trim"], True, tabard, 1)
    pygame.draw.line(canvas, shade(look["cloth"], 1.3), (hx - 4, top + 2), (hx - 4 + sway, top + 13), 1)

    belt = pygame.Rect(int(hx - 11), int(hy - 7), 23, 6)
    pygame.draw.rect(canvas, look["leather"], belt, border_radius=3)
    pygame.draw.line(canvas, shade(look["leather"], 1.35), (belt.left + 2, belt.top + 1), (belt.right - 3, belt.top + 1), 1)
    _ball(canvas, (belt.centerx + 2, belt.centery), 3, look["trim"])


def _draw_head(canvas: pygame.Surface, look: dict, head: tuple[float, float], t: float) -> None:
    hx, hy = head
    _limb(canvas, (hx - 2, hy + 12), (hx - 1, hy + 6), 5, 5, shade(look["skin"], 0.85))  # neck
    if look["helmet"]:
        steel = look["armor"]
        wave = math.sin(t * 5) * 1.5
        for i, r in enumerate((5.0, 4.5, 4.0, 3.2)):
            _ball(canvas, (hx - 4 - i * 4.5, hy - 10 + i * 3 + wave * i / 3), r, shade(look["cloth"], 1.35))  # plume
        _ball(canvas, (hx, hy), 12, steel)
        pygame.draw.rect(canvas, (14, 12, 16), (int(hx + 2), int(hy - 2), 11, 4), border_radius=2)  # visor slit
        _blob(canvas, (hx + 6, hy + 6), 12, 9, shade(steel, 0.9))  # cheek guard
        pygame.draw.line(canvas, look["trim"], (hx - 2, hy - 11), (hx - 2, hy + 9), 2)
        return

    if look.get("hair") is not None:
        _draw_human_head(canvas, look, hx, hy, t)
        return

    skin = look["skin"]
    if look.get("horns"):
        for base, tip in (((hx - 5, hy - 9), (hx - 15, hy - 22)), ((hx + 4, hy - 10), (hx + 9, hy - 24))):
            _capsule(canvas, base, tip, 3.5, 1.0, (120, 104, 90))
            _capsule(canvas, (base[0] - 0.5, base[1] - 0.5), tip, 2.6, 0.6, (226, 214, 190))
    ear = [(hx - 5, hy - 2), (hx - 17, hy - 10), (hx - 7, hy + 4)]
    pygame.draw.polygon(canvas, shade(skin, 0.75), ear)
    _ball(canvas, (hx, hy), 12, skin)  # round skull
    _blob(canvas, (hx + 6, hy + 7), 15, 10, shade(skin, 0.9))  # heavy jaw
    hair = [(hx - 11, hy - 3), (hx - 7, hy - 12), (hx + 4, hy - 13), (hx - 1, hy - 7)]
    pygame.draw.polygon(canvas, shade(look["leather"], 0.6), hair)
    pygame.draw.line(canvas, shade(skin, 0.45), (hx + 3, hy - 5), (hx + 11, hy - 3), 3)  # heavy brow
    eye = look["eye"]
    pygame.draw.circle(canvas, shade(eye, 0.45), (hx + 7, hy - 1), 3)
    pygame.draw.circle(canvas, eye, (hx + 7, hy - 1), 2)
    pygame.draw.circle(canvas, (255, 255, 230), (hx + 7, hy - 1), 1)
    for tooth_x in (hx + 7, hx + 10):
        pygame.draw.polygon(canvas, (236, 226, 196), [(tooth_x - 1, hy + 5), (tooth_x + 1, hy + 5), (tooth_x, hy + 2)])
    if look.get("tusks"):  # ogre/orc fangs jutting up from the lower jaw
        for base, tip in (((hx + 6, hy + 11), (hx + 5, hy + 2)), ((hx + 12, hy + 11), (hx + 13, hy + 2))):
            _capsule(canvas, base, tip, 2.2, 1.0, (238, 228, 200))


def _draw_human_head(canvas: pygame.Surface, look: dict, hx: float, hy: float, t: float) -> None:
    skin = look["skin"]
    hair = look["hair"]
    sway = math.sin(t * 5) * 1.5
    _capsule(canvas, (hx - 7, hy - 1), (hx - 15 - sway, hy + 13), 4.5, 2.5, shade(hair, 0.75))  # ponytail / mane
    _ball(canvas, (hx, hy), 11, skin)
    _blob(canvas, (hx + 4, hy + 6), 13, 9, skin)  # jaw
    _ball(canvas, (hx - 3, hy - 4), 9, hair)
    pygame.draw.ellipse(canvas, skin, (hx - 1, hy - 4, 12, 13))
    _ball(canvas, (hx - 4, hy + 1), 3, shade(skin, 0.9))  # ear
    pygame.draw.line(canvas, shade(hair, 0.8), (hx + 4, hy - 4), (hx + 9, hy - 4), 2)
    pygame.draw.circle(canvas, (30, 24, 24), (hx + 6, hy - 1), 1.6)
    pygame.draw.circle(canvas, shade(skin, 0.82), (hx + 10, hy + 2), 2)  # nose


def _draw_weapon_arm(
    canvas: pygame.Surface,
    look: dict,
    pivot: tuple[float, float],
    angle: float,
    reach: float = 13.0,
    bend: float = 3.0,
    grip: tuple[float, float] | None = None,
    blade_angle: float | None = None,
) -> tuple[float, float]:
    """
    Draw the sword arm (with a bent elbow) and weapon; return the blade tip position.

    Normally the blade continues the arm's line; a ready stance instead passes the
    hand position (grip) and the blade's own direction (blade_angle).
    """
    px, py = pivot
    if grip is not None:
        hand = grip
        elbow = _elbow(pivot, hand, 5)
        a = math.radians(blade_angle if blade_angle is not None else angle)
    else:
        a = math.radians(angle)
        arm = reach * 1.35
        hand = (px + math.cos(a) * arm, py + math.sin(a) * arm)
        elbow = (px + math.cos(a) * arm * 0.52 - math.sin(a) * bend, py + math.sin(a) * arm * 0.52 + math.cos(a) * bend)
    dx, dy = math.cos(a), math.sin(a)
    nx, ny = -dy, dx
    hx, hy = hand
    length = look["blade_len"] * 1.15
    w = look["blade_width"] * 1.15

    base = (hx + dx * 5, hy + dy * 5)
    tip = (hx + dx * (5 + length), hy + dy * (5 + length))
    shoulder = (tip[0] - dx * 7, tip[1] - dy * 7)
    blade = [
        (base[0] + nx * w, base[1] + ny * w),
        (shoulder[0] + nx * w * 0.85, shoulder[1] + ny * w * 0.85),
        tip,
        (shoulder[0] - nx * w * 0.85, shoulder[1] - ny * w * 0.85),
        (base[0] - nx * w, base[1] - ny * w),
    ]
    blade_color = look["blade"]
    pygame.draw.polygon(canvas, shade(blade_color, 0.75), blade)
    pygame.draw.line(canvas, shade(blade_color, 1.25), (base[0] + nx * w * 0.5, base[1] + ny * w * 0.5), (shoulder[0] + nx * w * 0.35, shoulder[1] + ny * w * 0.35), 2)
    pygame.draw.line(canvas, shade(blade_color, 0.55), base, (tip[0] - dx * 9, tip[1] - dy * 9), 1)

    guard = (hx + dx * 4, hy + dy * 4)
    _capsule(canvas, (guard[0] + nx * 7, guard[1] + ny * 7), (guard[0] - nx * 7, guard[1] - ny * 7), 2, 2, look["trim"])
    _ball(canvas, (hx - dx * 5, hy - dy * 5), 3, look["trim"])

    armor = look["armor"]
    _limb(canvas, pivot, elbow, 5.5, 4.8, armor)
    _limb(canvas, elbow, hand, 4.8, 4.2, look["leather"])
    _ball(canvas, pivot, 8, shade(armor, 1.05))  # round pauldron
    _ball(canvas, hand, 4.8, look["leather"])  # fist
    return tip


def _draw_thrust_streak(canvas: pygame.Surface, tip: tuple[float, float], strength: float, color: Color) -> None:
    layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
    tx, ty = tip
    for offset, length in ((-4, 22), (0, 34), (4, 18)):
        pygame.draw.line(layer, (*color, int(170 * strength)), (tx - length, ty + offset), (tx - 4, ty + offset), 2)
    canvas.blit(layer, (0, 0))


def _draw_glint(canvas: pygame.Surface, tip: tuple[float, float], t: float) -> None:
    """A twinkle on the blade tip: the 'about to strike' tell."""
    tx, ty = tip
    r = 5 + 2 * math.sin(t * 30)
    pygame.draw.line(canvas, (255, 255, 230), (tx - r, ty), (tx + r, ty), 2)
    pygame.draw.line(canvas, (255, 255, 230), (tx, ty - r), (tx, ty + r), 2)
    pygame.draw.circle(canvas, (255, 240, 160), tip, 2)


def _draw_slash(
    canvas: pygame.Surface,
    pivot: tuple[float, float],
    start: float,
    end: float,
    radius: float,
    color: Color = (255, 236, 190),
    thickness: float = 13,
) -> None:
    sweep = end - start
    if abs(sweep) < 8:
        return
    layer = pygame.Surface(canvas.get_size(), pygame.SRCALPHA)
    px, py = pivot
    steps = max(12, int(abs(sweep) / 12))
    previous = None
    for i in range(steps + 1):
        k = i / steps
        ang = math.radians(start + sweep * k)
        inner_radius = radius - 3 - thickness * k
        outer = (px + math.cos(ang) * radius, py + math.sin(ang) * radius)
        inner = (px + math.cos(ang) * inner_radius, py + math.sin(ang) * inner_radius)
        if previous is not None:
            pygame.draw.polygon(layer, (*color, int(25 + 150 * k)), [previous[0], outer, inner, previous[1]])
        previous = (outer, inner)
    canvas.blit(layer, (0, 0))


def _draw_held_shield(canvas: pygame.Surface, look: dict, center: tuple[float, float]) -> None:
    """A round Golden Axe-style shield with a rim and boss."""
    _ball(canvas, center, 11, shade(look["cloth"], 1.15))
    pygame.draw.circle(canvas, look["trim"], center, 11, 2)
    _ball(canvas, center, 3.5, look["trim"])


# --------------------------------------------------------------------------
# HUD icons
# --------------------------------------------------------------------------


def draw_sword_icon(surface: pygame.Surface, center: tuple[int, int], size: int) -> None:
    """Draw a diagonal sword icon."""
    cx, cy = center
    s = size / 34
    dx, dy = 0.707, -0.707
    nx, ny = 0.707, 0.707
    base = (cx - 7 * s, cy + 7 * s)
    tip = (cx + 13 * s, cy - 13 * s)
    shoulder = (tip[0] - dx * 5 * s, tip[1] - dy * 5 * s)
    blade = [
        (base[0] + nx * 3 * s, base[1] + ny * 3 * s),
        (shoulder[0] + nx * 2.4 * s, shoulder[1] + ny * 2.4 * s),
        tip,
        (shoulder[0] - nx * 2.4 * s, shoulder[1] - ny * 2.4 * s),
        (base[0] - nx * 3 * s, base[1] - ny * 3 * s),
    ]
    pygame.draw.polygon(surface, (196, 204, 214), blade)
    pygame.draw.line(surface, (250, 252, 255), (base[0] - nx * 1.5 * s, base[1] - ny * 1.5 * s), (shoulder[0] - nx * 1.2 * s, shoulder[1] - ny * 1.2 * s), 2)
    pygame.draw.line(surface, (214, 172, 86), (base[0] + nx * 8 * s, base[1] + ny * 8 * s), (base[0] - nx * 8 * s, base[1] - ny * 8 * s), max(2, round(4 * s)))
    grip_end = (base[0] - dx * 8 * s, base[1] - dy * 8 * s)
    pygame.draw.line(surface, (92, 60, 40), base, grip_end, max(2, round(4 * s)))
    pygame.draw.circle(surface, (214, 172, 86), (grip_end[0] - dx * 2 * s, grip_end[1] - dy * 2 * s), 3 * s)


def draw_special_icon(surface: pygame.Surface, center: tuple[int, int], size: int, kind: str, look: dict) -> None:
    """Draw the icon for a hero's special ability (see SPECIALS in core.constants)."""
    cx, cy = center
    s = size / 34
    gold, light = (236, 196, 100), (250, 240, 210)
    if kind == "charge":  # shield rushing forward with speed lines
        for i, length in enumerate((10, 14, 10)):
            y = cy - 7 * s + i * 7 * s
            pygame.draw.line(surface, light, (cx - 16 * s, y), (cx - (16 - length) * s, y), 2)
        draw_shield_icon(surface, (round(cx + 5 * s), cy), round(size * 0.8), look)
    elif kind == "arrow":  # an arrow flying right
        pygame.draw.line(surface, (150, 104, 60), (cx - 14 * s, cy + 6 * s), (cx + 10 * s, cy - 6 * s), max(2, round(3 * s)))
        pygame.draw.polygon(surface, (220, 226, 236), [(cx + 16 * s, cy - 9 * s), (cx + 6 * s, cy - 8 * s), (cx + 12 * s, cy - 1 * s)])
        for off in (-1, 1):
            pygame.draw.line(surface, (80, 160, 100), (cx - 14 * s, cy + 6 * s), (cx - 17 * s + off * 3 * s, cy + (1 + off * 4) * s), max(2, round(3 * s)))
    elif kind == "shadow_step":  # a dagger over a purple smoke puff
        for dx, dy, r in ((-7, 6, 8), (3, 9, 7), (9, 3, 6), (-2, 0, 6)):
            pygame.draw.circle(surface, (96, 70, 124), (cx + dx * s, cy + dy * s), r * s)
        blade = [(cx - 8 * s, cy + 4 * s), (cx + 14 * s, cy - 14 * s), (cx - 2 * s, cy + 10 * s)]
        pygame.draw.polygon(surface, (230, 236, 246), blade)
        pygame.draw.polygon(surface, (30, 24, 40), blade, 1)
        pygame.draw.line(surface, gold, (cx - 12 * s, cy + 4 * s), (cx - 2 * s, cy + 14 * s), max(3, round(4 * s)))
        pygame.draw.line(surface, (92, 60, 40), (cx - 6 * s, cy + 10 * s), (cx - 12 * s, cy + 16 * s), max(3, round(4 * s)))
    elif kind == "holy_light":  # a radiant sun with a cross
        for i in range(8):
            a = i * math.pi / 4
            pygame.draw.line(surface, gold, (cx + math.cos(a) * 9 * s, cy + math.sin(a) * 9 * s), (cx + math.cos(a) * 16 * s, cy + math.sin(a) * 16 * s), 2)
        pygame.draw.circle(surface, (255, 226, 130), center, 9 * s)
        pygame.draw.line(surface, (255, 255, 240), (cx, cy - 6 * s), (cx, cy + 6 * s), max(2, round(3 * s)))
        pygame.draw.line(surface, (255, 255, 240), (cx - 4 * s, cy - 2 * s), (cx + 4 * s, cy - 2 * s), max(2, round(3 * s)))
    elif kind == "war_cry":  # an open shout with sound waves
        pygame.draw.circle(surface, (210, 70, 50), (cx - 6 * s, cy), 8 * s)
        pygame.draw.ellipse(surface, (40, 10, 10), pygame.Rect(cx - 9 * s, cy - 3 * s, 7 * s, 8 * s))
        for r in (10, 15, 20):
            rect = pygame.Rect(0, 0, r * 2 * s, r * 2 * s)
            rect.center = (cx - 6 * s, cy)
            pygame.draw.arc(surface, (250, 140, 100), rect, -0.7, 0.7, 2)
    elif kind == "earthquake":  # cracked ground with rocks flying up
        pygame.draw.rect(surface, (120, 100, 76), pygame.Rect(cx - 16 * s, cy + 4 * s, 32 * s, 10 * s), border_radius=2)
        pygame.draw.lines(surface, (40, 28, 20), False, [(cx - 12 * s, cy + 4 * s), (cx - 4 * s, cy + 10 * s), (cx + 2 * s, cy + 5 * s), (cx + 10 * s, cy + 13 * s)], 2)
        for dx, dy, r in ((-9, -6, 3), (2, -12, 4), (11, -5, 3)):
            pygame.draw.circle(surface, (170, 146, 112), (cx + dx * s, cy + dy * s), r * s)
        pygame.draw.line(surface, gold, (cx, cy - 2 * s), (cx, cy - 16 * s), 2)


def draw_shield_icon(surface: pygame.Surface, center: tuple[int, int], size: int, look: dict) -> None:
    """Draw a heater shield icon in the given look's colors."""
    cx, cy = center
    s = size / 34
    points = [(cx - 12 * s, cy - 14 * s), (cx + 12 * s, cy - 14 * s), (cx + 12 * s, cy + 1 * s), (cx, cy + 15 * s), (cx - 12 * s, cy + 1 * s)]
    pygame.draw.polygon(surface, shade(look["cloth"], 1.2), points)
    left_half = [points[0], (cx, cy - 14 * s), (cx, cy + 15 * s), points[4]]
    pygame.draw.polygon(surface, shade(look["cloth"], 1.5), left_half)
    pygame.draw.polygon(surface, look["trim"], points, max(2, round(2 * s)))
    pygame.draw.line(surface, look["trim"], (cx, cy - 12 * s), (cx, cy + 12 * s), 2)
    pygame.draw.line(surface, look["trim"], (cx - 9 * s, cy - 5 * s), (cx + 9 * s, cy - 5 * s), 2)


def draw_heavy_icon(surface: pygame.Surface, center: tuple[int, int], size: int) -> None:
    """Draw a heavy downward strike: a broad blade with impact lines."""
    cx, cy = center
    s = size / 34
    blade = [(cx - 5 * s, cy - 8 * s), (cx + 5 * s, cy - 8 * s), (cx + 5 * s, cy + 6 * s), (cx, cy + 13 * s), (cx - 5 * s, cy + 6 * s)]
    pygame.draw.polygon(surface, (196, 204, 214), blade)
    pygame.draw.line(surface, (250, 252, 255), (cx - 2 * s, cy - 7 * s), (cx - 2 * s, cy + 7 * s), 2)
    pygame.draw.line(surface, (214, 172, 86), (cx - 10 * s, cy - 9 * s), (cx + 10 * s, cy - 9 * s), max(2, round(4 * s)))
    pygame.draw.line(surface, (92, 60, 40), (cx, cy - 10 * s), (cx, cy - 16 * s), max(2, round(4 * s)))
    for side in (-1, 1):
        pygame.draw.line(surface, (255, 206, 110), (cx + side * 8 * s, cy + 11 * s), (cx + side * 14 * s, cy + 6 * s), 2)
        pygame.draw.line(surface, (255, 206, 110), (cx + side * 9 * s, cy + 15 * s), (cx + side * 15 * s, cy + 15 * s), 2)


def draw_spin_icon(surface: pygame.Surface, center: tuple[int, int], size: int) -> None:
    """Draw a whirlwind: a circular arrow around a small blade."""
    cx, cy = center
    r = size * 0.4
    rect = pygame.Rect(0, 0, int(r * 2), int(r * 2))
    rect.center = (cx, cy)
    pygame.draw.arc(surface, (200, 230, 255), rect, math.radians(30), math.radians(320), 3)
    tip_angle = math.radians(30)
    tip = (cx + math.cos(tip_angle) * r, cy - math.sin(tip_angle) * r)
    pygame.draw.polygon(surface, (200, 230, 255), [(tip[0] - 7, tip[1] - 1), (tip[0] + 5, tip[1] - 4), (tip[0] + 1, tip[1] + 8)])
    draw_sword_icon(surface, center, int(size * 0.55))


def draw_fury_icon(surface: pygame.Surface, center: tuple[int, int], size: int, t: float) -> None:
    """Draw a live flame icon for the Fury slot."""
    cx, cy = center
    draw_flame(surface, cx, cy + size * 0.38, t, size * 0.55, seed=3.0)


def draw_potion(surface: pygame.Surface, x: float, bottom: float, t: float) -> None:
    """A Golden Axe blue magic pot: round glass jar, cork, and a soft glow."""
    glow = radial_glow(26, shade((40, 80, 160), 0.8 + 0.2 * math.sin(t * 5)))
    surface.blit(glow, glow.get_rect(center=(int(x), int(bottom) - 9)), special_flags=pygame.BLEND_RGB_ADD)
    pygame.draw.ellipse(surface, (34, 64, 150), (x - 8, bottom - 16, 16, 16))
    pygame.draw.ellipse(surface, (70, 120, 235), (x - 7, bottom - 15, 14, 13))
    pygame.draw.rect(surface, (60, 100, 200), (x - 3, bottom - 21, 6, 6))
    pygame.draw.rect(surface, (130, 86, 50), (x - 3, bottom - 24, 6, 4), border_radius=1)
    pygame.draw.circle(surface, (200, 230, 255), (x - 3, bottom - 11), 2)


# --------------------------------------------------------------------------
# Riders: goblin wolf riders and bat riders (drawn side-on facing right, then mirrored)
# --------------------------------------------------------------------------

BEAST_CANVAS = (220, 170)
BEAST_ANCHOR = (110, 150)  # feet (or, for a bat, the point under it on the floor) sit here
RIDER_LOOKS = {
    # A black-furred warg with grey hackles and a goblin raider in a horned skull helm.
    "wolf_rider": {"fur": (46, 42, 48), "belly": (92, 86, 90), "hackles": (120, 116, 122), "eye": (255, 50, 30),
                   "skin": (110, 140, 70), "armor": (70, 52, 40), "trim": (150, 120, 70), "helm": (214, 206, 186), "cloth": (120, 28, 26)},
    # A giant bat with blood-red wing membranes ridden by a hooded goblin.
    "bat_rider": {"fur": (44, 32, 48), "membrane": (96, 30, 40), "bones": (26, 18, 28), "eye": (255, 60, 40),
                  "skin": (150, 160, 120), "armor": (50, 44, 60), "trim": (130, 110, 140), "hood": (38, 30, 46), "cloth": (70, 20, 30)},
}


def render_beast(kind: str, t: float, gait: float, stride: float, pose: str = "stand", charge: float = 0.0, face_sign: int = 1) -> pygame.Surface:
    """
    Paint a wolf rider or bat rider on its own canvas.

    pose: "run", "crouch" (about to lunge), "lunge" (mid-leap), "screech"/"fly"/"swoop" (bat), "dead".
    charge (0..1) brightens the eyes during a telegraph.
    """
    canvas = pygame.Surface(BEAST_CANVAS, pygame.SRCALPHA)
    look = RIDER_LOOKS[kind]
    if kind == "bat_rider":
        _draw_bat_rider(canvas, look, t, pose, charge)
    else:
        _draw_wolf_rider(canvas, look, gait, stride, pose, charge, t)
    canvas = _outline(canvas)
    if face_sign < 0:
        canvas = pygame.transform.flip(canvas, True, False)
    return canvas


def _glow_eye(canvas: pygame.Surface, center: tuple[float, float], color: Color, charge: float, r: float = 2.4) -> None:
    """A burning eye in a dark socket; it swells and turns white-hot during a telegraph."""
    r = r + 1.2 * charge
    pygame.draw.circle(canvas, (20, 6, 6), center, r + 1.2)
    pygame.draw.circle(canvas, color, center, r)
    pygame.draw.circle(canvas, mix(color, (255, 250, 220), 0.4 + 0.6 * charge), center, max(1.0, r * 0.5))


def _draw_goblin_rider(
    canvas: pygame.Surface, look: dict, seat: tuple[float, float], lean: float, weapon_angle: float, t: float,
    hooded: bool = False, dead: bool = False,
) -> None:
    """A wiry goblin warrior sitting at `seat`, leaning forward, with a spear held at `weapon_angle` (degrees)."""
    sx, sy = seat
    armor, skin = look["armor"], look["skin"]
    if dead:  # thrown off, lying beside the mount
        _blob(canvas, (sx + 30, sy + 26), 26, 10, armor)
        _ball(canvas, (sx + 46, sy + 24), 7, skin)
        return
    hip = (sx, sy)
    shoulder = (sx + 6 + lean, sy - 20)
    _limb(canvas, hip, (sx + 8, sy + 14), 4.5, 3.5, shade(armor, 0.8))  # leg down the mount's side
    _ball(canvas, (sx + 10, sy + 16), 3.5, (40, 30, 26))  # boot in the stirrup
    _blob(canvas, ((hip[0] + shoulder[0]) / 2, (hip[1] + shoulder[1]) / 2), 16, 24, armor)  # torso
    pygame.draw.line(canvas, look["trim"], (hip[0] - 4, hip[1] - 4), (shoulder[0] + 3, shoulder[1] + 4), 2)  # strap
    cape = [(shoulder[0] - 5, shoulder[1]), (shoulder[0] - 18, shoulder[1] + 6 + math.sin(t * 7) * 3), (hip[0] - 12, hip[1] - 2)]
    pygame.draw.polygon(canvas, look["cloth"], cape)  # tattered cape streaming behind
    head = (shoulder[0] + 4, shoulder[1] - 10)
    if hooded:
        _ball(canvas, head, 8, look["hood"])
        pygame.draw.polygon(canvas, look["hood"], [(head[0] - 6, head[1] - 4), (head[0] - 14, head[1] - 14), (head[0] - 2, head[1] - 7)])
        _ball(canvas, (head[0] + 3, head[1] + 1), 5, shade(skin, 0.8))  # face in the hood's shadow
        pygame.draw.circle(canvas, (255, 210, 80), (head[0] + 5, head[1]), 1.5)
    else:
        _ball(canvas, (head[0] + 2, head[1] + 2), 6, skin)
        pygame.draw.polygon(canvas, skin, [(head[0] - 3, head[1]), (head[0] - 13, head[1] - 4), (head[0] - 4, head[1] + 4)])  # long ear
        _ball(canvas, (head[0] + 1, head[1] - 2), 7, look["helm"])  # a beast's skull worn as a helm
        for base, mid, tip in (((head[0] - 4, head[1] - 7), (head[0] - 11, head[1] - 10), (head[0] - 12, head[1] - 3)),
                               ((head[0] + 1, head[1] - 8), (head[0] - 5, head[1] - 14), (head[0] - 4, head[1] - 7))):
            _capsule(canvas, base, mid, 2.4, 1.6, shade(look["helm"], 0.75))  # curled horns sweeping back
            _capsule(canvas, mid, tip, 1.6, 0.7, shade(look["helm"], 0.6))
        pygame.draw.circle(canvas, (24, 12, 12), (head[0] + 4, head[1] - 2), 2.6)  # dark eye socket
        pygame.draw.circle(canvas, (255, 190, 50), (head[0] + 4.5, head[1] - 2), 1.2)
        for tooth in range(3):  # the skull's teeth over the goblin's face
            pygame.draw.line(canvas, shade(look["helm"], 0.9), (head[0] + 2 + tooth * 2, head[1] + 3), (head[0] + 2 + tooth * 2, head[1] + 6), 1)
    a = math.radians(weapon_angle)
    hand = (shoulder[0] + 10 + lean * 0.5, shoulder[1] + 10)
    _limb(canvas, shoulder, hand, 3.6, 3, armor)
    butt = (hand[0] - math.cos(a) * 24, hand[1] - math.sin(a) * 24)
    tip = (hand[0] + math.cos(a) * 36, hand[1] + math.sin(a) * 36)
    pygame.draw.line(canvas, (96, 66, 40), butt, tip, 3)  # spear shaft
    nx, ny = -math.sin(a), math.cos(a)
    head_base = (tip[0] - math.cos(a) * 10, tip[1] - math.sin(a) * 10)
    point = (tip[0] + math.cos(a) * 4, tip[1] + math.sin(a) * 4)
    pygame.draw.polygon(canvas, (214, 220, 230), [(head_base[0] + nx * 4, head_base[1] + ny * 4), point, (head_base[0] - nx * 4, head_base[1] - ny * 4)])
    _ball(canvas, hand, 3, skin)
    pygame.draw.line(canvas, look["cloth"], (butt[0] + math.cos(a) * 30, butt[1] + math.sin(a) * 30), (butt[0] + math.cos(a) * 24, butt[1] + math.sin(a) * 24 + 8), 3)  # war ribbon


def _draw_wolf_rider(canvas: pygame.Surface, look: dict, gait: float, stride: float, pose: str, charge: float, t: float) -> None:
    """A huge warg (hackles up, snarling, burning eyes) with a goblin raider and spear on its back."""
    k = 1.25
    fx, fy = BEAST_ANCHOR
    fur, belly = look["fur"], look["belly"]
    dead = pose == "dead"
    crouch = 8 * k if pose == "crouch" else 0
    lean = 7 * k if pose == "lunge" else -4 * k if pose == "crouch" else 0
    body_y = fy - (14 if dead else 32) * k + crouch
    hind, chest = (fx - 24 * k, body_y), (fx + 20 * k + lean, body_y - 4 * k)

    wag = math.sin(t * 5) * 3
    # A long, bushy tail: a chain of tapering segments sweeping back, sagging, then lifting at the tip.
    tail = [(hind[0] - 8 * k, hind[1] - 6 * k)]
    for i in range(1, 7):
        u = i / 6
        sag = math.sin(u * math.pi * 0.9) * 9 * k - u * u * 10 * k  # droops, then the tip curls up
        tail.append((hind[0] - 8 * k - u * 50 * k, hind[1] - 6 * k + sag + wag * u + (12 * u if dead else 0)))
    for i, (a, b) in enumerate(zip(tail, tail[1:])):
        _capsule(canvas, a, b, (8.0 - i * 0.6) * k, (8.0 - (i + 1) * 0.6) * k, fur)
    for a, b in zip(tail[3:], tail[4:]):  # pale fur toward the tip
        _capsule(canvas, (a[0], a[1] - 2), (b[0], b[1] - 2), 3.0 * k, 2.4 * k, look["hackles"])
    legs = ((hind, 0.0, 0.65), (chest, math.pi, 0.65), (hind, math.pi, 1.0), (chest, 0.0, 1.0))
    for root, phase, light in legs:
        color = shade(fur, light)
        if dead:
            _limb(canvas, root, (root[0] + 24 * k, root[1] + 4 * k), 5 * k, 3.5 * k, color)
            continue
        swing = math.sin(gait + phase) * 11 * k * stride
        if pose == "lunge":
            swing = 16 * k if root is chest else -16 * k
        knee = (root[0] + swing * 0.5, root[1] + 13 * k)
        foot = (root[0] + swing, fy - max(0.0, math.sin(gait + phase)) * 5 * stride - (7 * k if pose == "lunge" else 0))
        _limb(canvas, root, knee, 6.5 * k, 4.5 * k, color)
        _limb(canvas, knee, foot, 4.5 * k, 3.2 * k, shade(color, 0.9))
        _ball(canvas, foot, 3.6 * k, shade(fur, light * 0.7))
        for c in (-2, 1, 4):  # claws
            pygame.draw.line(canvas, (226, 220, 206), (foot[0] + c, foot[1] + 2), (foot[0] + c + 2, foot[1] + 4), 1)
    mid_x = (hind[0] + chest[0]) / 2
    # Lean, predatory torso: deep chest, tucked-up waist, muscled haunch (not a round barrel).
    torso = [
        (chest[0] + 13 * k, chest[1] - 6 * k), (chest[0] + 4 * k, chest[1] - 15 * k),  # chest front, withers
        (mid_x, body_y - 12 * k), (hind[0] - 4 * k, body_y - 11 * k),  # back line
        (hind[0] - 14 * k, body_y - 3 * k), (hind[0] - 9 * k, body_y + 9 * k),  # rump, back of thigh
        (hind[0] + 6 * k, body_y + 6 * k), (mid_x + 2 * k, body_y + 3 * k),  # tucked-up waist
        (chest[0] - 6 * k, body_y + 13 * k), (chest[0] + 8 * k, chest[1] + 12 * k),  # deep brisket
    ]
    pygame.draw.polygon(canvas, fur, torso)
    _ball(canvas, (hind[0] - 4 * k, body_y - 1 * k), 11 * k, shade(fur, 1.08))  # haunch muscle
    _ball(canvas, (chest[0] + 2 * k, chest[1] - 2 * k), 12 * k, shade(fur, 1.08))  # shoulder muscle
    ruff = [(chest[0] + 12 * k, chest[1] - 2 * k), (chest[0] + 6 * k, chest[1] + 12 * k), (chest[0] - 4 * k, body_y + 12 * k), (chest[0] + 2 * k, chest[1] + 2 * k)]
    pygame.draw.polygon(canvas, belly, ruff)  # pale chest ruff
    pygame.draw.line(canvas, shade(belly, 0.8), (chest[0] - 6 * k, body_y + 11 * k), (mid_x + 2 * k, body_y + 4 * k), 2)  # underside
    for i in range(7):  # bristling hackles along the spine
        hx = chest[0] - 4 * k - i * 7 * k
        base = body_y - (13 - abs(i - 2) * 0.8) * k
        pygame.draw.polygon(canvas, look["hackles"], [(hx - 4 * k, base + 3), (hx + 1 * k, base - 9 * k - (2 if i < 3 else 0)), (hx + 4 * k, base + 3)])

    # Saddle and harness, then the rider.
    saddle_x = mid_x - 4 * k
    if not dead:
        pygame.draw.rect(canvas, (90, 56, 34), pygame.Rect(saddle_x - 12 * k, body_y - 16 * k, 24 * k, 9 * k), border_radius=4)
        pygame.draw.line(canvas, (60, 38, 24), (saddle_x, body_y - 8 * k), (saddle_x + 2 * k, body_y + 10 * k), 3)  # girth strap
    spear = 18.0 if pose == "lunge" else -35.0 + math.sin(t * 3) * 4
    _draw_goblin_rider(canvas, look, (saddle_x, body_y - 16 * k), 6 if pose == "lunge" else 0, spear, t, dead=dead)

    # Head: low, ears pinned back, snarling jaws, burning eyes.
    head = (chest[0] + 16 * k, chest[1] - 6 * k + (7 * k if pose == "crouch" else 0) + (12 * k if dead else 0))
    _limb(canvas, (chest[0] + 4 * k, chest[1] - 2 * k), head, 9 * k, 7.5 * k, fur)
    hx, hy = head
    pygame.draw.polygon(canvas, shade(fur, 0.7), [(hx - 8 * k, hy - 4 * k), (hx - 14 * k, hy - 14 * k), (hx - 2 * k, hy - 7 * k)])  # pinned ear
    _ball(canvas, (hx, hy), 9 * k, fur)
    gape = 0 if dead else (7 if pose in ("lunge", "crouch") or charge > 0.3 else 3) * k
    upper = [(hx + 2 * k, hy - 3 * k), (hx + 20 * k, hy + 1 * k), (hx + 19 * k, hy + 4 * k), (hx + 2 * k, hy + 4 * k)]
    lower = [(hx + 2 * k, hy + 4 * k + gape * 0.3), (hx + 16 * k, hy + 5 * k + gape), (hx + 14 * k, hy + 8 * k + gape), (hx + 1 * k, hy + 8 * k)]
    if gape:
        pygame.draw.polygon(canvas, (80, 10, 14), [upper[2], upper[3], lower[0], lower[1]])  # red maw
        for i in range(4):  # fangs, top and bottom
            tx = hx + (6 + i * 4) * k
            pygame.draw.polygon(canvas, (242, 236, 220), [(tx - 1.5, hy + 4 * k), (tx + 1.5, hy + 4 * k), (tx, hy + 4 * k + 4)])
            pygame.draw.polygon(canvas, (242, 236, 220), [(tx - 1.5, hy + 5 * k + gape), (tx + 1.5, hy + 5 * k + gape), (tx, hy + 5 * k + gape - 4)])
    pygame.draw.polygon(canvas, fur, upper)
    pygame.draw.polygon(canvas, shade(fur, 0.85), lower)
    _ball(canvas, (hx + 20 * k, hy + 1 * k), 2.6 * k, (16, 10, 12))  # nose
    pygame.draw.line(canvas, shade(fur, 0.5), (hx + 4 * k, hy - 5 * k), (hx + 12 * k, hy - 2 * k), 2)  # snarl wrinkle
    if dead:
        ex, ey = hx + 4 * k, hy - 3 * k
        pygame.draw.line(canvas, (20, 14, 14), (ex - 3, ey - 3), (ex + 3, ey + 3), 2)
        pygame.draw.line(canvas, (20, 14, 14), (ex - 3, ey + 3), (ex + 3, ey - 3), 2)
    else:
        _glow_eye(canvas, (hx + 5 * k, hy - 3 * k), look["eye"], charge)
    if not dead:  # harness across the chest
        pygame.draw.arc(canvas, (90, 56, 34), pygame.Rect(chest[0] - 10 * k, chest[1] - 12 * k, 22 * k, 26 * k), -1.0, 1.6, 3)
        _ball(canvas, (chest[0] + 9 * k, chest[1] + 2 * k), 2.5, look["trim"])


def _draw_bat_rider(canvas: pygame.Surface, look: dict, t: float, pose: str, charge: float) -> None:
    """A giant bat (ragged blood-red wings, fangs, burning eyes) carrying a hooded goblin with a hooked spear."""
    k = 2.2
    cx, cy = BEAST_CANVAS[0] / 2, BEAST_ANCHOR[1] - 52
    dead = pose == "dead"
    if dead:
        cy = BEAST_ANCHOR[1] - 12
    flap = -0.7 if dead else math.sin(t * (24 if pose == "swoop" else 14))
    for side, light in ((-1, 0.7), (1, 1.0)):  # far wing, then near wing
        tip = (cx + side * 40 * k, cy - 22 * k - flap * 16 * k)
        fingers = [tip, (cx + side * 38 * k, cy - 2 * k - flap * 8 * k), (cx + side * 26 * k, cy + 9 * k - flap * 4 * k)]
        wrist = (cx + side * 16 * k, cy - 16 * k - flap * 11 * k)
        membrane = [(cx, cy - 2 * k), wrist, tip]
        for a, b in zip(fingers, fingers[1:]):  # ragged scallops between finger bones
            membrane.append(((a[0] + b[0]) / 2 - side * 3 * k, (a[1] + b[1]) / 2 - 2 * k))
            membrane.append(b)
        membrane.append((cx + side * 6 * k, cy + 8 * k))
        pygame.draw.polygon(canvas, shade(look["membrane"], light), membrane)
        for finger in fingers:
            pygame.draw.line(canvas, shade(look["bones"], light), wrist, finger, 2)
        pygame.draw.line(canvas, shade(look["bones"], light), (cx, cy - 2 * k), wrist, 3)
        _capsule(canvas, wrist, (wrist[0] + side * 2, wrist[1] - 5), 1.8, 0.6, (220, 214, 200))  # wing claw
    body = [(cx + 7 * k, cy - 5 * k), (cx + 9 * k, cy + 3 * k), (cx + 4 * k, cy + 11 * k), (cx, cy + 15 * k),
            (cx - 4 * k, cy + 10 * k), (cx - 7 * k, cy + 1 * k), (cx - 3 * k, cy - 6 * k)]
    pygame.draw.polygon(canvas, look["fur"], body)  # lean, tapering body
    pygame.draw.line(canvas, shade(look["fur"], 1.4), (cx + 6 * k, cy - 2 * k), (cx + 2 * k, cy + 10 * k), 2)  # chest fur
    for side in (-1, 1):  # clawed feet hanging below
        foot = (cx + side * 4 * k, cy + 15 * k)
        pygame.draw.line(canvas, look["bones"], (cx + side * 3 * k, cy + 10 * k), foot, 2)
        pygame.draw.line(canvas, (220, 214, 200), foot, (foot[0] + 3, foot[1] + 3), 1)
    spear = 40.0 if pose == "swoop" else 10.0 + math.sin(t * 3) * 5
    _draw_goblin_rider(canvas, look, (cx - 4 * k, cy - 6 * k), 3, spear, t, hooded=True, dead=dead)
    head = (cx + 14 * k, cy + 1 * k)  # the bat's head juts out in front of its rider
    _limb(canvas, (cx + 5 * k, cy - 1 * k), head, 3.5 * k, 3 * k, look["fur"])  # thin neck
    skull = [(head[0] - 5 * k, head[1] - 4 * k), (head[0] + 2 * k, head[1] - 5 * k), (head[0] + 9 * k, head[1] + 1 * k),
             (head[0] + 3 * k, head[1] + 4 * k), (head[0] - 4 * k, head[1] + 3 * k)]
    pygame.draw.polygon(canvas, look["fur"], skull)  # wedge skull with a pointed snout
    pygame.draw.circle(canvas, (20, 12, 16), (head[0] + 8 * k, head[1] + 0.5 * k), 1.6)  # nostril
    for ex in (-1, 1):  # tall ears
        pygame.draw.polygon(canvas, look["bones"], [(head[0] - 2 + ex * 4 * k, head[1] - 4 * k), (head[0] + ex * 6 * k, head[1] - 17 * k), (head[0] + 2 + ex * 1 * k, head[1] - 6 * k)])
    if not dead:
        _glow_eye(canvas, (head[0] + 3 * k, head[1] - 2 * k), look["eye"], charge, 2.0)
        mouth_open = 4 * k if pose in ("screech", "swoop") else 1.5 * k
        pygame.draw.ellipse(canvas, (80, 10, 14), pygame.Rect(head[0] + 1 * k, head[1] + 2 * k, 7 * k, mouth_open))
        for fx in (head[0] + 2.5 * k, head[0] + 6 * k):
            pygame.draw.polygon(canvas, (242, 236, 220), [(fx - 1.5, head[1] + 2 * k), (fx + 1.5, head[1] + 2 * k), (fx, head[1] + 2 * k + 5)])


def draw_reward(surface: pygame.Surface, kind: str, x: float, bottom: float, t: float) -> None:
    """The special drops from riders: bat elixir (purple vial) and wolf pelt. They glow and sparkle."""
    colors = {"elixir": (170, 80, 230), "pelt": (150, 140, 128)}
    pulse = 0.75 + 0.25 * math.sin(t * 5)
    glow = radial_glow(30, shade(colors[kind], 0.7 * pulse))
    surface.blit(glow, glow.get_rect(center=(int(x), int(bottom) - 11)), special_flags=pygame.BLEND_RGB_ADD)
    if kind == "elixir":
        pygame.draw.polygon(surface, (60, 30, 80), [(x - 7, bottom - 4), (x + 7, bottom - 4), (x + 4, bottom - 14), (x - 4, bottom - 14)])
        pygame.draw.polygon(surface, (190, 100, 255), [(x - 6, bottom - 5), (x + 6, bottom - 5), (x + 3, bottom - 12), (x - 3, bottom - 12)])
        pygame.draw.rect(surface, (220, 220, 230), (x - 2, bottom - 21, 4, 8))
        pygame.draw.rect(surface, (130, 90, 50), (x - 3, bottom - 24, 6, 4))
    elif kind == "pelt":
        pelt = [(x - 13, bottom - 4), (x - 9, bottom - 12), (x - 2, bottom - 14), (x + 8, bottom - 13), (x + 14, bottom - 7), (x + 9, bottom - 2), (x - 6, bottom - 1)]
        pygame.draw.polygon(surface, (150, 140, 128), pelt)
        pygame.draw.polygon(surface, (70, 64, 60), pelt, 2)
        for i in range(3):
            pygame.draw.line(surface, (100, 94, 88), (x - 6 + i * 6, bottom - 11), (x - 3 + i * 6, bottom - 4), 1)
        pygame.draw.circle(surface, (226, 182, 70), (x, bottom - 8), 3)  # charm: a shield rune
    if int(t * 4) % 2 == 0:  # twinkle
        sx, sy = x + 10, bottom - 22
        pygame.draw.line(surface, (255, 255, 230), (sx - 3, sy), (sx + 3, sy), 1)
        pygame.draw.line(surface, (255, 255, 230), (sx, sy - 3), (sx, sy + 3), 1)


def draw_meat(surface: pygame.Surface, x: float, bottom: float) -> None:
    """A roast leg of meat."""
    pygame.draw.line(surface, (236, 228, 210), (x + 3, bottom - 7), (x + 11, bottom - 13), 3)
    pygame.draw.circle(surface, (236, 228, 210), (x + 12, bottom - 15), 3)
    pygame.draw.circle(surface, (236, 228, 210), (x + 13, bottom - 12), 3)
    pygame.draw.ellipse(surface, (120, 56, 30), (x - 10, bottom - 14, 17, 13))
    pygame.draw.ellipse(surface, (176, 92, 48), (x - 9, bottom - 14, 14, 10))
    pygame.draw.ellipse(surface, (226, 150, 96), (x - 6, bottom - 13, 5, 3))


def draw_skull(surface: pygame.Surface, center: tuple[int, int], r: int, color: Color = (214, 204, 184)) -> None:
    """Draw a small skull glyph."""
    cx, cy = center
    pygame.draw.circle(surface, color, (cx, cy - 1), r)
    pygame.draw.rect(surface, color, (cx - r * 0.6, cy + r * 0.4, r * 1.2, r * 0.8), border_radius=2)
    dark = (30, 22, 20)
    pygame.draw.circle(surface, dark, (cx - r * 0.4, cy - 1), max(1, r * 0.3))
    pygame.draw.circle(surface, dark, (cx + r * 0.4, cy - 1), max(1, r * 0.3))


def draw_diamond(surface: pygame.Surface, center: tuple[int, int], r: int, color: Color) -> None:
    """Draw a small ornamental diamond."""
    cx, cy = center
    pygame.draw.polygon(surface, color, [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)])
    pygame.draw.polygon(surface, shade(color, 0.5), [(cx, cy - r), (cx + r, cy), (cx, cy + r), (cx - r, cy)], 1)
