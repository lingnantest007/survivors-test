"""Tests for the game rules. No window is opened: `python -m unittest`."""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import rules
from rules import Game, weapon_stats, xp_needed

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "..", "data")


def make_survivor_game(seed=1):
    """A weaponless, unkillable hero: the run never pauses for a card and
    never ends, so tests can just watch waves, spawns and the clock."""
    g = Game(seed=seed, start_weapon=None)
    g.hero.hp = g.hero.max_hp = 1_000_000
    return g


class TestDataFiles(unittest.TestCase):
    def test_json_is_valid_and_complete(self):
        with open(os.path.join(DATA, "weapons.json"), encoding="utf-8") as f:
            weapons = json.load(f)
        with open(os.path.join(DATA, "enemies.json"), encoding="utf-8") as f:
            enemies = json.load(f)
        with open(os.path.join(DATA, "waves.json"), encoding="utf-8") as f:
            waves = json.load(f)
        for field in ("wave_interval", "wave_count", "boss_time",
                      "enemies_per_wave_base", "enemies_per_wave_growth",
                      "enemy_cap"):
            self.assertIn(field, waves, "waves.json missing %s" % field)
            self.assertIsInstance(waves[field], (int, float),
                                  "waves.json %s is not a number" % field)
        self.assertGreater(waves["enemy_cap"], 0)
        for name, w in weapons["weapons"].items():
            for field in ("kind", "base_damage", "base_shots", "base_cooldown"):
                self.assertIn(field, w, "%s missing %s" % (name, field))
        bosses = [k for k, e in enemies.items() if e.get("is_boss")]
        self.assertEqual(len(bosses), 1)
        for name, e in enemies.items():
            for field in ("hp", "speed", "xp", "damage", "wave", "radius", "sprite"):
                self.assertIn(field, e, "%s missing %s" % (name, field))
        self.assertEqual(len(weapons["weapons"]), 4)
        self.assertEqual(len([e for e in enemies.values() if not e.get("is_boss")]), 4)


class TestHeroMovement(unittest.TestCase):
    def test_walks_130_px_in_one_second(self):
        g = Game(seed=1, start_weapon=None)
        g.set_target(130.0, 0.0)
        g.run_time(1.0)
        self.assertAlmostEqual(g.hero.x, 130.0, delta=0.5)
        self.assertAlmostEqual(g.hero.y, 0.0, delta=0.5)

    def test_stops_at_the_target(self):
        g = Game(seed=1, start_weapon=None)
        g.set_target(50.0, 0.0)
        g.run_time(2.0)
        self.assertAlmostEqual(g.hero.x, 50.0, delta=1e-6)
        g.run_time(1.0)
        self.assertAlmostEqual(g.hero.x, 50.0, delta=1e-6)

    def test_clear_target_stops_the_hero(self):
        g = Game(seed=1, start_weapon=None)
        g.set_target(400.0, 0.0)
        g.run_time(1.0)
        moved = g.hero.x
        self.assertGreater(moved, 0.0)
        g.clear_target()
        g.run_time(2.0)
        self.assertAlmostEqual(g.hero.x, moved, delta=1e-6)

    def test_clamped_to_the_field(self):
        g = Game(seed=1, start_weapon=None)
        g.set_target(9999.0, 0.0)
        g.run_time(60.0)
        self.assertAlmostEqual(g.hero.x, rules.WORLD_HALF, delta=1e-6)


class TestEnemies(unittest.TestCase):
    def test_contact_damage_is_fixed_cooldown(self):
        dmg = rules.ENEMIES["bat"]["damage"]
        g = Game(seed=1, start_weapon=None)
        g.spawn_enemy("bat", g.hero.x, g.hero.y)
        g.run_time(1.0)          # exactly 2 hits landed (t=0 and t=0.5)
        self.assertEqual(g.hero.hp, 100 - 2 * dmg)
        g.run_time(0.2)          # by 1.2 s the third hit has landed, no fourth
        self.assertEqual(g.hero.hp, 100 - 3 * dmg)

    def test_enemy_walks_toward_the_hero(self):
        g = Game(seed=1, start_weapon=None)
        e = g.spawn_enemy("bat", 300.0, 0.0)
        before = abs(e.x - g.hero.x)
        g.run_time(1.0)
        after = abs(e.x - g.hero.x)
        self.assertLess(after, before)
        self.assertAlmostEqual(before - after, e.speed, delta=20.0)

    def test_hero_death_ends_the_run(self):
        g = Game(seed=1, start_weapon=None)
        g.hero.hp = rules.ENEMIES["bat"]["damage"]
        g.spawn_enemy("bat", g.hero.x, g.hero.y)
        g.step()
        self.assertEqual(g.state, "lost")


class TestWeapons(unittest.TestCase):
    def test_whip_level_1_kills_a_bat(self):
        g = Game(seed=3)
        # no target: the hero stands still and faces +x, where the bat walks in
        g.spawn_enemy("bat", 40.0, 0.0)
        g.run_time(2.0)
        self.assertEqual(g.kills, 1)

    def test_level_math_follows_the_json(self):
        for name, w in rules.WEAPONS.items():
            for level in (1, 3, 5):
                s = weapon_stats(name, level)
                inc = level - 1
                self.assertEqual(s["damage"], w["base_damage"] + w["damage_per_level"] * inc)
                self.assertEqual(s["shots"], int(w["base_shots"] + w["shots_per_level"] * inc))
                self.assertAlmostEqual(
                    s["cooldown"],
                    max(0.2, w["base_cooldown"] + w["cooldown_change_per_level"] * inc))
        # and a few concrete spot checks of the per-level growth
        self.assertEqual(weapon_stats("Whip", 5)["shots"], 6)     # +1 shot per level
        self.assertEqual(weapon_stats("Axe", 5)["shots"], 3)      # +1 axe per 2 levels
        self.assertEqual(weapon_stats("Garlic", 3)["radius"], 56)  # +8 px per level

    def test_every_weapon_in_the_json_fires(self):
        """A new weapon added to the JSON must work without code changes."""
        for name in rules.WEAPONS:
            g = Game(seed=5, start_weapon=None)
            g.add_weapon(name)
            g.set_target(200.0, 0.0)
            g.spawn_enemy("bat", 50.0, 0.0)
            g.run_time(2.0)
            self.assertGreater(g.shots_fired[name], 0, "%s never fired" % name)

    def test_garlic_aura_damages_nearby_enemy(self):
        g = Game(seed=5, start_weapon=None)
        g.add_weapon("Garlic")
        e = g.spawn_enemy("bat", 30.0, 0.0)
        g.run_time(1.0)
        self.assertLess(e.hp, e.max_hp)


class TestXPAndCards(unittest.TestCase):
    def test_level_up_at_the_curve_then_one_more_step(self):
        need1 = xp_needed(1)
        need2 = xp_needed(2)
        self.assertGreater(need2, need1)
        g = Game(seed=1, start_weapon=None)
        g.add_xp(need1 - 1)
        self.assertEqual(g.hero.level, 1)
        self.assertEqual(g.state, "running")
        g.add_xp(1)
        self.assertEqual(g.hero.level, 2)
        self.assertEqual(g.state, "levelup")
        self.assertEqual(len(g.cards), 3)
        g.pick_card(0)
        self.assertEqual(g.state, "running")
        g.add_xp(need2 - 1)
        self.assertEqual(g.hero.level, 2)
        g.add_xp(1)
        self.assertEqual(g.hero.level, 3)

    def test_levelup_pauses_the_game(self):
        g = Game(seed=1, start_weapon=None)
        g.add_xp(5)
        frozen = g.time
        g.run_time(2.0)
        self.assertEqual(g.time, frozen)
        self.assertEqual(g.state, "levelup")

    def test_no_card_offers_a_level_above_max(self):
        g = Game(seed=1, start_weapon=None)
        for name in rules.WEAPONS:
            g.add_weapon(name)
        for _ in range(50):
            g.weapons = {k: min(5, v + 1) for k, v in g.weapons.items()}
            for card in g.generate_cards():
                if card["kind"] != "passive":
                    self.assertLessEqual(card["level"], rules.MAX_WEAPON_LEVEL)
        # everything owned and maxed -> only passives are left, still 3 cards
        g.weapons = {k: 5 for k in rules.WEAPONS}
        cards = g.generate_cards()
        self.assertEqual(len(cards), 3)
        self.assertTrue(all(c["kind"] == "passive" for c in cards))

    def test_picking_a_new_weapon_card_adds_the_weapon(self):
        g = Game(seed=1, start_weapon=None)
        card = {"kind": "new", "name": "Axe", "level": 1, "text": ""}
        g.state = "levelup"
        g.cards = [card, card, card]
        g.pending_cards = 1
        g.pick_card(0)
        self.assertEqual(g.weapons.get("Axe"), 1)
        self.assertEqual(g.state, "running")

    def test_big_gem_grants_one_card_per_level(self):
        g = Game(seed=1, start_weapon=None)
        g.add_xp(100)                       # boss gem: several levels at once
        levels_gained = g.hero.level - 1
        self.assertGreater(levels_gained, 1)
        self.assertEqual(g.pending_cards, levels_gained)
        for _ in range(levels_gained):
            self.assertEqual(g.state, "levelup")
            self.assertEqual(len(g.cards), 3)
            g.pick_card(0)
        self.assertEqual(g.state, "running")
        self.assertEqual(g.pending_cards, 0)


class TestWavesAndBoss(unittest.TestCase):
    def test_first_tick_spawns_the_wave_one_budget(self):
        g = make_survivor_game(seed=2)
        g.run_time(rules.WAVE_INTERVAL)
        self.assertEqual(g.wave, 2)
        self.assertEqual(len(g.enemies), rules.wave_budget(1))

    def test_wave_size_grows_with_the_formula(self):
        g = make_survivor_game(seed=2)
        expected = sum(rules.wave_budget(n) for n in (1, 2, 3))
        g.run_time(3 * rules.WAVE_INTERVAL)
        self.assertEqual(g.kills + len(g.enemies), expected)

    def test_alive_enemies_never_exceed_the_cap(self):
        g = make_survivor_game(seed=2)
        for _ in range(600):
            g.step()
            self.assertLessEqual(len(g.enemies), rules.ENEMY_CAP)

    def test_boss_spawns_once_at_the_boss_time(self):
        g = make_survivor_game(seed=2)
        g.run_time(rules.BOSS_TIME + 1.0)
        self.assertTrue(g.boss_spawned)
        bosses = [e for e in g.enemies if e.is_boss]
        self.assertEqual(len(bosses), 1)

    def test_killing_the_boss_wins_the_run(self):
        g = make_survivor_game(seed=2)
        boss = g.spawn_enemy("giant_bat", 100.0, 0.0)
        g.damage_enemy(boss, boss.hp)
        g.step()
        self.assertEqual(g.state, "won")


class TestFullRunSmoke(unittest.TestCase):
    def test_five_minutes_without_a_window(self):
        g = Game(seed=7)
        g.hero.hp = g.hero.max_hp = 1_000_000   # cheat: always reach the boss
        frames = 0
        while g.state == "running" and frames < 8 * 60 * 60:
            e = g.nearest_enemy()
            if e is not None:
                g.set_target(e.x, e.y)
            g.step()
            frames += 1
            while g.state == "levelup":
                g.pick_card(0)
        self.assertGreaterEqual(g.time, rules.BOSS_TIME)
        self.assertEqual(g.state, "won", "run should end with the boss dead")
        self.assertGreater(g.kills, 100)


if __name__ == "__main__":
    unittest.main()
