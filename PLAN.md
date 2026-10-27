# PLAN.md — how we will build the game

Read GAME.md first; it has the rules and numbers. This file says which files we make,
in what order, and how each part is tested without opening a window.

## The files

| File | What it does | Depends on |
|---|---|---|
| `data/enemies.json` | The 4 enemies + boss: hp, speed, xp, damage, first wave, sprite name | nothing |
| `data/weapons.json` | The 4 weapons: base damage, cooldown, shots, how each grows per level | nothing |
| `rules.py` | All game logic as plain Python: `Game` class, `step(dt)`, hero, enemies, gems, weapons, waves, level-up, win/lose. No pygame import. Reads the two JSON files. | the JSON files |
| `main.py` | pygame-ce window 390x700, `async def main()`, one `await asyncio.sleep(0)` per frame. Converts mouse position to a world target, calls `Game.step()`, draws everything, shows upgrade cards, handles clicks. | rules.py |
| `tests/test_rules.py` | `unittest` tests for rules.py. Run with `python -m unittest`. | rules.py |
| `raw_art/` | Already there. main.py loads these; we never change them. | — |

The split matters: because `rules.py` has no pygame, every rule can be tested from
the command line, and the browser build (pygbag) will work later.

## Build order, with the test for each step

Work top to bottom. After each step run the test, then start the next step.
A step is not finished until its test passes.

### Step 1 — the data files
Make `data/enemies.json` and `data/weapons.json` by copying the tables from GAME.md.
Test: `python -c "import json; json.load(open('data/enemies.json')); json.load(open('data/weapons.json'))"`
— it must print nothing (valid JSON). Also check every enemy has hp, speed, xp, damage, wave fields.

### Step 2 — hero + world + camera math
In `rules.py`: `Game(fixed_dt)` with hero at world origin, `set_target(x, y)`,
movement toward the target at 130 px/s, clamped to the field (2000x2000).
Test: step 60 times at 1/60 s and check the hero moved about 130 px toward the target;
step with the target at (0,0) and check the hero stops.

### Step 3 — enemies: spawn, chase, contact damage
Enemies move toward the hero at their own speed; touching the hero costs 5 HP with a
0.5 s cooldown per enemy; enemies push each other apart a little so they don't stack.
Test: spawn 1 bat next to the hero, step 1 s, HP is down but not by more than
1s/0.5s = 2 hits = 10 HP. Spawn off-screen, step, check it walks inward.

### Step 4 — weapons from JSON
Each weapon has a cooldown timer; when it fires it spawns projectiles (whip, wand, axe)
or damages the aura circle (garlic). Projectiles fly, damage the first (or every, for axe)
enemy they touch, then expire. Levels read from `weapons.json`.
Test: one bat with 6 hp, whip at level 1 kills it in one hit; check the cooldown counts
in the JSON equals shots per second; check every weapon in the JSON file is buildable
by the code (loop over the file, so a new weapon in JSON needs no code change).

### Step 5 — XP, gems, level-up cards
Killed enemy drops a gem (white/blue/purple by enemy xp). Magnet radius 40 px pulls gems in.
XP curve 5, 11, 17, 23… Level-up pauses the game (`state == "levelup"`) and `cards`
holds 3 choices: new weapon, or +1 level of an owned weapon, or a small passive like +10% speed.
Test: give exact XP, check level up at 5 then 11 more; check `pick_card(i)` applies the
upgrade and the game leaves the level-up state; check no card offers a level-6 weapon.

### Step 6 — waves, timer, boss, win/lose
Wave number = `int(t / 15) + 1`, capped at 20. Each tick spawns `3 + 2n` enemies from
the allowed types for that wave (GAME.md mix), max 60 alive, just outside a random screen edge.
At 5:00 spawn the boss once. Boss dead → `state == "won"`; hero HP 0 → `state == "lost"`.
Test: step the clock with no enemies killing to t=300 s, check the boss appeared exactly once;
check enemy count after tick 1 is 5 (3+2·1) and never exceeds 60; set hero hp to 1 and
land a hit, check "lost".

### Step 7 — the full-run smoke test (still no window)
One test: create a Game, aim the "mouse" at a fixed point, and call `step()` 18 000 times
(5 minutes at 1/60), picking card 0 whenever the state is "levelup". Assert no exception,
the timer reached 5:00, the run ended in won or lost, and the whole thing runs in a few
seconds. This catches crashes and forgetting a timer.

### Step 8 — main.py: drawing and input
Last, because now the game already works. Load sprites from `raw_art/` (hero.png, bat.png,
ghost.png, demon.png for boss, axe.png, gem.png, floor.png, sword.png for whip, slime.png),
camera follows hero, blit enemies/gems/projectiles, draw HP bar, XP bar, timer `M:SS`,
weapon names + levels at the bottom, the 3 cards on level-up, end screen with restart.
Test without a real window: `SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python main.py`
run for ~100 frames then exit (an env var or a `--frames N` flag). It must print the
survivor count and exit with code 0 — this proves the drawing calls and the async loop
work, even though I cannot see pixels. Then I will tell you to run it normally once so
you can see it and play it.

## How to run the tests (for me, every step)
```
python -m unittest -v          # all rules tests, no window needed
SDL_VIDEODRIVER=dummy python main.py --frames 120   # headless game check
```

## Rules I will follow (from AGENTS.md)
- Only stdlib + pygame-ce (+ Pillow if needed for art). I ask before installing anything.
- Numbers live in the JSON files, so changing balance never needs a code change.
- I show you the real test output before saying a step works.
- No git commit unless you ask.
