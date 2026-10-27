"""Headless balance check: a simple bot plays full runs at full speed.

The bot only does what a mouse can do: aim the hero away from the nearest
enemy and click a random card on level up. No window, no pygame.

Usage:  python sim.py [number_of_runs]
"""

import random
import statistics
import sys
from collections import Counter

import rules
from rules import Game, BOSS_TIME

MAX_TIME = 600.0          # stop a run 5 minutes after the boss appears
FLEE_DISTANCE = 300.0     # how far ahead of the hero the "mouse" points
RUNS = 200
BASE_SEED = 1000          # fixed: the same 200 runs every time, so
                          # before/after balance changes are comparable


def play_run(seed):
    g = Game(seed=seed)
    rng = random.Random(seed * 7919 + 13)   # the bot's clicks
    picks = []
    frames = 0
    max_frames = int(MAX_TIME / g.dt)
    while g.state == "running" and frames < max_frames:
        e = g.nearest_enemy()
        if e is not None:
            dx = g.hero.x - e.x
            dy = g.hero.y - e.y
            d = (dx * dx + dy * dy) ** 0.5 or 1.0
            g.set_target(g.hero.x + dx / d * FLEE_DISTANCE,
                         g.hero.y + dy / d * FLEE_DISTANCE)
        g.step()
        frames += 1
        while g.state == "levelup":
            i = rng.randrange(len(g.cards))
            picks.append(g.cards[i]["name"])
            g.pick_card(i)
    return {
        "time": g.time,
        "boss": g.boss_spawned,
        "won": g.state == "won",
        "state": g.state,
        "kills": g.kills,
        "level": g.hero.level,
        "picks": picks,
    }


def main(n):
    runs = [play_run(BASE_SEED + i) for i in range(n)]
    wins = [r for r in runs if r["won"]]
    reached = [r for r in runs if r["boss"]]

    print("runs:                    %d (seeds %d..%d)" % (n, BASE_SEED, BASE_SEED + n - 1))
    print("average survival time:   %.1f s  (%d:%02d)" % (
        statistics.mean(r["time"] for r in runs),
        int(statistics.mean(r["time"] for r in runs)) // 60,
        int(statistics.mean(r["time"] for r in runs)) % 60))
    print("median survival time:    %.1f s" % statistics.median(r["time"] for r in runs))
    print("reached the boss:        %d / %d (%.0f%%)" % (len(reached), n, 100 * len(reached) / n))
    print("won:                     %d / %d (%.0f%%)" % (len(wins), n, 100 * len(wins) / n))
    timeouts = [r for r in runs if r["state"] == "running"]
    if timeouts:
        print("boss met but never killed (%d s cap): %d" % (int(MAX_TIME), len(timeouts)))
    print("average kills:           %.0f" % statistics.mean(r["kills"] for r in runs))
    print("average level at death:  %.1f" % statistics.mean(r["level"] for r in runs))

    def table(label, rows):
        c = Counter(name for r in rows for name in r["picks"])
        total = sum(c.values())
        print("\n%s picks (%d cards taken):" % (label, total))
        for name, count in c.most_common():
            print("  %-16s %4d  %5.1f%%" % (name, count, 100 * count / total))

    table("winners", wins)
    table("all runs", runs)

    win_rate = 100 * len(wins) / n
    print("\nTARGET: win rate between 20%% and 60%% -> %s" % (
        "OK" if 20 <= win_rate <= 60 else "OUT OF RANGE, rebalance data/"))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else RUNS)
