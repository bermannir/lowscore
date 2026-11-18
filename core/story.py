"""
Module: story
Purpose: Story-mode script shown before each level and after the final victory.
Dependencies: None
Used by: core.game and ui.renderer.

Edit freely. Each scene is a list of (speaker, text) lines, where speaker is
"narrator", "hero", or "foe" (the monster of that level). "{hero}" in a line is
replaced with the chosen character's name. SCENES / CHAPTER_TITLES are English;
SCENES_HE / CHAPTER_TITLES_HE are the Hebrew script (keep the same line counts).
"""

from core.i18n import get_language

CHAPTER_TITLES: dict[int | str, str] = {
    1: "Chapter I  ·  The Goblin Stairs",
    2: "Chapter II  ·  The Sealed Crypts",
    3: "Chapter III  ·  The War Hall",
    4: "Chapter IV  ·  The Ember Throne",
    "ending": "Epilogue  ·  The Quiet Keep",
}

SCENES: dict[int | str, list[tuple[str, str]]] = {
    1: [
        ("narrator", "Beneath the ruined keep of Lowscore, the old torches have begun to burn again."),
        ("narrator", "Villagers whisper of goblins dragging stolen lanterns into the deep halls."),
        ("hero", "If something has woken down there, I'll be the one to put it back to sleep."),
        ("foe", "Fresh meat on the stairs! Grab it, lads!"),
    ],
    2: [
        ("narrator", "The goblins scatter. Deeper down, the air turns cold and smells of old graves."),
        ("hero", "These crypts were sealed for a reason. Someone broke the seals from the inside."),
        ("foe", "...the living... do not belong... below..."),
    ],
    3: [
        ("narrator", "Past the crypts lies the war hall, where orc chieftains once sold their axes to any king."),
        ("foe", "A lone {hero}? The master promised us a better fight than this."),
        ("hero", "Your master? Then I'm getting close."),
    ],
    4: [
        ("narrator", "At the bottom of Lowscore Keep, a fire burns that no one lit."),
        ("foe", "Little {hero}. Every torch in this keep answers to me."),
        ("hero", "Then I'll put them out one by one, starting with you."),
    ],
    "ending": [
        ("narrator", "The demon's flame gutters and dies. One by one, the torches of Lowscore go dark."),
        ("hero", "Rest now. The keep is quiet again."),
        ("narrator", "The villagers will sing of {hero} for years, though few will believe the tale."),
    ],
}

CHAPTER_TITLES_HE: dict[int | str, str] = {
    1: "פרק א׳  ·  מדרגות הגובלינים",
    2: "פרק ב׳  ·  הקריפטות החתומות",
    3: "פרק ג׳  ·  אולם המלחמה",
    4: "פרק ד׳  ·  כס הגחלים",
    "ending": "אפילוג  ·  המבצר השקט",
}

SCENES_HE: dict[int | str, list[tuple[str, str]]] = {
    1: [
        ("narrator", "מתחת להריסות מבצר לואוסקור, הלפידים הישנים החלו לבעור שוב."),
        ("narrator", "תושבי הכפר לוחשים על גובלינים שגוררים פנסים גנובים אל המעמקים."),
        ("hero", "אם משהו התעורר שם למטה, אני אשלח אותו לישון בחזרה."),
        ("foe", "בשר טרי על המדרגות! קדימה, חבר'ה!"),
    ],
    2: [
        ("narrator", "הגובלינים מתפזרים. עמוק יותר, האוויר מתקרר ומדיף ריח של קברים עתיקים."),
        ("hero", "הקריפטות האלה נחתמו מסיבה. מישהו שבר את החותמות מבפנים."),
        ("foe", "...החיים... לא שייכים... למטה..."),
    ],
    3: [
        ("narrator", "מעבר לקריפטות נמצא אולם המלחמה, שם מכרו פעם ראשי שבטי האורקים את גרזניהם לכל מלך."),
        ("foe", "{hero} לבד? האדון הבטיח לנו קרב טוב יותר מזה."),
        ("hero", "האדון שלכם? אז הוא כבר לא רחוק."),
    ],
    4: [
        ("narrator", "בתחתית מבצר לואוסקור בוערת אש שאיש לא הדליק."),
        ("foe", "{hero}... כל לפיד במבצר הזה נשמע לי."),
        ("hero", "אז אכבה אותם אחד אחד, ואתחיל בך."),
    ],
    "ending": [
        ("narrator", "להבת השד מהבהבת ודועכת. אחד אחד, הלפידים של לואוסקור כבים."),
        ("hero", "נוחו עכשיו. המבצר שקט שוב."),
        ("narrator", "תושבי הכפר ישירו על {hero} עוד שנים רבות, אף שמעטים יאמינו לסיפור."),
    ],
}


def scene(key: int | str) -> list[tuple[str, str]]:
    """The script for a scene in the active language."""
    return (SCENES_HE if get_language() == "he" else SCENES)[key]


def chapter_title(key: int | str) -> str:
    """A chapter heading in the active language."""
    return (CHAPTER_TITLES_HE if get_language() == "he" else CHAPTER_TITLES).get(key, "")
