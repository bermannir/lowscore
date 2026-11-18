"""
Module: settings
Purpose: Player options (language, volumes) saved between runs in settings.json.
Dependencies: None
Used by: core.game (settings menu) and its apply/save steps.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

from core.i18n import LANGUAGES

SETTINGS_PATH = Path(__file__).resolve().parent.parent / "settings.json"

VOLUME_STEPS = 5  # Off, 25%, 50%, 75%, 100%


@dataclass
class Settings:
    """
    The options shown in the settings menu.

    Attributes:
        language: "en" or "he".
        sfx_level: Sound-effects volume step, 0 (off) .. 4 (100%).
        music_level: Music volume step, 0 (off) .. 4 (100%).
    """

    language: str = "en"
    sfx_level: int = 3
    music_level: int = 3

    @classmethod
    def load(cls) -> "Settings":
        """Read saved settings, falling back to defaults for anything missing or invalid."""
        try:
            data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(data, dict):
            return cls()
        settings = cls()
        if data.get("language") in LANGUAGES:
            settings.language = data["language"]
        settings.sfx_level = _clamped_int(data.get("sfx_level"), 0, VOLUME_STEPS - 1, settings.sfx_level)
        settings.music_level = _clamped_int(data.get("music_level"), 0, VOLUME_STEPS - 1, settings.music_level)
        return settings

    def save(self) -> None:
        """Write the settings to disk (silently skipped if the folder is read-only)."""
        try:
            SETTINGS_PATH.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass


def _clamped_int(value: object, low: int, high: int, default: int) -> int:
    """An int from saved data, clamped to [low, high]; default if it isn't a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    return max(low, min(high, int(value)))
