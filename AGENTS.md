# Survivors game — project rules (CDT501 Lecture 9)

## What this project is
A small action roguelike like Vampire Survivors, in Python with pygame-ce.
Window 390 x 700 px (portrait, like a phone). Mouse or finger only.

## How the project is organised
- rules.py: all the game rules, stepped with a fixed time step. No pygame in this file.
- data/weapons.json and data/enemies.json: the content. Changing a number there must not need a code change.
- main.py: the window, drawing and input (pygame-ce). The main loop is `async def main()`
  with `await asyncio.sleep(0)` once per frame, so pygbag can run it in a browser later.
- tests/: tests with the standard library `unittest`.
- raw_art/: original 16x16 pictures (Kenney, CC0). Never change, move or delete them.

## Rules for the agent
- Use only Python's standard library, pygame-ce and Pillow. Ask before installing anything else.
- Before you say something works, run it: `python -m unittest` for the rules, and a short run of
  main.py without a window (SDL_VIDEODRIVER=dummy) for the game. Show me the real output.
- Explain what you did in simple English: I am learning to program.
- Do not run git commit unless I ask you to.
