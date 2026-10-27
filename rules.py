"""All the game rules, stepped with a fixed time step.

No pygame in this file on purpose: the whole game can be tested from the
command line and can later run in a browser with pygbag.
Numbers live in data/weapons.json, data/enemies.json and data/waves.json.
"""

import json
import math
import os
import random

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

FIXED_DT = 1.0 / 60.0          # seconds per step
WORLD_HALF = 1000.0            # the field is 2000 x 2000 px, centred on (0, 0)
HERO_RADIUS = 10.0
MAGNET_BASE = 40.0             # gems this close fly to the hero
CONTACT_COOLDOWN = 0.5         # each enemy can hit once per 0.5 s


def _load(filename):
    with open(os.path.join(DATA_DIR, filename), encoding="utf-8") as f:
        return json.load(f)


WEAPONS_DATA = _load("weapons.json")
ENEMIES = _load("enemies.json")
WAVES = _load("waves.json")
WAVE_INTERVAL = float(WAVES["wave_interval"])       # seconds between wave ticks
WAVE_COUNT = int(WAVES["wave_count"])               # wave ticks before spawning stops
BOSS_TIME = float(WAVES["boss_time"])               # when the boss walks in
ENEMY_CAP = int(WAVES["enemy_cap"])
ENEMIES_PER_WAVE_BASE = int(WAVES["enemies_per_wave_base"])
ENEMIES_PER_WAVE_GROWTH = int(WAVES["enemies_per_wave_growth"])
WEAPONS = WEAPONS_DATA["weapons"]
PASSIVES = WEAPONS_DATA["passives"]
XP_CURVE = WEAPONS_DATA["xp_curve"]
MAX_WEAPONS = WEAPONS_DATA["max_weapons"]
MAX_WEAPON_LEVEL = WEAPONS_DATA["max_weapon_level"]


def xp_needed(level):
    """XP needed to go from `level` to `level + 1`: 4, 7, 10, 13 ..."""
    return XP_CURVE["base"] + XP_CURVE["per_level"] * (level - 1)


def weapon_stats(name, level):
    """All numbers a weapon has at a given level, computed from the JSON."""
    w = WEAPONS[name]
    inc = level - 1
    return {
        "kind": w["kind"],
        "damage": w["base_damage"] + w["damage_per_level"] * inc,
        "shots": int(w["base_shots"] + w["shots_per_level"] * inc),
        "cooldown": max(0.2, w["base_cooldown"] + w["cooldown_change_per_level"] * inc),
        "speed": w.get("projectile_speed", 0.0),
        "lifetime": w.get("projectile_lifetime", 0.0),
        "gravity": w.get("gravity", 0.0),
        "pierce": w.get("pierce", 1),
        "radius": w.get("radius", 0.0) + w.get("radius_per_level", 0.0) * inc,
        "spread_deg": w.get("spread_deg", 0.0),
        "range": w.get("range", 0.0),
    }


def wave_budget(wave):
    """How many enemies wave `wave` schedules, straight from data/waves.json."""
    return ENEMIES_PER_WAVE_BASE + ENEMIES_PER_WAVE_GROWTH * wave


def gem_tier(xp):
    if xp <= 1:
        return "white"
    if xp <= 3:
        return "blue"
    return "purple"


class Hero:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.radius = HERO_RADIUS
        self.speed = 130.0
        self.max_hp = 100.0
        self.hp = 100.0
        self.level = 1
        self.xp = 0.0
        self.facing = (1.0, 0.0)   # unit vector, used by the Whip
        self.target = None         # world position the mouse/finger points at


class Enemy:
    def __init__(self, kind, x, y):
        spec = ENEMIES[kind]
        self.kind = kind
        self.name = spec["name"]
        self.x = x
        self.y = y
        self.hp = float(spec["hp"])
        self.max_hp = self.hp
        self.speed = float(spec["speed"])
        self.xp = spec["xp"]
        self.damage = spec["damage"]
        self.radius = float(spec["radius"])
        self.is_boss = bool(spec.get("is_boss"))
        self.contact_timer = 0.0   # counts down; 0 means "may hit now"
        self.dead = False


class Gem:
    def __init__(self, x, y, xp):
        self.x = x
        self.y = y
        self.xp = xp
        self.tier = gem_tier(xp)


class Projectile:
    def __init__(self, x, y, vx, vy, stats):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.gravity = stats["gravity"]
        self.damage = stats["damage"]
        self.lifetime = stats["lifetime"]
        self.pierce = stats["pierce"]
        self.radius = 5.0
        self.hit_ids = set()
        self.dead = False


class Game:
    """The whole simulation. Create it, call set_target(), call step()
    60 times per second (or run_time() in tests). Read the lists to draw."""

    def __init__(self, seed=0, start_weapon="Whip"):
        self.dt = FIXED_DT
        self.rng = random.Random(seed)
        self.time = 0.0
        self.state = "running"     # running | levelup | won | lost

        self.hero = Hero()
        self.weapons = {}          # weapon name -> level
        self.weapon_timers = {}    # weapon name -> seconds until next shot
        self.shots_fired = {}      # weapon name -> total shots (for tests/HUD)
        self.speed_mult = 1.0
        self.magnet_bonus = 0.0
        if start_weapon:
            self.add_weapon(start_weapon)

        self.enemies = []
        self.gems = []
        self.projectiles = []
        self.spawn_queue = []      # list of (spawn_time, enemy_kind)
        self.wave = 0
        self.next_tick = 0.0
        self.boss_spawned = False
        self.cards = []
        self.pending_cards = 0     # levels gained but not yet paid with a card
        self.kills = 0
        self.events = []           # things that happened in the last step:
                                   # (kind, x, y, amount) for sound & effects
        self._schedule_next_wave()

    # ---------- content helpers ----------

    def add_weapon(self, name):
        self.weapons[name] = 1
        self.weapon_timers[name] = 0.3   # small delay before the first shot
        self.shots_fired.setdefault(name, 0)

    def spawn_enemy(self, kind, x, y):
        e = Enemy(kind, x, y)
        self.enemies.append(e)
        return e

    # ---------- waves ----------

    def _allowed_kinds(self, wave):
        return [k for k, spec in ENEMIES.items()
                if not spec.get("is_boss") and spec["wave"] <= wave]

    def _schedule_next_wave(self):
        self.wave += 1
        budget = wave_budget(self.wave)
        kinds = self._allowed_kinds(self.wave)
        newest = max(kinds, key=lambda k: ENEMIES[k]["wave"])
        for i in range(budget):
            if len(kinds) > 1 and self.rng.random() < 0.5:
                kind = newest           # half the budget goes to the newest type
            else:
                kind = self.rng.choice(kinds)
            when = self.next_tick + (i + 0.5) / budget * WAVE_INTERVAL
            self.spawn_queue.append((when, kind))
        self.next_tick += WAVE_INTERVAL

    def _spawn_due_enemies(self):
        still = []
        for when, kind in self.spawn_queue:
            if when > self.time:
                still.append((when, kind))
                continue
            if len(self.enemies) >= ENEMY_CAP:
                continue               # this tick's enemy is simply lost
            # just outside the visible screen, on a random edge of the box
            edge = self.rng.randrange(4)
            ox = self.rng.uniform(-250.0, 250.0)
            oy = self.rng.uniform(-400.0, 400.0)
            if edge == 0:
                x, y = self.hero.x + ox, self.hero.y - 400.0
            elif edge == 1:
                x, y = self.hero.x + ox, self.hero.y + 400.0
            elif edge == 2:
                x, y = self.hero.x - 250.0, self.hero.y + oy
            else:
                x, y = self.hero.x + 250.0, self.hero.y + oy
            self.spawn_enemy(kind, x, y)
        self.spawn_queue = still

    # ---------- main step ----------

    def step(self):
        if self.state != "running":
            return
        self.events = []
        self.time += self.dt
        half = self.dt / 2.0   # avoid float noise at exact tick boundaries

        while self.wave < WAVE_COUNT and self.time >= self.next_tick - half:
            self._schedule_next_wave()
        self._spawn_due_enemies()
        if not self.boss_spawned and self.time >= BOSS_TIME - half:
            self.boss_spawned = True
            self.spawn_enemy("giant_bat", self.hero.x, self.hero.y - 400.0)

        self._move_hero()
        self._fire_weapons()
        self._move_projectiles()
        self._move_enemies()
        self._contact_damage()
        self._update_gems()
        self._cleanup_deaths()

    def run_time(self, seconds):
        for _ in range(round(seconds / self.dt)):
            self.step()

    # ---------- hero ----------

    def set_target(self, x, y):
        self.hero.target = (float(x), float(y))

    def clear_target(self):
        """The player lifted their finger: stop walking."""
        self.hero.target = None

    def _move_hero(self):
        h = self.hero
        if h.target is None:
            return
        dx = h.target[0] - h.x
        dy = h.target[1] - h.y
        dist = math.hypot(dx, dy)
        step_len = h.speed * self.speed_mult * self.dt
        if dist <= step_len:
            h.x, h.y = h.target        # arrive, do not overshoot
        else:
            h.x += dx / dist * step_len
            h.y += dy / dist * step_len
            h.facing = (dx / dist, dy / dist)
        h.x = max(-WORLD_HALF, min(WORLD_HALF, h.x))
        h.y = max(-WORLD_HALF, min(WORLD_HALF, h.y))

    # ---------- weapons ----------

    def nearest_enemy(self, max_range=0.0):
        best, best_d = None, None
        for e in self.enemies:
            if e.dead:
                continue
            d = math.hypot(e.x - self.hero.x, e.y - self.hero.y)
            if max_range and d > max_range:
                continue
            if best_d is None or d < best_d:
                best, best_d = e, d
        return best

    def _fire_weapons(self):
        for name in list(self.weapons):
            self.weapon_timers[name] -= self.dt
            if self.weapon_timers[name] > 0:
                continue
            stats = weapon_stats(name, self.weapons[name])
            fired = self._fire_once(name, stats)
            if fired:
                self.weapon_timers[name] += stats["cooldown"]
                self.shots_fired[name] += 1
            else:
                self.weapon_timers[name] = 0.0   # nothing to shoot at, retry soon

    def _fire_once(self, name, stats):
        kind = stats["kind"]
        h = self.hero
        if kind == "aura":
            for e in self.enemies:
                if not e.dead and math.hypot(e.x - h.x, e.y - h.y) <= stats["radius"] + e.radius:
                    self.damage_enemy(e, stats["damage"])
            return True
        if kind == "fan":
            angle = math.atan2(h.facing[1], h.facing[0])
            n = max(1, stats["shots"])
            spread = math.radians(stats["spread_deg"])
            for i in range(n):
                a = angle - spread / 2 + spread * (i / (n - 1) if n > 1 else 0.5)
                self.projectiles.append(Projectile(
                    h.x, h.y, math.cos(a) * stats["speed"], math.sin(a) * stats["speed"], stats))
            return True
        if kind == "aim":
            target = self.nearest_enemy(stats["range"])
            if target is None:
                return False
            dx, dy = target.x - h.x, target.y - h.y
            d = math.hypot(dx, dy) or 1.0
            for i in range(max(1, stats["shots"])):
                # a small fan for extra shots, centred on the target
                a = math.atan2(dy, dx) + (i - (stats["shots"] - 1) / 2) * 0.15
                self.projectiles.append(Projectile(
                    h.x, h.y, math.cos(a) * stats["speed"], math.sin(a) * stats["speed"], stats))
            return True
        if kind == "arc":
            for i in range(max(1, stats["shots"])):
                a = -math.pi / 2 + math.radians(self.rng.uniform(-stats["spread_deg"], stats["spread_deg"]))
                self.projectiles.append(Projectile(
                    h.x, h.y, math.cos(a) * stats["speed"], math.sin(a) * stats["speed"], stats))
            return True
        raise ValueError("weapon %r has unknown kind %r" % (name, kind))

    def _move_projectiles(self):
        for p in self.projectiles:
            if p.dead:
                continue
            p.vy += p.gravity * self.dt
            p.x += p.vx * self.dt
            p.y += p.vy * self.dt
            p.lifetime -= self.dt
            if p.lifetime <= 0:
                p.dead = True
                continue
            for e in self.enemies:
                if e.dead or id(e) in p.hit_ids:
                    continue
                if math.hypot(e.x - p.x, e.y - p.y) <= e.radius + p.radius:
                    self.damage_enemy(e, p.damage)
                    p.hit_ids.add(id(e))
                    p.pierce -= 1
                    if p.pierce <= 0:
                        p.dead = True
                        break
        self.projectiles = [p for p in self.projectiles if not p.dead]

    # ---------- enemies ----------

    def _move_enemies(self):
        h = self.hero
        for e in self.enemies:
            if e.dead:
                continue
            dx, dy = h.x - e.x, h.y - e.y
            d = math.hypot(dx, dy)
            if d > 1e-6:
                move = e.speed * self.dt
                if d - move > h.radius:      # do not walk through the hero
                    e.x += dx / d * move
                    e.y += dy / d * move
        # gentle separation so enemies do not stack (every 4th frame is enough)
        if int(self.time / self.dt) % 4 == 0:
            n = len(self.enemies)
            for i in range(n):
                a = self.enemies[i]
                if a.dead:
                    continue
                for j in range(i + 1, n):
                    b = self.enemies[j]
                    if b.dead:
                        continue
                    dx, dy = b.x - a.x, b.y - a.y
                    d = math.hypot(dx, dy)
                    need = a.radius + b.radius
                    if 1e-6 < d < need:
                        push = (need - d) / 2.0
                        nx, ny = dx / d * push, dy / d * push
                        a.x -= nx
                        a.y -= ny
                        b.x += nx
                        b.y += ny

    def _contact_damage(self):
        h = self.hero
        for e in self.enemies:
            if e.dead:
                continue
            touching = math.hypot(e.x - h.x, e.y - h.y) <= h.radius + e.radius
            if touching and e.contact_timer <= 0:
                self.damage_hero(e.damage)
                e.contact_timer = CONTACT_COOLDOWN
            else:
                e.contact_timer -= self.dt

    def _emit(self, kind, x=0.0, y=0.0, amount=0):
        self.events.append((kind, x, y, amount))

    def damage_enemy(self, e, amount):
        if e.dead:
            return
        e.hp -= amount
        self._emit("hit", e.x, e.y, amount)
        if e.hp <= 0:
            e.dead = True

    def damage_hero(self, amount):
        self.hero.hp -= amount
        self._emit("hurt", self.hero.x, self.hero.y, amount)
        if self.hero.hp <= 0:
            self.hero.hp = 0
            self.state = "lost"
            self._emit("over")

    # ---------- xp, gems, level up ----------

    def _update_gems(self):
        h = self.hero
        magnet = MAGNET_BASE + self.magnet_bonus
        for g in self.gems:
            d = math.hypot(g.x - h.x, g.y - h.y)
            if d <= magnet:
                if d <= h.radius + 4.0:
                    self._emit("gem", g.x, g.y, g.xp)
                    self.add_xp(g.xp)
                    g.taken = True
                else:
                    g.x += (h.x - g.x) / d * 400.0 * self.dt
                    g.y += (h.y - g.y) / d * 400.0 * self.dt

    def add_xp(self, amount):
        h = self.hero
        h.xp += amount
        while h.xp >= xp_needed(h.level):
            h.xp -= xp_needed(h.level)
            h.level += 1
            self.pending_cards += 1
        if self.pending_cards and self.state == "running":
            self.state = "levelup"
            self.cards = self.generate_cards()
            self._emit("levelup", h.x, h.y)

    def generate_cards(self):
        pool = []
        for name in WEAPONS:
            owned = self.weapons.get(name)
            if owned is not None:
                if owned < MAX_WEAPON_LEVEL:
                    pool.append({"kind": "levelup", "name": name,
                                 "level": owned + 1,
                                 "text": "%s level %d" % (name, owned + 1)})
            elif len(self.weapons) < MAX_WEAPONS:
                pool.append({"kind": "new", "name": name, "level": 1,
                             "text": "NEW: %s - %s" % (name, WEAPONS[name]["desc"])})
        for name, spec in PASSIVES.items():
            pool.append({"kind": "passive", "name": name, "level": 1, "text": spec["desc"]})
        return self.rng.sample(pool, 3)

    def pick_card(self, index):
        if self.state != "levelup":
            return
        card = self.cards[index]
        if card["kind"] == "new":
            self.add_weapon(card["name"])
        elif card["kind"] == "levelup":
            self.weapons[card["name"]] += 1
        else:
            spec = PASSIVES[card["name"]]
            if spec["kind"] == "speed":
                self.speed_mult += spec["amount"]
            elif spec["kind"] == "health":
                self.hero.max_hp += spec["amount"]
                self.hero.hp = min(self.hero.max_hp, self.hero.hp + spec["amount"])
            elif spec["kind"] == "magnet":
                self.magnet_bonus += spec["amount"]
        # more levels may still be waiting from one big gem
        self.pending_cards -= 1
        self.cards = []
        if self.pending_cards > 0:
            self.cards = self.generate_cards()
        else:
            self.state = "running"

    # ---------- deaths and end of run ----------

    def _cleanup_deaths(self):
        survivors = []
        for e in self.enemies:
            if not e.dead:
                survivors.append(e)
                continue
            self.kills += 1
            self.gems.append(Gem(e.x, e.y, e.xp))
            self._emit("die", e.x, e.y)
            if e.is_boss:
                self.state = "won"
                self._emit("win")
        self.enemies = survivors
        self.gems = [g for g in self.gems if not getattr(g, "taken", False)]
