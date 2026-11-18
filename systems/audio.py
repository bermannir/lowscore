"""
Module: audio
Purpose: Procedurally synthesized sound effects and the master volume / mute control.
Dependencies: pygame (mixer)
Used by: Player, Enemy, Game, and Renderer to give every move audible feedback.

No audio files are needed for effects: each one is built from filtered noise and
sine partials at startup. Music is streamed from assets/music (see its README).
If the mixer can't open (no audio device), every call is a silent no-op so the
game still runs.
"""

from __future__ import annotations

import math
import random
from array import array
from pathlib import Path
from typing import Callable

import pygame

RATE = 22050  # sample rate the effects are synthesized at
MIXER_RATE = 44100  # the mixer runs at CD quality in stereo so the music sounds right
MIXER_CHANNELS = 2
VOLUME_LEVELS = (0.25, 0.5, 0.75, 1.0)
DEFAULT_VOLUME_INDEX = 2
MUSIC_LEVELS = (0.0, 0.25, 0.5, 0.75, 1.0)
MUSIC_DIR = Path(__file__).resolve().parent.parent / "assets" / "music"
MUSIC_EXTENSIONS = (".ogg", ".mp3", ".wav")
# Music files are matched by how their names start (case-insensitive):
#   "modal drift..." plays on menus, hero select, story, and the level-complete / victory / game-over screens;
#   "war..." tracks play in battle: level 1 gets the first, level 2 the second, ... (wrapping around),
#   and the boss fight gets the last one.
MUSIC_GROUPS = {"menu": ("modal drift",), "level": ("war",), "boss": ("war",)}
VARIANTS = 3  # versions of each sound so repeats don't sound robotic

Samples = list[float]


# --------------------------------------------------------------------------
# Synthesis building blocks
# --------------------------------------------------------------------------


def _n(duration: float) -> int:
    return max(1, int(RATE * duration))


def _whoosh(rng: random.Random, duration: float, cut_lo: float, cut_hi: float, pulses: int = 0) -> Samples:
    """Band-swept noise: the air of a blade or a body moving fast."""
    n = _n(duration)
    out: Samples = []
    y1 = y2 = 0.0
    for i in range(n):
        p = i / n
        shape = math.sin(math.pi * p)
        a = cut_lo + (cut_hi - cut_lo) * shape
        y1 += a * (rng.uniform(-1, 1) - y1)
        y2 += a * (y1 - y2)
        env = shape ** 1.5
        if pulses:
            env *= 0.55 + 0.45 * math.cos(2 * math.pi * pulses * p)
        out.append(y2 * env)
    return out


def _noise_burst(rng: random.Random, duration: float, decay: float, cut: float) -> Samples:
    """A short, decaying, low-passed noise hit: the 'thwack' of contact."""
    out: Samples = []
    y = 0.0
    for i in range(_n(duration)):
        t = i / RATE
        y += cut * (rng.uniform(-1, 1) - y)
        out.append(y * math.exp(-t * decay))
    return out


def _ring(duration: float, partials: list[tuple[float, float]], decay: float) -> Samples:
    """Decaying sine partials: metal clangs, chimes, and glints."""
    out: Samples = []
    for i in range(_n(duration)):
        t = i / RATE
        value = sum(amp * math.sin(2 * math.pi * freq * t) for freq, amp in partials)
        out.append(value * math.exp(-t * decay))
    return out


def _sweep(duration: float, f0: float, f1: float, harmonics: int = 1, envelope: Callable[[float], float] | None = None) -> Samples:
    """A pitch glide with optional overtones (growls, roars, falling groans)."""
    out: Samples = []
    phase = 0.0
    n = _n(duration)
    for i in range(n):
        p = i / n
        phase += 2 * math.pi * (f0 + (f1 - f0) * p) / RATE
        value = sum(math.sin(phase * h) / h for h in range(1, harmonics + 1))
        out.append(value * (envelope(p) if envelope else 1 - p))
    return out


def _notes(notes: list[tuple[float, float, float]], tail: float = 0.4) -> Samples:
    """Plucked bell notes as (start seconds, frequency, amplitude)."""
    total = max(start for start, _, _ in notes) + tail
    out = [0.0] * _n(total)
    for start, freq, amp in notes:
        offset = _n(start)
        for i, value in enumerate(_ring(tail, [(freq, amp), (freq * 2, amp * 0.3), (freq * 3, amp * 0.12)], 7.0)):
            if offset + i < len(out):
                out[offset + i] += value
    return out


def _mix(*tracks: tuple[Samples, float, float]) -> Samples:
    """Layer tracks given as (samples, start seconds, gain)."""
    length = max(_n(start) + len(samples) for samples, start, _ in tracks)
    out = [0.0] * length
    for samples, start, gain in tracks:
        offset = _n(start)
        for i, value in enumerate(samples):
            out[offset + i] += value * gain
    return out


def _to_sound(samples: Samples, peak: float) -> pygame.mixer.Sound:
    """Normalize, fade the edges to avoid clicks, and wrap as a pygame Sound."""
    loudest = max(1e-6, max(abs(v) for v in samples))
    fade = min(len(samples) // 4, _n(0.004))
    count = len(samples)
    levels = []
    for i, value in enumerate(samples):
        edge = 1.0
        if i < fade:
            edge = i / fade
        elif i >= count - fade:
            edge = (count - i) / fade
        levels.append(max(-1.0, min(1.0, value / loudest * peak * edge)) * 32767)

    # The effects are made at RATE in mono; convert them to the mixer's own rate and
    # channel count (linear interpolation), or they would play at the wrong speed and pitch.
    mixer_rate, _, channels = pygame.mixer.get_init() or (RATE, -16, 1)
    if mixer_rate != RATE:
        step = RATE / mixer_rate
        last = count - 1
        resampled = []
        for j in range(int(count / step)):
            position = j * step
            i = int(position)
            if i >= last:
                resampled.append(levels[last])
            else:
                frac = position - i
                resampled.append(levels[i] + (levels[i + 1] - levels[i]) * frac)
        levels = resampled
    data = array("h", [int(v) for v in levels for _ in range(channels)])
    return pygame.mixer.Sound(buffer=data.tobytes())


# --------------------------------------------------------------------------
# Sound recipes
# --------------------------------------------------------------------------


def _recipes(rng: random.Random) -> dict[str, tuple[Samples, float]]:
    """Build one variant of every effect as (samples, peak loudness)."""
    pitch = rng.uniform(0.92, 1.08)

    def hit_core() -> Samples:
        return _mix(
            (_noise_burst(rng, 0.12, 45, 0.35), 0, 1.0),
            (_sweep(0.12, 140 * pitch, 70 * pitch, envelope=lambda p: math.exp(-p * 5)), 0, 0.9),
        )

    return {
        "slash": (_whoosh(rng, 0.18 * pitch, 0.06, 0.5), 0.55),
        "heavy": (_mix((_whoosh(rng, 0.34 * pitch, 0.03, 0.28), 0, 1.0), (_sweep(0.2, 90, 50, 2, lambda p: math.sin(math.pi * p)), 0.12, 0.5)), 0.7),
        "spin": (_whoosh(rng, 0.42 * pitch, 0.05, 0.4, pulses=3), 0.6),
        "strafe": (_whoosh(rng, 0.13, 0.25, 0.75), 0.35),
        "hit": (hit_core(), 0.7),
        "crit": (_mix((hit_core(), 0, 1.0), (_ring(0.45, [(1800 * pitch, 0.5), (2710 * pitch, 0.35), (4130 * pitch, 0.2)], 9), 0.01, 0.7)), 0.85),
        "block": (_mix((_noise_burst(rng, 0.03, 120, 0.8), 0, 0.6), (_ring(0.4, [(880 * pitch, 0.5), (1347 * pitch, 0.4), (2093 * pitch, 0.25)], 12), 0, 1.0)), 0.6),
        "hurt": (_mix((_noise_burst(rng, 0.1, 35, 0.25), 0, 0.8), (_sweep(0.24, 230 * pitch, 110 * pitch, 3, lambda p: math.exp(-p * 4)), 0, 0.8)), 0.7),
        "death": (_mix((_noise_burst(rng, 0.2, 18, 0.15), 0, 1.0), (_sweep(0.55, 160 * pitch, 55 * pitch, 3, lambda p: (1 - p) ** 1.5), 0.03, 0.9)), 0.7),
        "shield": (_notes([(0.0, 660, 0.6), (0.06, 880, 0.5), (0.12, 1320, 0.4)], tail=0.4), 0.45),
        "fury": (_mix((_sweep(0.9, 80, 230, 5, lambda p: math.sin(math.pi * min(1, p * 1.3)) ** 0.7), 0, 1.0), (_whoosh(rng, 0.9, 0.02, 0.2), 0, 1.6)), 0.75),
        "boss_fury": (_mix((_sweep(1.0, 55, 140, 6, lambda p: math.sin(math.pi * min(1, p * 1.2)) ** 0.7), 0, 1.0), (_whoosh(rng, 1.0, 0.02, 0.15), 0, 1.8)), 0.8),
        "jump": (_whoosh(rng, 0.16, 0.1, 0.4), 0.4),
        "land": (_mix((_noise_burst(rng, 0.08, 50, 0.2), 0, 1.0), (_sweep(0.08, 110, 60, envelope=lambda p: 1 - p), 0, 0.7)), 0.45),
        "knockdown": (_mix((_noise_burst(rng, 0.25, 22, 0.12), 0, 1.0), (_sweep(0.22, 95 * pitch, 40 * pitch, 2, lambda p: (1 - p) ** 2), 0, 1.0)), 0.8),
        "throw": (_mix((_whoosh(rng, 0.36, 0.04, 0.3), 0, 1.0), (_sweep(0.2, 260 * pitch, 150 * pitch, 3, lambda p: math.sin(math.pi * p)), 0.02, 0.5)), 0.7),
        "pickup": (_notes([(0.0, 1047, 0.5), (0.05, 1319, 0.5), (0.1, 1568, 0.5), (0.15, 2093, 0.6)], tail=0.3), 0.45),
        "windup": (_ring(0.2, [(3100 * pitch, 0.5), (4650 * pitch, 0.3)], 18), 0.25),
        "ui_move": (_ring(0.05, [(1250, 1.0)], 60), 0.3),
        "ui_confirm": (_notes([(0.0, 660, 0.6), (0.07, 990, 0.6)], tail=0.18), 0.45),
        "ui_tick": (_ring(0.03, [(1700, 1.0)], 90), 0.18),
        "level_complete": (_notes([(0.0, 523, 0.6), (0.12, 659, 0.6), (0.24, 784, 0.6), (0.36, 1047, 0.7)], tail=0.6), 0.55),
        "victory": (_notes([(0.0, 523, 0.6), (0.15, 659, 0.6), (0.3, 784, 0.6), (0.5, 1047, 0.8), (0.7, 784, 0.5), (0.85, 1047, 0.9)], tail=0.9), 0.6),
        "game_over": (_notes([(0.0, 392, 0.7), (0.25, 349, 0.7), (0.5, 311, 0.7), (0.8, 196, 0.9)], tail=0.9), 0.55),
    }


# --------------------------------------------------------------------------
# Player-facing API
# --------------------------------------------------------------------------


class Audio:
    """Holds the synthesized sounds and the master volume / mute state."""

    def __init__(self) -> None:
        self.enabled = False
        self.muted = False
        self.volume_index = DEFAULT_VOLUME_INDEX
        self._sounds: dict[str, list[pygame.mixer.Sound]] = {}
        self._rng = random.Random()
        self.changed_at = -10.0  # seconds; drives the on-screen volume toast
        self.music_level = 3
        self._track: str | None = None

    @property
    def volume(self) -> float:
        """Effective master volume (0 when muted)."""
        return 0.0 if self.muted else VOLUME_LEVELS[self.volume_index]

    def init(self) -> None:
        """Open the mixer and synthesize every effect. Call before pygame.init()."""
        if self.enabled:
            return
        try:
            pygame.mixer.pre_init(MIXER_RATE, -16, MIXER_CHANNELS, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(32)
        except pygame.error:
            return

        for seed in range(VARIANTS):
            for name, (samples, peak) in _recipes(random.Random(seed * 7919 + 13)).items():
                self._sounds.setdefault(name, []).append(_to_sound(samples, peak))
        self.enabled = True

    def play(self, name: str, volume: float = 1.0) -> None:
        """Play a named effect at a relative volume (scaled by the master volume)."""
        if not self.enabled or self.volume <= 0:
            return
        variants = self._sounds.get(name)
        if not variants:
            return
        channel = self._rng.choice(variants).play()
        if channel is not None:
            channel.set_volume(max(0.0, min(1.0, volume * self.volume)))

    @property
    def sfx_level(self) -> int:
        """Effects volume as a settings step: 0 off, 1..4 = 25%..100%."""
        return 0 if self.muted else self.volume_index + 1

    def set_sfx_level(self, level: int) -> None:
        """Set the effects volume from a settings step (0 mutes)."""
        self.muted = level <= 0
        if level > 0:
            self.volume_index = max(0, min(len(VOLUME_LEVELS) - 1, level - 1))
        if self.muted and self.enabled:
            pygame.mixer.stop()

    def set_music_level(self, level: int) -> None:
        """Set the music volume from a settings step (0 silences it)."""
        self.music_level = max(0, min(len(MUSIC_LEVELS) - 1, level))
        if self.enabled:
            pygame.mixer.music.set_volume(MUSIC_LEVELS[self.music_level])

    def has_music(self) -> bool:
        """Return True if any music file has been added to assets/music."""
        return MUSIC_DIR.is_dir() and any(path.suffix.lower() in MUSIC_EXTENSIONS for path in MUSIC_DIR.iterdir())

    def play_music(self, track: str) -> None:
        """
        Loop the music for a part of the game (see assets/music/README.md).

        Looks for <track>.ogg/.mp3/.wav, then the track name without its number
        (level3 -> level), then default.*. Plays nothing if no file matches.
        """
        if not self.enabled or track == self._track:
            return
        self._track = track
        path = self._find_track(track)
        if path is None:
            pygame.mixer.music.fadeout(400)
            return
        try:
            pygame.mixer.music.load(str(path))
            pygame.mixer.music.set_volume(MUSIC_LEVELS[self.music_level])
            pygame.mixer.music.play(-1, fade_ms=800)
        except pygame.error:
            pass

    @staticmethod
    def _find_track(track: str) -> Path | None:
        """
        The file for a track: an exact name first (menu.ogg, level3.wav, boss.mp3, ...),
        then a file from its MUSIC_GROUPS family ("modal drift..." / "war..."), then default.*.
        """
        if not MUSIC_DIR.is_dir():
            return None
        generic = track.rstrip("0123456789")
        for name in dict.fromkeys((track, generic)):
            for extension in MUSIC_EXTENSIONS:
                candidate = MUSIC_DIR / f"{name}{extension}"
                if candidate.is_file():
                    return candidate

        family = _music_family(MUSIC_GROUPS.get(generic, ()))
        if family:
            if generic == "boss":
                return family[-1]
            number = track[len(generic):]
            return family[(int(number) - 1 if number else 0) % len(family)]

        for extension in MUSIC_EXTENSIONS:
            candidate = MUSIC_DIR / f"default{extension}"
            if candidate.is_file():
                return candidate
        return None

    def toggle_mute(self) -> None:
        """Mute or unmute all effects."""
        self.muted = not self.muted
        self.changed_at = pygame.time.get_ticks() / 1000.0
        if self.muted and self.enabled:
            pygame.mixer.stop()

    def change_volume(self, step: int) -> None:
        """Step the master volume up or down (also unmutes)."""
        self.muted = False
        self.volume_index = max(0, min(len(VOLUME_LEVELS) - 1, self.volume_index + step))
        self.changed_at = pygame.time.get_ticks() / 1000.0
        self.play("ui_tick")


def _music_family(prefixes: tuple[str, ...]) -> list[Path]:
    """
    Music files whose names start with one of the prefixes, in name order.

    Exact copies (same size and same opening bytes, e.g. "song.wav" and "song (1).wav")
    are counted once, so a duplicated file doesn't play twice in a row.
    """
    if not prefixes:
        return []
    files = sorted(
        path for path in MUSIC_DIR.iterdir()
        if path.suffix.lower() in MUSIC_EXTENSIONS and path.name.lower().startswith(prefixes)
    )
    unique: list[Path] = []
    seen: set[tuple[int, bytes]] = set()
    for path in files:
        try:
            with path.open("rb") as handle:
                key = (path.stat().st_size, handle.read(1 << 16))
        except OSError:
            continue
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


audio = Audio()
