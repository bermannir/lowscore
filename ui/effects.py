"""
Module: effects
Purpose: Short-lived combat and ambient effects: particles, damage numbers, corpses, blood decals, shake.
Dependencies: pygame, lowscore.ui.art
Used by: ui.renderer.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

from core import i18n
from ui import art


@dataclass
class Particle:
    """A single spark, droplet, ember, or dust mote."""

    x: float
    y: float
    vx: float
    vy: float
    life: float
    max_life: float
    color: tuple[int, int, int]
    size: float
    gravity: float = 0.0
    drag: float = 0.0
    ground_y: float | None = None
    alpha: int = 255


@dataclass
class FloatingText:
    """A damage number that pops, rises, and fades."""

    x: float
    y: float
    surface: pygame.Surface
    life: float
    max_life: float


@dataclass
class Corpse:
    """A defeated actor that topples over and fades out."""

    canvas: pygame.Surface
    x: float
    feet_y: float
    face_sign: int
    age: float = 0.0
    rotate: float = 90.0  # fighters topple over; beasts are already drawn lying down (0)
    lift: float | None = None  # beasts: fixed height of the image centre above the floor


class Effects:
    """Owns every transient visual effect and the persistent blood decal layer."""

    CORPSE_LIFETIME = 2.6
    FALL_TIME = 0.32

    def __init__(self, size: tuple[int, int]) -> None:
        """Create empty effect lists and a transparent decal layer of the given size."""
        self.decals = pygame.Surface(size, pygame.SRCALPHA)
        self.particles: list[Particle] = []
        self.texts: list[FloatingText] = []
        self.corpses: list[Corpse] = []
        self.impacts: list[list[float]] = []  # [x, y, life, max_life, size] star flashes
        self.waves: list[dict] = []  # special-ability shapes: expanding rings, flying arrows, dizzy stars
        self.shake = 0.0
        self.load_fonts()
        self._rng = random.Random()

    def load_fonts(self) -> None:
        """Pick fonts for floating text that can draw the active language (Avenir has no Hebrew)."""
        family = "arial,lucidagrande" if i18n.is_rtl() else "avenirnext,avenir,helveticaneue,arial"
        self.font = pygame.font.SysFont(family, 24, bold=True)
        self.font_crit = pygame.font.SysFont(family, 34, bold=True)

    def resize(self, size: tuple[int, int]) -> None:
        """Match the decal layer to a new level's size (clears all effects)."""
        self.decals = pygame.Surface(size, pygame.SRCALPHA)
        self.reset()

    def reset(self) -> None:
        """Clear all effects, e.g. when a new level starts."""
        self.decals.fill((0, 0, 0, 0))
        self.particles.clear()
        self.texts.clear()
        self.corpses.clear()
        self.impacts.clear()
        self.waves.clear()
        self.shake = 0.0

    def add_shake(self, amount: float) -> None:
        """Kick the camera; repeated hits stack up to a cap."""
        self.shake = min(12.0, self.shake + amount)

    def shake_offset(self) -> tuple[int, int]:
        """Return this frame's camera offset."""
        if self.shake < 0.5:
            return (0, 0)
        return (round(self._rng.uniform(-1, 1) * self.shake), round(self._rng.uniform(-1, 1) * self.shake))

    def spawn_hit(
        self,
        x: float,
        y: float,
        direction: tuple[float, float] | None,
        damage: int,
        blood: tuple[int, int, int],
        sparks: tuple[int, int, int] | None,
        text_color: tuple[int, int, int],
        crit: bool = False,
    ) -> None:
        """Burst sparks (unless None) and blood at an impact point and show the damage dealt; crits hit bigger."""
        rng = self._rng
        dx, dy = direction if direction else (0.0, -1.0)
        length = math.hypot(dx, dy) or 1.0
        base_angle = math.atan2(dy / length, dx / length)

        for _ in range((24 if crit else 10) if sparks else 0):
            angle = base_angle + rng.uniform(-0.9, 0.9)
            speed = rng.uniform(160, 360)
            life = rng.uniform(0.12, 0.28)
            self.particles.append(Particle(x, y, math.cos(angle) * speed, math.sin(angle) * speed, life, life, sparks, rng.uniform(1.5, 2.8), drag=5.0))

        for _ in range(8):
            angle = base_angle + rng.uniform(-1.2, 1.2)
            speed = rng.uniform(60, 170)
            life = 1.2
            self.particles.append(
                Particle(
                    x, y,
                    math.cos(angle) * speed, math.sin(angle) * speed - 140,
                    life, life, blood, rng.uniform(1.8, 3.4),
                    gravity=640, ground_y=y + rng.uniform(16, 36),
                )
            )

        self.impacts.append([x, y, 0.12, 0.12, 30.0 if crit else 20.0])
        if crit:
            self._add_text(i18n.visual(i18n.t("crit", n=damage)), x + rng.uniform(-8, 8), y - 44, text_color, self.font_crit, 1.1)
        else:
            self._add_text(str(damage), x + rng.uniform(-8, 8), y - 36, text_color)

    def spawn_death(
        self, canvas: pygame.Surface, x: float, feet_y: float, face_sign: int, blood: tuple[int, int, int],
        rotate: float = 90.0, lift: float | None = None,
    ) -> None:
        """Topple a defeated actor and leave a pool of blood."""
        body = canvas.copy()
        body.fill((150, 150, 150), special_flags=pygame.BLEND_RGB_MULT)
        self.corpses.append(Corpse(body, x, feet_y, face_sign, rotate=rotate, lift=lift))
        self._stamp(x - face_sign * 22, feet_y - 4, 46, 16, blood, 170)

        rng = self._rng
        for _ in range(10):
            angle = rng.uniform(math.pi, 2 * math.pi)
            speed = rng.uniform(30, 90)
            life = rng.uniform(0.5, 0.9)
            self.particles.append(
                Particle(x, feet_y - 2, math.cos(angle) * speed, math.sin(angle) * speed * 0.3, life, life, (120, 108, 96), rng.uniform(3, 6), drag=3.0, alpha=90)
            )

    def spawn_dust(self, x: float, y: float) -> None:
        """Kick up a little dust at a footstep."""
        rng = self._rng
        life = rng.uniform(0.35, 0.55)
        self.particles.append(Particle(x + rng.uniform(-6, 6), y, rng.uniform(-18, 18), rng.uniform(-22, -8), life, life, (130, 118, 104), rng.uniform(2.5, 4.5), drag=3.0, alpha=80))

    def spawn_ember(self, x: float, y: float) -> None:
        """Release a glowing ember that drifts up from a fire."""
        rng = self._rng
        life = rng.uniform(0.8, 1.7)
        self.particles.append(Particle(x + rng.uniform(-6, 6), y, rng.uniform(-14, 14), rng.uniform(-80, -40), life, life, (255, 168, 60), rng.uniform(1.2, 2.0)))

    def update(self, dt: float) -> None:
        """Advance every effect by dt seconds."""
        self.shake = max(0.0, self.shake - dt * 32)

        alive: list[Particle] = []
        for p in self.particles:
            p.life -= dt
            if p.life <= 0:
                continue
            damping = max(0.0, 1 - p.drag * dt)
            p.vx *= damping
            p.vy = p.vy * damping + p.gravity * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            if p.ground_y is not None and p.vy > 0 and p.y >= p.ground_y:
                self._stamp(p.x, p.ground_y, p.size * 2.4, p.size * 1.3, p.color, 190)
                continue
            alive.append(p)
        self.particles = alive

        for text in self.texts:
            text.life -= dt
            text.y -= 38 * dt
        self.texts = [text for text in self.texts if text.life > 0]

        for impact in self.impacts:
            impact[2] -= dt
        self.impacts = [impact for impact in self.impacts if impact[2] > 0]

        for wave in self.waves:
            wave["life"] -= dt
        self.waves = [wave for wave in self.waves if wave["life"] > 0]

        for corpse in self.corpses:
            corpse.age += dt
        self.corpses = [corpse for corpse in self.corpses if corpse.age < self.CORPSE_LIFETIME]

    def draw_ground(self, surface: pygame.Surface) -> None:
        """Draw floor-level effects: blood decals and fallen bodies."""
        surface.blit(self.decals, (0, 0))
        for corpse in self.corpses:
            fall = min(1.0, corpse.age / self.FALL_TIME)
            image = pygame.transform.rotate(corpse.canvas, corpse.rotate * fall * corpse.face_sign) if corpse.rotate else corpse.canvas
            fade_start = 1.4
            if corpse.age > fade_start:
                image = art.faded(image, 255 * max(0.0, 1 - (corpse.age - fade_start) / (self.CORPSE_LIFETIME - fade_start)))
            size = corpse.canvas.get_height() / art.CANVAS_SIZE[1]  # bodies are drawn scaled up
            if corpse.lift is not None:
                center = (corpse.x, corpse.feet_y - corpse.lift)
            else:
                center = (corpse.x - corpse.face_sign * 30 * fall * size, corpse.feet_y - (44 - 38 * fall) * size)
            surface.blit(image, image.get_rect(center=(round(center[0]), round(center[1]))))

    def draw_air(self, surface: pygame.Surface) -> None:
        """Draw airborne effects: particles and damage numbers."""
        for p in self.particles:
            k = p.life / p.max_life
            radius = max(1.0, p.size * (0.5 + 0.5 * k))
            if p.alpha < 255:
                dot = pygame.Surface((int(radius * 2) + 2, int(radius * 2) + 2), pygame.SRCALPHA)
                pygame.draw.circle(dot, (*p.color, int(p.alpha * k)), dot.get_rect().center, radius)
                surface.blit(dot, dot.get_rect(center=(round(p.x), round(p.y))))
            else:
                pygame.draw.circle(surface, p.color, (p.x, p.y), radius)

        for x, y, life, max_life, size in self.impacts:
            self._draw_impact(surface, x, y, 1 - life / max_life, size)

        for wave in self.waves:
            self._draw_wave(surface, wave, 1 - wave["life"] / wave["max_life"])

        for text in self.texts:
            age = text.max_life - text.life
            image = text.surface
            if age < 0.12:
                scale = 1.5 - 0.5 * (age / 0.12)
                w, h = image.get_size()
                image = pygame.transform.smoothscale(image, (round(w * scale), round(h * scale)))
            fade = min(1.0, text.life / (text.max_life * 0.4))
            if fade < 1.0:
                image = art.faded(image, 255 * fade)
            surface.blit(image, image.get_rect(center=(round(text.x), round(text.y))))

    # ------------------------------------------------------------------
    # Special abilities
    # ------------------------------------------------------------------

    def spawn_special(self, kind: str, data: dict) -> None:
        """Show a hero's special ability: kind and data come from Player.special_events."""
        x, y = data["x"], data["y"]
        rng = self._rng
        if kind == "charge":
            self.add_shake(5)
            for _ in range(14):
                life = rng.uniform(0.3, 0.5)
                self.particles.append(Particle(x + rng.uniform(-10, 10), y - 2, -data["face"] * rng.uniform(40, 140), rng.uniform(-50, -10), life, life, (150, 136, 118), rng.uniform(3, 6), drag=3.0, alpha=110))
        elif kind == "arrow":
            self._add_wave("arrow", x, y - 62, 0.32, face=data["face"], reach=data["reach"])
        elif kind == "smoke":
            for _ in range(18):
                angle = rng.uniform(0, 2 * math.pi)
                speed = rng.uniform(30, 110)
                life = rng.uniform(0.35, 0.6)
                self.particles.append(Particle(x + rng.uniform(-14, 14), y - rng.uniform(10, 70), math.cos(angle) * speed, math.sin(angle) * speed - 30, life, life, (70, 52, 90), rng.uniform(5, 9), drag=4.0, alpha=150))
        elif kind == "holy":
            self._add_wave("ring", x, y, 0.45, reach=data["reach"], color=(255, 226, 130), width=6)
            self._add_wave("pillar", x, y, 0.5)
            for _ in range(22):
                life = rng.uniform(0.5, 0.9)
                self.particles.append(Particle(x + rng.uniform(-30, 30), y - rng.uniform(0, 90), rng.uniform(-10, 10), rng.uniform(-120, -50), life, life, (255, 236, 160), rng.uniform(1.5, 3)))
            if data.get("healed"):
                self._add_text(f"+{data['healed']}", x, y - 120, (130, 235, 140), self.font_crit, 1.0)
        elif kind == "roar":
            self.add_shake(6)
            for delay in (0.0, 0.12, 0.24):
                self._add_wave("ring", x, y - 58, 0.5 + delay, reach=data["reach"], color=(240, 90, 60), width=4, delay=delay)
        elif kind == "dazed":
            self._add_wave("dazed", x, y - 16, data["life"])
        elif kind == "grave":  # a ghoul claws its way out of the floor
            self._add_wave("ring", x, y, 0.5, reach=60, color=(110, 220, 160), width=4)
            for _ in range(16):
                life = rng.uniform(0.4, 0.8)
                self.particles.append(Particle(x + rng.uniform(-20, 20), y - rng.uniform(0, 10), rng.uniform(-40, 40), rng.uniform(-140, -60), life, life, (96, 84, 70), rng.uniform(2, 4), gravity=500, ground_y=y + 4))
                self.particles.append(Particle(x + rng.uniform(-14, 14), y - rng.uniform(0, 50), 0, rng.uniform(-60, -20), life, life, (120, 230, 170), rng.uniform(1.5, 2.5), alpha=150))
        elif kind == "text":  # a reward announcement rising over the hero
            self._add_text(data["text"], x, y - 110, data.get("color", (255, 230, 140)), self.font_crit, 1.4)
        elif kind == "embers":  # the demon smoulders: sparks drift off him
            for _ in range(data.get("count", 2)):
                self.spawn_ember(x + rng.uniform(-30, 30), y - rng.uniform(20, 120))
        elif kind == "summon":  # imps burst from a summoning circle
            self._add_wave("ring", x, y, 0.5, reach=70, color=(200, 90, 255), width=5)
            self._add_wave("pillar", x, y, 0.45, color=(190, 80, 255))
            for _ in range(20):
                angle = rng.uniform(0, 2 * math.pi)
                life = rng.uniform(0.4, 0.8)
                self.particles.append(Particle(x, y - 20, math.cos(angle) * rng.uniform(60, 180), math.sin(angle) * 60 - 90, life, life, rng.choice(((210, 120, 255), (255, 150, 60))), rng.uniform(1.5, 3), drag=2.5))
        elif kind == "burst":  # a fireball bursting on impact (smaller than a pillar)
            self._add_wave("ring", x, y, 0.3, reach=36, color=(255, 150, 60), width=4)
            for _ in range(14):
                angle = rng.uniform(0, 2 * math.pi)
                life = rng.uniform(0.2, 0.45)
                self.particles.append(Particle(x, y, math.cos(angle) * rng.uniform(80, 220), math.sin(angle) * rng.uniform(80, 220), life, life, rng.choice(((255, 200, 80), (255, 120, 40))), rng.uniform(1.5, 3.5), drag=4))
        elif kind == "fire":  # a fire pillar erupts
            self.add_shake(4)
            self._add_wave("pillar", x, y, 0.55, color=(255, 120, 40))
            self._add_wave("ring", x, y, 0.4, reach=60, color=(255, 150, 60), width=5)
            for _ in range(26):
                life = rng.uniform(0.35, 0.8)
                color = rng.choice(((255, 200, 80), (255, 130, 40), (220, 70, 30)))
                self.particles.append(Particle(x + rng.uniform(-18, 18), y - rng.uniform(0, 30), rng.uniform(-30, 30), rng.uniform(-320, -140), life, life, color, rng.uniform(2, 4.5), drag=1.5))
        elif kind == "quake":
            self.add_shake(12)
            self._add_wave("ring", x, y, 0.5, reach=data["reach"], color=(170, 140, 100), width=8)
            self._add_wave("ring", x, y, 0.65, reach=data["reach"] * 0.7, color=(120, 100, 76), width=5, delay=0.1)
            for _ in range(30):
                angle = rng.uniform(0, 2 * math.pi)
                dist = rng.uniform(10, data["reach"])
                life = rng.uniform(0.4, 0.8)
                self.particles.append(
                    Particle(x + math.cos(angle) * dist, y + math.sin(angle) * dist * 0.3, 0, rng.uniform(-160, -60), life, life, (110, 96, 80), rng.uniform(2, 4), gravity=520, ground_y=None)
                )

    def _add_wave(self, kind: str, x: float, y: float, life: float, **data: object) -> None:
        self.waves.append({"kind": kind, "x": x, "y": y, "life": life, "max_life": life, **data})

    def _draw_wave(self, surface: pygame.Surface, wave: dict, progress: float) -> None:
        kind, x, y = wave["kind"], wave["x"], wave["y"]
        delay = wave.get("delay", 0.0) / wave["max_life"]
        if progress < delay:
            return
        progress = (progress - delay) / max(0.01, 1 - delay)
        if kind == "ring":
            # A ground-level shockwave: an ellipse (the floor is seen at an angle) that grows and fades.
            radius = wave["reach"] * (0.15 + 0.85 * (1 - (1 - progress) ** 2))
            rect = pygame.Rect(0, 0, radius * 2, radius * 0.6)
            rect.center = (round(x), round(y))
            layer = pygame.Surface((rect.width + 16, rect.height + 16), pygame.SRCALPHA)
            alpha = int(220 * (1 - progress))
            pygame.draw.ellipse(layer, (*wave["color"], alpha), layer.get_rect().inflate(-16, -16), max(1, round(wave["width"] * (1 - progress * 0.6))))
            surface.blit(layer, layer.get_rect(center=rect.center))
        elif kind == "pillar":
            height, width = 180, round(46 * (1 - progress) + 6)
            layer = pygame.Surface((width, height), pygame.SRCALPHA)
            r, g, b = wave.get("color", (255, 230, 140))
            layer.blit(art.vertical_gradient(width, height, (r, g, b, 0), (r, g, b, int(170 * (1 - progress)))), (0, 0))
            surface.blit(layer, (round(x - width / 2), round(y - height)), special_flags=pygame.BLEND_RGBA_ADD)
        elif kind == "arrow":
            face, reach = wave["face"], wave["reach"]
            head = x + face * reach * min(1.0, progress / 0.55)  # the arrow crosses the screen in a blink
            tail = x + face * 30
            alpha = int(255 * (1 - max(0.0, progress - 0.55) / 0.45))
            streak = pygame.Surface((abs(head - tail) + 20, 14), pygame.SRCALPHA)
            sx = 10 if face > 0 else streak.get_width() - 10
            ex = streak.get_width() - 10 if face > 0 else 10
            pygame.draw.line(streak, (255, 236, 190, alpha // 3), (sx, 7), (ex, 7), 6)
            pygame.draw.line(streak, (255, 250, 230, alpha), (sx, 7), (ex, 7), 2)
            surface.blit(streak, (round(min(head, tail) - 10), round(y - 7)))
            if progress < 0.6:
                # The arrow itself: shaft, head, and fletching.
                pygame.draw.line(surface, (120, 84, 50), (head - face * 30, y), (head, y), 3)
                pygame.draw.polygon(surface, (220, 226, 236), [(head + face * 10, y), (head - face * 2, y - 5), (head - face * 2, y + 5)])
                pygame.draw.polygon(surface, (60, 130, 80), [(head - face * 30, y), (head - face * 38, y - 6), (head - face * 34, y)])
                pygame.draw.polygon(surface, (60, 130, 80), [(head - face * 30, y), (head - face * 38, y + 6), (head - face * 34, y)])
        elif kind == "dazed":
            # Little stars circling a stunned foe's head.
            spin = progress * wave["max_life"] * 7
            for i in range(3):
                angle = spin + i * 2 * math.pi / 3
                sx, sy = x + math.cos(angle) * 16, y + math.sin(angle) * 5
                pygame.draw.circle(surface, (255, 230, 120), (sx, sy), 3)
                pygame.draw.circle(surface, (255, 255, 230), (sx, sy), 1)

    @staticmethod
    def _draw_impact(surface: pygame.Surface, x: float, y: float, progress: float, size: float) -> None:
        """An 8-point arcade hit star that bursts open and fades."""
        radius = size * (0.6 + 0.6 * progress)
        layer = pygame.Surface((int(radius * 2) + 4, int(radius * 2) + 4), pygame.SRCALPHA)
        cx = cy = radius + 2
        points = []
        for i in range(16):
            angle = math.pi * i / 8 + 0.2
            r = radius if i % 2 == 0 else radius * 0.38
            points.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
        alpha = int(255 * (1 - progress))
        pygame.draw.polygon(layer, (255, 236, 160, alpha), points)
        pygame.draw.circle(layer, (255, 255, 255, alpha), (cx, cy), radius * 0.3)
        surface.blit(layer, layer.get_rect(center=(round(x), round(y))))

    def _add_text(
        self,
        text: str,
        x: float,
        y: float,
        color: tuple[int, int, int],
        font: pygame.font.Font | None = None,
        life: float = 0.8,
    ) -> None:
        font = font or self.font
        face = font.render(text, True, color)
        outline = font.render(text, True, (24, 8, 6))
        w, h = face.get_size()
        image = pygame.Surface((w + 4, h + 4), pygame.SRCALPHA)
        for ox, oy in ((0, 2), (4, 2), (2, 0), (2, 4), (0, 0), (4, 4), (0, 4), (4, 0)):
            image.blit(outline, (ox, oy))
        image.blit(face, (2, 2))
        self.texts.append(FloatingText(x, y, image, life, life))

    def _stamp(self, x: float, y: float, w: float, h: float, color: tuple[int, int, int], alpha: int) -> None:
        stain = pygame.Surface((max(2, int(w)), max(2, int(h))), pygame.SRCALPHA)
        pygame.draw.ellipse(stain, (*art.shade(color, 0.75), alpha), stain.get_rect())
        self.decals.blit(stain, stain.get_rect(center=(round(x), round(y))))
