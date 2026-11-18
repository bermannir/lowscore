"""
Module: i18n
Purpose: UI translations (English / Hebrew) and right-to-left text layout for pygame.
Dependencies: None
Used by: core.game, core.story, ui.renderer, ui.effects.

pygame draws text strictly left to right, so Hebrew must be put into *visual*
order before rendering: visual() reverses the Hebrew runs while keeping numbers
and Latin words (key names like ENTER, values like 60% or 1/3) reading
left to right, the way a bidi-aware text engine would.
"""

from __future__ import annotations

import re

LANGUAGES = ("en", "he")
LANGUAGE_NAMES = {"en": "English", "he": "עברית"}

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "menu_start": "START GAME",
        "menu_settings": "SETTINGS",
        "menu_quit": "QUIT",
        "menu_hint": "UP / DOWN  choose     ENTER  select",
        "controls_hint": "Arrows move (2x tap strafe)   R combo   SPACE jump   E heavy   Q spin   W special   A shield   F fury   X ally   M sound",
        "level_complete": "LEVEL COMPLETE",
        "prompt_continue": "Press ENTER to continue",
        "prompt_continue_swap": "ENTER  continue     ·     C  change hero",
        "change_hero": "CHANGE HERO",
        "swap_select_hint": "LEFT / RIGHT  hero     ENTER  confirm     ESC  back",
        "swap_hint": "CHANGE HERO",
        "next_level": "Level {n} is waiting",
        "victory": "VICTORY",
        "prompt_epilogue": "Press ENTER for the epilogue",
        "all_cleared": "All levels cleared",
        "game_over": "GAME OVER",
        "prompt_retry": "Press ENTER to retry   ·   R to return home",
        "tip": "Keep moving, use shield before contact, then counterattack",
        "choose_hero": "CHOOSE YOUR HERO",
        "stat_health": "HEALTH",
        "stat_speed": "SPEED",
        "stat_power": "POWER",
        "select_hint": "LEFT / RIGHT  hero     UP / DOWN  difficulty     ENTER  confirm",
        "diff_easy": "EASY",
        "diff_medium": "MEDIUM",
        "diff_hard": "HARD",
        "diff_detail": "{dmg}% dmg  ·  +{regen} HP/s",
        "class_knight": "KNIGHT",
        "class_ranger": "RANGER",
        "class_rogue": "ROGUE",
        "class_paladin": "PALADIN",
        "class_barbarian": "BARBARIAN",
        "class_warlord": "WARLORD",
        "hero_ran": "Ran",
        "hero_florella": "Florella",
        "hero_nili": "Nili",
        "hero_gili": "Gili",
        "hero_snib": "Snib",
        "hero_hogipog": "Hogipog",
        "level_of": "LEVEL {n}  OF  {total}",
        "foes": "{n} FOES",
        "foe_one": "1 FOE",
        "wave": "WAVE {n}/{total}",
        "score": "SCORE  {n}",
        "hits": "HITS!",
        "go": "GO",
        "ready": "READY",
        "crit": "CRIT {n}!",
        "boss_name": "EMBER DEMON",
        "boss_title": "— BOSS —",
        "ally_label": "ALLY",
        "ally_active": "FIGHTING",
        "ally_call_earned": "ALLY CALL EARNED!  (X)",
        "ally_joins": "{name} JOINS THE FIGHT!",
        "rally_label": "RALLY",
        "rally_combo_label": "BEST COMBO",
        "rally_points_label": "POINTS",
        "rally_ready": "READY FOR THE NEXT BOSS",
        "rally_active": "ALL HEROES!",
        "rally_earned": "HEROES' RALLY EARNED!",
        "rally_title": "HEROES' RALLY!",
        "rally_sub": "Every hero fights beside you until this boss falls",
        "rally_showcase": "A gift for your first boss. Earn it again: a {combo}-hit combo and {points} points",
        "reward_elixir": "SPECIAL READY!",
        "reward_pelt": "+1 SHIELD",
        "midboss_title": "— MID-BOSS —",
        "enraged_tag": "ENRAGED",
        "midboss_grukk": "GRUKK THE OGRE",
        "midboss_gravewarden": "THE GRAVEWARDEN",
        "midboss_gorrak": "WARCHIEF GORRAK",
        "midboss_brannoc": "BRANNOC THE PYRE OGRE",
        "fury_tag": "FURY",
        "volume": "VOLUME {n}%",
        "sound_off": "SOUND OFF",
        "ctl_move": "MOVE",
        "ctl_strafe": "STRAFE",
        "ctl_combo": "COMBO",
        "ctl_jump": "JUMP",
        "ctl_heavy": "HEAVY",
        "ctl_spin": "SPIN",
        "ctl_shield": "SHIELD",
        "ctl_fury": "FURY",
        "ctl_special": "SPECIAL",
        "special_charge": "SHIELD CHARGE",
        "special_arrow": "PIERCING ARROW",
        "special_shadow_step": "SHADOW STEP",
        "special_holy_light": "HOLY LIGHT",
        "special_war_cry": "WAR CRY",
        "special_earthquake": "EARTHQUAKE",
        "special_desc_charge": "Charge forward behind your shield, knocking down every foe in the way",
        "special_desc_arrow": "Loose an arrow that pierces every foe in your lane",
        "special_desc_shadow_step": "Vanish and reappear behind the nearest foe for a critical backstab",
        "special_desc_holy_light": "Heal yourself and blast nearby foes off their feet",
        "special_desc_war_cry": "Stun the foes around you, then rage for extra damage",
        "special_desc_earthquake": "Slam the ground and knock down every foe nearby",
        "key_arrows": "ARROWS",
        "key_double": "2x TAP",
        "key_space": "SPACE",
        "story_next": "ENTER  >",
        "story_begin": "ENTER  begin",
        "story_finish": "ENTER  finish",
        "foe_1": "Goblin",
        "foe_2": "Ghoul",
        "foe_3": "Orc Chieftain",
        "foe_4": "Ember Demon",
        "settings_title": "SETTINGS",
        "set_language": "Language",
        "set_sfx": "Sound effects",
        "set_music": "Music",
        "set_back": "Back",
        "off": "Off",
        "settings_hint": "UP / DOWN  select     LEFT / RIGHT  change     ESC  back",
        "music_missing": "No music yet: add files to the assets/music folder",
        "paused": "PAUSED",
        "resume": "RESUME",
        "quit_title": "QUIT TO TITLE",
    },
    "he": {
        "menu_start": "התחל משחק",
        "menu_settings": "הגדרות",
        "menu_quit": "יציאה",
        "menu_hint": "למעלה / למטה  בחירה     ENTER  אישור",
        "controls_hint": "חצים: תנועה (הקשה כפולה: התחמקות)   R קומבו   SPACE קפיצה   E מכה כבדה   Q סחרור   W מיוחדת   A מגן   F זעם   X עזרה   M צליל",
        "level_complete": "השלב הושלם",
        "prompt_continue": "לחץ ENTER כדי להמשיך",
        "prompt_continue_swap": "ENTER  המשך     ·     C  החלפת גיבור",
        "change_hero": "החלפת גיבור",
        "swap_select_hint": "ימינה / שמאלה  גיבור     ENTER  אישור     ESC  חזרה",
        "swap_hint": "החלפת גיבור",
        "next_level": "שלב {n} מחכה",
        "victory": "ניצחון",
        "prompt_epilogue": "לחץ ENTER לאפילוג",
        "all_cleared": "כל השלבים הושלמו",
        "game_over": "המשחק נגמר",
        "prompt_retry": "ENTER לנסות שוב   ·   R לחזרה לתפריט",
        "tip": "המשך לזוז, הפעל מגן לפני המגע ואז תקוף בחזרה",
        "choose_hero": "בחר את הגיבור שלך",
        "stat_health": "חיים",
        "stat_speed": "מהירות",
        "stat_power": "כוח",
        "select_hint": "ימינה / שמאלה  גיבור     למעלה / למטה  רמת קושי     ENTER  אישור",
        "diff_easy": "קל",
        "diff_medium": "בינוני",
        "diff_hard": "קשה",
        "diff_detail": "{dmg}% נזק  ·  ריפוי +{regen}",
        "class_knight": "אביר",
        "class_ranger": "סיירת",
        "class_rogue": "נוכלת",
        "class_paladin": "פלדין",
        "class_barbarian": "ברברי",
        "class_warlord": "מצביא",
        "hero_ran": "רן",
        "hero_florella": "פלורלה",
        "hero_nili": "נילי",
        "hero_gili": "גילי",
        "hero_snib": "סניב",
        "hero_hogipog": "הוגיפוג",
        "level_of": "שלב {n}  מתוך  {total}",
        "foes": "{n} אויבים",
        "foe_one": "אויב 1",
        "wave": "גל {n}/{total}",
        "score": "ניקוד  {n}",
        "hits": "מכות!",
        "go": "קדימה",
        "ready": "מוכן",
        "crit": "קריטי {n}!",
        "boss_name": "שד הגחלים",
        "boss_title": "— בוס —",
        "ally_label": "עזרה",
        "ally_active": "נלחם",
        "ally_call_earned": "קריאה לעזרה הושגה!  (X)",
        "ally_joins": "{name} לצידך!",
        "rally_label": "התכנסות",
        "rally_combo_label": "הקומבו הטוב",
        "rally_points_label": "נקודות",
        "rally_ready": "מוכן לבוס הבא",
        "rally_active": "כל הגיבורים!",
        "rally_earned": "התכנסות הגיבורים הושגה!",
        "rally_title": "התכנסות הגיבורים!",
        "rally_sub": "כל הגיבורים נלחמים לצידך עד שהבוס ייפול",
        "rally_showcase": "מתנה לבוס הראשון. השג אותה שוב: קומבו של {combo} מכות ו-{points} נקודות",
        "reward_elixir": "מיוחדת מוכנה!",
        "reward_pelt": "+1 מגן",
        "midboss_title": "— בוס ביניים —",
        "enraged_tag": "משתולל",
        "midboss_grukk": "גרוק האוגר",
        "midboss_gravewarden": "שומר הקברים",
        "midboss_gorrak": "ראש המלחמה גוראק",
        "midboss_brannoc": "ברנוק, אוגר האש",
        "fury_tag": "זעם",
        "volume": "עוצמה {n}%",
        "sound_off": "צליל כבוי",
        "ctl_move": "תנועה",
        "ctl_strafe": "התחמקות",
        "ctl_combo": "קומבו",
        "ctl_jump": "קפיצה",
        "ctl_heavy": "כבדה",
        "ctl_spin": "סחרור",
        "ctl_shield": "מגן",
        "ctl_fury": "זעם",
        "ctl_special": "מיוחדת",
        "special_charge": "הסתערות מגן",
        "special_arrow": "חץ חודר",
        "special_shadow_step": "צעד צל",
        "special_holy_light": "אור קדוש",
        "special_war_cry": "קריאת קרב",
        "special_earthquake": "רעידת אדמה",
        "special_desc_charge": "הסתער קדימה מאחורי המגן והפל כל אויב בדרך",
        "special_desc_arrow": "ירי חץ שחודר דרך כל האויבים בנתיב שלך",
        "special_desc_shadow_step": "היעלמי והופיעי מאחורי האויב הקרוב לדקירה קריטית",
        "special_desc_holy_light": "רפא את עצמך והעף אויבים קרובים מהרגליים",
        "special_desc_war_cry": "הלם את האויבים סביבך ואז השתולל לנזק נוסף",
        "special_desc_earthquake": "הכה באדמה והפל כל אויב בסביבה",
        "key_arrows": "חצים",
        "key_double": "הקשה כפולה",
        "key_space": "רווח",
        "story_next": "ENTER  <",
        "story_begin": "ENTER  התחל",
        "story_finish": "ENTER  סיום",
        "foe_1": "גובלין",
        "foe_2": "גול",
        "foe_3": "ראש שבט האורקים",
        "foe_4": "שד הגחלים",
        "settings_title": "הגדרות",
        "set_language": "שפה",
        "set_sfx": "אפקטים קוליים",
        "set_music": "מוזיקה",
        "set_back": "חזרה",
        "off": "כבוי",
        "settings_hint": "למעלה / למטה  בחירה     ימינה / שמאלה  שינוי     ESC  חזרה",
        "music_missing": "אין עדיין מוזיקה: הוסף קבצים לתיקייה assets/music",
        "paused": "השהיה",
        "resume": "המשך",
        "quit_title": "חזרה לתפריט הראשי",
    },
}

_language = "en"


def set_language(code: str) -> None:
    """Switch the UI language ("en" or "he")."""
    global _language
    _language = code if code in LANGUAGES else "en"


def get_language() -> str:
    """Return the active UI language code."""
    return _language


def is_rtl() -> bool:
    """Return True when the active language reads right to left."""
    return _language == "he"


def t(key: str, **values: object) -> str:
    """Translate a UI string key into the active language, filling {placeholders}."""
    text = STRINGS[_language].get(key) or STRINGS["en"].get(key, key)
    return text.format(**values) if values else text


def hero_name(name: str) -> str:
    """Display name for a hero id (e.g. "ran")."""
    return t(f"hero_{name}")


def class_title(title: str) -> str:
    """Display name for a hero class (e.g. "Knight")."""
    return t(f"class_{title.lower()}")


_HEBREW = re.compile(r"[֐-׿]")
_LTR_TOKEN = r"[+\-]?[A-Za-z0-9](?:[A-Za-z0-9%.,:/+\-]*[A-Za-z0-9%])?"
_LTR_RUN = re.compile(rf"{_LTR_TOKEN}(?:\s+{_LTR_TOKEN})*")
_MIRROR = str.maketrans("()[]<>{}", ")(][><}{")


def has_hebrew(text: str) -> bool:
    """Return True if the text contains Hebrew letters."""
    return bool(_HEBREW.search(text))


def visual(text: str) -> str:
    """
    Reorder a right-to-left string into the left-to-right visual order pygame draws.

    Hebrew runs are reversed (with brackets mirrored) and the runs are laid out
    right to left; embedded Latin/number runs keep their own reading order.
    Strings without Hebrew are returned unchanged.
    """
    if not _HEBREW.search(text):
        return text
    parts: list[tuple[bool, str]] = []
    position = 0
    for match in _LTR_RUN.finditer(text):
        if match.start() > position:
            parts.append((False, text[position:match.start()]))
        parts.append((True, match.group()))
        position = match.end()
    if position < len(text):
        parts.append((False, text[position:]))
    return "".join(chunk if is_ltr else chunk[::-1].translate(_MIRROR) for is_ltr, chunk in reversed(parts))
