# Survivors game — design document (CDT501 Lecture 9)

One screen, one hero, weapons that fire by themselves. Survive 5 minutes, then kill the boss.

Every number in this document is copied from `data/waves.json`, `data/enemies.json`,
`data/weapons.json` or from a small fixed constant in `rules.py` (marked `rules.py` below).
Change the JSON file, not the code.

## Core loop (one cycle, about 10 seconds)
1. Hero walks toward the mouse pointer / finger. Player never aims or presses attack.
2. Weapons fire on their own timers and kill enemies.
3. Dead enemies drop XP gems; walking over a gem picks it up.
4. Enough XP → game pauses, shows 3 upgrade cards, player clicks one.
5. Waves get bigger. At 5:00 the boss spawns. Kill it = win. Hero HP = 0 = lose.

## Win / lose
- Win: boss HP reaches 0.
- Lose: hero HP reaches 0 (enemies touch you, boss touches you).
- Timer at 5:00 does not end the run by itself; it only spawns the boss.

## Controls
- Window 390 x 700, portrait. The hero walks toward the pointer, at full speed, for as long
  as you keep pointing: on a computer a mouse pointer that stands still still walks (the
  target is re-aimed every frame, so the screen offset keeps moving with the camera); on a
  phone he walks while your finger is on the screen and stops the moment you lift it.
- Point at the middle of the screen (= at the hero) to stand still.
- Click / tap: choose an upgrade card, or start a new run after the end. One tap takes
  exactly one card. Nothing else to press.
- Escape or `p`: pause.

## Numbers (the whole balance in one table)
| Thing | Value | Where |
|---|---|---|
| Hero speed | 130 px/s | rules.py |
| Hero HP | 100, regen 0 | rules.py |
| Hero hit radius | 10 px | rules.py |
| Contact damage | 1 per enemy (boss 5), 0.5 s cooldown per enemy | enemies.json / rules.py |
| XP needed to reach next level | 4 at level 1, then +3 per level (4, 7, 10, 13, …) | weapons.json |
| Gem XP | white 1, blue 3, purple 10 or more | rules.py (tiers), enemies.json (values) |
| Pickup magnet radius | 40 px (+15 per Magnet Clasp) | rules.py / weapons.json |
| Wave interval | every 12 s the wave number goes up | waves.json |
| Number of waves | 25 | waves.json |
| Enemies per wave | wave n = 8 + 1 × n (wave 1 → 9, wave 25 → 33) | waves.json |
| Enemies alive cap | 60 | waves.json |
| Boss spawn | at 5:00 (300 s), from the top | waves.json |

## Weapons (4, each level 1–5; max 4 weapons held)
Level 1 of a weapon you do not own yet = "new weapon" card. Otherwise = "+1 level" card.

1. **Whip** — slashes forward in a fan: 7 damage, 2 shots, 0.9 s cooldown, 30° spread.
   +2 damage and +1 shot per level. Projectile speed 300 px/s, lives 0.35 s.
2. **Magic Wand** — shoots the nearest enemy: 7 damage, 1 shot, 0.8 s cooldown, range 500 px.
   +2 damage and −0.05 s cooldown per level. Projectile speed 350 px/s, lives 1.5 s.
3. **Garlic** — damages everything around you: 4 damage every 0.5 s within 40 px.
   +8 px radius per level (damage stays 4).
4. **Axe** — thrown up in an arc, hits everything it passes: 12 damage, 1 axe, 1.5 s cooldown,
   25° spread, pierces 99 times. +3 damage per level, +1 axe per 2 levels.
   Projectile speed 260 px/s, lives 2.0 s, gravity 500 px/s².

Passives (one pick each): **Swift Boots** +10% move speed, **Hearty Cherry** +25 max HP, heals 25,
**Magnet Clasp** +15 gem pickup radius.

## Enemies (4 + boss)
| Enemy | HP | Speed | XP | Damage | Radius | Appears from wave | Looks like |
|---|---|---|---|---|---|---|---|
| Bat | 5 | 80 | 1 | 1 | 8 | 1 | small grey circle, fast, weak |
| Zombie | 14 | 45 | 2 | 1 | 10 | 2 | green square, slow, tanky |
| Skeleton | 10 | 80 | 3 | 1 | 9 | 5 | white triangle, medium |
| Ghost | 7 | 110 | 3 | 1 | 8 | 8 | pale blue circle, drifts straight at you, ignores walls |
| **Boss: Giant Bat** | 600 | 60 | 100 | 5 | 40 | 99 (only the timer) | 5× bat, chases slowly |

Spawn order: wave 1 bats; wave 2+ add zombies; wave 5+ add skeletons; wave 8+ add ghosts;
roughly half of each wave budget goes to the newest type, the rest is spread over everything
allowed. Enemies spawn just off-screen on any of the 4 edges.

## Waves (`data/waves.json`)
25 spawn ticks of 12 s each → the ticks run out at 5:00, when the boss arrives (boss_time 300 s).
Wave n spawns `8 + 1 × n` enemies, spread evenly over the tick: 9 in the first 12 seconds,
10 in the next, 33 in the last tick.
Cap 60 alive; an enemy that cannot fit is simply not spawned. The mix is from the table above.
Why these numbers: the opening minute used to show about 3 bats at 10 s and only bats all minute,
which players found boring. With 12 s ticks, a 9-enemy first wave and zombies from wave 2, the
same minute shows ~8 enemies at 10 s and ~26 at 40 s; the third type (skeleton) joins at ~49 s,
so by 60 s the player has met three kinds instead of one. Measured over 30 bot runs, sim.py seeds.

## What the screen shows
- Field: dark green, tiles scroll as the hero moves (hero stays near the middle, camera follows).
- Top-left: HP bar (red) and XP bar (blue) with the level number.
- Top-right: run timer `M:SS`.
- Bottom: icons for each weapon owned + its level, e.g. `Whip 3`.
- Pause card screen: 3 rounded rectangles, click to pick, each shows name, one-line description, level.
- End: "VICTORY" or "GAME OVER", kills and level reached, click to restart.

## Build order (one afternoon)
1. `rules.py`: hero movement, enemies chasing, contact damage, game state. Pure Python, no pygame.
2. `data/waves.json`, `data/weapons.json`, `data/enemies.json`: all the numbers above.
3. Weapons firing and projectiles in `rules.py`.
4. XP, level-up, 3-card upgrade choice.
5. Waves + timer + boss (all read from `data/waves.json`).
6. `main.py`: camera, sprites from `raw_art/`, HUD, cards.
7. `tests/`: XP curve, wave sizing, weapon level math.
