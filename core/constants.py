"""
Module: constants
Purpose: Global configuration and balance constants for LOWSCORE.
Dependencies: None
Used by: Core engine, entities, systems, and UI modules.
"""

# Display settings
SCREEN_WIDTH = 1200
SCREEN_HEIGHT = 600
SCREEN_CENTER_X = SCREEN_WIDTH // 2
SCREEN_CENTER_Y = SCREEN_HEIGHT // 2
FPS = 60
WINDOW_TITLE = "LOWSCORE"

# Debug settings
DEBUG_MODE = True
SHOW_FPS = True

# Colors
COLORS = {
    "background": (9, 12, 28),
    "arena": (13, 19, 38),
    "arena_line": (30, 40, 65),
    "panel": (18, 24, 44),
    "panel_border": (66, 83, 118),
    "player": (0, 220, 255),
    "player_shadow": (0, 115, 145),
    "player_attack": (255, 255, 120),
    "enemy": (255, 80, 160),
    "enemy_hit": (255, 190, 210),
    "enemy_shadow": (120, 20, 72),
    "boss": (220, 40, 40),
    "white": (255, 255, 255),
    "black": (0, 0, 0),
    "gray": (150, 160, 178),
    "dark_gray": (35, 40, 55),
    "green": (80, 220, 120),
    "red": (235, 70, 70),
    "yellow": (255, 220, 90),
    "orange": (255, 154, 71),
    "gold": (232, 190, 105),
}

# Player defaults
PLAYER_WIDTH = 40
PLAYER_HEIGHT = 50
PLAYER_START_X = SCREEN_CENTER_X
PLAYER_START_Y = SCREEN_CENTER_Y
PLAYER_DEFAULT_SPEED = 270
PLAYER_DEFAULT_HP = 100
PLAYER_DEFAULT_DAMAGE = 12

# Player combat
ATTACK_KEY = "r"
SHIELD_KEY = "a"
ATTACK_DURATION = 0.14
ATTACK_COOLDOWN = 0.38
ATTACK_RANGE = 92
SHIELD_CHARGES = 4
SHIELD_DURATION = 2.4
SHIELD_DAMAGE_MULTIPLIER = 0.25

# Attack modes: damage multiplier, reach, swing time, cooldown, hits all around, knockback px.
HEAVY_KEY = "e"
SPIN_KEY = "q"
FURY_KEY = "f"
ATTACK_MODES = {
    # R presses chain slash -> slash2 -> finisher (or throw when hugging an enemy).
    "slash": {"damage": 1.0, "range": ATTACK_RANGE, "duration": ATTACK_DURATION, "cooldown": 0.16, "full_circle": False, "knockback": 0, "knockdown": False},
    "slash2": {"damage": 1.0, "range": ATTACK_RANGE, "duration": ATTACK_DURATION, "cooldown": 0.16, "full_circle": False, "knockback": 0, "knockdown": False},
    "finisher": {"damage": 1.6, "range": 102, "duration": 0.22, "cooldown": 0.45, "full_circle": False, "knockback": 0, "knockdown": True},
    "throw": {"damage": 2.0, "range": 48, "duration": 0.36, "cooldown": 0.5, "full_circle": False, "knockback": 0, "knockdown": True},
    "heavy": {"damage": 2.0, "range": 114, "duration": 0.28, "cooldown": 1.1, "full_circle": False, "knockback": 0, "knockdown": True},
    "spin": {"damage": 0.8, "range": 108, "duration": 0.36, "cooldown": 3.0, "full_circle": True, "knockback": 0, "knockdown": True, "depth": 2.6},
    # In the air, R chains air1 -> air2 -> jump (a downward plunge that knocks down).
    "air1": {"damage": 0.9, "range": 92, "duration": 0.16, "cooldown": 0.1, "full_circle": False, "knockback": 0, "knockdown": False},
    "air2": {"damage": 0.9, "range": 92, "duration": 0.16, "cooldown": 0.1, "full_circle": False, "knockback": 0, "knockdown": False},
    "jump": {"damage": 1.4, "range": 90, "duration": 0.24, "cooldown": 0.3, "full_circle": False, "knockback": 0, "knockdown": True},
    "dash": {"damage": 1.5, "range": 104, "duration": 0.24, "cooldown": 0.6, "full_circle": False, "knockback": 0, "knockdown": True},
}

# Special abilities (SPECIAL_KEY), one per hero, fitting their trade.
#   range: reach in px (forward for line attacks, all around for bursts); depth: lane multiplier.
SPECIAL_KEY = "w"
SPECIALS = {
    # Knight: charges forward behind the shield, bowling over everyone in the way (dodges hits while charging).
    "ran": {"kind": "charge", "cooldown": 8.0, "damage": 1.6, "range": 230, "depth": 1.4, "duration": 0.3},
    # Ranger: a piercing arrow that flies along her lane and hits every foe in line.
    "florella": {"kind": "arrow", "cooldown": 7.0, "damage": 2.0, "range": 720, "depth": 1.2, "duration": 0.26},
    # Rogue: vanishes and reappears behind the nearest foe for a guaranteed-critical backstab.
    "nili": {"kind": "shadow_step", "cooldown": 7.0, "damage": 2.0, "range": 420, "depth": 4.0, "duration": 0.24, "stun": 1.0},
    # Paladin: holy light heals the hero and knocks back foes close by.
    "gili": {"kind": "holy_light", "cooldown": 12.0, "damage": 1.2, "range": 170, "depth": 2.6, "duration": 0.32, "heal": 30},
    # Barbarian: a war cry that stuns foes around him, then rage boosts his damage.
    "snib": {"kind": "war_cry", "cooldown": 12.0, "damage": 0.0, "range": 300, "depth": 3.2, "duration": 0.36, "stun": 2.0, "rage": 6.0, "rage_bonus": 1.5},
    # Warlord: slams the ground; the quake knocks down every foe on the ground nearby.
    "hogipog": {"kind": "earthquake", "cooldown": 10.0, "damage": 1.5, "range": 300, "depth": 3.6, "duration": 0.32},
}

# Critical hits and the Fury buff (meter fills on hits; press FURY_KEY when full).
CRIT_CHANCE = 0.10
CRIT_MULTIPLIER = 2.0
FURY_MAX = 100
FURY_PER_HIT = 8
FURY_PER_CRIT = 20
FURY_DURATION = 6.0
FURY_CRIT_CHANCE = 0.5
FURY_DAMAGE_BONUS = 1.25
FURY_COOLDOWN_SCALE = 0.7

# Difficulty: share of enemy damage the hero takes, and HP regenerated per second.
DIFFICULTIES = ("easy", "medium", "hard")
DEFAULT_DIFFICULTY = "medium"
DIFFICULTY_DAMAGE_TAKEN = {"easy": 0.6, "medium": 1.0, "hard": 1.35}
DIFFICULTY_HP_REGEN = {"easy": 4.0, "medium": 2.0, "hard": 0.75}
HP_REGEN_DELAY = 2.0  # seconds without being hit before healing resumes

# Character balance
CHARACTER_SPEEDS = {
    "ran": 270,
    "florella": 245,
    "nili": 290,
    "gili": 260,
    "snib": 230,
    "hogipog": 215,
}

CHARACTER_DAMAGE = {
    "ran": 12,
    "florella": 10,
    "nili": 9,
    "gili": 11,
    "snib": 14,
    "hogipog": 16,
}

CHARACTER_HP = {
    "ran": 100,
    "florella": 105,
    "nili": 90,
    "gili": 100,
    "snib": 115,
    "hogipog": 130,
}

# Movement and world bounds
MIN_X = 0
MIN_Y = 100  # keep actors on the floor, in front of the back wall
MAX_X = SCREEN_WIDTH
MAX_Y = SCREEN_HEIGHT
FRICTION = 0.0

# Enemy defaults for later phases
ENEMY_WIDTH = 38
ENEMY_HEIGHT = 48
ENEMY_DEFAULT_SPEED = 150
ENEMY_DEFAULT_HP = 40
ENEMY_DEFAULT_DAMAGE = 8
ENEMY_ATTACK_RANGE = 45
ENEMY_ATTACK_COOLDOWN = 0.95

# Enemy attack modes. windup is the telegraph (raised blade + glint) before the hit lands.
ENEMY_ATTACK_MODES = {
    "slash": {"damage": 1.0, "range": 66, "windup": 0.25, "duration": 0.16, "cooldown": 0.95, "full_circle": False, "knockback": 0, "knockdown": False, "weight": 6},
    "heavy": {"damage": 1.8, "range": 78, "windup": 0.55, "duration": 0.3, "cooldown": 2.4, "full_circle": False, "knockback": 0, "knockdown": True, "weight": 2},
    "spin": {"damage": 0.8, "range": 72, "windup": 0.4, "duration": 0.36, "cooldown": 3.6, "full_circle": True, "knockback": 0, "knockdown": True, "weight": 2},
}
ENEMY_ATTACK_RECOVERY = 0.45  # pause after any enemy strike before the next wind-up

# Strafe: double-tap a direction to dash that way without turning; brief dodge window.
STRAFE_DISTANCE = 140
STRAFE_DURATION = 0.18
STRAFE_COOLDOWN = 0.7
DOUBLE_TAP_WINDOW = 0.25
ENEMY_STRAFE_COOLDOWN = 1.6
ENEMY_DODGE_CHANCE = 0.25  # chance an enemy in reach strafes away from your swing
ENEMY_CIRCLE_RATE = 0.35  # sidesteps per second while closing in

# Boss (final level only; the only enemy that can use Fury)
BOSS_HP_MULTIPLIER = 3.5
BOSS_DAMAGE_BONUS = 4
BOSS_SCALE = 1.35
BOSS_FURY_PER_HIT = 25  # meter gained per hit the boss lands
BOSS_FURY_PER_DAMAGE = 1.0  # meter gained per HP the boss loses

# Bonuses
#   Ally Call (ALLY_KEY): the first call costs ALLY_FIRST_COST points, and each call after that costs
#   ALLY_COST_STEP more than the last (12k, 18k, 24k, ...). Only ALLY_MAX_CALLS can be held, and points
#   scored while holding one don't count toward the next. A call brings a random other hero,
#   auto-played, for ALLY_DURATION seconds.
#   Heroes' Rally (rare): after a RALLY_COMBO-hit combo AND RALLY_POINTS points since the last Rally,
#   every other hero joins the next boss or mid-boss fight, auto-played, until that wave is cleared.
#   The first mid-boss of a run brings a free Rally, to show it off.
ALLY_KEY = "x"
ALLY_FIRST_COST = 12000
ALLY_COST_STEP = 6000
ALLY_MAX_CALLS = 1
ALLY_DURATION = 30.0
RALLY_COMBO = 25
RALLY_POINTS = 30000
RALLY_DELAY = 2.8  # seconds after a boss arrives (its name banner) before the heroes charge in

# Mid-bosses: one per level, arriving in the middle wave with a few escorts.
#   scale: size vs a regular foe; hp: HP multiplier; damage: bonus damage; speed: speed change.
#   move: signature attack, used every `cooldown` seconds after a `windup` telegraph.
#   Below MID_BOSS_ENRAGE of their HP they enrage: signature comes faster, they move quicker.
MID_BOSSES = {
    1: {"key": "grukk", "scale": 1.6, "hp": 5.0, "damage": 4, "speed": -50, "move": "ground_pound",
        "cooldown": 6.5, "windup": 1.0, "radius": 210, "power": 2.0},
    2: {"key": "gravewarden", "scale": 1.45, "hp": 4.5, "damage": 3, "speed": -30, "move": "summon",
        "cooldown": 9.0, "windup": 0.9, "minions": 2, "max_minions": 3},
    3: {"key": "gorrak", "scale": 1.5, "hp": 5.0, "damage": 5, "speed": -20, "move": "bull_rush",
        "cooldown": 6.0, "windup": 0.8, "rush_distance": 760, "rush_time": 0.75, "power": 2.2, "winded": 1.4},
    4: {"key": "brannoc", "scale": 1.6, "hp": 5.5, "damage": 5, "speed": -40, "move": "fire_pillars",
        "cooldown": 6.5, "windup": 0.7, "pillars": 3, "radius": 50, "delay": 1.0, "power": 1.6},
}
# The final boss, the Ember Demon (last wave of the last level): a winged caster-brute with
# three phases. Each move has its own cooldown; "phase" is the first phase it's used in.
#   fire_spit: fireballs fly along the floor at the hero (1 / 3 / 5 per volley by phase): jump or change lane.
#   summon_magic: rune circles glow on the floor, then imps burst out of them.
#   fire_pillars: from phase 2, rings appear under and around the hero, then erupt.
FINAL_BOSS = {
    "key": "ember_demon", "scale": 1.75, "hp": 8.0, "damage": 6, "speed": -40,
    "move_gap": 1.8,  # pause between any two signature moves
    "phases": (0.65, 0.3),  # HP shares where phase 2 and phase 3 begin
    "moves": {
        "fire_spit": {"cooldown": 3.2, "windup": 0.65, "speed": 470, "power": 1.2, "spread": 85, "phase": 1},
        "summon_magic": {"cooldown": 10.0, "windup": 1.1, "minions": 2, "max_minions": 4, "phase": 1},
        "fire_pillars": {"cooldown": 7.0, "windup": 0.7, "pillars": 4, "radius": 54, "delay": 1.0, "power": 1.4, "phase": 2},
    },
}
FIREBALL_HIT_REACH = 28  # px (x) a fireball must pass within to hit
FIREBALL_HEIGHT = 58  # fireballs fly this high above the floor (chest height)

MID_BOSS_ENRAGE = 0.5  # share of HP left when a mid-boss enrages
MID_BOSS_ENRAGED_COOLDOWN = 0.6  # signature cooldown multiplier once enraged
MID_BOSS_ENRAGED_SPEED = 1.25
SCORE_PER_MID_BOSS = 2000

# Goblin riders: one group joins every wave (except the final boss's). Killing one drops its reward.
#   hp/damage grow by level (+hp_per_level, +level); speed in px/s; size is the hitbox.
BEASTS = {
    "bat_rider": {"hp": 16, "hp_per_level": 3, "damage": 5, "speed": 230, "size": (46, 34), "reward": "elixir", "score": 300},
    "wolf_rider": {"hp": 42, "hp_per_level": 7, "damage": 7, "speed": 300, "size": (70, 52), "reward": "pelt", "score": 400},
}
# How many riders show up: only some waves bring a rider group, and both the share of
# waves and the group size grow with difficulty and with each level.
#   share: part of a level's ordinary waves (not mid-boss/boss waves) that bring riders,
#          plus RIDER_SHARE_PER_LEVEL for every level after the first (at least 1 wave per level).
#   group: riders per group on level 1, plus 1 more every RIDER_GROUP_LEVEL_STEP levels (max RIDER_GROUP_MAX).
#   escort: bat riders flying with the mid-boss.
RIDER_DENSITY = {
    "easy": {"share": 0.2, "group": 1, "escort": 0},
    "medium": {"share": 0.35, "group": 1, "escort": 0},
    "hard": {"share": 0.5, "group": 2, "escort": 1},
}
RIDER_SHARE_PER_LEVEL = 0.1
RIDER_GROUP_LEVEL_STEP = 2
RIDER_GROUP_MAX = 3
BAT_HOVER_HEIGHT = 74  # bats circle this high: out of reach of ground swings until they swoop (or you jump)
BAT_SWOOP_TIME = 0.36
WOLF_LUNGE_DISTANCE = 190
WOLF_LUNGE_TIME = 0.22
# Rewards: elixir (bat riders) recharges the special and adds Fury; pelt (wolf riders) adds a shield charge.
ELIXIR_FURY = 15
PELT_SHIELD_CAP = 7

# Fighters are drawn this much larger than their art canvas: big, Golden Axe-sized sprites.
FIGHTER_SCALE = 1.35

# Movement feel: momentum, pseudo-3D depth, and planted footsteps
ACCELERATION = 2400  # px/s^2 toward the desired speed
DECELERATION = 3200  # px/s^2 when slowing or stopping (a short skid)
ENEMY_ACCELERATION = 1500
AIR_CONTROL = 0.35  # share of acceleration available mid-jump
DEPTH_SPEED_RATIO = 0.65  # walking up/down the screen (into/out of depth) is slower, as in a belt-scroller
STRIDE_LENGTH = 24  # px travelled per step; drives the walk cycle so feet don't slide
LAND_CROUCH = 0.14  # seconds of knee-bend when landing a jump

# Golden Axe-style combat feel
LANE_DEPTH = 28  # how far apart on screen (up/down) two fighters can be and still hit each other
# An attack's optional "depth" multiplies LANE_DEPTH (the Whirlwind sweeps a wide band up and down).
COMBO_WINDOW = 0.45  # seconds after a combo hit to press attack again and continue the chain
THROW_REACH = 46  # hugging an enemy this close turns the finisher into a throw
GRAVITY = 1900
JUMP_SPEED = 560
JUMP_SQUAT = 0.07  # crouch before take-off
APEX_BAND = 150  # vertical speed (px/s) around the top of a jump where gravity eases off...
APEX_GRAVITY = 0.35  # ...to this share, for a brief hang-time float
AIR_HIT_HOVER = 90  # each air-combo swing lifts the hero this fast (px/s) to keep the chain aloft
JUMP_KEY = "space"
KNOCKDOWN_LAUNCH = 360  # upward speed when knocked down
KNOCKDOWN_SPEED = 190  # sideways flight speed when knocked down
DOWN_TIME = 0.8  # seconds lying on the ground
GETUP_TIME = 0.28
GETUP_INVULNERABLE = 0.9  # blinking grace period after standing up
HITSTUN = 0.28  # a hit interrupts the target for this long
HITSTOP = {"hit": 0.045, "knockdown": 0.08, "crit": 0.1}  # freeze frames on impact
AIR_DODGE_HEIGHT = 22  # ground swings pass under a fighter jumping higher than this

# Drops (Golden Axe magic pots and food)
POTION_DROP_CHANCE = 0.3
MEAT_DROP_CHANCE = 0.15
POTION_FURY = 34
MEAT_HEAL = 25
PICKUP_RADIUS = 30

# Arcade score
SCORE_PER_DAMAGE = 10
SCORE_PER_KILL = 300
SCORE_PER_BOSS = 5000
SCORE_COMBO_BONUS = 50  # per hit beyond the 2nd in a chain
HIT_CHAIN_WINDOW = 1.5  # hits closer together than this build the on-screen hit counter

# Level flow
LEVEL_WAVES = {1: 5, 2: 5, 3: 6, 4: 6}  # waves per level; each wave fights in its own scenery section
GO_SCROLL_SPEED = 420  # px/s the camera may pan while following the hero forward
ENEMY_OFFSCREEN = 140  # how far past the screen edge enemies spawn and may wander
MAX_LEVEL = 4
LEVEL_SAFE_TOP = 72

# UI settings
FONT_SIZE_SMALL = 18
FONT_SIZE_MEDIUM = 24
FONT_SIZE_LARGE = 36
HUD_PADDING = 16
