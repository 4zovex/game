"""
RAFT FARTS - pygame / browser edition
=====================================
Walk around the edge of the raft and fart to push it the other way.
Reach islands, grab coins and power-ups, dodge rocks, logs and whirlpools,
sink pirates and sharks, beat the flagship boss, buy upgrades and abilities.

There are up to 4 crew members. Choose the number of human players, then
choose how many AI crew mates to add (up to 4 players total).

  Player   Walk          Fart   Ability
  P1       A / D         W      S      Z block
  P2       F / H         T      G      Y block
  P3       J / L         I      K      U block
  P4       LEFT / RIGHT  UP     DOWN   R-SHIFT block

  TAB or M  in-game menu (Resume / Shop / Settings / Main Menu)
  P pause   V 2D <-> 3D view   C chase camera on/off (3D)
  Q / E     rotate the 3D camera
  Shop:     Q/E switch page (upgrades / abilities / prestige), 1-9 / 0 buy.
            On the ability page every crew mate (AI too) is equipped with its
            own LEFT/RIGHT keys.
  Pirates:  stats stay capped - they get smarter instead. From 6 sunk pirates on
            they learn telegraphed tricks (look for the rings, arcs and pips).
            Every kill drops plunder; max all upgrades to spend it on PRESTIGE.

Runs on desktop pygame (python main.py) and in the browser with pygbag
(the file must be called main.py). Sounds are generated in code, so there
are no asset files to load.
"""
import asyncio
import io
import math
import random
import struct

import pygame

W, H = 960, 640
FPS = 60


def _hex(h):
    return (int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16))


_COL = {}


def col(h):
    c = _COL.get(h)
    if c is None:
        c = _COL[h] = _hex(h)
    return c


WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
WATER = col("#2a7fb8")
WAVE = col("#4a9fd0")
WOOD = col("#a6713a")
WOOD_DARK = col("#7a4e22")
GOLD = col("#ffd23f")
LIME = col("#c6ff3d")
PANEL = col("#1b1b2f")

# ---------------------------------------------------------------- tuning ---
BASE_FART_POWER = 110
BASE_FART_COOLDOWN = 0.7
BASE_MAX_SPEED = 300
BASE_WALK_SPEED = 1.0        # radians per second around the raft
BASE_HULL = 100
BASE_DRAG = 0.75             # fraction of speed kept per second
# World population limits keep encounters readable and performance steady.
OBSTACLE_COUNT = 12
COIN_COUNT = 8
MAX_PIRATES = 5          # includes the flagship boss (dinghies are extra)
MAX_SHARKS = 2
MAX_WHIRLPOOLS = 2
MAX_POWERUPS = 2
MAX_CANNONBALLS = 20
MAX_SHELLS = 8
MAX_CLOUDS = 3
MAX_MINES = 4
MAX_SHOCKWAVES = 5
MAX_PUFFS = 90
MAX_FLOAT_TEXTS = 24
MAX_LEVEL = 5
PRESTIGE_MAX = 25
SHOP_PAGES = 3
MAX_HOSTILE_MINES = 6
ADMIRAL_EVERY = 15                # a flagship also hunts you every N pirates sunk
ISLAND_REWARD = 20
TREASURE_BONUS = 30
REPAIR_COST = 30
REPAIR_AMOUNT = 40
PIRATE_BOUNTY = 15           # plus 3 per island reached
CAM_PITCHES = [math.radians(a) for a in (20, 28, 38)]   # low / medium / high
CAM_DIST = 560
FOCAL = 640
DIFFICULTY_NAMES = ["Easy", "Normal", "Hard"]
PIRATE_DMG_MULT = [0.6, 1.0, 1.5]
PIRATE_HP_MULT = [0.7, 1.0, 1.4]
NUM_CREW = 4                 # there are always this many players
AI_LEVELS = ["Rookie", "Sailor", "Captain"]
AI_REACT = [0.45, 0.25, 0.1]      # seconds between AI decisions
AI_NOISE = [0.7, 0.35, 0.1]       # aiming error (radians)
AI_FWD = [0.55, 0.7, 0.85]        # AI farts until it reaches this share of top speed
BOSS_EVERY = 4                    # a pirate flagship every N islands

PLAYER_DEFS = [
    dict(name="P1", color="#ffd23f", left="a", right="d", fart="w",
         ability="s", block="q", label="A/D   W   S   Q"),
    dict(name="P2", color="#ee6055", left="f", right="h", fart="t",
         ability="g", block="y", label="F/H   T   G   Y"),
    dict(name="P3", color="#60d394", left="j", right="l", fart="i",
         ability="k", block="u", label="J/L   I   K   U"),
    dict(name="P4", color="#6ec5ff", left="left", right="right", fart="up",
         ability="down", block="rshift", label="LEFT/RIGHT   UP   DOWN   R-SHIFT"),
]

ABILITIES = [
    dict(name="Mega Blast", cost=60, cd=9, color="#ff9f1c",
         desc="Huge push plus a shockwave that hurts enemies"),
    dict(name="Stink Bomb", cost=50, cd=10, color="#9ae66e",
         desc="Drops a toxic cloud that burns enemies over time"),
    dict(name="Fart Cannon", cost=40, cd=3, color="#ffd23f",
         desc="Fires a homing gas shell that chases nearby enemies"),
    dict(name="Patch Kit", cost=35, cd=7, color="#60d394",
         desc="Repairs 15% of the raft hull"),
    dict(name="Bubble Shield", cost=45, cd=15, color="#7ae7ff",
         desc="Blocks all damage for a few seconds"),
    dict(name="Coin Vacuum", cost=30, cd=12, color="#f4a6ff",
         desc="Sucks in every coin and power-up nearby"),
    dict(name="Gas Mine", cost=45, cd=6, color="#ff6b6b",
         desc="Drops a mine that blows up when enemies touch it"),
    dict(name="Turbo Toot", cost=40, cd=12, color="#6ec5ff",
         desc="A big shove plus a few seconds of turbo speed"),
]

UPGRADES = [
    dict(id="power", name="Fart Power", base=20, desc="+15% push per fart"),
    dict(id="recharge", name="Fart Recharge", base=20, desc="-10% fart cooldown"),
    dict(id="hull", name="Hull Plating", base=25, desc="+20 max hull (heals 20)"),
    dict(id="glide", name="Slippery Raft", base=15, desc="Less drag, glide further"),
    dict(id="speed", name="Top Speed", base=20, desc="+45 max raft speed"),
    dict(id="walk", name="Fast Feet", base=12, desc="+0.4 radians/sec walking speed"),
    dict(id="abpower", name="Ability Power", base=25, desc="Abilities hit harder"),
    dict(id="abcd", name="Ability Recharge", base=25, desc="-10% ability cooldown"),
    dict(id="magnet", name="Coin Magnet", base=10, desc="Pulls coins in from further"),
]

# Prestige upgrades: bought with plunder (dropped by every kill) once all the
# normal upgrades are maxed. They are the long-term goal for strong players.
PRESTIGE = [
    dict(id="p_power", name="Mighty Gas", base=3, desc="+5% fart push"),
    dict(id="p_hull", name="Iron Raft", base=3, desc="+15 max hull"),
    dict(id="p_abpower", name="Ability Mastery", base=4, desc="+8% ability power"),
    dict(id="p_magnet", name="Super Magnet", base=3, desc="+25 coin pull range"),
    dict(id="p_speed", name="Afterburner", base=4, desc="+10 max raft speed"),
    dict(id="p_walk", name="Nimble Hippos", base=3, desc="+0.08 walk speed"),
    dict(id="p_bounty", name="Bounty Hunter", base=4, desc="+5% coins & plunder"),
]

# Pirates never get more HP or damage from kills. Instead they unlock tricks
# (after `unlock` pirates sunk). Every trick has a visible tell.
PIRATE_ABILITIES = {
    "broadside": dict(name="Broadside", unlock=6, cd=7.0, wind=1.1, color="#ff6b6b",
                      letter="B", tip="red ring, then a fan of cannonballs"),
    "chainshot": dict(name="Chain Shot", unlock=8, cd=8.0, wind=0.6, color="#c77dff",
                      letter="C", tip="slow purple homing ball - block it"),
    "bulwark": dict(name="Bulwark", unlock=10, cd=0, wind=0, color="#9fb3c8",
                    letter="S", tip="front shield blocks shells - flank it"),
    "minelayer": dict(name="Mine Layer", unlock=12, cd=9.0, wind=0.5, color="#ff9f1c",
                      letter="M", tip="drops mines in your path"),
    "blinker": dict(name="Blinker", unlock=14, cd=9.0, wind=0.7, color="#4dd0e1",
                    letter="T", tip="teleports away when you get close"),
    "bosun": dict(name="Bosun", unlock=18, cd=6.0, wind=0.8, color="#60d394",
                  letter="H", tip="heals other pirates - sink it first"),
    "splitter": dict(name="Splitter", unlock=22, cd=0, wind=0, color="#ffd23f",
                     letter="X", tip="breaks into dinghies when sunk"),
    "beastmaster": dict(name="Beastmaster", unlock=26, cd=14.0, wind=1.0,
                        color="#7ae7ff", letter="W", tip="calls a shark"),
}

POWERUPS = {
    "crate": dict(color="#60d394", letter="+", label="Supply crate"),
    "beans": dict(color="#b5742f", letter="B", label="Bean boost"),
    "turbo": dict(color="#6ec5ff", letter="T", label="Turbo"),
    "shield": dict(color="#7ae7ff", letter="S", label="Bubble shield"),
    "treasure": dict(color="#ffd23f", letter="$", label="Treasure cache"),
}

# ------------------------------------------------------------------ keys ---
SPECIAL_KEYS = {
    pygame.K_LEFT: "left", pygame.K_RIGHT: "right", pygame.K_UP: "up",
    pygame.K_DOWN: "down", pygame.K_TAB: "tab", pygame.K_SPACE: "space",
    pygame.K_RETURN: "return", pygame.K_KP_ENTER: "return",
    pygame.K_ESCAPE: "escape", pygame.K_BACKSPACE: "backspace",
    pygame.K_RSHIFT: "rshift",
}
for _i in range(10):
    SPECIAL_KEYS[getattr(pygame, "K_KP%d" % _i)] = str(_i)


def key_name(event):
    k = event.key
    if k in SPECIAL_KEYS:
        return SPECIAL_KEYS[k]
    if 0 < k < 128:
        return chr(k).lower()
    return ""


def angle_diff(a, b):
    """Shortest signed angle from a to b."""
    return (b - a + math.pi) % math.tau - math.pi


# ----------------------------------------------------------------- sound ---
SAMPLE_RATE = 16000


def render_wav(dur, freq, shape="sine", noise=0.0, decay=1.0, trem=0.0, amp=0.6):
    """Tiny synthesizer. `freq` is a function of time (seconds) -> Hz."""
    n = int(SAMPLE_RATE * dur)
    out = []
    phase = 0.0
    for i in range(n):
        t = i / SAMPLE_RATE
        phase += freq(t) / SAMPLE_RATE
        ph = phase % 1.0
        if shape == "saw":
            v = 2 * ph - 1
        elif shape == "square":
            v = 1.0 if ph < 0.5 else -1.0
        else:
            v = math.sin(math.tau * ph)
        if noise:
            v = v * (1 - noise) + random.uniform(-1, 1) * noise
        env = (1 - t / dur) ** decay
        env *= min(1.0, t * 200)                  # no click at the start
        if trem:
            env *= 0.65 + 0.35 * math.sin(math.tau * trem * t)
        out.append(int(max(-1, min(1, v * env * amp)) * 32767))
    data = struct.pack("<%dh" % len(out), *out)
    header = b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVEfmt " + \
        struct.pack("<IHHIIHH", 16, 1, 1, SAMPLE_RATE, SAMPLE_RATE * 2, 2, 16) + \
        b"data" + struct.pack("<I", len(data))
    return header + data


def _sound_recipe(name):
    if name.startswith("fart"):
        base = {"fart0": 95, "fart1": 120, "fart2": 75}.get(name, 95)
        return render_wav(0.38, lambda t: base * (1 - 0.35 * t / 0.38) + 6 * math.sin(t * 90),
                          "saw", noise=0.35, decay=0.7, trem=28, amp=0.55)
    if name == "mega":
        return render_wav(0.9, lambda t: 62 - 28 * t, "saw", noise=0.45,
                          decay=0.8, trem=18, amp=0.8)
    if name == "boom":
        return render_wav(0.45, lambda t: 70 - 40 * t, "sine", noise=0.55,
                          decay=2.0, amp=0.8)
    if name == "hit":
        return render_wav(0.2, lambda t: 110 - 200 * t, "sine", noise=0.5,
                          decay=1.6, amp=0.8)
    if name == "coin":
        return render_wav(0.13, lambda t: 900 if t < 0.05 else 1350,
                          "square", decay=1.0, amp=0.25)
    if name == "sunk":
        return render_wav(0.7, lambda t: 600 - 700 * t, "saw", noise=0.2,
                          decay=1.0, amp=0.5)
    if name == "buy":
        return render_wav(0.22, lambda t: 520 if t < 0.1 else 780,
                          "sine", decay=0.8, amp=0.5)
    if name == "heal":
        return render_wav(0.4, lambda t: 400 + 1250 * t, "sine", decay=0.9, amp=0.45)
    if name == "shield":
        return render_wav(0.4, lambda t: 300 + 900 * t + 20 * math.sin(t * 60),
                          "sine", decay=0.8, amp=0.45)
    if name == "island":
        return render_wav(0.45, lambda t: (440, 554, 659, 880)[min(3, int(t / 0.11))],
                          "square", decay=0.6, amp=0.3)
    if name == "click":
        return render_wav(0.05, lambda t: 650, "square", decay=1.0, amp=0.2)
    if name == "gameover":
        return render_wav(1.0, lambda t: 420 - 340 * t, "saw", noise=0.1,
                          decay=0.9, amp=0.5)
    if name == "powerup":
        return render_wav(0.35, lambda t: 600 + 1400 * t, "square", decay=0.8, amp=0.28)
    if name == "bite":
        return render_wav(0.18, lambda t: 220 - 400 * t, "saw", noise=0.4,
                          decay=1.4, amp=0.7)
    if name == "vac":
        return render_wav(0.5, lambda t: 200 + 800 * t, "sine", decay=0.7,
                          trem=20, amp=0.4)
    if name == "horn":
        return render_wav(1.0, lambda t: 110 + 4 * math.sin(t * 30), "saw",
                          decay=0.8, amp=0.5)
    return None


class Sounds:
    """Sounds are synthesized the first time they are needed and cached."""
    def __init__(self):
        self.enabled = True
        self.cache = {}
        self.broken = False

    def play(self, name, volume=1.0):
        if not self.enabled or self.broken:
            return
        try:
            if name == "fart":
                name = random.choice(["fart0", "fart1", "fart2"])
            snd = self.cache.get(name)
            if snd is None:
                if not pygame.mixer.get_init():
                    pygame.mixer.init(SAMPLE_RATE, -16, 1, 512)
                wav = _sound_recipe(name)
                if wav is None:
                    return
                snd = pygame.mixer.Sound(file=io.BytesIO(wav))
                self.cache[name] = snd
            snd.set_volume(max(0.0, min(1.0, volume)))
            snd.play()
        except Exception:
            self.broken = True      # no audio available (that's fine)


# --------------------------------------------------------------- objects ---
class Raft:
    def __init__(self):
        self.x = self.y = 0.0
        self.vx = self.vy = 0.0
        self.radius = 70
        self.hull = BASE_HULL
        self.invuln = 0.0
        self.shield = 0.0
        self.beans = 0.0      # bean boost timer (stronger, faster farts)
        self.turbo = 0.0      # turbo timer (higher top speed, less drag)

    def edge_point(self, angle):
        nx, ny = math.cos(angle), math.sin(angle)
        return nx * self.radius, ny * self.radius, nx, ny

    def push(self, nx, ny, power, max_speed):
        self.vx -= nx * power      # fart goes out, raft goes the other way
        self.vy -= ny * power
        self.clamp(max_speed)

    def clamp(self, max_speed):
        speed = math.hypot(self.vx, self.vy)
        if speed > max_speed:
            self.vx *= max_speed / speed
            self.vy *= max_speed / speed

    def update(self, dt, drag_base, max_speed):
        self.x += self.vx * dt
        self.y += self.vy * dt
        drag = drag_base ** dt
        self.vx *= drag
        self.vy *= drag
        self.clamp(max_speed)
        self.invuln -= dt
        self.shield -= dt
        self.beans -= dt
        self.turbo -= dt

    def damage(self, amount):
        if self.shield > 0 or self.invuln > 0:
            return False
        self.hull -= amount
        self.invuln = 0.5
        return True


class Puff:
    def __init__(self, x, y, nx, ny, spread=0.6, big=False):
        self.x, self.y = x, y
        ang = math.atan2(ny, nx) + random.uniform(-spread, spread)
        speed = random.uniform(30, 90)
        self.vx = math.cos(ang) * speed
        self.vy = math.sin(ang) * speed
        self.life = self.max_life = random.uniform(0.6, 1.1)
        self.r = random.uniform(10, 18) if big else random.uniform(6, 12)

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt


class FloatText:
    def __init__(self, x, y, text, color):
        self.x, self.y, self.text, self.color = x, y, text, color
        self.life = 1.2

    def update(self, dt):
        self.y -= 35 * dt
        self.life -= dt


class Player:
    def __init__(self, d, angle, ability, ai=False):
        self.name = d["name"] + (" AI" if ai else "")
        self.color = col(d["color"])
        self.k = d
        self.angle = angle
        self.ability = ability
        self.cooldown = 0.0
        self.ability_cd = 0.0
        self.ability_cd_max = 1.0
        self.block_charges = 3.0
        self.block_timer = 0.0
        self.block_recharge_timer = 0.0
        self.flash = 0.0
        self.word = ""
        # AI state
        self.ai = ai
        self.ai_dir = 0
        self.think = random.uniform(0.0, 0.4)
        self.target = angle
        self.want_fart = False
        self.gunner = False
        self.offset = random.uniform(-0.25, 0.25)

    def update(self, dt, keys, walk_speed):
        self.cooldown -= dt
        self.ability_cd -= dt
        self.block_timer = max(0.0, self.block_timer - dt)
        if self.block_charges < 3.0:
            self.block_recharge_timer += dt
            while self.block_recharge_timer >= 4.0 and self.block_charges < 3.0:
                self.block_charges = min(3.0, self.block_charges + 1.0)
                self.block_recharge_timer -= 4.0
        else:
            self.block_recharge_timer = 0.0
        self.flash -= dt
        if self.ai:
            direction = self.ai_dir
        else:
            direction = (self.k["right"] in keys) - (self.k["left"] in keys)
        self.angle += direction * walk_speed * dt
        # players never block each other: they just walk through


class Obstacle:
    def __init__(self, x, y, r, kind, vx=0.0, vy=0.0):
        self.x, self.y, self.r, self.kind = x, y, r, kind
        self.vx, self.vy = vx, vy

    def update(self, dt):
        self.x += self.vx * dt
        self.y += self.vy * dt


class Island:
    def __init__(self, x, y, r, kind="palm"):
        self.x, self.y, self.r, self.kind = x, y, r, kind


class Coin:
    def __init__(self, x, y, value=5):
        self.x, self.y, self.value = x, y, value
        self.pull = 0.0


class Powerup:
    def __init__(self, x, y, kind):
        self.x, self.y, self.kind = x, y, kind
        self.pull = 0.0


class Whirlpool:
    def __init__(self, x, y, r):
        self.x, self.y, self.r = x, y, r
        self.spin = random.uniform(0, math.tau)


class Pirate:
    def __init__(self, x, y, hp, kind="gun"):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.hp = self.max_hp = hp
        self.kind = kind
        self.r = {"gun": 34, "ram": 28, "boss": 58, "dinghy": 18}[kind]
        self.fire_t = random.uniform(1.5, 3.0)
        self.orbit = random.choice([-1, 1])
        self.hit_cd = 0.0
        self.abil = []            # pirate tricks (see PIRATE_ABILITIES)
        self.cd = {}              # trick cooldowns
        self.charging = None      # [trick, time_left, total] while winding up
        self.face = 0.0           # Bulwark shield direction
        self.heal_to = None
        self.heal_t = 0.0


class Shark:
    def __init__(self, x, y, hp):
        self.x, self.y = x, y
        self.vx = self.vy = 0.0
        self.hp = self.max_hp = hp
        self.r = 22
        self.bite_cd = 1.0
        self.hit_cd = 0.0
        self.phase = random.uniform(0, math.tau)
        self.hx, self.hy = 1.0, 0.0


class Cannonball:
    def __init__(self, x, y, vx, vy, dmg=10):
        self.x, self.y, self.vx, self.vy, self.dmg = x, y, vx, vy, dmg
        self.life = 5.0
        self.homing = 0.0          # turn rate for Chain Shot


class HostileMine:
    def __init__(self, x, y, dmg):
        self.x, self.y, self.dmg = x, y, dmg
        self.life = 14.0
        self.arm = 1.5


class Shell:
    def __init__(self, x, y, vx, vy, dmg):
        self.x, self.y, self.vx, self.vy, self.dmg = x, y, vx, vy, dmg
        self.life = 2.4
        self.speed = math.hypot(vx, vy)
        self.turn_rate = 3.2  # radians per second


class Cloud:
    def __init__(self, x, y, r, dps):
        self.x, self.y, self.r, self.dps = x, y, r, dps
        self.life = self.max_life = 5.0


class Mine:
    def __init__(self, x, y, dmg):
        self.x, self.y, self.dmg = x, y, dmg
        self.life = 25.0
        self.arm = 0.8


class Shockwave:
    def __init__(self, x, y, max_r, dmg):
        self.x, self.y, self.max_r, self.dmg = x, y, max_r, dmg
        self.life = self.max_life = 0.5
        self.hit = set()

    @property
    def radius(self):
        return self.max_r * (1 - self.life / self.max_life)


# ------------------------------------------------------------------ game ---
class Game:
    def __init__(self, screen):
        self.screen = screen
        try:
            self.fx = pygame.Surface((W, H), pygame.SRCALPHA)
        except Exception:
            self.fx = None
        self.fx_used = False
        self.fonts = {}
        self.text_cache = {}
        self.snd = Sounds()
        self.keys = set()

        self.state = "menu_count"   # menu_count, menu_abilities, play, paused,
        #                             menu_ai_count, menu_abilities, play, paused,
        #                             pause_menu, settings, shop, over
        self.n_players = 1          # number of human players
        self.n_ai = 3               # number of AI crew mates (total crew <= 4)
        self.ability_choice = [0, 1, 2, 3]
        self.levels = {u["id"]: 0 for u in UPGRADES + PRESTIGE}
        self.raft = Raft()
        self.shop_msg = ""
        self.shop_page = 0
        self.shop_return = "play"
        self.settings_return = "menu_count"
        self.settings = dict(view3d=False, difficulty=1, pirates=True, hints=True,
                             cam=1, chase=True, sound=True, shake=True, fx=1, ai=1)
        self.yaw = math.pi / 2
        self.yaw_off = 0.0
        self.cam_x = self.cam_y = 0.0
        self.cam_dist = CAM_DIST
        self.frame = 0
        self.shake_mag = 0.0
        self.sx = self.sy = 0.0
        self.running = True
        self.best = 0
        self.coins = self.score = self.kills = 0
        self.plunder = 0
        self.pirate_kills = 0
        self.pending_boss = False
        self.seen_abil = set()
        self.hmines = []
        self.run_time = 0.0
        self.leg_time = 0.0
        self.banner_text = ""
        self.banner_t = 0.0
        self.nav = (1.0, 0.0)
        self.nav_t = 0.0

    # ---------- derived stats ----------
    def lvl(self, key):
        return self.levels.get(key, 0)

    def fart_power(self):
        mult = 1.8 if self.raft.beans > 0 else 1.0
        return BASE_FART_POWER * (1 + 0.15 * self.lvl("power") + 0.05 * self.lvl("p_power")) * mult

    def fart_cooldown(self):
        mult = 0.6 if self.raft.beans > 0 else 1.0
        return BASE_FART_COOLDOWN * 0.9 ** self.lvl("recharge") * mult

    def max_hull(self):
        return BASE_HULL + 20 * self.lvl("hull") + 15 * self.lvl("p_hull")

    def drag_base(self):
        d = min(0.93, BASE_DRAG + 0.035 * self.lvl("glide"))
        if self.raft.turbo > 0:
            d = min(0.97, d + 0.12)
        return d

    def max_speed(self):
        # Several AI crew mates fart in coordinated bursts; keep the raft
        # controllable as the AI crew gets larger.
        ai_count = getattr(self, "n_ai", 0)
        s = (BASE_MAX_SPEED + 45 * self.lvl("speed") + 10 * self.lvl("p_speed")) * max(
            0.68, 1.0 - 0.08 * max(0, ai_count - 1))
        if self.raft.turbo > 0:
            s *= 1.5
        return s

    def walk_speed(self):
        return BASE_WALK_SPEED + 0.4 * self.lvl("walk") + 0.08 * self.lvl("p_walk")

    def ability_power(self):
        return 1 + 0.25 * self.lvl("abpower") + 0.08 * self.lvl("p_abpower")

    def ability_cd_mult(self):
        return 0.9 ** self.lvl("abcd")

    def magnet_range(self):
        return 40 + 70 * self.lvl("magnet") + 25 * self.lvl("p_magnet")

    def max_pirates(self):
        return min(MAX_PIRATES, 1 + self.score // 2 + self.pirate_kills // 12)

    def upgrade_cost(self, u):
        return int(u["base"] * (1 + 0.6 * self.lvl(u["id"])))

    def prestige_cost(self, u):
        return int(u["base"] * (1 + 0.25 * self.lvl(u["id"])))

    def prestige_unlocked(self):
        return all(self.lvl(u["id"]) >= MAX_LEVEL for u in UPGRADES)

    def coin_mult(self):
        return 1 + 0.05 * self.lvl("p_bounty")

    def plunder_roll(self, base):
        v = base * self.coin_mult()
        return int(v) + (1 if random.random() < v - int(v) else 0)

    def add_shake(self, mag):
        self.shake_mag = min(18.0, max(self.shake_mag, mag))

    def announce(self, text, t=3.0):
        self.banner_text = text
        self.banner_t = t

    def enemies(self):
        return self.pirates + self.sharks

    # ---------- setup ----------
    def new_run(self):
        self.levels = {u["id"]: 0 for u in UPGRADES + PRESTIGE}
        self.raft = Raft()
        self.raft.hull = self.max_hull()
        self.coins = 0
        self.score = 0
        self.kills = 0
        self.plunder = 0
        self.pirate_kills = 0
        self.pending_boss = False
        self.seen_abil = set()
        self.run_time = 0.0
        self.leg_time = 0.0
        n = self.n_players
        total_crew = min(NUM_CREW, n + self.n_ai)
        self.players = []
        for i in range(total_crew):
            # every crew slot (human or AI) starts with the ability picked in the menu
            self.players.append(Player(PLAYER_DEFS[i], -math.pi / 2 + i * math.tau / NUM_CREW,
                                       self.ability_choice[i], i >= n))
        self.puffs, self.texts = [], []
        self.obstacles, self.coin_items = [], []
        self.pirates, self.cannonballs, self.shells = [], [], []
        self.sharks, self.mines, self.whirls, self.powerups = [], [], [], []
        self.hmines = []
        self.clouds, self.shockwaves = [], []
        self.pirate_timer = 15.0
        self.shark_timer = 20.0
        self.whirl_timer = 8.0
        self.powerup_timer = 9.0
        self.wind_ang = random.uniform(0, math.tau)
        self.wind_str = 0.0
        self.wind_t = 12.0
        self.banner_t = 0.0
        self.island = None
        self.shop_msg = ""
        self.shop_page = 0
        self.owned = {p.ability for p in self.players}
        self.spawn_island()
        while len(self.obstacles) < OBSTACLE_COUNT:
            self.spawn_obstacle(220, 1300)
        while len(self.coin_items) < COIN_COUNT:
            self.spawn_coin(250, 1100)
        self.yaw = math.pi / 2
        self.yaw_off = 0.0
        self.cam_x, self.cam_y = self.raft.x, self.raft.y
        self.cam_dist = CAM_DIST
        self.nav = (1.0, 0.0)
        self.nav_t = 0.0
        self.state = "play"

    def spawn_island(self):
        ang = random.uniform(0, math.tau)
        dist = random.uniform(800, 1200)
        if self.score > 0:
            roll = random.random()
            kind = "treasure" if roll < 0.22 else ("ruins" if roll < 0.40 else "palm")
        else:
            kind = "palm"
        self.island = Island(self.raft.x + math.cos(ang) * dist,
                             self.raft.y + math.sin(ang) * dist,
                             random.uniform(60, 90), kind)
        self.obstacles = [o for o in self.obstacles
                          if math.hypot(o.x - self.island.x, o.y - self.island.y)
                          > self.island.r + o.r + 100]
        self.whirls = [w for w in self.whirls
                       if math.hypot(w.x - self.island.x, w.y - self.island.y)
                       > self.island.r + w.r + 200]

    def spawn_obstacle(self, min_dist=650, max_dist=1300):
        if len(self.obstacles) >= OBSTACLE_COUNT:
            return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(min_dist, max_dist)
        x = self.raft.x + math.cos(ang) * dist
        y = self.raft.y + math.sin(ang) * dist
        if self.island and math.hypot(x - self.island.x, y - self.island.y) \
                < self.island.r + 140:
            return
        if random.random() < 0.7:
            self.obstacles.append(Obstacle(x, y, random.uniform(25, 55), "rock"))
        else:
            d = random.uniform(0, math.tau)
            sp = random.uniform(20, 55)
            self.obstacles.append(Obstacle(x, y, random.uniform(18, 30), "log",
                                           math.cos(d) * sp, math.sin(d) * sp))

    def spawn_coin(self, min_dist=500, max_dist=1100):
        if len(self.coin_items) >= COIN_COUNT:
            return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(min_dist, max_dist)
        self.coin_items.append(Coin(self.raft.x + math.cos(ang) * dist,
                                    self.raft.y + math.sin(ang) * dist))

    def spawn_whirl(self):
        if len(self.whirls) >= MAX_WHIRLPOOLS:
            return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(600, 1100)
        x = self.raft.x + math.cos(ang) * dist
        y = self.raft.y + math.sin(ang) * dist
        r = random.uniform(90, 140)
        if math.hypot(x - self.island.x, y - self.island.y) < self.island.r + r + 250:
            return
        self.whirls.append(Whirlpool(x, y, r))

    def spawn_powerup(self):
        if len(self.powerups) >= MAX_POWERUPS:
            return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(450, 900)
        kind = random.choices(
            ["crate", "beans", "turbo", "shield", "treasure"],
            [4, 3, 3, 2, 2]
        )[0]
        self.powerups.append(Powerup(self.raft.x + math.cos(ang) * dist,
                                     self.raft.y + math.sin(ang) * dist, kind))

    def pirate_abilities_for(self, kind):
        k = self.pirate_kills
        if k < 6 or kind in ("ram", "dinghy"):
            return []
        pool = [n for n, a in PIRATE_ABILITIES.items() if a["unlock"] <= k]
        if k < 14:
            count = 1
        elif k < 30:
            count = random.choice((1, 2))
        else:
            count = 2
        if kind == "boss":
            count += 1
        return random.sample(pool, min(count, len(pool), 3))

    def spawn_pirate(self, kind=None):
        # A flagship can replace a regular pirate, but never exceed the cap.
        if len(self.pirates) >= MAX_PIRATES:
            if kind == "boss":
                regulars = [p for p in self.pirates if p.kind not in ("boss", "dinghy")]
                if not regulars:
                    return
                weakest = min(regulars, key=lambda p: p.hp)
                self.pirates.remove(weakest)
            else:
                return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(750, 900)
        if kind is None:
            kind = "ram" if self.score >= 3 and random.random() < 0.3 else "gun"
        mult = PIRATE_HP_MULT[self.settings["difficulty"]]
        # Hard HP caps: pirates never become unkillable, whatever you have sunk.
        if kind == "boss":
            hp = min(220, 150 + 15 * self.score) * mult
        elif kind == "ram":
            hp = min(70, 28 + 4 * self.score) * mult
        else:
            hp = min(90, 40 + 5 * self.score) * mult
        pr = Pirate(self.raft.x + math.cos(ang) * dist,
                    self.raft.y + math.sin(ang) * dist, hp, kind)
        pr.abil = self.pirate_abilities_for(kind)
        pr.cd = {n: random.uniform(3.0, 6.0) for n in pr.abil}
        pr.face = ang + math.pi
        self.pirates.append(pr)
        for n in pr.abil:
            if n not in self.seen_abil:
                self.seen_abil.add(n)
                a = PIRATE_ABILITIES[n]
                self.announce(f"New pirate trick: {a['name']} - {a['tip']}", 5.0)

    def spawn_shark(self):
        if len(self.sharks) >= MAX_SHARKS:
            return
        ang = random.uniform(0, math.tau)
        dist = random.uniform(600, 800)
        hp = min(60, 24 + 4 * self.score) * PIRATE_HP_MULT[self.settings["difficulty"]]
        self.sharks.append(Shark(self.raft.x + math.cos(ang) * dist,
                                 self.raft.y + math.sin(ang) * dist, hp))

    def float_text(self, x, y, text, color=WHITE):
        if len(self.texts) >= MAX_FLOAT_TEXTS:
            self.texts.pop(0)
        self.texts.append(FloatText(x, y, text, color))

    # ---------- input ----------
    def handle_events(self):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                k = key_name(e)
                if k:
                    self.on_press(k)
            elif e.type == pygame.KEYUP:
                k = key_name(e)
                if k:
                    self.keys.discard(k)

    def click(self):
        self.snd.play("click", 0.6)

    def leave_shop(self):
        self.state = self.shop_return

    def on_press(self, key):
        if key in self.keys:
            return  # ignore key auto-repeat
        self.keys.add(key)
        self.snd.enabled = self.settings["sound"]

        if key == "r" and self.state == "over":
            self.state = "menu_count"
            return
        if key == "p" and self.state in ("play", "paused"):
            self.state = "paused" if self.state == "play" else "play"
            return
        if key == "v" and self.state in ("play", "paused"):
            self.settings["view3d"] = not self.settings["view3d"]
            return
        if key == "c" and self.state in ("play", "paused"):
            self.settings["chase"] = not self.settings["chase"]
            self.announce("Chase camera " + ("ON" if self.settings["chase"] else "OFF"), 1.5)
            return
        if key in ("tab", "m"):      # TAB (or M) opens / closes the in-game menu
            if self.state in ("play", "paused", "shop"):
                self.state = "pause_menu"
                self.click()
                return
            if self.state == "pause_menu":
                self.state = "play"
                return
            if self.state == "settings" and self.settings_return == "pause_menu":
                self.state = "pause_menu"
                return

        if self.state == "menu_count":
            if key in ("0", "1", "2", "3", "4"):
                self.n_players = int(key)
                self.n_ai = 0
                self.state = "menu_ai_count"
                self.click()
            elif key == "s":
                self.settings_return = "menu_count"
                self.state = "settings"
                self.click()
        elif self.state == "menu_ai_count":
            max_ai = NUM_CREW - self.n_players
            min_ai = 1 if self.n_players == 0 else 0
            if key.isdigit() and min_ai <= int(key) <= max_ai:
                self.n_ai = int(key)
                self.click()
                if self.n_players + self.n_ai == 0:
                    self.state = "menu_count"
                else:
                    self.state = "menu_abilities"
            elif key in ("backspace", "escape"):
                self.state = "menu_count"
                self.click()
            elif key == "s":
                self.settings_return = "menu_ai_count"
                self.state = "settings"
                self.click()
        elif self.state == "menu_abilities":
            for i in range(min(NUM_CREW, self.n_players + self.n_ai)):
                d = PLAYER_DEFS[i]
                if key == d["left"]:
                    self.ability_choice[i] = (self.ability_choice[i] - 1) % len(ABILITIES)
                    self.click()
                elif key == d["right"]:
                    self.ability_choice[i] = (self.ability_choice[i] + 1) % len(ABILITIES)
                    self.click()
            if key in ("return", "space"):
                self.new_run()
            elif key in ("backspace", "escape"):
                self.state = "menu_count"
        elif self.state == "play":
            for p in self.players:
                if p.ai:
                    continue
                if key == p.k["fart"] and p.cooldown <= 0:
                    self.fart(p)
                elif key == p.k["ability"] and p.ability_cd <= 0:
                    self.use_ability(p)
                elif key == p.k["block"]:
                    self.activate_block(p)
        elif self.state == "shop":
            if key in ("q", "e"):
                self.shop_page = (self.shop_page + (1 if key == "e" else -1)) % SHOP_PAGES
                self.shop_msg = ""
                self.click()
            elif key in ("return", "space", "escape", "backspace"):
                self.leave_shop()
            elif self.shop_page == 0:
                if len(key) == 1 and key in "123456789":
                    self.shop_buy(int(key) - 1)
                elif key == "0":
                    self.shop_buy(9)
            elif self.shop_page == 1:
                if len(key) == 1 and key in "12345678":
                    self.buy_ability(int(key) - 1)
                # every crew mate, AI included, is equipped with its own keys
                for pl in self.players:
                    if key == pl.k["left"]:
                        self.equip(pl, -1)
                    elif key == pl.k["right"]:
                        self.equip(pl, 1)
            else:
                if len(key) == 1 and key in "1234567":
                    self.buy_prestige(int(key) - 1)
        elif self.state == "pause_menu":
            if key in ("1", "escape"):
                self.state = "play"
            elif key == "2":
                self.shop_return = "pause_menu"
                self.shop_msg = ""
                self.state = "shop"
                self.click()
            elif key == "3":
                self.settings_return = "pause_menu"
                self.state = "settings"
                self.click()
            elif key == "4":
                self.state = "menu_count"
                self.click()
        elif self.state == "settings":
            st = self.settings
            changed = True
            if key == "1":
                st["view3d"] = not st["view3d"]
            elif key == "2":
                st["difficulty"] = (st["difficulty"] + 1) % 3
            elif key == "3":
                st["pirates"] = not st["pirates"]
                if not st["pirates"] and self.settings_return == "pause_menu":
                    self.pirates, self.cannonballs, self.sharks = [], [], []
                    self.hmines = []
            elif key == "4":
                st["hints"] = not st["hints"]
            elif key == "5":
                st["cam"] = (st["cam"] + 1) % 3
            elif key == "6":
                st["chase"] = not st["chase"]
            elif key == "7":
                st["sound"] = not st["sound"]
            elif key == "8":
                st["shake"] = not st["shake"]
            elif key == "9":
                st["fx"] = 1 - st["fx"]
            elif key == "0":
                st["ai"] = (st["ai"] + 1) % 3
            elif key in ("escape", "backspace", "return", "space"):
                self.state = self.settings_return
                changed = False
            else:
                changed = False
            if changed:
                self.snd.enabled = st["sound"]
                self.click()

    # ---------- shop ----------
    def shop_buy(self, idx):
        if idx == 9:
            if self.raft.hull >= self.max_hull():
                self.shop_msg = "Hull is already full"
            elif self.coins < REPAIR_COST:
                self.shop_msg = "Not enough coins"
            else:
                self.coins -= REPAIR_COST
                self.raft.hull = min(self.max_hull(), self.raft.hull + REPAIR_AMOUNT)
                self.shop_msg = "Raft repaired!"
                self.snd.play("heal")
            return
        u = UPGRADES[idx]
        if self.lvl(u["id"]) >= MAX_LEVEL:
            self.shop_msg = f"{u['name']} is maxed out"
            return
        cost = self.upgrade_cost(u)
        if self.coins < cost:
            self.shop_msg = "Not enough coins"
            return
        was_unlocked = self.prestige_unlocked()
        self.coins -= cost
        self.levels[u["id"]] += 1
        if u["id"] == "hull":
            self.raft.hull = min(self.max_hull(), self.raft.hull + 20)
        self.shop_msg = f"Bought {u['name']}!"
        if not was_unlocked and self.prestige_unlocked():
            self.shop_msg = "ALL UPGRADES MAXED! Prestige page unlocked (press E)"
            self.announce("PRESTIGE UPGRADES UNLOCKED - spend plunder!", 4.0)
        self.snd.play("buy")

    def buy_prestige(self, idx):
        if idx >= len(PRESTIGE):
            return
        u = PRESTIGE[idx]
        if not self.prestige_unlocked():
            done = sum(1 for x in UPGRADES if self.lvl(x["id"]) >= MAX_LEVEL)
            self.shop_msg = f"Locked: max out all upgrades first ({done}/{len(UPGRADES)})"
            return
        if self.lvl(u["id"]) >= PRESTIGE_MAX:
            self.shop_msg = f"{u['name']} is maxed out"
            return
        cost = self.prestige_cost(u)
        if self.plunder < cost:
            self.shop_msg = "Not enough plunder"
            return
        self.plunder -= cost
        self.levels[u["id"]] += 1
        if u["id"] == "p_hull":
            self.raft.hull = min(self.max_hull(), self.raft.hull + 15)
        self.shop_msg = f"{u['name']} is now level {self.lvl(u['id'])}!"
        self.snd.play("buy")

    def buy_ability(self, idx):
        ab = ABILITIES[idx]
        if idx in self.owned:
            self.shop_msg = f"You already own {ab['name']}"
        elif self.coins < ab["cost"]:
            self.shop_msg = "Not enough coins"
        else:
            self.coins -= ab["cost"]
            self.owned.add(idx)
            self.shop_msg = f"Unlocked {ab['name']}! Equip it with your LEFT/RIGHT keys"
            self.snd.play("buy")

    def equip(self, player, step):
        order = sorted(self.owned)
        pos = order.index(player.ability) if player.ability in order else 0
        player.ability = order[(pos + step) % len(order)]
        player.ability_cd = 0
        self.shop_msg = f"{player.name} equipped {ABILITIES[player.ability]['name']}"
        self.click()

    def ai_equip(self):
        """AI-only runs: the AI swaps to owned abilities its mates don't use."""
        taken = {p.ability for p in self.players if not p.ai}
        for p in self.players:
            if not p.ai:
                continue
            free = [a for a in sorted(self.owned) if a not in taken]
            if free and (p.ability in taken or random.random() < 0.35):
                p.ability = random.choice(free)
            taken.add(p.ability)

    def ai_shop(self):
        """When nobody is human the AI does the shopping itself."""
        for _ in range(30):
            if self.raft.hull < self.max_hull() * 0.6 and self.coins >= REPAIR_COST:
                self.shop_buy(9)
                continue
            opts = [i for i, u in enumerate(UPGRADES)
                    if self.lvl(u["id"]) < MAX_LEVEL and self.coins >= self.upgrade_cost(u)]
            if not opts:
                break
            opts.sort(key=lambda i: self.lvl(UPGRADES[i]["id"]))
            self.shop_buy(opts[0])
        if self.prestige_unlocked():
            for _ in range(40):
                popts = [i for i, u in enumerate(PRESTIGE)
                         if self.lvl(u["id"]) < PRESTIGE_MAX
                         and self.plunder >= self.prestige_cost(u)]
                if not popts:
                    break
                popts.sort(key=lambda i: self.lvl(PRESTIGE[i]["id"]))
                self.buy_prestige(popts[0])
        new = [i for i, a in enumerate(ABILITIES)
               if i not in self.owned and self.coins >= a["cost"]]
        if new:
            self.buy_ability(random.choice(new))
        self.ai_equip()
        self.state = "play"

    # ---------- actions ----------
    def player_pos(self, p):
        ex, ey, nx, ny = self.raft.edge_point(p.angle)
        return self.raft.x + ex, self.raft.y + ey, nx, ny

    def activate_block(self, p):
        if p.block_charges >= 1.0 and p.block_timer <= 0:
            p.block_charges -= 1.0
            p.block_timer = 0.5
            p.word = "BLOCK!"
            p.flash = 0.5
            self.float_text(*self.player_pos(p)[:2], "BLOCK!", col("#7ae7ff"))
            self.snd.play("click", 0.8)

    def hurt_raft(self, amount):
        r = self.raft
        # Any crew member can time a half-second block to negate an incoming hit.
        blockers = [p for p in self.players if p.block_timer > 0]
        if blockers:
            blocker = max(blockers, key=lambda p: p.block_timer)
            blocker.block_timer = 0.0
            blocker.block_charges = min(3.0, blocker.block_charges + 1.5)
            self.float_text(r.x, r.y - 90, "BLOCKED! +1.5 CHARGES",
                            col("#7ae7ff"))
            self.snd.play("click", 1.0)
            return False
        if r.damage(amount):
            self.add_shake(3 + amount * 0.5)
            self.snd.play("hit")
            self.float_text(r.x, r.y - 90, f"-{int(amount)}", col("#ff6b6b"))
            return True
        return False

    def hit_enemy(self, e, dmg, color=GOLD):
        e.hp -= dmg
        self.float_text(e.x, e.y - 45, f"-{int(dmg)}", color)

    def fart(self, p):
        p.cooldown = self.fart_cooldown()
        p.flash = 0.4
        p.word = random.choice(["PFFT", "BRAAP", "TOOT", "PRRRT", "FRRP", "POOT"])
        wx, wy, nx, ny = self.player_pos(p)
        # Give human-controlled crew a modest, fixed push bonus.
        # This does not change with crew size; AI balancing stays separate.
        player_push_bonus = 1.20 if not p.ai else 1.0
        ai_push_scale = max(0.48, 1.0 - 0.16 * max(0, self.n_ai - 1)) if p.ai else 1.0
        total_push = self.fart_power() * player_push_bonus * ai_push_scale
        self.raft.push(nx, ny, total_push, self.max_speed())
        for _ in range(8):
            self.puffs.append(Puff(wx, wy, nx, ny))
        self.snd.play("fart", 0.8)
        self.add_shake(1.5)

    def use_ability(self, p):
        a = p.ability
        pm = self.ability_power()
        wx, wy, nx, ny = self.player_pos(p)
        p.ability_cd_max = ABILITIES[a]["cd"] * self.ability_cd_mult()
        p.ability_cd = p.ability_cd_max
        p.flash = 0.6
        r = self.raft
        if a == 0:      # Mega Blast
            p.word = "BLAAAST!"
            r.push(nx, ny, self.fart_power() * 2.5, self.max_speed())
            for _ in range(24):
                self.puffs.append(Puff(wx, wy, nx, ny, 1.2, True))
            if len(self.shockwaves) < MAX_SHOCKWAVES:
                self.shockwaves.append(Shockwave(wx, wy, 220 * math.sqrt(pm), 30 * pm))
            self.snd.play("mega")
            self.add_shake(11)
        elif a == 1:    # Stink Bomb
            p.word = "STINK!"
            if len(self.clouds) < MAX_CLOUDS:
                self.clouds.append(Cloud(wx + nx * 120, wy + ny * 120,
                                         80 * math.sqrt(pm), 14 * pm))
            for _ in range(10):
                self.puffs.append(Puff(wx, wy, nx, ny, 0.5, True))
            self.snd.play("fart2", 1.0)
            self.add_shake(3)
        elif a == 2:    # Fart Cannon
            p.word = "FIRE!"
            if len(self.shells) < MAX_SHELLS:
                self.shells.append(Shell(wx, wy, nx * 450, ny * 450, 25 * pm))
            r.push(nx, ny, 35, self.max_speed())
            for _ in range(6):
                self.puffs.append(Puff(wx, wy, nx, ny, 0.3))
            self.snd.play("boom", 0.8)
            self.add_shake(4)
        elif a == 3:    # Patch Kit
            p.word = "PATCH!"
            amount = self.max_hull() * 0.15
            r.hull = min(self.max_hull(), r.hull + amount)
            self.float_text(r.x, r.y - 30, f"+{int(amount)} hull (15%)", col("#60d394"))
            self.snd.play("heal")
        elif a == 4:    # Bubble Shield
            p.word = "BUBBLE!"
            r.shield = max(r.shield, 3.5 * pm)
            self.snd.play("shield")
        elif a == 5:    # Coin Vacuum
            p.word = "SUCK!"
            for c in self.coin_items + self.powerups:
                if math.hypot(c.x - r.x, c.y - r.y) < 900:
                    c.pull = 3.0
            self.snd.play("vac")
        elif a == 6:    # Gas Mine
            p.word = "MINE!"
            if len(self.mines) < MAX_MINES:
                self.mines.append(Mine(wx + nx * 40, wy + ny * 40, 45 * pm))
            for _ in range(5):
                self.puffs.append(Puff(wx, wy, nx, ny, 0.5))
            self.snd.play("fart1", 0.8)
        elif a == 7:    # Turbo Toot
            p.word = "TURBO!"
            r.turbo = max(r.turbo, 4.0)
            r.push(nx, ny, self.fart_power() * 1.5, self.max_speed())
            for _ in range(16):
                self.puffs.append(Puff(wx, wy, nx, ny, 0.9, True))
            self.snd.play("mega", 0.6)
            self.add_shake(6)

    # ---------- AI crew ----------
    def ai_navigate(self):
        """Work out which way the raft should be pushed (shared by all AI)."""
        r = self.raft
        isl = self.island
        dx, dy = isl.x - r.x, isl.y - r.y
        d = math.hypot(dx, dy) or 1
        bx, by = dx / d, dy / d
        vx, vy = bx, by
        # coins and power-ups worth a detour
        if d > 250:
            best, bd = None, 520
            for c in self.coin_items + self.powerups:
                cd = math.hypot(c.x - r.x, c.y - r.y)
                bonus = 120 if isinstance(c, Powerup) else 0
                if cd - bonus < bd:
                    best, bd = c, cd - bonus
            if best is not None:
                cx, cy = best.x - r.x, best.y - r.y
                cd = math.hypot(cx, cy) or 1
                wgt = 0.5 + 0.9 * (1 - min(1.0, bd / 600))
                vx += cx / cd * wgt
                vy += cy / cd * wgt
        # stay away from rocks, logs and whirlpools
        for o in self.obstacles:
            ox, oy = r.x - o.x, r.y - o.y
            od = math.hypot(ox, oy) or 1
            reach = o.r + r.radius + 280
            if od < reach:
                tox, toy = -ox / od, -oy / od
                if tox * bx + toy * by > -0.3 or tox * r.vx + toy * r.vy > 0:
                    w = (reach - od) / reach
                    vx += ox / od * w * 2.4
                    vy += oy / od * w * 2.4
        for w_ in self.whirls:
            ox, oy = r.x - w_.x, r.y - w_.y
            od = math.hypot(ox, oy) or 1
            reach = w_.r * 1.7 + r.radius + 60
            if od < reach:
                w = (reach - od) / reach
                vx += ox / od * w * 3.0
                vy += oy / od * w * 3.0
        for hm in self.hmines:
            ox, oy = r.x - hm.x, r.y - hm.y
            od = math.hypot(ox, oy) or 1
            reach = r.radius + 200
            if od < reach:
                w = (reach - od) / reach
                vx += ox / od * w * 2.0
                vy += oy / od * w * 2.0
        # lean against the wind a little
        vx -= math.cos(self.wind_ang) * self.wind_str / 90
        vy -= math.sin(self.wind_ang) * self.wind_str / 90
        n = math.hypot(vx, vy) or 1
        self.nav = (vx / n, vy / n)

    def nearest_enemy(self):
        r = self.raft
        best, bd = None, 1e9
        for e in self.enemies():
            d = math.hypot(e.x - r.x, e.y - r.y)
            if d < bd:
                best, bd = e, d
        return best, bd

    def ai_decide(self, p):
        r = self.raft
        lvl = self.settings["ai"]
        nvx, nvy = self.nav
        ang = math.atan2(nvy, nvx) + random.uniform(-1, 1) * AI_NOISE[lvl]
        # to push the raft along `ang` the player stands on the opposite side
        p.target = ang + math.pi + p.offset
        fwd = r.vx * nvx + r.vy * nvy
        p.want_fart = fwd < AI_FWD[lvl] * self.max_speed()
        p.gunner = False
        enemy, ed = self.nearest_enemy()
        ready = p.ability_cd <= 0
        a = p.ability
        if a == 2 and ready and enemy is not None and ed < 700:
            # gunner: aim at the enemy instead of steering
            p.target = math.atan2(enemy.y - r.y, enemy.x - r.x)
            p.gunner = True
            p.want_fart = False
            return
        if not ready:
            return
        use = False
        if a == 0:
            use = ed < 260 or (self.island and math.hypot(self.island.x - r.x,
                                                           self.island.y - r.y) > 1000
                               and random.random() < 0.15)
        elif a == 1:
            use = ed < 360
        elif a == 3:
            use = r.hull < self.max_hull() * 0.6
        elif a == 4:
            near_ball = any(math.hypot(cb.x - r.x, cb.y - r.y) < 200 for cb in self.cannonballs)
            use = near_ball or (r.hull < self.max_hull() * 0.5 and ed < 300)
        elif a == 5:
            use = sum(1 for c in self.coin_items + self.powerups
                      if math.hypot(c.x - r.x, c.y - r.y) < 700) >= 3
        elif a == 6:
            use = ed < 420
        elif a == 7:
            use = math.hypot(self.island.x - r.x, self.island.y - r.y) > 600 \
                and r.turbo <= 0
        if use and r.shield <= 0 or (use and a != 4):
            self.use_ability(p)

    def update_ai(self, dt):
        if not any(p.ai for p in self.players):
            return
        self.nav_t -= dt
        if self.nav_t <= 0:
            self.nav_t = 0.15
            self.ai_navigate()
        lvl = self.settings["ai"]
        for p in self.players:
            if not p.ai:
                continue
            p.think -= dt
            if p.think <= 0:
                p.think = AI_REACT[lvl] * random.uniform(0.7, 1.3)
                self.ai_decide(p)
            diff = angle_diff(p.angle, p.target)
            p.ai_dir = 0 if abs(diff) < 0.05 else (1 if diff > 0 else -1)
            if p.gunner:
                if abs(diff) < 0.15 and p.ability_cd <= 0 and p.ability == 2:
                    self.use_ability(p)
                    p.gunner = False
            elif p.want_fart and p.cooldown <= 0 and abs(diff) < 0.3:
                self.fart(p)
                p.want_fart = False

    # ---------- update ----------
    def update(self, dt):
        self.snd.enabled = self.settings["sound"]
        if self.state in ("menu_count", "menu_ai_count", "menu_abilities"):
            self.raft.x += 25 * dt
        elif self.state == "play":
            self.update_play(dt)
        elif self.state == "over":
            for p in self.puffs:
                p.update(dt)
            self.puffs = [p for p in self.puffs if p.life > 0]
        # screen shake decays and produces an offset for this frame
        self.shake_mag *= 0.88 ** (dt * 60)
        if self.shake_mag < 0.3:
            self.shake_mag = 0.0
        if self.settings["shake"] and self.shake_mag > 0:
            self.sx = random.uniform(-1, 1) * self.shake_mag
            self.sy = random.uniform(-1, 1) * self.shake_mag
        else:
            self.sx = self.sy = 0.0

    def update_camera(self, dt):
        """3D camera: glides after the raft, looks ahead, zooms with speed and
        (in chase mode) swings round to face the way the raft is travelling."""
        r = self.raft
        spd = math.hypot(r.vx, r.vy)
        k = 1 - math.exp(-4.0 * dt)
        self.cam_x += (r.x + r.vx * 0.45 - self.cam_x) * k
        self.cam_y += (r.y + r.vy * 0.45 - self.cam_y) * k
        target_dist = CAM_DIST + min(spd, 600) * 0.25
        self.cam_dist += (target_dist - self.cam_dist) * (1 - math.exp(-2.0 * dt))
        rot = (("q" in self.keys) - ("e" in self.keys)) * 1.6 * dt
        if self.settings["chase"]:
            self.yaw_off += rot
            if spd > 45:
                heading = math.atan2(-r.vy, r.vx)
                diff = angle_diff(self.yaw, heading + self.yaw_off)
                strength = min(1.0, (spd - 45) / 80)
                self.yaw += diff * (1 - math.exp(-1.6 * dt)) * strength
        else:
            self.yaw += rot

    def update_events(self, dt):
        """Wind, and timers that bring in new hazards and pick-ups."""
        self.wind_t -= dt
        if self.wind_t <= 0:
            self.wind_t = random.uniform(18, 30)
            if random.random() < 0.3:
                self.wind_str = 0.0
                self.announce("The wind dies down")
            else:
                self.wind_ang = random.uniform(0, math.tau)
                self.wind_str = random.uniform(15, 45)
                self.announce("The wind shifts!")
        self.banner_t -= dt

        self.whirl_timer -= dt
        if self.whirl_timer <= 0:
            self.whirl_timer = random.uniform(6, 12)
            if self.score >= 1 and len(self.whirls) < MAX_WHIRLPOOLS:
                self.spawn_whirl()
        self.whirls = [w for w in self.whirls
                       if math.hypot(w.x - self.raft.x, w.y - self.raft.y) < 1800]
        self.powerup_timer -= dt
        if self.powerup_timer <= 0:
            self.powerup_timer = random.uniform(8, 14)
            if len(self.powerups) < MAX_POWERUPS:
                self.spawn_powerup()
        self.powerups = [c for c in self.powerups
                         if math.hypot(c.x - self.raft.x, c.y - self.raft.y) < 1600]

    def apply_whirls(self, dt):
        r = self.raft
        dmult = PIRATE_DMG_MULT[self.settings["difficulty"]]
        for w in self.whirls:
            w.spin += dt * 2.2
            dx, dy = w.x - r.x, w.y - r.y
            d = math.hypot(dx, dy) or 1
            reach = w.r * 1.7
            if d < reach:
                k = 1 - d / reach
                r.vx += dx / d * 380 * k * dt - dy / d * 150 * k * dt
                r.vy += dy / d * 380 * k * dt + dx / d * 150 * k * dt
                if d < w.r * 0.35:
                    self.hurt_raft(6 * dmult)

    def update_play(self, dt):
        r = self.raft
        self.run_time += dt
        self.leg_time += dt
        self.update_events(dt)
        self.update_ai(dt)
        for p in self.players:
            p.update(dt, self.keys, self.walk_speed())
            # Holding the fart key auto-fires again whenever the cooldown expires.
            if not p.ai and p.k["fart"] in self.keys and p.cooldown <= 0:
                self.fart(p)
        r.vx += math.cos(self.wind_ang) * self.wind_str * dt
        r.vy += math.sin(self.wind_ang) * self.wind_str * dt
        self.apply_whirls(dt)
        r.update(dt, self.drag_base(), self.max_speed())
        self.update_camera(dt)
        for o in self.obstacles:
            o.update(dt)
        self.collide_obstacles()
        self.update_pirates(dt)
        self.update_sharks(dt)
        self.update_projectiles(dt)
        self.update_hmines(dt)
        self.update_mines(dt)
        self.update_coins(dt)

        for group in (self.puffs, self.texts):
            for item in group:
                item.update(dt)
        self.puffs = [p for p in self.puffs if p.life > 0]
        self.texts = [t for t in self.texts if t.life > 0]

        self.obstacles = [o for o in self.obstacles
                          if math.hypot(o.x - r.x, o.y - r.y) < 1500]
        self.coin_items = [c for c in self.coin_items
                           if math.hypot(c.x - r.x, c.y - r.y) < 1500]
        for _ in range(20):
            if len(self.obstacles) < OBSTACLE_COUNT:
                self.spawn_obstacle()
            if len(self.coin_items) < COIN_COUNT:
                self.spawn_coin()

        isl = self.island
        if math.hypot(r.x - isl.x, r.y - isl.y) < isl.r + 30:
            self.reach_island()

        # Final per-frame limits also cover bursts of loot and visual effects.
        limits = (
            (self.pirates, MAX_PIRATES + 4), (self.sharks, MAX_SHARKS),
            (self.hmines, MAX_HOSTILE_MINES),
            (self.whirls, MAX_WHIRLPOOLS), (self.obstacles, OBSTACLE_COUNT),
            (self.powerups, MAX_POWERUPS),
            (self.cannonballs, MAX_CANNONBALLS), (self.shells, MAX_SHELLS),
            (self.clouds, MAX_CLOUDS), (self.mines, MAX_MINES),
            (self.shockwaves, MAX_SHOCKWAVES), (self.puffs, MAX_PUFFS),
            (self.texts, MAX_FLOAT_TEXTS),
        )
        for collection, maximum in limits:
            if len(collection) > maximum:
                del collection[:-maximum]

        if r.hull <= 0:
            r.hull = 0
            self.best = max(self.best, self.score)
            self.snd.play("gameover")
            self.add_shake(14)
            self.state = "over"

    def reach_island(self):
        isl = self.island
        self.score += 1
        reward = ISLAND_REWARD
        parts = [f"+{ISLAND_REWARD}"]
        if isl.kind == "treasure":
            reward += TREASURE_BONUS
            parts.append(f"+{TREASURE_BONUS} treasure")
        elif isl.kind == "ruins":
            reward += 15
            parts.append("+15 ancient ruins")
        bonus = max(0, int((60 - self.leg_time) / 3))
        if bonus:
            reward += bonus
            parts.append(f"+{bonus} speed bonus")
        self.coins += reward
        self.leg_time = 0.0
        self.shop_msg = "Island reached! " + "  ".join(parts) + " coins"
        self.shop_page = 0
        self.shop_return = "play"
        self.spawn_island()
        self.snd.play("island")
        self.add_shake(3)
        self.keys.clear()
        if self.settings["pirates"] and self.score % BOSS_EVERY == 0:
            self.spawn_pirate("boss")
            self.announce("WARNING: PIRATE FLAGSHIP!", 4.0)
            self.snd.play("horn")
        self.state = "shop"
        if self.n_players == 0:
            self.ai_shop()

    def collide_obstacles(self):
        r = self.raft
        for o in self.obstacles:
            dx, dy = r.x - o.x, r.y - o.y
            d = math.hypot(dx, dy)
            min_d = r.radius + 10 + o.r
            if d >= min_d or d == 0:
                continue
            nx, ny = dx / d, dy / d
            r.x += nx * (min_d - d)
            r.y += ny * (min_d - d)
            vn = (r.vx - o.vx) * nx + (r.vy - o.vy) * ny
            if vn < 0:
                r.vx -= 1.6 * vn * nx
                r.vy -= 1.6 * vn * ny
                if -vn > 60:
                    self.hurt_raft(min(25, -vn * 0.1))

    def update_pirates(self, dt):
        r = self.raft
        self.pirate_timer -= dt
        if self.pirate_timer <= 0:
            if self.settings["pirates"] and len(self.pirates) < self.max_pirates():
                self.spawn_pirate()
            self.pirate_timer = max(7.0, random.uniform(10, 16) - 0.1 * self.pirate_kills)
        if self.pending_boss and self.settings["pirates"] \
                and not any(p.kind == "boss" for p in self.pirates):
            self.pending_boss = False
            self.spawn_pirate("boss")
            self.announce("THE ADMIRAL'S FLAGSHIP IS HUNTING YOU!", 4.0)
            self.snd.play("horn")

        speed = min(140, 85 + 3 * self.score)
        dmult = PIRATE_DMG_MULT[self.settings["difficulty"]]
        for pr in self.pirates:
            pr.hit_cd -= dt
            pr.heal_t -= dt
            dx, dy = r.x - pr.x, r.y - pr.y
            d = math.hypot(dx, dy) or 1
            ux, uy = dx / d, dy / d
            rammer = pr.kind in ("ram", "dinghy")
            if rammer:
                sway = math.sin(self.frame * 0.04 + pr.orbit * 3) * 0.45 * min(1.0, d / 450)
                a = math.atan2(dy, dx) + sway
                tvx, tvy = math.cos(a) * speed * 1.5, math.sin(a) * speed * 1.5
            else:
                spd = speed * (0.7 if pr.kind == "boss" else 1.0)
                far, near = (420, 320) if pr.kind == "boss" else (300, 220)
                if d > far:
                    tvx, tvy = ux * spd, uy * spd
                elif d < near:
                    tvx, tvy = -ux * spd * 0.7, -uy * spd * 0.7
                else:
                    tvx = -uy * pr.orbit * 60
                    tvy = ux * pr.orbit * 60
            pr.vx += (tvx - pr.vx) * 2 * dt
            pr.vy += (tvy - pr.vy) * 2 * dt
            pr.x += pr.vx * dt
            pr.y += pr.vy * dt
            if "bulwark" in pr.abil:
                # the shield turns slowly, so you can get round the side of it
                turn = angle_diff(pr.face, math.atan2(dy, dx))
                pr.face += max(-1.2 * dt, min(1.2 * dt, turn))
            self.update_pirate_abilities(pr, dt, d)

            pr.fire_t -= dt
            if not rammer and pr.fire_t <= 0 and d < 650 and pr.charging is None:
                base = math.atan2(dy, dx)
                if pr.kind == "boss":
                    shots, dmg = (-0.22, 0.0, 0.22), 8
                    pr.fire_t = random.uniform(2.0, 3.0)
                else:
                    shots, dmg = (random.uniform(-0.08, 0.08),), 10
                    pr.fire_t = random.uniform(2.5, 4.0)
                for off in shots:
                    if len(self.cannonballs) >= MAX_CANNONBALLS:
                        break
                    ang = base + off
                    self.cannonballs.append(Cannonball(pr.x, pr.y, math.cos(ang) * 230,
                                                       math.sin(ang) * 230, dmg))
                self.snd.play("boom", 0.35)

            min_d = r.radius + 10 + pr.r
            d = math.hypot(r.x - pr.x, r.y - pr.y)
            if 0 < d < min_d:
                nx, ny = (r.x - pr.x) / d, (r.y - pr.y) / d
                pr.x -= nx * (min_d - d)
                pr.y -= ny * (min_d - d)
                rel = (r.vx - pr.vx) * nx + (r.vy - pr.vy) * ny
                if rel < 0:
                    impact = -rel
                    r.vx -= 1.2 * rel * nx
                    r.vy -= 1.2 * rel * ny
                    pr.vx -= nx * impact * 0.8
                    pr.vy -= ny * impact * 0.8
                    if impact > 70 and pr.hit_cd <= 0:
                        dmg = impact * 0.12
                        pr.hit_cd = 0.5
                        self.hit_enemy(pr, dmg)
                        self.add_shake(5)
                        self.snd.play("hit", 0.7)
                        self.hurt_raft({"gun": 6, "ram": 14, "boss": 10,
                                        "dinghy": 4}[pr.kind] * dmult)

        alive, spawned = [], []
        for pr in self.pirates:
            if pr.hp > 0:
                alive.append(pr)
                continue
            self.kills += 1
            if pr.kind != "dinghy":
                self.pirate_kills += 1
                if self.pirate_kills % ADMIRAL_EVERY == 0:
                    self.pending_boss = True
                if self.pirate_kills in (6, 14, 30):
                    self.announce("The pirates have learned new tricks!", 3.5)
            if pr.kind == "boss":
                bounty, plunder = 80 + 5 * self.score, 25
                if len(self.powerups) < MAX_POWERUPS:
                    self.powerups.append(Powerup(pr.x, pr.y, "crate"))
                self.announce("FLAGSHIP SUNK!", 3.0)
            elif pr.kind == "ram":
                bounty, plunder = 12 + 2 * self.score, 4
            elif pr.kind == "dinghy":
                bounty, plunder = 4, 1
            else:
                bounty, plunder = PIRATE_BOUNTY + 3 * self.score, 4
            bounty = int(bounty * self.coin_mult())
            gain = self.plunder_roll(plunder)
            self.coins += bounty
            self.plunder += gain
            self.float_text(pr.x, pr.y - 25, f"+{bounty} bounty", GOLD)
            self.float_text(pr.x, pr.y + 22, f"+{gain} plunder", col("#ffb86b"))
            drop_count = 10 if pr.kind == "boss" else (1 if pr.kind == "dinghy"
                                                       else random.randint(3, 5))
            # Enemy bounty coins are loot, not ambient spawns: never discard
            # them just because several enemies were defeated together.
            for _ in range(drop_count):
                self.coin_items.append(Coin(pr.x + random.uniform(-40, 40),
                                            pr.y + random.uniform(-40, 40), 5))
            if "splitter" in pr.abil:
                hp = 14 * PIRATE_HP_MULT[self.settings["difficulty"]]
                for sgn in (-1, 1):
                    spawned.append(Pirate(pr.x + sgn * 30, pr.y + random.uniform(-20, 20),
                                          hp, "dinghy"))
                self.float_text(pr.x, pr.y - 55, "SPLIT!", col("#ffd23f"))
            self.float_text(pr.x, pr.y, "SUNK!", GOLD)
            for _ in range(10):
                a = random.uniform(0, math.tau)
                self.puffs.append(Puff(pr.x, pr.y, math.cos(a), math.sin(a), 0.2, True))
            self.snd.play("sunk")
            self.add_shake(7 if pr.kind != "boss" else 12)
        self.pirates = alive + spawned

    # ---- pirate tricks: every one has a wind-up the player can read ----
    def update_pirate_abilities(self, pr, dt, d):
        if pr.charging:
            pr.charging[1] -= dt
            if pr.charging[1] <= 0:
                name = pr.charging[0]
                pr.charging = None
                self.fire_pirate_ability(pr, name)
            return
        for name in pr.abil:
            spec = PIRATE_ABILITIES[name]
            if spec["cd"] <= 0:
                continue                      # passive trick (Bulwark, Splitter)
            pr.cd[name] -= dt
            if pr.cd[name] > 0:
                continue
            if not self.pirate_ready(pr, name, d):
                pr.cd[name] = 0.4
                continue
            pr.cd[name] = spec["cd"] * random.uniform(0.9, 1.25)
            pr.charging = [name, spec["wind"], spec["wind"]]
            break

    def pirate_ready(self, pr, name, d):
        if name == "broadside":
            return d < 620
        if name == "chainshot":
            return d < 650
        if name == "minelayer":
            return d < 750 and len(self.hmines) < MAX_HOSTILE_MINES
        if name == "blinker":
            return d < 230
        if name == "bosun":
            return any(o is not pr and o.hp < o.max_hp * 0.85
                       and math.hypot(o.x - pr.x, o.y - pr.y) < 550 for o in self.pirates)
        if name == "beastmaster":
            return len(self.sharks) < MAX_SHARKS
        return False

    def fire_pirate_ability(self, pr, name):
        r = self.raft
        base = math.atan2(r.y - pr.y, r.x - pr.x)
        if name == "broadside":
            for off in (-0.36, -0.18, 0.0, 0.18, 0.36):
                if len(self.cannonballs) >= MAX_CANNONBALLS:
                    break
                a = base + off
                self.cannonballs.append(Cannonball(pr.x, pr.y, math.cos(a) * 260,
                                                   math.sin(a) * 260, 8))
            self.snd.play("boom", 0.5)
        elif name == "chainshot":
            if len(self.cannonballs) < MAX_CANNONBALLS:
                cb = Cannonball(pr.x, pr.y, math.cos(base) * 120, math.sin(base) * 120, 14)
                cb.homing = 1.6
                cb.life = 6.0
                self.cannonballs.append(cb)
            self.snd.play("boom", 0.4)
        elif name == "minelayer":
            a = random.uniform(0, math.tau)
            dist = random.uniform(140, 220)
            self.hmines.append(HostileMine(r.x + r.vx + math.cos(a) * dist,
                                           r.y + r.vy + math.sin(a) * dist, 12))
            self.float_text(pr.x, pr.y - 50, "mine!", col("#ff9f1c"))
        elif name == "blinker":
            for _ in range(8):
                a = random.uniform(0, math.tau)
                self.puffs.append(Puff(pr.x, pr.y, math.cos(a), math.sin(a), 0.2, True))
            a = random.uniform(0, math.tau)
            dist = random.uniform(480, 560)
            pr.x, pr.y = r.x + math.cos(a) * dist, r.y + math.sin(a) * dist
            pr.vx = pr.vy = 0.0
            self.snd.play("powerup", 0.4)
        elif name == "bosun":
            hurt = [o for o in self.pirates if o is not pr and o.hp < o.max_hp * 0.85
                    and math.hypot(o.x - pr.x, o.y - pr.y) < 550]
            if hurt:
                t = min(hurt, key=lambda o: o.hp / o.max_hp)
                t.hp = min(t.max_hp, t.hp + t.max_hp * 0.3)
                pr.heal_to, pr.heal_t = t, 0.7
                self.float_text(t.x, t.y - 45, "+heal", col("#60d394"))
                self.snd.play("heal", 0.5)
        elif name == "beastmaster":
            if len(self.sharks) < MAX_SHARKS:
                hp = min(60, 24 + 4 * self.score) * PIRATE_HP_MULT[self.settings["difficulty"]]
                self.sharks.append(Shark(pr.x, pr.y, hp))
                self.float_text(pr.x, pr.y - 50, "shark!", col("#7ae7ff"))
                self.snd.play("bite", 0.5)

    def update_hmines(self, dt):
        r = self.raft
        dmult = PIRATE_DMG_MULT[self.settings["difficulty"]]
        keep = []
        for m in self.hmines:
            m.life -= dt
            m.arm -= dt
            if m.arm <= 0 and math.hypot(m.x - r.x, m.y - r.y) < r.radius + 22:
                self.hurt_raft(m.dmg * dmult)
                for _ in range(10):
                    a = random.uniform(0, math.tau)
                    self.puffs.append(Puff(m.x, m.y, math.cos(a), math.sin(a), 0.2, True))
                self.snd.play("boom", 0.6)
                self.add_shake(4)
                continue
            if m.life > 0:
                keep.append(m)
        self.hmines = keep

    def update_sharks(self, dt):
        r = self.raft
        dmult = PIRATE_DMG_MULT[self.settings["difficulty"]]
        self.shark_timer -= dt
        if self.shark_timer <= 0:
            if self.settings["pirates"] and self.score >= 2 \
                    and len(self.sharks) < MAX_SHARKS:
                self.spawn_shark()
                self.announce("Sharks in the water!", 2.5)
            self.shark_timer = random.uniform(16, 26)
        speed = min(170, 120 + 4 * self.score)
        for s in self.sharks:
            s.bite_cd -= dt
            s.hit_cd -= dt
            s.phase += dt
            dx, dy = r.x - s.x, r.y - s.y
            d = math.hypot(dx, dy) or 1
            ux, uy = dx / d, dy / d
            if d > r.radius + 170 or math.sin(s.phase * 1.4) > 0.2:
                tvx, tvy = ux * speed * 1.2, uy * speed * 1.2
            else:
                tvx, tvy = -uy * speed * 0.8, ux * speed * 0.8
            s.vx += (tvx - s.vx) * 3 * dt
            s.vy += (tvy - s.vy) * 3 * dt
            s.x += s.vx * dt
            s.y += s.vy * dt
            sp = math.hypot(s.vx, s.vy)
            if sp > 5:
                s.hx, s.hy = s.vx / sp, s.vy / sp
            min_d = r.radius + 8 + s.r
            d = math.hypot(r.x - s.x, r.y - s.y)
            if 0 < d < min_d:
                nx, ny = (r.x - s.x) / d, (r.y - s.y) / d
                s.x -= nx * (min_d - d)
                s.y -= ny * (min_d - d)
                rel = (r.vx - s.vx) * nx + (r.vy - s.vy) * ny
                if s.bite_cd <= 0:
                    s.bite_cd = 1.3
                    if self.hurt_raft(7 * dmult):
                        self.snd.play("bite")
                    s.vx, s.vy = -nx * 160, -ny * 160
                if rel < -90 and s.hit_cd <= 0:
                    s.hit_cd = 0.5
                    self.hit_enemy(s, -rel * 0.12)
                    s.vx -= nx * -rel * 0.8
                    s.vy -= ny * -rel * 0.8
                    self.snd.play("hit", 0.5)
        alive = []
        for s in self.sharks:
            if s.hp > 0:
                alive.append(s)
                continue
            self.kills += 1
            bounty = int((10 + self.score) * self.coin_mult())
            self.coins += bounty
            self.plunder += self.plunder_roll(3)
            self.float_text(s.x, s.y - 25, f"+{bounty} shark!  +3 plunder", GOLD)
            # Shark loot also remains available regardless of other drops.
            for _ in range(2):
                self.coin_items.append(Coin(s.x + random.uniform(-30, 30),
                                            s.y + random.uniform(-30, 30), 5))
            for _ in range(6):
                a = random.uniform(0, math.tau)
                self.puffs.append(Puff(s.x, s.y, math.cos(a), math.sin(a), 0.2, True))
            self.snd.play("sunk", 0.8)
            self.add_shake(4)
        self.sharks = alive

    def update_projectiles(self, dt):
        r = self.raft
        dmult = PIRATE_DMG_MULT[self.settings["difficulty"]]
        keep = []
        for cb in self.cannonballs:
            if cb.homing:
                cur = math.atan2(cb.vy, cb.vx)
                turn = angle_diff(cur, math.atan2(r.y - cb.y, r.x - cb.x))
                turn = max(-cb.homing * dt, min(cb.homing * dt, turn))
                sp = math.hypot(cb.vx, cb.vy)
                cb.vx, cb.vy = math.cos(cur + turn) * sp, math.sin(cur + turn) * sp
            cb.x += cb.vx * dt
            cb.y += cb.vy * dt
            cb.life -= dt
            if math.hypot(cb.x - r.x, cb.y - r.y) < r.radius + 8:
                if not self.hurt_raft(cb.dmg * dmult):
                    self.float_text(cb.x, cb.y, "blocked", col("#7ae7ff"))
                continue
            if cb.life > 0:
                keep.append(cb)
        self.cannonballs = keep

        keep = []
        for sh in self.shells:
            # Homing gas shells gently steer toward the nearest living enemy.
            targets = self.enemies()
            if targets:
                target = min(targets, key=lambda e: math.hypot(e.x - sh.x, e.y - sh.y))
                dx, dy = target.x - sh.x, target.y - sh.y
                desired = math.atan2(dy, dx)
                current = math.atan2(sh.vy, sh.vx)
                delta = (desired - current + math.pi) % math.tau - math.pi
                turn = max(-sh.turn_rate * dt, min(sh.turn_rate * dt, delta))
                angle = current + turn
                sh.vx = math.cos(angle) * sh.speed
                sh.vy = math.sin(angle) * sh.speed
            sh.x += sh.vx * dt
            sh.y += sh.vy * dt
            sh.life -= dt
            hit = False
            for e in self.enemies():
                if math.hypot(sh.x - e.x, sh.y - e.y) < e.r + 8:
                    if "bulwark" in getattr(e, "abil", ()) and abs(angle_diff(
                            e.face, math.atan2(sh.y - e.y, sh.x - e.x))) < 1.0:
                        self.float_text(sh.x, sh.y - 20, "deflected", col("#9fb3c8"))
                        self.snd.play("click", 0.8)
                    else:
                        self.hit_enemy(e, sh.dmg)
                        self.snd.play("hit", 0.6)
                        self.add_shake(3)
                    hit = True
                    break
            if not hit and sh.life > 0:
                keep.append(sh)
        self.shells = keep

        for cl in self.clouds:
            cl.life -= dt
            for e in self.enemies():
                if math.hypot(cl.x - e.x, cl.y - e.y) < cl.r + e.r:
                    e.hp -= cl.dps * dt
        self.clouds = [c for c in self.clouds if c.life > 0]

        for sw in self.shockwaves:
            sw.life -= dt
            for e in self.enemies():
                if id(e) in sw.hit:
                    continue
                d = math.hypot(sw.x - e.x, sw.y - e.y)
                if d < sw.radius + e.r:
                    sw.hit.add(id(e))
                    self.hit_enemy(e, sw.dmg, col("#ff9f1c"))
                    d = d or 1
                    e.vx += (e.x - sw.x) / d * 260
                    e.vy += (e.y - sw.y) / d * 260
        self.shockwaves = [s for s in self.shockwaves if s.life > 0]

    def update_mines(self, dt):
        keep = []
        for m in self.mines:
            m.life -= dt
            m.arm -= dt
            boom = False
            if m.arm <= 0:
                for e in self.enemies():
                    if math.hypot(m.x - e.x, m.y - e.y) < e.r + 40:
                        boom = True
                        break
            if boom:
                for e in self.enemies():
                    d = math.hypot(m.x - e.x, m.y - e.y)
                    if d < 130 + e.r:
                        self.hit_enemy(e, m.dmg, col("#ff6b6b"))
                        d = d or 1
                        e.vx += (e.x - m.x) / d * 220
                        e.vy += (e.y - m.y) / d * 220
                for _ in range(12):
                    a = random.uniform(0, math.tau)
                    self.puffs.append(Puff(m.x, m.y, math.cos(a), math.sin(a), 0.2, True))
                if len(self.shockwaves) < MAX_SHOCKWAVES:
                    self.shockwaves.append(Shockwave(m.x, m.y, 130, 0))
                self.snd.play("boom", 0.9)
                self.add_shake(6)
            elif m.life > 0:
                keep.append(m)
        self.mines = keep

    def update_coins(self, dt):
        r = self.raft
        reach = r.radius + self.magnet_range()
        keep = []
        for c in self.coin_items:
            dx, dy = r.x - c.x, r.y - c.y
            d = math.hypot(dx, dy) or 1
            if d < r.radius + 6:
                self.coins += c.value
                self.float_text(c.x, c.y, f"+{c.value}", GOLD)
                self.snd.play("coin", 0.7)
                continue
            if c.pull > 0:
                c.pull -= dt
                c.x += dx / d * 700 * dt
                c.y += dy / d * 700 * dt
            elif d < reach:
                c.x += dx / d * 220 * dt
                c.y += dy / d * 220 * dt
            keep.append(c)
        self.coin_items = keep

        keep = []
        for pu in self.powerups:
            dx, dy = r.x - pu.x, r.y - pu.y
            d = math.hypot(dx, dy) or 1
            if d < r.radius + 16:
                self.collect_powerup(pu)
                continue
            if pu.pull > 0:
                pu.pull -= dt
                pu.x += dx / d * 700 * dt
                pu.y += dy / d * 700 * dt
            elif d < reach:
                pu.x += dx / d * 220 * dt
                pu.y += dy / d * 220 * dt
            keep.append(pu)
        self.powerups = keep

    def collect_powerup(self, pu):
        r = self.raft
        if pu.kind == "crate":
            r.hull = min(self.max_hull(), r.hull + 30)
            self.coins += 10
            self.float_text(r.x, r.y - 60, "+30 hull  +10 coins", col("#60d394"))
        elif pu.kind == "beans":
            r.beans = 10.0
            self.float_text(r.x, r.y - 60, "BEANS! Stronger farts", col("#e0a050"))
        elif pu.kind == "turbo":
            r.turbo = 6.0
            self.float_text(r.x, r.y - 60, "TURBO!", col("#6ec5ff"))
        elif pu.kind == "shield":
            r.shield = max(r.shield, 5.0)
            self.float_text(r.x, r.y - 60, "BUBBLE SHIELD!", col("#7ae7ff"))
        elif pu.kind == "treasure":
            self.coins += 35
            self.float_text(r.x, r.y - 60, "+35 TREASURE COINS!", GOLD)
        self.snd.play("powerup")

    # ======================================================== drawing =====
    # ---- tiny drawing helpers ----
    def font(self, size, bold):
        key = (size, bold)
        f = self.fonts.get(key)
        if f is None:
            f = pygame.font.Font(None, size)
            if bold:
                f.set_bold(True)
            self.fonts[key] = f
        return f

    def text(self, s, x, y, size=24, color=WHITE, anchor="topleft", bold=False):
        key = (s, size, color, bold)
        img = self.text_cache.get(key)
        if img is None:
            if len(self.text_cache) > 700:
                self.text_cache.clear()
            img = self.font(size, bold).render(s, True, color)
            self.text_cache[key] = img
        rect = img.get_rect()
        setattr(rect, anchor, (int(x), int(y)))
        self.screen.blit(img, rect)

    def circle(self, color, x, y, r, width=0):
        pygame.draw.circle(self.screen, color, (int(x), int(y)), max(1, int(r)), width)

    def oval(self, color, x1, y1, x2, y2, width=0):
        x1, x2 = min(x1, x2), max(x1, x2)
        y1, y2 = min(y1, y2), max(y1, y2)
        rect = pygame.Rect(int(x1), int(y1), max(2, int(x2 - x1)), max(2, int(y2 - y1)))
        pygame.draw.ellipse(self.screen, color, rect, width)

    def rect(self, color, x1, y1, x2, y2, width=0):
        rect = pygame.Rect(int(x1), int(y1), max(1, int(x2 - x1)), max(1, int(y2 - y1)))
        pygame.draw.rect(self.screen, color, rect, width)

    def line(self, color, x1, y1, x2, y2, width=1):
        pygame.draw.line(self.screen, color, (int(x1), int(y1)), (int(x2), int(y2)),
                         max(1, int(width)))

    def poly(self, pts, fill=None, outline=None, width=2):
        if not pts or len(pts) < 3:
            return
        ipts = [(int(x), int(y)) for x, y in pts]
        if fill is not None:
            pygame.draw.polygon(self.screen, fill, ipts)
        if outline is not None:
            pygame.draw.polygon(self.screen, outline, ipts, max(1, int(width)))

    def fx_circle(self, color, x, y, r, alpha):
        """Translucent circle (real alpha when Effects = High)."""
        if self.fx is not None and self.settings["fx"] == 1:
            pygame.draw.circle(self.fx, (color[0], color[1], color[2], int(255 * alpha)),
                               (int(x), int(y)), max(1, int(r)))
            self.fx_used = True
        else:
            mixed = tuple(int(color[i] * alpha + WATER[i] * (1 - alpha)) for i in range(3))
            self.circle(mixed, x, y, r)

    def fx_poly(self, pts, color, alpha):
        if not pts or len(pts) < 3:
            return
        ipts = [(int(x), int(y)) for x, y in pts]
        if self.fx is not None and self.settings["fx"] == 1:
            pygame.draw.polygon(self.fx, (color[0], color[1], color[2], int(255 * alpha)), ipts)
            self.fx_used = True
        else:
            mixed = tuple(int(color[i] * alpha + WATER[i] * (1 - alpha)) for i in range(3))
            pygame.draw.polygon(self.screen, mixed, ipts)

    def flush_fx(self):
        if self.fx_used:
            self.screen.blit(self.fx, (0, 0))
            self.fx.fill((0, 0, 0, 0))
            self.fx_used = False

    def skull(self, x, y, size):
        self.circle(WHITE, x, y - size * 0.1, size)
        self.rect(WHITE, x - size * 0.55, y + size * 0.4, x + size * 0.55, y + size * 1.0)
        self.circle(BLACK, x - size * 0.4, y - size * 0.15, size * 0.28)
        self.circle(BLACK, x + size * 0.4, y - size * 0.15, size * 0.28)
        self.line(BLACK, x - size * 0.2, y + size * 0.5, x - size * 0.2, y + size * 0.95, 1)
        self.line(BLACK, x + size * 0.2, y + size * 0.5, x + size * 0.2, y + size * 0.95, 1)

    def arrow(self, x, y, direction, size, color):
        """Little triangle pointing left (-1) or right (+1)."""
        pts = [(x + direction * size, y), (x - direction * size * 0.6, y - size),
               (x - direction * size * 0.6, y + size)]
        self.poly(pts, fill=color)

    def panel(self, x1, y1, x2, y2):
        self.rect(PANEL, x1, y1, x2, y2)
        self.rect(WHITE, x1, y1, x2, y2, 3)

    def pirate_colors(self, pr):
        if pr.kind == "boss":
            return col("#2a0f1a"), col("#5a1f33"), GOLD
        if pr.kind == "ram":
            return col("#2b1414"), col("#7a2a2a"), col("#140606")
        return col("#2b1d14"), col("#4a3324"), col("#140c06")

    def whirl_arms(self, w):
        arms = []
        for k in range(3):
            a = w.spin + k * math.tau / 3
            arm = []
            for j in range(6):
                t = j / 5
                ang = a + t * 1.6
                rad = w.r * (0.15 + 0.85 * t)
                arm.append((w.x + math.cos(ang) * rad, w.y + math.sin(ang) * rad))
            arms.append(arm)
        return arms

    # ---- 2D scene ----
    def to_screen(self, wx, wy):
        return (wx - self.raft.x + W / 2 + self.sx, wy - self.raft.y + H / 2 + self.sy)

    def draw_water_2d(self):
        # Layered tropical-water gradient with moving sun glints.
        for band in range(16):
            t = band / 15
            shade = (int(10 + 12 * t), int(125 + 38 * t), int(170 + 48 * t))
            self.rect(shade, 0, band * H / 16, W, (band + 1) * H / 16 + 1)
        step_x, step_y = 86, 58
        ox = (-self.raft.x + self.sx) % step_x
        oy = (-self.raft.y + self.sy) % step_y
        phase = self.frame * 0.035
        for row, y in enumerate(range(-step_y, H + step_y, step_y)):
            shift = (row % 2) * step_x / 2
            for x in range(-step_x, W + step_x, step_x):
                px, py = x + ox + shift, y + oy
                wobble = math.sin(phase + row * 0.8 + x * 0.012) * 3
                pygame.draw.lines(self.screen, col("#78dce8"), False,
                                  [(px - 13, py + wobble), (px - 6, py - 3 + wobble),
                                   (px + 1, py + wobble), (px + 8, py + 3 + wobble),
                                   (px + 14, py + wobble)], 2)
                if (row * 7 + x // step_x) % 5 == 0:
                    self.line(col("#a2d9e8"), px + 22, py - 13,
                              px + 32, py - 13 + wobble * 0.35, 1)
        # Soft vignette makes the playable area stand out.
        edge = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(edge, (3, 24, 48, 30), (0, 0, W, H), 18)
        self.screen.blit(edge, (0, 0))

    def draw_island_2d(self):
        isl = self.island
        sx, sy = self.to_screen(isl.x, isl.y)
        treasure = isl.kind == "treasure"
        self.circle(col("#f2d36b") if treasure else col("#e8d28a"), sx, sy, isl.r + 12)
        self.circle(col("#4caf50"), sx, sy, isl.r)
        self.circle(col("#2e7d32"), sx, sy, isl.r, 3)
        # Patchy foliage and little beach stones add texture without obscuring play.
        for k in range(9):
            a = math.tau * k / 9
            rr = isl.r * (0.42 + 0.12 * math.sin(k * 2.1))
            self.circle(col("#63bd55"), sx + math.cos(a) * rr,
                        sy + math.sin(a) * rr, max(4, isl.r * 0.09))
            self.circle(col("#d8c27b"), sx + math.cos(a + 0.25) * isl.r * 0.78,
                        sy + math.sin(a + 0.25) * isl.r * 0.78, 3)
        if treasure:
            self.rect(col("#7a4e22"), sx - 22, sy - 14, sx + 22, sy + 14)
            self.rect(GOLD, sx - 22, sy - 14, sx + 22, sy - 4)
            self.rect(BLACK, sx - 22, sy - 14, sx + 22, sy + 14, 2)
            self.circle(GOLD, sx, sy + 2, 4)
            self.text("TREASURE", sx, sy - isl.r - 26, 22, GOLD, "center", True)
        elif isl.kind == "ruins":
            stone = col("#9a9b91")
            for ox, oy in ((-24, -12), (22, -15), (-4, 23)):
                self.rect(col("#555b59"), sx + ox - 9, sy + oy - 15,
                          sx + ox + 9, sy + oy + 15)
                self.rect(stone, sx + ox - 7, sy + oy - 14,
                          sx + ox + 7, sy + oy + 12)
                self.line(col("#d4d1b9"), sx + ox - 7, sy + oy - 12,
                          sx + ox + 7, sy + oy - 12, 2)
            self.text("ANCIENT RUINS", sx, sy - isl.r - 25, 18,
                      col("#e8e0c0"), "center", True)
        else:
            for k in range(7):                     # palm tree seen from above
                a = math.tau * k / 7
                self.line(col("#2e9e44"), sx, sy, sx + math.cos(a) * isl.r * 0.55,
                          sy + math.sin(a) * isl.r * 0.55, 8)
            self.circle(col("#6b4423"), sx, sy, 8)

    def draw_whirls_2d(self):
        for w in self.whirls:
            sx, sy = self.to_screen(w.x, w.y)
            if sx < -200 or sx > W + 200 or sy < -200 or sy > H + 200:
                continue
            self.circle(col("#2370a3"), sx, sy, w.r)
            self.circle(col("#1d5f93"), sx, sy, w.r * 0.6)
            self.circle(col("#16486f"), sx, sy, w.r * 0.25)
            self.circle(col("#9fd8f5"), sx, sy, w.r, 2)
            for arm in self.whirl_arms(w):
                pts = [self.to_screen(x, y) for x, y in arm]
                pygame.draw.lines(self.screen, col("#9fd8f5"), False,
                                  [(int(a), int(b)) for a, b in pts], 3)

    def draw_coins_2d(self):
        for coin in self.coin_items:
            sx, sy = self.to_screen(coin.x, coin.y)
            if -20 < sx < W + 20 and -20 < sy < H + 20:
                self.circle(GOLD, sx, sy, 9)
                self.circle(col("#b8860b"), sx, sy, 9, 2)
                self.text("$", sx, sy, 18, col("#8a6500"), "center", True)

    def draw_powerups_2d(self):
        for pu in self.powerups:
            sx, sy = self.to_screen(pu.x, pu.y)
            if -30 < sx < W + 30 and -30 < sy < H + 30:
                d = POWERUPS[pu.kind]
                pulse = 15 + 2 * math.sin(self.frame * 0.15)
                self.circle(WHITE, sx, sy, pulse + 4)
                self.circle(col(d["color"]), sx, sy, pulse)
                self.circle(BLACK, sx, sy, pulse, 2)
                self.text(d["letter"], sx, sy, 26, BLACK, "center", True)

    def draw_obstacles_2d(self):
        for o in self.obstacles:
            sx, sy = self.to_screen(o.x, o.y)
            if sx < -100 or sx > W + 100 or sy < -100 or sy > H + 100:
                continue
            if o.kind == "rock":
                self.circle(col("#6b6b73"), sx, sy, o.r)
                self.circle(col("#3d3d44"), sx, sy, o.r, 3)
                self.circle(col("#8a8a94"), sx - o.r * 0.3, sy - o.r * 0.35, o.r * 0.28)
            else:
                self.circle(col("#8d5a2b"), sx, sy, o.r)
                self.circle(col("#4e2f12"), sx, sy, o.r, 3)
                for k in (0.6, 0.25):
                    self.circle(col("#b17a45"), sx, sy, o.r * k, 2)

    def draw_clouds_2d(self):
        for cl in self.clouds:
            sx, sy = self.to_screen(cl.x, cl.y)
            k = cl.life / cl.max_life
            rad = cl.r * (0.85 + 0.15 * math.sin(cl.life * 8))
            self.fx_circle(col("#7bd34a"), sx, sy, rad, 0.45)
            self.fx_circle(col("#b6ff7a"), sx, sy, rad * 0.65 * (0.5 + 0.5 * k), 0.5)

    def draw_mines_2d(self):
        for m in self.mines:
            sx, sy = self.to_screen(m.x, m.y)
            blink = m.arm <= 0 and self.frame % 40 < 20
            for k in range(8):
                a = math.tau * k / 8
                self.line(BLACK, sx, sy, sx + math.cos(a) * 15, sy + math.sin(a) * 15, 3)
            self.circle(col("#2b2b30"), sx, sy, 11)
            self.circle(col("#e63946") if blink else col("#555560"), sx, sy, 4)

    def draw_health_bar(self, sx, sy, hw, frac):
        frac = max(0.0, frac)
        self.rect(col("#440000"), sx - hw, sy - 4, sx + hw, sy + 4)
        self.rect(col("#e63946"), sx - hw, sy - 4, sx - hw + 2 * hw * frac, sy + 4)
        self.rect(BLACK, sx - hw, sy - 4, sx + hw, sy + 4, 1)

    def draw_hmines_2d(self):
        for m in self.hmines:
            sx, sy = self.to_screen(m.x, m.y)
            armed = m.arm <= 0
            body = col("#3a1414") if armed else col("#5a3a3a")
            for k in range(8):
                a = k * math.tau / 8
                self.line(BLACK, sx + math.cos(a) * 12, sy + math.sin(a) * 12,
                          sx + math.cos(a) * 20, sy + math.sin(a) * 20, 3)
            self.circle(body, sx, sy, 14)
            blink = armed and int(self.frame / 8) % 2 == 0
            self.circle(col("#ff3b30") if blink else col("#7a2a2a"), sx, sy, 5)
            if not armed:
                self.circle(GOLD, sx, sy, 24, 2)       # still arming

    def pirate_tell_pips(self, pr, x, y):
        n = len(pr.abil)
        for i, name in enumerate(pr.abil):
            spec = PIRATE_ABILITIES[name]
            px = x + (i - (n - 1) / 2) * 20
            self.circle(col(spec["color"]), px, y, 9)
            self.circle(BLACK, px, y, 9, 1)
            self.text(spec["letter"], px, y, 16, BLACK, "center", True)

    def draw_pirates_2d(self):
        r = self.raft
        for pr in self.pirates:
            sx, sy = self.to_screen(pr.x, pr.y)
            if sx < -100 or sx > W + 100 or sy < -100 or sy > H + 100:
                continue
            dark, mid, edge = self.pirate_colors(pr)
            self.circle(dark, sx, sy, pr.r + 5)
            self.circle(mid, sx, sy, pr.r)
            self.circle(edge, sx, sy, pr.r, 3)
            self.skull(sx, sy - 2, 13 * pr.r / 34)
            if pr.kind == "boss":
                self.text("FLAGSHIP", sx, sy - pr.r - 34, 22, GOLD, "center", True)
            self.draw_health_bar(sx, sy - pr.r - 14, max(26, pr.r * 0.8), pr.hp / pr.max_hp)
            self.pirate_tell_pips(pr, sx, sy - pr.r - (52 if pr.kind == "boss" else 30))
            if "bulwark" in pr.abil:
                pts = [(sx + math.cos(pr.face - 1.0 + k * 0.25) * (pr.r + 9),
                        sy + math.sin(pr.face - 1.0 + k * 0.25) * (pr.r + 9))
                       for k in range(9)]
                for k in range(8):
                    self.line(col("#9fb3c8"), pts[k][0], pts[k][1],
                              pts[k + 1][0], pts[k + 1][1], 6)
            if pr.charging:
                name, t, total = pr.charging
                c = col(PIRATE_ABILITIES[name]["color"])
                self.circle(c, sx, sy, pr.r + 8 + 60 * (t / total), 3)    # closing ring
                if name == "broadside":
                    a = math.atan2(r.y - pr.y, r.x - pr.x)
                    self.line(c, sx, sy, sx + math.cos(a) * 160, sy + math.sin(a) * 160, 2)
            if pr.heal_t > 0 and pr.heal_to is not None:
                tx, ty = self.to_screen(pr.heal_to.x, pr.heal_to.y)
                self.line(col("#60d394"), sx, sy, tx, ty, 3)

    def draw_sharks_2d(self):
        for s in self.sharks:
            sx, sy = self.to_screen(s.x, s.y)
            if sx < -100 or sx > W + 100 or sy < -100 or sy > H + 100:
                continue
            hx, hy = s.hx, s.hy
            px, py = -hy, hx
            self.circle(col("#1f6a9a"), sx, sy, s.r + 4)
            pts = [(sx + hx * 30, sy + hy * 30),
                   (sx - hx * 18 + px * 14, sy - hy * 18 + py * 14),
                   (sx - hx * 8, sy - hy * 8),
                   (sx - hx * 18 - px * 14, sy - hy * 18 - py * 14)]
            self.poly(pts, fill=col("#7f8f9c"), outline=col("#2f3a44"), width=2)
            if s.hp < s.max_hp:
                self.draw_health_bar(sx, sy - 40, 20, s.hp / s.max_hp)

    def draw_projectiles_2d(self):
        for cb in self.cannonballs:
            sx, sy = self.to_screen(cb.x, cb.y)
            self.circle(col("#2a0f3a") if cb.homing else BLACK, sx, sy, 9 if cb.homing else 7)
            self.circle(col("#c77dff") if cb.homing else col("#e63946"), sx, sy,
                        9 if cb.homing else 7, 2)
        for sh in self.shells:
            sx, sy = self.to_screen(sh.x, sh.y)
            self.circle(LIME, sx, sy, 9)
            self.circle(col("#6b8e00"), sx, sy, 9, 2)
        for sw in self.shockwaves:
            sx, sy = self.to_screen(sw.x, sw.y)
            self.circle(col("#ff9f1c"), sx, sy, max(2, sw.radius), 5)

    def draw_raft_2d(self):
        r = self.raft
        sx, sy = self.to_screen(r.x, r.y)
        R = r.radius
        flash = r.invuln > 0 and int(r.invuln * 20) % 2 == 0
        self.circle(col("#ff7b72") if flash else col("#087f9c"), sx, sy, R + 12)
        self.circle(col("#49c7c7"), sx, sy, R + 5)
        self.circle(WOOD, sx, sy, R)
        self.circle(col("#70451f"), sx, sy, R, 3)
        for i in range(-3, 4):
            off = i * R / 3.5
            half = math.sqrt(max(0, R * R - off * off))
            self.line(WOOD_DARK, sx + off, sy - half, sx + off, sy + half, 2)
            self.line(col("#c28b50"), sx + off + 2, sy - half * 0.82,
                      sx + off + 2, sy + half * 0.82, 1)
        # Rope lashings and a small mast make the raft silhouette more readable.
        for a in (0, math.pi / 2, math.pi, math.pi * 1.5):
            self.circle(col("#d7b078"), sx + math.cos(a) * (R - 5),
                        sy + math.sin(a) * (R - 5), 4)
        self.circle(col("#5a351b"), sx, sy, 10)
        self.line(col("#f0d7a0"), sx, sy - 6, sx, sy - 27, 2)
        self.poly([(sx, sy - 26), (sx + 15, sy - 20), (sx, sy - 14)],
                  fill=col("#ee6055"), outline=col("#7a2525"), width=1)
        if r.shield > 0:
            self.circle(col("#7ae7ff"), sx, sy, R + 18, 4)
        if r.turbo > 0:
            self.circle(col("#6ec5ff"), sx, sy, R + 24, 3)
        if r.beans > 0:
            self.circle(col("#b5742f"), sx, sy, R + 30, 2)

    def draw_face(self, sx, sy, s=1.0):
        self.circle(WHITE, sx - 4.5 * s, sy - 2.5 * s, 3 * s)
        self.circle(WHITE, sx + 4.5 * s, sy - 2.5 * s, 3 * s)
        self.circle(BLACK, sx - 4 * s, sy - 2 * s, 1.4 * s)
        self.circle(BLACK, sx + 5 * s, sy - 2 * s, 1.4 * s)

    def draw_hippo_2d(self, p, sx, sy, nx=0.0, ny=-1.0, scale=1.0):
        # Original cartoon hippo crew: rounded ears, broad muzzle, tiny nostrils,
        # bright team-color life vest, and thick friendly outlines.
        skin = col("#9da8b7")
        skin_light = col("#c3cbd4")
        muzzle = col("#d9a6a7")
        dark = col("#394452")
        side = -ny
        front = nx
        self.oval(dark, sx - 15 * scale, sy + 8 * scale,
                  sx + 15 * scale, sy + 22 * scale)
        self.oval(p.color, sx - 13 * scale, sy + 1 * scale,
                  sx + 13 * scale, sy + 17 * scale)
        self.oval(dark, sx - 16 * scale, sy - 12 * scale,
                  sx + 16 * scale, sy + 13 * scale, 2)
        # Ears peek out above the head.
        self.circle(skin, sx - 10 * scale, sy - 12 * scale, 5.2 * scale)
        self.circle(skin, sx + 10 * scale, sy - 12 * scale, 5.2 * scale)
        self.circle(muzzle, sx - 10 * scale, sy - 12 * scale, 2.3 * scale)
        self.circle(muzzle, sx + 10 * scale, sy - 12 * scale, 2.3 * scale)
        self.circle(skin, sx, sy - 2 * scale, 14 * scale)
        self.circle(dark, sx, sy - 2 * scale, 14 * scale, 2)
        self.oval(skin_light, sx - 10 * scale, sy - 11 * scale,
                  sx + 3 * scale, sy - 5 * scale)
        self.oval(muzzle, sx - 10 * scale, sy + 1 * scale,
                  sx + 10 * scale, sy + 10 * scale)
        self.oval(dark, sx - 10 * scale, sy + 1 * scale,
                  sx + 10 * scale, sy + 10 * scale, 1)
        self.circle(dark, sx - 4 * scale, sy + 4 * scale, 1.5 * scale)
        self.circle(dark, sx + 4 * scale, sy + 4 * scale, 1.5 * scale)
        self.circle(WHITE, sx - 5 * scale, sy - 7 * scale, 2.5 * scale)
        self.circle(WHITE, sx + 5 * scale, sy - 7 * scale, 2.5 * scale)
        self.circle(BLACK, sx - 4.2 * scale, sy - 6.5 * scale, 1.2 * scale)
        self.circle(BLACK, sx + 5.8 * scale, sy - 6.5 * scale, 1.2 * scale)

    def draw_players_2d(self):
        for p in self.players:
            wx, wy, nx, ny = self.player_pos(p)
            sx, sy = self.to_screen(wx, wy)
            sx += nx * 8
            sy += ny * 8
            self.draw_hippo_2d(p, sx, sy, nx, ny, 1.0)
            if p.block_timer > 0:
                self.circle(col("#7ae7ff"), sx, sy - 2, 23, 3)
            self.text(p.name, sx, sy + 31, 18, WHITE, "center", True)
            if p.cooldown > 0:
                frac = max(0, 1 - p.cooldown / self.fart_cooldown())
                self.rect(LIME, sx - 14, sy - 43, sx - 14 + 28 * frac, sy - 39)
                self.rect(WHITE, sx - 14, sy - 43, sx + 14, sy - 39, 1)
            if p.flash > 0:
                self.text(p.word, sx + nx * 50, sy + ny * 50, 28, LIME, "center", True)

    def draw_puffs_2d(self):
        for p in self.puffs:
            sx, sy = self.to_screen(p.x, p.y)
            k = max(0.0, p.life / p.max_life)
            rad = p.r * (1.6 - k)
            shade = int(120 + 100 * k)
            self.fx_circle((int(shade * 0.55), min(255, int(shade * 1.12)),
                            int(shade * 0.58)), sx, sy, rad * 1.12, 0.5 + 0.3 * k)

    def draw_texts_2d(self):
        for t in self.texts:
            sx, sy = self.to_screen(t.x, t.y)
            self.text(t.text, sx, sy, 26, t.color, "center", True)

    def draw_scene_2d(self):
        self.draw_water_2d()
        self.draw_whirls_2d()
        self.draw_island_2d()
        self.draw_coins_2d()
        self.draw_powerups_2d()
        self.draw_obstacles_2d()
        self.draw_mines_2d()
        self.draw_hmines_2d()
        self.draw_clouds_2d()
        self.flush_fx()
        self.draw_sharks_2d()
        self.draw_pirates_2d()
        self.draw_projectiles_2d()
        self.draw_raft_2d()
        self.draw_puffs_2d()
        self.flush_fx()
        self.draw_players_2d()
        self.draw_texts_2d()

    # ---- 3D scene ----
    def setup_camera(self):
        th = self.yaw
        ph = CAM_PITCHES[self.settings["cam"]]
        F = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), -math.sin(ph))
        R = (math.sin(th), -math.cos(th), 0.0)
        U = (math.cos(th) * math.sin(ph), math.sin(th) * math.sin(ph), math.cos(ph))
        tx, ty = self.cam_x, -self.cam_y   # 3D "north" is up the 2D screen
        C = (tx - F[0] * self.cam_dist, ty - F[1] * self.cam_dist, -F[2] * self.cam_dist)
        self.cam = (C, F, R, U)
        self.sin_pitch = math.sin(ph)
        self.cam_cy = H * 0.56 + self.sy
        self.horizon_y = self.cam_cy - FOCAL * math.tan(ph)

    def proj(self, wx, wy, wz=0.0):
        C, F, R, U = self.cam
        vx, vy, vz = wx - C[0], -wy - C[1], wz - C[2]
        zc = vx * F[0] + vy * F[1] + vz * F[2]
        if zc < 40:
            return None
        xc = vx * R[0] + vy * R[1]
        yc = vx * U[0] + vy * U[1] + vz * U[2]
        s = FOCAL / zc
        return W / 2 + xc * s + self.sx, self.cam_cy - yc * s, zc, s

    def ring(self, wx, wy, z, r, n=24):
        pts = []
        for i in range(n):
            a = math.tau * i / n
            p = self.proj(wx + math.cos(a) * r, wy + math.sin(a) * r, z)
            if p is None:
                return None
            pts.append((p[0], p[1]))
        return pts

    def shadow(self, wx, wy, r):
        p = self.proj(wx, wy, 0)
        if p:
            rx = r * p[3]
            self.oval(col("#1f6a9a"), p[0] - rx, p[1] - rx * self.sin_pitch,
                      p[0] + rx, p[1] + rx * self.sin_pitch)

    def ball(self, color, wx, wy, z, r, outline=None, width=2):
        p = self.proj(wx, wy, z)
        if p:
            rr = r * p[3]
            self.circle(color, p[0], p[1], rr)
            if outline:
                self.circle(outline, p[0], p[1], rr, width)
        return p

    def draw_water_3d(self):
        yh = max(0, min(H, self.horizon_y))
        # Blue-to-cyan sky with a warm band at the horizon.
        for i in range(18):
            t = i / 17
            c = (int(20 + 95 * t), int(65 + 125 * t), int(125 + 115 * t))
            self.rect(c, 0, yh * i / 18, W, yh * (i + 1) / 18 + 1)
        if yh < H:
            self.rect(col("#f4c98b"), 0, max(0, yh - 3), W, max(0, yh + 5))
            for i in range(16):
                t = i / 15
                c = (int(8 + 12 * t), int(112 + 38 * t), int(158 + 45 * t))
                y1 = yh + 5 + (H - yh - 5) * i / 16
                y2 = yh + 5 + (H - yh - 5) * (i + 1) / 16
                self.rect(c, 0, y1, W, y2 + 1)
        # Sun and soft broken cloud shapes.
        sun_x, sun_y = W * 0.78, max(55, yh * 0.34)
        self.circle(col("#ffe6a3"), sun_x, sun_y, 34)
        self.circle(col("#fff4cf"), sun_x - 7, sun_y - 7, 23)
        for cx, cy, scale in ((W * 0.20, yh * 0.30, 1.0),
                              (W * 0.48, yh * 0.18, 0.72),
                              (W * 0.91, yh * 0.52, 0.82)):
            cloud = col("#d5eaf0")
            self.oval(cloud, cx - 45 * scale, cy - 8 * scale,
                      cx + 45 * scale, cy + 10 * scale)
            self.circle(cloud, cx - 20 * scale, cy - 5 * scale, 13 * scale)
            self.circle(cloud, cx + 5 * scale, cy - 13 * scale, 18 * scale)
            self.circle(cloud, cx + 27 * scale, cy - 4 * scale, 12 * scale)
        # Perspective wavelets and sunlight streaks.
        cx, cy = self.cam_x, self.cam_y
        step = 95
        for j in range(int((cy - 1500) // step), int((cy + 1500) // step) + 1):
            for i in range(int((cx - 1500) // step), int((cx + 1500) // step) + 1):
                wx = i * step + (j % 2) * step / 2
                wy = j * step
                p = self.proj(wx, wy, 0)
                if p is None:
                    continue
                sx, sy, _, s = p
                if sx < -60 or sx > W + 60 or sy < yh or sy > H + 10:
                    continue
                ln = 24 * s
                glint = col("#9af1ed") if (i + j) % 4 else col("#fff0b3")
                self.line(glint, sx - ln, sy, sx + ln, sy,
                          max(1, int(3 * s)))
                if (i - j) % 7 == 0:
                    self.line(col("#3d9fc0"), sx - ln * 0.55, sy + 4 * s,
                              sx + ln * 0.55, sy + 4 * s, max(1, int(2 * s)))

    def d3_island(self, isl):
        treasure = isl.kind == "treasure"
        self.poly(self.ring(isl.x, isl.y, 0, isl.r + 12, 28),
                  fill=col("#f2d36b") if treasure else col("#e8d28a"))
        self.poly(self.ring(isl.x, isl.y, 10, isl.r, 28), fill=col("#4caf50"),
                  outline=col("#2e7d32"), width=3)
        self.poly(self.ring(isl.x, isl.y, 24, isl.r * 0.6, 20), fill=col("#5fc45f"))
        if treasure:
            self.poly(self.ring(isl.x, isl.y, 40, 22, 4), fill=col("#7a4e22"),
                      outline=BLACK, width=2)
            p = self.ball(GOLD, isl.x, isl.y, 60, 14, col("#b8860b"))
            if p:
                self.text("TREASURE", p[0], p[1] - 40 * p[3] - 8, 22, GOLD, "center", True)
            return
        if isl.kind == "ruins":
            stone = col("#aaa997")
            for ox, oy, height in ((-28, -10, 75), (28, -10, 62), (0, 25, 48)):
                base = self.proj(isl.x + ox, isl.y + oy, 12)
                top = self.proj(isl.x + ox, isl.y + oy, height)
                if base and top:
                    self.line(col("#555b59"), base[0], base[1], top[0], top[1],
                              max(7, int(15 * base[3])))
                    self.line(stone, base[0] - 3, base[1], top[0] - 3, top[1],
                              max(3, int(6 * base[3])))
                    self.circle(stone, top[0], top[1], max(4, 7 * top[3]))
            p1 = self.proj(isl.x - 28, isl.y - 10, 70)
            p2 = self.proj(isl.x + 28, isl.y - 10, 70)
            if p1 and p2:
                self.line(stone, p1[0], p1[1], p2[0], p2[1],
                          max(6, int(13 * p1[3])))
            label = self.proj(isl.x, isl.y, 100)
            if label:
                self.text("ANCIENT RUINS", label[0], label[1] - 12,
                          20, col("#e8e0c0"), "center", True)
            return
        base = self.proj(isl.x, isl.y, 24)
        top = self.proj(isl.x, isl.y, 130)
        if base and top:
            self.line(col("#6b4423"), base[0], base[1], top[0], top[1],
                      max(3, int(10 * base[3])))
            for k in range(7):
                a = math.tau * k / 7
                tip = self.proj(isl.x + math.cos(a) * 55, isl.y + math.sin(a) * 55, 105)
                if tip:
                    self.line(col("#2e9e44"), top[0], top[1], tip[0], tip[1],
                              max(3, int(8 * top[3])))

    def d3_rock(self, o):
        self.poly(self.ring(o.x, o.y, 0, o.r, 18), fill=col("#3d3d44"))
        p = self.proj(o.x, o.y, o.r * 0.55)
        if p:
            rr = o.r * p[3]
            self.oval(col("#6b6b73"), p[0] - rr, p[1] - rr * 0.9, p[0] + rr, p[1] + rr * 0.9)
            self.oval(col("#3d3d44"), p[0] - rr, p[1] - rr * 0.9, p[0] + rr, p[1] + rr * 0.9, 2)
            self.oval(col("#8a8a94"), p[0] - rr * 0.55, p[1] - rr * 0.7,
                      p[0] - rr * 0.05, p[1] - rr * 0.2)

    def d3_log(self, o):
        self.poly(self.ring(o.x, o.y, 0, o.r, 16), fill=col("#4e2f12"))
        self.poly(self.ring(o.x, o.y, 7, o.r, 16), fill=col("#6b4220"))
        self.poly(self.ring(o.x, o.y, 14, o.r, 16), fill=col("#8d5a2b"),
                  outline=col("#4e2f12"), width=2)
        for k in (0.6, 0.25):
            self.poly(self.ring(o.x, o.y, 14, o.r * k, 14), outline=col("#b17a45"), width=2)

    def d3_coin(self, coin):
        self.shadow(coin.x, coin.y, 9)
        bob = 6 * math.sin(self.frame * 0.1 + coin.x * 0.01)
        p = self.ball(GOLD, coin.x, coin.y, 22 + bob, 9, col("#b8860b"))
        if p:
            self.text("$", p[0], p[1], max(12, int(20 * p[3])), col("#8a6500"), "center", True)

    def d3_powerup(self, pu):
        d = POWERUPS[pu.kind]
        self.shadow(pu.x, pu.y, 14)
        bob = 8 * math.sin(self.frame * 0.1 + pu.x * 0.01)
        p = self.ball(col(d["color"]), pu.x, pu.y, 34 + bob, 17, BLACK)
        if p:
            self.text(d["letter"], p[0], p[1], max(14, int(30 * p[3])), BLACK, "center", True)

    def d3_mine(self, m):
        self.shadow(m.x, m.y, 12)
        blink = m.arm <= 0 and self.frame % 40 < 20
        self.ball(col("#2b2b30"), m.x, m.y, 10, 11, col("#e63946") if blink else BLACK)

    def d3_shark(self, s):
        self.shadow(s.x, s.y, 24)
        hx, hy = s.hx, s.hy
        pts = []
        for ox, oy, oz in ((-16, 0, 0), (10, 0, 0), (-6, 0, 34)):
            wx = s.x + hx * ox
            wy = s.y + hy * ox
            p = self.proj(wx, wy, oz)
            if p is None:
                return
            pts.append((p[0], p[1]))
        self.poly(pts, fill=col("#7f8f9c"), outline=col("#2f3a44"), width=2)
        hp = self.proj(s.x, s.y, 50)
        if hp and s.hp < s.max_hp:
            self.draw_health_bar(hp[0], hp[1], 18 * hp[3] + 6, s.hp / s.max_hp)

    def d3_pirate(self, pr):
        dark, mid, edge = self.pirate_colors(pr)
        self.poly(self.ring(pr.x, pr.y, 0, pr.r + 5, 20), fill=dark)
        self.poly(self.ring(pr.x, pr.y, 16, pr.r, 20), fill=mid, outline=edge, width=3)
        base = self.proj(pr.x, pr.y, 16)
        top = self.proj(pr.x, pr.y, 125)
        sb = self.proj(pr.x, pr.y, 35)
        st = self.proj(pr.x, pr.y, 115)
        if base and top and sb and st:
            self.line(col("#2b1d14"), base[0], base[1], top[0], top[1],
                      max(2, int(5 * base[3])))
            s = (sb[3] + st[3]) / 2
            hw = 34 * s * (pr.r / 34 if pr.kind == "boss" else 1)
            self.poly([(sb[0] - hw, sb[1]), (sb[0] + hw, sb[1]),
                       (st[0] + hw * 0.7, st[1]), (st[0] - hw * 0.7, st[1])],
                      fill=col("#15151c"), outline=col("#666666"), width=2)
            self.skull((sb[0] + st[0]) / 2, (sb[1] + st[1]) / 2 - 2 * s, max(4, 13 * s))
            hp = self.proj(pr.x, pr.y, 150)
            if hp:
                self.draw_health_bar(hp[0], hp[1], max(26, pr.r * 0.8) * hp[3],
                                     pr.hp / pr.max_hp)
                if pr.kind == "boss":
                    self.text("FLAGSHIP", hp[0], hp[1] - 18, 22, GOLD, "center", True)
                self.d3_tells(pr, hp)

    def d3_hmine(self, m):
        self.shadow(m.x, m.y, 16)
        blink = m.arm <= 0 and int(self.frame / 8) % 2 == 0
        self.ball(col("#3a1414"), m.x, m.y, 14, 15,
                  col("#ff3b30") if blink else col("#7a2a2a"))

    def d3_tells(self, pr, hp):
        n = len(pr.abil)
        for i, name in enumerate(pr.abil):
            spec = PIRATE_ABILITIES[name]
            px = hp[0] + (i - (n - 1) / 2) * 20
            py = hp[1] - (40 if pr.kind == "boss" else 18)
            self.circle(col(spec["color"]), px, py, 9)
            self.circle(BLACK, px, py, 9, 1)
            self.text(spec["letter"], px, py, 16, BLACK, "center", True)
        if pr.charging:
            name, t, total = pr.charging
            rad = pr.r + 8 + 60 * (t / total)
            self.poly(self.ring(pr.x, pr.y, 3, rad, 24),
                      outline=col(PIRATE_ABILITIES[name]["color"]), width=3)
        if "bulwark" in pr.abil:
            pts = []
            for k in range(9):
                a = pr.face - 1.0 + k * 0.25
                p = self.proj(pr.x + math.cos(a) * (pr.r + 9),
                              pr.y + math.sin(a) * (pr.r + 9), 22)
                if p:
                    pts.append(p)
            for k in range(len(pts) - 1):
                self.line(col("#9fb3c8"), pts[k][0], pts[k][1], pts[k + 1][0], pts[k + 1][1], 6)

    def d3_cannonball(self, cb):
        self.shadow(cb.x, cb.y, 7)
        self.ball(BLACK, cb.x, cb.y, 24, 7, col("#e63946"))

    def d3_shell(self, sh):
        self.shadow(sh.x, sh.y, 9)
        self.ball(LIME, sh.x, sh.y, 24, 9, col("#6b8e00"))

    def d3_puff(self, pf):
        k = max(0.0, pf.life / pf.max_life)
        p = self.proj(pf.x, pf.y, 16 + 50 * (1 - k))
        if p:
            shade = int(120 + 100 * k)
            self.fx_circle((shade // 2, shade, shade // 3), p[0], p[1],
                           pf.r * (1.6 - k) * p[3], 0.5 + 0.3 * k)

    def d3_whirl(self, w):
        self.poly(self.ring(w.x, w.y, 1, w.r, 26), fill=col("#2370a3"),
                  outline=col("#9fd8f5"), width=2)
        self.poly(self.ring(w.x, w.y, 1, w.r * 0.6, 20), fill=col("#1d5f93"))
        self.poly(self.ring(w.x, w.y, 1, w.r * 0.25, 14), fill=col("#16486f"))
        for arm in self.whirl_arms(w):
            pts = []
            for x, y in arm:
                p = self.proj(x, y, 2)
                if p is None:
                    pts = []
                    break
                pts.append((int(p[0]), int(p[1])))
            if len(pts) > 1:
                pygame.draw.lines(self.screen, col("#9fd8f5"), False, pts, 3)

    def d3_raft(self, _):
        r = self.raft
        R, top_z, n = r.radius, 14, 36
        flash = r.invuln > 0 and int(r.invuln * 20) % 2 == 0
        bottom = self.ring(r.x, r.y, 0, R + 8, n)
        top = self.ring(r.x, r.y, top_z, R + 8, n)
        if not bottom or not top:
            return
        self.poly(bottom, fill=col("#075c78"))
        C = self.cam[0]
        cwx, cwy = C[0], -C[1]
        for i in range(n):
            j = (i + 1) % n
            am = math.tau * (i + 0.5) / n
            if math.cos(am) * (cwx - r.x) + math.sin(am) * (cwy - r.y) > 0:
                self.poly([bottom[i], bottom[j], top[j], top[i]],
                          fill=col("#ff7b72") if flash else col("#087f9c"))
        self.poly(top, fill=col("#ff7b72") if flash else col("#087f9c"))
        self.poly(self.ring(r.x, r.y, top_z + 1, R + 3, n), fill=col("#49c7c7"),
                  outline=col("#075c78"), width=3)
        self.poly(self.ring(r.x, r.y, top_z + 2, R - 2, n), fill=WOOD,
                  outline=WOOD_DARK, width=2)
        # Warm plank highlights, rope knots and central mast.
        for i in range(-3, 4):
            off = i * R / 3.5
            half = math.sqrt(max(0, R * R - off * off))
            a = self.proj(r.x + off, r.y - half, top_z + 1)
            b = self.proj(r.x + off, r.y + half, top_z + 1)
            if a and b:
                self.line(WOOD_DARK, a[0], a[1], b[0], b[1], 2)
                self.line(col("#c28b50"), a[0] + 2, a[1], b[0] + 2, b[1], 1)
        mast_base = self.proj(r.x, r.y, top_z + 2)
        mast_top = self.proj(r.x, r.y, top_z + 62)
        if mast_base and mast_top:
            self.line(col("#5a351b"), mast_base[0], mast_base[1],
                      mast_top[0], mast_top[1], max(2, int(4 * mast_base[3])))
            flag = self.proj(r.x + 30, r.y, top_z + 53)
            if flag:
                self.poly([(mast_top[0], mast_top[1]), (flag[0], flag[1]),
                           (mast_top[0], mast_top[1] + 13 * mast_top[3])],
                          fill=col("#ee6055"), outline=col("#7a2525"), width=1)

        order = []
        for pl in self.players:
            wx, wy, nx, ny = self.player_pos(pl)
            q = self.proj(wx + nx * 8, wy + ny * 8, top_z)
            if q:
                order.append((q[2], pl, wx + nx * 8, wy + ny * 8, nx, ny))
        order.sort(key=lambda t: -t[0])
        for _, pl, x, y, nx, ny in order:
            foot = self.proj(x, y, top_z + 1)
            body = self.proj(x, y, top_z + 20)
            head = self.proj(x, y, top_z + 42)
            if not (foot and body and head):
                continue
            s = foot[3]
            self.oval(col("#6b4520"), foot[0] - 15 * s, foot[1] - 5 * s,
                      foot[0] + 15 * s, foot[1] + 5 * s)
            self.oval(pl.color, body[0] - 15 * s, body[1] - 18 * s,
                      body[0] + 15 * s, body[1] + 15 * s)
            self.oval(col("#394452"), body[0] - 15 * s, body[1] - 18 * s,
                      body[0] + 15 * s, body[1] + 15 * s, 2)
            hr = 12 * head[3]
            skin = col("#9da8b7")
            muzzle = col("#d9a6a7")
            self.circle(skin, head[0] - 8 * hr / 12, head[1] - 8 * hr / 12, 4 * head[3])
            self.circle(skin, head[0] + 8 * hr / 12, head[1] - 8 * hr / 12, 4 * head[3])
            self.circle(muzzle, head[0] - 8 * hr / 12, head[1] - 8 * hr / 12, 1.8 * head[3])
            self.circle(muzzle, head[0] + 8 * hr / 12, head[1] - 8 * hr / 12, 1.8 * head[3])
            self.circle(skin, head[0], head[1], hr)
            self.circle(col("#394452"), head[0], head[1], hr, 2)
            self.oval(muzzle, head[0] - 8 * head[3], head[1] + 1 * head[3],
                      head[0] + 8 * head[3], head[1] + 8 * head[3])
            self.circle(col("#394452"), head[0] - 3 * head[3], head[1] + 4 * head[3],
                        1.2 * head[3])
            self.circle(col("#394452"), head[0] + 3 * head[3], head[1] + 4 * head[3],
                        1.2 * head[3])
            self.circle(WHITE, head[0] - 4 * head[3], head[1] - 3 * head[3], 2.2 * head[3])
            self.circle(WHITE, head[0] + 4 * head[3], head[1] - 3 * head[3], 2.2 * head[3])
            self.circle(BLACK, head[0] - 3.5 * head[3], head[1] - 2.5 * head[3], 1 * head[3])
            self.circle(BLACK, head[0] + 4.5 * head[3], head[1] - 2.5 * head[3], 1 * head[3])
            lab = self.proj(x, y, top_z + 66)
            if lab:
                ls = lab[3]
                self.text(pl.name, lab[0], lab[1], max(12, int(18 * ls)), WHITE, "center", True)
                if pl.cooldown > 0:
                    f = max(0, 1 - pl.cooldown / self.fart_cooldown())
                    bw = 14 * ls
                    self.rect(LIME, lab[0] - bw, lab[1] - 18 * ls,
                              lab[0] - bw + 2 * bw * f, lab[1] - 12 * ls)
                    self.rect(WHITE, lab[0] - bw, lab[1] - 18 * ls,
                              lab[0] + bw, lab[1] - 12 * ls, 1)
            if pl.flash > 0:
                w = self.proj(x + nx * 50, y + ny * 50, top_z + 40)
                if w:
                    self.text(pl.word, w[0], w[1], max(16, int(28 * w[3])), LIME, "center", True)
        for timer, color, extra in ((r.shield, "#7ae7ff", 24), (r.turbo, "#6ec5ff", 34),
                                    (r.beans, "#b5742f", 44)):
            if timer > 0:
                p = self.proj(r.x, r.y, top_z + 25)
                if p:
                    rr = (R + extra) * p[3]
                    self.oval(col(color), p[0] - rr, p[1] - rr * 0.85,
                              p[0] + rr, p[1] + rr * 0.85, 4 if extra == 24 else 3)

    def draw_scene_3d(self):
        self.setup_camera()
        self.draw_water_3d()
        for w in self.whirls:
            self.d3_whirl(w)
        for cl in self.clouds:
            k = cl.life / cl.max_life
            rad = cl.r * (0.85 + 0.15 * math.sin(cl.life * 8))
            self.fx_poly(self.ring(cl.x, cl.y, 2, rad, 20), col("#7bd34a"), 0.45)
            self.fx_poly(self.ring(cl.x, cl.y, 3, rad * 0.65 * (0.5 + 0.5 * k), 16),
                         col("#b6ff7a"), 0.5)
        self.flush_fx()
        for sw in self.shockwaves:
            self.poly(self.ring(sw.x, sw.y, 4, max(1.0, sw.radius), 28),
                      outline=col("#ff9f1c"), width=4)

        items = []

        def add(x, y, fn, obj):
            p = self.proj(x, y, 0)
            if p:
                items.append((p[2], fn, obj))

        add(self.island.x, self.island.y, self.d3_island, self.island)
        for o in self.obstacles:
            add(o.x, o.y, self.d3_rock if o.kind == "rock" else self.d3_log, o)
        for coin in self.coin_items:
            add(coin.x, coin.y, self.d3_coin, coin)
        for pu in self.powerups:
            add(pu.x, pu.y, self.d3_powerup, pu)
        for m in self.mines:
            add(m.x, m.y, self.d3_mine, m)
        for m in self.hmines:
            add(m.x, m.y, self.d3_hmine, m)
        for s in self.sharks:
            add(s.x, s.y, self.d3_shark, s)
        for pr in self.pirates:
            add(pr.x, pr.y, self.d3_pirate, pr)
        for cb in self.cannonballs:
            add(cb.x, cb.y, self.d3_cannonball, cb)
        for sh in self.shells:
            add(sh.x, sh.y, self.d3_shell, sh)
        add(self.raft.x, self.raft.y, self.d3_raft, None)
        items.sort(key=lambda t: -t[0])
        for _, fn, obj in items:
            fn(obj)
        for pf in self.puffs:
            self.d3_puff(pf)
        self.flush_fx()

        for t in self.texts:
            p = self.proj(t.x, t.y, 50 + (1.2 - t.life) * 30)
            if p:
                self.text(t.text, p[0], p[1], max(18, int(28 * p[3])), t.color, "center", True)
        # Fine atmospheric frame, kept subtle so it doesn't cover gameplay.
        shade = pygame.Surface((W, H), pygame.SRCALPHA)
        pygame.draw.rect(shade, (4, 24, 42, 24), (0, 0, W, H), 14)
        self.screen.blit(shade, (0, 0))

    # ---- HUD and screens ----
    def screen_angle(self, dx, dy):
        """Angle on screen for a world-space direction (2D or 3D view)."""
        if self.settings["view3d"]:
            th = self.yaw
            right = dx * math.sin(th) + dy * math.cos(th)
            fwd = dx * math.cos(th) - dy * math.sin(th)
            return math.atan2(-fwd, right)
        return math.atan2(dy, dx)

    def draw_hud(self):
        isl = self.island
        r = self.raft
        dx, dy = isl.x - r.x, isl.y - r.y
        dist = math.hypot(dx, dy)
        ang = self.screen_angle(dx, dy)
        if dist > 370:    # arrow to the island when it is offscreen
            ax, ay = W / 2 + math.cos(ang) * 230, H / 2 + math.sin(ang) * 230
            tip = (ax + math.cos(ang) * 22, ay + math.sin(ang) * 22)
            left = (ax + math.cos(ang + 2.5) * 14, ay + math.sin(ang + 2.5) * 14)
            right_ = (ax + math.cos(ang - 2.5) * 14, ay + math.sin(ang - 2.5) * 14)
            self.poly([tip, left, right_],
                      fill=GOLD if isl.kind == "treasure" else col("#ffff00"),
                      outline=BLACK, width=2)
        # arrows to flagship bosses
        for pr in self.pirates:
            if pr.kind == "boss":
                pdx, pdy = pr.x - r.x, pr.y - r.y
                if math.hypot(pdx, pdy) > 420:
                    a = self.screen_angle(pdx, pdy)
                    ax, ay = W / 2 + math.cos(a) * 250, H / 2 + math.sin(a) * 250
                    tip = (ax + math.cos(a) * 16, ay + math.sin(a) * 16)
                    l_ = (ax + math.cos(a + 2.5) * 10, ay + math.sin(a + 2.5) * 10)
                    r_ = (ax + math.cos(a - 2.5) * 10, ay + math.sin(a - 2.5) * 10)
                    self.poly([tip, l_, r_], fill=col("#e63946"), outline=BLACK, width=2)

        self.text(f"Islands: {self.score}    Coins: {self.coins}    "
                  f"Sunk: {self.kills}", 15, 10, 28, WHITE, "topleft", True)
        mins, secs = divmod(int(self.run_time), 60)
        self.text(f"Distance to island: {int(dist)}m    Time {mins}:{secs:02d}", 15, 38, 20)

        mh = self.max_hull()
        frac = max(0, r.hull / mh)
        c = col("#60d394") if frac > 0.5 else GOLD if frac > 0.25 else col("#ee6055")
        self.rect(c, 15, 62, 15 + 200 * frac, 78)
        self.rect(WHITE, 15, 62, 215, 78, 2)
        self.text(f"HULL {int(r.hull)}/{int(mh)}", 115, 70, 18, BLACK, "center", True)

        self.text(f"Plunder: {self.plunder}", 230, 70, 20, col("#ffb86b"), "midleft", True)
        if self.pirate_kills:
            self.text(f"Pirates sunk: {self.pirate_kills}", 360, 70, 20,
                      col("#ff8a80"), "midleft", True)

        # wind indicator
        if self.wind_str > 0:
            wa = self.screen_angle(math.cos(self.wind_ang), math.sin(self.wind_ang))
            self.text("Wind", 15, 98, 20, WHITE, "midleft")
            wx, wy = 85, 98
            tip = (wx + math.cos(wa) * 14, wy + math.sin(wa) * 14)
            l_ = (wx + math.cos(wa + 2.6) * 9, wy + math.sin(wa + 2.6) * 9)
            r_ = (wx + math.cos(wa - 2.6) * 9, wy + math.sin(wa - 2.6) * 9)
            self.poly([tip, l_, r_], fill=col("#d9f1ff"), outline=BLACK, width=1)
            self.text("strong" if self.wind_str > 30 else "breezy", 110, 98, 18,
                      col("#d9f1ff"), "midleft")
        else:
            self.text("Wind: calm", 15, 98, 20, col("#d9f1ff"), "midleft")
        ey = 118
        for label, timer, color in (("BEAN BOOST", r.beans, "#e0a050"),
                                    ("TURBO", r.turbo, "#6ec5ff"),
                                    ("SHIELD", r.shield, "#7ae7ff")):
            if timer > 0:
                self.text(f"{label} {timer:.0f}s", 15, ey, 22, col(color), "midleft", True)
                ey += 22

        if self.settings["hints"]:
            self.text("move   fart   ability", W - 15, 10, 18, WHITE, "topright")
            lines = 0
            for i, p in enumerate(self.players):
                if p.ai:
                    continue
                self.text(f"{p.name}:  {PLAYER_DEFS[i]['label']}", W - 15, 28 + lines * 20,
                          20, p.color, "topright", True)
                lines += 1
            if self.n_players < NUM_CREW:
                first = self.n_players + 1
                who = f"P{first}-P{NUM_CREW}" if first < NUM_CREW else f"P{NUM_CREW}"
                self.text(f"{who}: AI crew", W - 15, 28 + lines * 20, 20, WHITE, "topright")
                lines += 1
            hint = "Block: P1 Z  P2 Y  P3 U  P4 R-SHIFT   |   TAB/M menu   P pause   V 2D/3D"
            if self.settings["view3d"]:
                hint += "   C chase   Q/E rotate"
            self.text(hint, W - 15, 28 + lines * 20 + 6, 18, WHITE, "topright")
        else:
            self.text("TAB/M menu", W - 15, 10, 18, WHITE, "topright")

        n = len(self.players)
        for i, p in enumerate(self.players):
            y = H - 22 - (n - 1 - i) * 24
            ab = ABILITIES[p.ability]
            abc = col(ab["color"])
            self.text(p.name, 15, y, 22, p.color, "midleft", True)
            self.text(ab["name"], 90, y, 20, WHITE, "midleft")
            block_color = col("#7ae7ff") if p.block_charges >= 1 else col("#87939d")
            block_status = f"BLOCK {p.block_charges:g}/3"
            if p.block_timer > 0:
                block_status += f"  {p.block_timer:.1f}s"
            self.text(block_status, 370, y, 17, block_color, "midleft", True)
            if p.ability_cd <= 0:
                self.rect(abc, 235, y - 8, 355, y + 8)
                self.text("READY", 295, y, 16, BLACK, "center", True)
            else:
                f = 1 - p.ability_cd / p.ability_cd_max
                self.rect(col("#5a6b7a"), 235, y - 8, 235 + 120 * max(0, f), y + 8)
            self.rect(WHITE, 235, y - 8, 355, y + 8, 1)

        if self.banner_t > 0 and self.banner_text:
            self.text(self.banner_text, W / 2, 110, 44, GOLD, "center", True)

    def draw_shop_upgrades(self):
        self.panel(110, 30, W - 110, H - 25)
        self.text("UPGRADE SHOP", W / 2, 62, 46, GOLD, "center", True)
        self.text(f"Coins: {self.coins}      Plunder: {self.plunder}", W / 2, 98, 28, WHITE,
                  "center", True)
        y = 135
        for i, u in enumerate(UPGRADES):
            lv = self.lvl(u["id"])
            maxed = lv >= MAX_LEVEL
            cost = self.upgrade_cost(u)
            afford = (not maxed) and self.coins >= cost
            c = col("#7a7a8c") if maxed else WHITE if afford else col("#a06060")
            self.text(f"[{i + 1}]", 140, y, 26, GOLD, "midleft", True)
            self.text(u["name"], 190, y, 26, c, "midleft", True)
            self.text(u["desc"], 370, y, 22, c, "midleft")
            for k in range(MAX_LEVEL):
                px = 640 + k * 18
                self.rect(c, px, y - 7, px + 13, y + 6, 0 if k < lv else 1)
            self.text("MAX" if maxed else f"{cost} coins", W - 140, y, 24, c,
                      "midright", True)
            y += 31
        full = self.raft.hull >= self.max_hull()
        c = col("#7a7a8c") if full else WHITE if self.coins >= REPAIR_COST else col("#a06060")
        self.text("[0]", 140, y, 26, GOLD, "midleft", True)
        self.text("Repair Raft", 190, y, 26, c, "midleft", True)
        self.text(f"+{REPAIR_AMOUNT} hull   (hull {int(self.raft.hull)}/{int(self.max_hull())})",
                  370, y, 22, c, "midleft")
        self.text(f"{REPAIR_COST} coins", W - 140, y, 24, c, "midright", True)
        if self.prestige_unlocked():
            self.text("All upgrades maxed!  Press E for PRESTIGE upgrades (plunder)",
                      W / 2, y + 40, 24, GOLD, "center", True)
        else:
            self.text("Max out every upgrade to unlock the PRESTIGE page (press E)",
                      W / 2, y + 40, 22, col("#aaaaaa"), "center")
        self.text(self.shop_msg, W / 2, H - 85, 26, LIME, "center")
        self.text("Q / E: change page      TAB: menu      SPACE: continue",
                  W / 2, H - 52, 24, WHITE, "center", True)

    def draw_shop_abilities(self):
        self.panel(110, 30, W - 110, H - 25)
        self.text("ABILITY SHOP", W / 2, 62, 46, GOLD, "center", True)
        self.text(f"Coins: {self.coins}      Plunder: {self.plunder}", W / 2, 98, 28, WHITE,
                  "center", True)
        y = 138
        for i, ab in enumerate(ABILITIES):
            owned = i in self.owned
            afford = self.coins >= ab["cost"]
            abc = col(ab["color"])
            c = abc if owned else WHITE if afford else col("#a06060")
            self.text(f"[{i + 1}]", 140, y, 24, GOLD, "midleft", True)
            self.text(ab["name"], 185, y, 24, c, "midleft", True)
            self.text(ab["desc"], 345, y, 20, c, "midleft")
            self.text("OWNED" if owned else f"{ab['cost']} coins", W - 140, y, 22, c,
                      "midright", True)
            y += 29
        y += 8
        self.text("Equip: every crew mate (AI too) uses its own LEFT / RIGHT keys",
                  140, y, 22, LIME, "midleft", True)
        y += 28
        for p in self.players:
            ab = ABILITIES[p.ability]
            self.text(p.name, 140, y, 24, p.color, "midleft", True)
            self.arrow(255, y, -1, 7, col(ab["color"]))
            self.text(ab["name"], 275, y, 24, col(ab["color"]), "midleft", True)
            self.arrow(470, y, 1, 7, col(ab["color"]))
            k = p.k
            self.text(f"{k['left'].upper()} / {k['right'].upper()}", 500, y, 20,
                      col("#aaaaaa"), "midleft")
            y += 25
        self.text(self.shop_msg, W / 2, H - 80, 24, LIME, "center")
        self.text("Q / E: change page      TAB: menu      SPACE: continue",
                  W / 2, H - 50, 24, WHITE, "center", True)

    def draw_shop_prestige(self):
        self.panel(110, 30, W - 110, H - 25)
        self.text("PRESTIGE UPGRADES", W / 2, 62, 46, GOLD, "center", True)
        self.text(f"Plunder: {self.plunder}", W / 2, 98, 28, col("#ffb86b"), "center", True)
        unlocked = self.prestige_unlocked()
        y = 145
        for i, u in enumerate(PRESTIGE):
            lv = self.lvl(u["id"])
            maxed = lv >= PRESTIGE_MAX
            cost = self.prestige_cost(u)
            afford = unlocked and not maxed and self.plunder >= cost
            c = col("#7a7a8c") if (maxed or not unlocked) else WHITE if afford \
                else col("#a06060")
            self.text(f"[{i + 1}]", 140, y, 26, GOLD, "midleft", True)
            self.text(u["name"], 190, y, 24, c, "midleft", True)
            self.text(u["desc"], 385, y, 20, c, "midleft")
            self.text(f"Lv {lv}/{PRESTIGE_MAX}", 625, y, 20, c, "midleft")
            self.text("MAX" if maxed else f"{cost} plunder", W - 140, y, 20, c,
                      "midright", True)
            y += 40
        if unlocked:
            self.text("Plunder drops from every pirate and shark you sink.",
                      W / 2, y + 12, 22, LIME, "center")
        else:
            done = sum(1 for x in UPGRADES if self.lvl(x["id"]) >= MAX_LEVEL)
            self.text(f"LOCKED: max out all {len(UPGRADES)} upgrades first ({done}/{len(UPGRADES)})",
                      W / 2, y + 12, 26, col("#ee6055"), "center", True)
            self.text("You still collect plunder from kills - it will be waiting for you.",
                      W / 2, y + 44, 20, col("#cccccc"), "center")
        self.text(self.shop_msg, W / 2, H - 85, 26, LIME, "center")
        self.text("Q / E: change page      TAB: menu      SPACE: continue",
                  W / 2, H - 52, 24, WHITE, "center", True)

    def draw_shop(self):
        if self.shop_page == 0:
            self.draw_shop_upgrades()
        elif self.shop_page == 1:
            self.draw_shop_abilities()
        else:
            self.draw_shop_prestige()

    def draw_over(self):
        self.panel(W / 2 - 280, H / 2 - 120, W / 2 + 280, H / 2 + 120)
        self.text("RAFT DESTROYED", W / 2, H / 2 - 70, 60, col("#ee6055"), "center", True)
        self.text(f"Islands: {self.score}    Sunk: {self.kills}    Best: {self.best}",
                  W / 2, H / 2 - 15, 32, WHITE, "center")
        mins, secs = divmod(int(self.run_time), 60)
        self.text(f"You survived {mins}:{secs:02d}", W / 2, H / 2 + 25, 26, WHITE, "center")
        self.text("Press R for the main menu", W / 2, H / 2 + 70, 26, LIME, "center")

    def draw_pause_menu(self):
        self.panel(W / 2 - 250, 110, W / 2 + 250, 510)
        self.text("MENU", W / 2, 155, 56, GOLD, "center", True)
        self.text(f"Coins {self.coins}   Plunder {self.plunder}   Islands {self.score}   Sunk {self.kills}",
                  W / 2, 200, 24, WHITE, "center")
        for i, label in enumerate(["Resume", "Shop", "Settings", "Return to Main Menu"]):
            y = 270 + i * 55
            self.text(f"[{i + 1}]", W / 2 - 170, y, 34, GOLD, "midleft", True)
            self.text(label, W / 2 - 115, y, 34, WHITE, "midleft", True)
        self.text("Press a number, or TAB / M / ESC to resume", W / 2, 480, 22, LIME, "center")

    def draw_settings(self):
        st = self.settings
        self.panel(100, 30, W - 100, H - 30)
        self.text("SETTINGS", W / 2, 66, 52, GOLD, "center", True)
        rows = [
            ("View", "3D" if st["view3d"] else "2D (top-down)"),
            ("Difficulty", DIFFICULTY_NAMES[st["difficulty"]]),
            ("Pirates and sharks", "On" if st["pirates"] else "Off"),
            ("Key hints", "On" if st["hints"] else "Off"),
            ("3D camera angle", ["Low", "Medium", "High"][st["cam"]]),
            ("3D chase camera", "On (follows the raft)" if st["chase"] else "Off (fixed)"),
            ("Sound", "On" if st["sound"] else "Off"),
            ("Screen shake", "On" if st["shake"] else "Off"),
            ("Effects quality", "High (transparent)" if st["fx"] else "Low (faster)"),
            ("AI crew skill", AI_LEVELS[st["ai"]]),
        ]
        for i, (label, value) in enumerate(rows):
            y = 118 + i * 40
            self.text(f"[{(i + 1) % 10}]", 140, y, 30, GOLD, "midleft", True)
            self.text(label, 200, y, 30, WHITE, "midleft", True)
            self.arrow(W - 400, y, -1, 8, LIME)
            self.text(value, W - 140, y, 30, LIME, "midright", True)
        self.text("In 3D view: Q / E rotate the camera, V switches views, C toggles chase",
                  W / 2, H - 92, 22, col("#aaaaaa"), "center")
        self.text("Press a number to change a setting      ESC to go back",
                  W / 2, H - 62, 24, WHITE, "center", True)

    def draw_menu_count(self):
        self.text("RAFT FARTS", W / 2, 85, 120, WHITE, "center", True)
        self.text("Fart your way across the sea. Sink pirates. Buy upgrades.",
                  W / 2, 148, 30, LIME, "center")
        self.panel(W / 2 - 330, 185, W / 2 + 330, 505)
        self.text("How many HUMAN players?  Press 0, 1, 2, 3 or 4",
                  W / 2, 218, 34, GOLD, "center", True)
        self.text("Next, you will choose how many AI crew mates to add.",
                  W / 2, 255, 23, WHITE, "center")
        self.text("There can be up to 4 players total.", W / 2, 286, 22,
                  col("#cccccc"), "center")
        self.text("move       fart       ability", W / 2 + 120, 322, 20, WHITE, "center")
        for i, d in enumerate(PLAYER_DEFS):
            y = 354 + i * 34
            self.text(d["name"], W / 2 - 290, y, 29, col(d["color"]), "midleft", True)
            self.text(d["label"], W / 2 - 200, y, 25, WHITE, "midleft", True)
        self.text("Press S for settings (including AI skill)",
                  W / 2, 535, 25, WHITE, "center")
        extra = (f"Best run so far: {self.best} islands" if self.best
                 else "Choose 0 humans if you want an AI-only crew")
        self.text(extra, W / 2, 575, 20, col("#cccccc"), "center")

    def draw_menu_ai_count(self):
        self.text("RAFT FARTS", W / 2, 85, 100, WHITE, "center", True)
        self.panel(W / 2 - 330, 185, W / 2 + 330, 455)
        self.text("How many AI players?", W / 2, 235, 48, GOLD, "center", True)
        self.text(f"Human players selected: {self.n_players}",
                  W / 2, 292, 30, WHITE, "center")
        max_ai = NUM_CREW - self.n_players
        min_ai = 1 if self.n_players == 0 else 0
        choices = "   ".join(str(i) for i in range(min_ai, max_ai + 1))
        prompt = f"Press a number from {min_ai} to {max_ai}"
        self.text(prompt,
                  W / 2, 350, 34, LIME, "center", True)
        self.text(f"Available choices: {choices}", W / 2, 398, 28,
                  WHITE, "center")
        self.text(f"AI skill: {AI_LEVELS[self.settings['ai']]}  (change in Settings)",
                  W / 2, 440, 23, col("#cccccc"), "center")
        self.text("BACKSPACE to change human players     S for settings",
                  W / 2, 535, 23, WHITE, "center")
        self.text("The total number of human + AI players cannot exceed 4.",
                  W / 2, 575, 20, col("#cccccc"), "center")

    def draw_menu_abilities(self):
        total = min(NUM_CREW, self.n_players + self.n_ai)
        self.text("Choose your crew's abilities", W / 2, 60, 62, WHITE, "center", True)
        self.text("Each crew mate (AI too) switches with its own LEFT / RIGHT keys",
                  W / 2, 105, 26, LIME, "center")
        self.panel(70, 130, W - 70, 130 + total * 100 + 20)
        for i in range(total):
            d = PLAYER_DEFS[i]
            ab = ABILITIES[self.ability_choice[i]]
            abc = col(ab["color"])
            y = 180 + i * 100
            label = d["name"] + (" AI" if i >= self.n_players else "")
            self.text(label, 100, y, 40, col(d["color"]), "midleft", True)
            self.arrow(255, y, -1, 10, abc)
            self.text(ab["name"], 280, y, 40, abc, "midleft", True)
            self.arrow(540, y, 1, 10, abc)
            self.text(f"{ab['desc']}  (cooldown {ab['cd']}s)", 255, y + 32, 24, WHITE, "midleft")
            self.text(f"{d['left'].upper()} / {d['right'].upper()}", W - 100, y, 24,
                      col("#aaaaaa"), "midright")
        if self.n_ai:
            self.text("AI crew keep what you pick - re-equip them any time in the shop",
                      W / 2, H - 75, 22, col("#cccccc"), "center")
        self.text("SPACE or ENTER to set sail      BACKSPACE to go back",
                  W / 2, H - 40, 28, WHITE, "center", True)

    def draw(self):
        st = self.state
        self.fx_used = False
        if st == "menu_count":
            self.draw_water_2d()
            self.draw_menu_count()
            return
        if st == "menu_ai_count":
            self.draw_water_2d()
            self.draw_menu_ai_count()
            return
        if st == "menu_abilities":
            self.draw_water_2d()
            self.draw_menu_abilities()
            return
        if st == "settings" and self.settings_return == "menu_count":
            self.draw_water_2d()
            self.draw_settings()
            return

        if self.settings["view3d"]:
            self.draw_scene_3d()
        else:
            self.draw_scene_2d()
        self.draw_hud()

        if st == "paused":
            self.panel(W / 2 - 170, H / 2 - 55, W / 2 + 170, H / 2 + 55)
            self.text("PAUSED", W / 2, H / 2 - 12, 56, WHITE, "center", True)
            self.text("Press P to resume, TAB for the menu", W / 2, H / 2 + 30, 22,
                      LIME, "center")
        elif st == "pause_menu":
            self.draw_pause_menu()
        elif st == "settings":
            self.draw_settings()
        elif st == "shop":
            self.draw_shop()
        elif st == "over":
            self.draw_over()


async def main():
    pygame.mixer.pre_init(SAMPLE_RATE, -16, 1, 512)
    pygame.init()
    pygame.display.set_caption("Raft Farts")
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()
    game = Game(screen)
    while game.running:
        dt = min(clock.tick(FPS) / 1000.0, 1 / 30)   # cap dt so lag can't cause jumps
        game.frame += 1
        game.handle_events()
        game.update(dt)
        game.draw()
        pygame.display.flip()
        await asyncio.sleep(0)      # lets the browser breathe (needed for pygbag)
    pygame.quit()


if __name__ == "__main__":
    asyncio.run(main())
