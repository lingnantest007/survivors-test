"""The window: drawing and input only. All the rules live in rules.py.

Run normally:      python main.py
Headless check:    SDL_VIDEODRIVER=dummy python main.py --frames 300
Web build:         python -m pygbag --build .   -> build/web/index.html

This file must only read the finished files from assets/ and sounds/:
make_assets.py (Pillow) and make_sounds.py (wave) are separate scripts you run
on your computer, because neither library works in a browser.

The hero walks toward the mouse pointer (a pointer that stands still keeps him
walking) or toward your finger; on a phone he stops the moment you lift it.
Weapons fire themselves. Click a card when you level up. P pauses, Esc quits.
"""

import asyncio
import os
import random
import sys

import pygame

import rules
from rules import Game, weapon_stats

W, H = 390, 700
FPS = 60
TILE = 48                       # size of an upscaled floor tile
CARD_KEYS = ("new", "levelup", "passive")

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET_DIR = os.path.join(HERE, "assets")
SOUND_DIR = os.path.join(HERE, "sounds")


def sprite_path(name):
    return os.path.join(ASSET_DIR, name)


def sprite_names():
    """The pictures the game needs. One per enemy comes from data/enemies.json,
    so a new enemy in the JSON needs no change here. make_assets.py makes these
    from raw_art/ - on your computer, never in the browser."""
    fixed = ["floor.png", "hero.png", "axe.png",
             "gem_white.png", "gem_blue.png", "gem_purple.png"]
    return sorted(set(fixed + [spec["sprite"] for spec in rules.ENEMIES.values()]))


class Assets:
    def __init__(self):
        self.img = {}
        missing = [n for n in sprite_names() if not os.path.exists(sprite_path(n))]
        if missing:
            raise SystemExit(
                "assets/ is missing: %s\n"
                "Run  python make_assets.py  on your computer to build them "
                "from raw_art/." % ", ".join(missing))
        for name in sprite_names():
            surf = pygame.image.load(sprite_path(name)).convert_alpha()
            self.img[name] = surf

    def get(self, name):
        return self.img[name]

    def draw(self, screen, name, world_x, world_y, cam_x, cam_y):
        img = self.img[name]
        screen.blit(img, (world_x - cam_x - img.get_width() // 2,
                          world_y - cam_y - img.get_height() // 2))


VOLUMES = {"hit": 0.25, "gem": 0.4, "levelup": 0.7, "hurt": 0.55, "gameover": 0.8}


def sound_path(name):
    """sounds/<name>.ogg if it is there, else sounds/<name>.wav.
    pygbag turns the .wav files into .ogg when it builds the web version,
    so on the computer you get .wav and in the browser the .ogg."""
    for ext in (".ogg", ".wav"):
        path = os.path.join(SOUND_DIR, name + ext)
        if os.path.exists(path):
            return path
    return None


class Sounds:
    """Loads sounds/*.wav (or *.ogg in the browser build) if audio works; silently
    does nothing if not (for example in the headless test with SDL_AUDIODRIVER=dummy).
    make_sounds.py writes these on your computer, never in the browser."""

    def __init__(self):
        self.snd = {}
        if not pygame.mixer.get_init():
            try:
                pygame.mixer.init()
            except pygame.error:
                return
        for name in VOLUMES:
            path = sound_path(name)
            if path is None:
                continue
            try:
                s = pygame.mixer.Sound(path)
                s.set_volume(VOLUMES[name])
                self.snd[name] = s
            except pygame.error:
                pass

    def play(self, name):
        s = self.snd.get(name)
        if s:
            s.play()


def fmt_time(t):
    return "%d:%02d" % (int(t) // 60, int(t) % 60)


async def main(max_frames=0):
    pygame.init()
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Survivors")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("monospace", 16)
    big_font = pygame.font.SysFont("monospace", 26, bold=True)
    art = Assets()
    sounds = Sounds()
    dmg_font = pygame.font.SysFont("monospace", 15, bold=True)

    game = Game(seed=random.randrange(10 ** 9))
    paused = False
    card_rects = []
    floats = []      # damage numbers rising from enemies
    flashes = []     # white bursts where an enemy died
    shake = 0.0      # seconds of screen shake left
    frames = 0

    def new_run():
        nonlocal game, card_rects, floats, flashes, shake
        game = Game(seed=random.randrange(10 ** 9))
        card_rects = []
        floats = []
        flashes = []
        shake = 0.0

    def tap(mx, my):
        """A click or a finger lift: pick a card, or start a new run."""
        if game.state == "levelup":
            for i, r in enumerate(card_rects):
                if r.collidepoint(mx, my):
                    game.pick_card(i)
                    return True
        elif game.state in ("won", "lost"):
            new_run()
            return True
        return False

    # Where the hero walks to, as a screen point. None = the player is not
    # pointing, so the hero stands still.
    # On a phone a finger must be on the screen: lifting it sets this to None.
    # On a computer one mouse position is enough: it keeps aiming every frame,
    # so the hero walks on while the pointer sits still.
    pointer = None
    saw_finger = False   # a phone sends a fake mouse event for every touch, so once
    #                      finger events show up, the mouse events are ignored

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_p:
                paused = not paused
            elif ev.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
                saw_finger = True
                mx, my = int(ev.x * W), int(ev.y * H)
                if ev.type == pygame.FINGERUP:
                    tap(mx, my)             # a tap is one pick: only the lift counts
                    pointer = None        # finger lifted: stop walking
                    game.clear_target()   # ... right now, not after the last aim
                elif game.state == "running":
                    pointer = (mx, my)
            elif ev.type in (pygame.MOUSEMOTION, pygame.MOUSEBUTTONDOWN):
                if not saw_finger:
                    mx, my = ev.pos
                    if ev.type == pygame.MOUSEBUTTONDOWN:
                        tap(mx, my)
                    else:
                        pointer = (mx, my)

        if pointer is not None and game.state == "running" and not paused:
            # screen point -> world point, repeated every frame: the camera keeps the
            # hero centred, so a pointer that does not move still walks.
            game.set_target(pointer[0] + game.hero.x - W // 2,
                            pointer[1] + game.hero.y - H // 2)

        if game.state == "running" and not paused:
            game.step()

        # ---------- turn the last step's events into sound and effects ----------
        dt = 1.0 / FPS
        hit_sfx = 0
        for kind, ex, ey, amount in game.events:
            if kind == "hit":
                if len(floats) < 60:
                    floats.append({"x": ex, "y": ey - 14, "text": str(int(round(amount))), "age": 0.0})
                if hit_sfx < 2:
                    sounds.play("hit")
                    hit_sfx += 1
            elif kind == "die":
                if len(flashes) < 30:
                    flashes.append({"x": ex, "y": ey, "age": 0.0})
            elif kind == "gem":
                sounds.play("gem")
            elif kind == "hurt":
                shake = 0.18
                sounds.play("hurt")
            elif kind == "levelup" or kind == "win":
                sounds.play("levelup")
            elif kind == "over":
                sounds.play("gameover")
        game.events.clear()

        for f in floats:
            f["age"] += dt
            f["y"] -= 55.0 * dt
        floats = [f for f in floats if f["age"] < 0.8]
        for fl in flashes:
            fl["age"] += dt
        flashes = [fl for fl in flashes if fl["age"] < 0.25]
        shake = max(0.0, shake - dt)

        # ---------- draw ----------
        cam_x = game.hero.x - W // 2
        cam_y = game.hero.y - H // 2
        if shake > 0:
            strength = 5.0 * shake / 0.18
            cam_x += random.uniform(-strength, strength)
            cam_y += random.uniform(-strength, strength)
        screen.fill((40, 70, 40))
        for ty in range(-TILE + (-(int(cam_y)) % TILE), H, TILE):
            for tx in range(-TILE + (-(int(cam_x)) % TILE), W, TILE):
                screen.blit(art.get("floor.png"), (tx, ty))

        for g in game.gems:
            art.draw(screen, "gem_%s.png" % g.tier, g.x, g.y, cam_x, cam_y)

        if "Garlic" in game.weapons:                  # show the aura
            st = weapon_stats("Garlic", game.weapons["Garlic"])
            aura = pygame.Surface((W, H), pygame.SRCALPHA)
            pygame.draw.circle(aura, (255, 255, 160, 30),
                               (game.hero.x - cam_x, game.hero.y - cam_y),
                               int(st["radius"]))
            screen.blit(aura, (0, 0))

        for e in game.enemies:
            art.draw(screen, rules.ENEMIES[e.kind]["sprite"], e.x, e.y, cam_x, cam_y)
            if e.hp < e.max_hp:                       # little health pips
                wpx = 26
                pygame.draw.rect(screen, (60, 0, 0),
                                 (e.x - cam_x - wpx // 2, e.y - cam_y - 34, wpx, 4))
                pygame.draw.rect(screen, (220, 40, 40),
                                 (e.x - cam_x - wpx // 2, e.y - cam_y - 34,
                                  int(wpx * max(0.0, e.hp / e.max_hp)), 4))

        for p in game.projectiles:
            if p.gravity:
                art.draw(screen, "axe.png", p.x, p.y, cam_x, cam_y)
            else:
                pygame.draw.circle(screen, (255, 230, 120),
                                   (int(p.x - cam_x), int(p.y - cam_y)), 5)

        art.draw(screen, "hero.png", game.hero.x, game.hero.y, cam_x, cam_y)

        for fl in flashes:
            k = fl["age"] / 0.25
            r = int(12 + 34 * k)
            burst = pygame.Surface((r * 2, r * 2), pygame.SRCALPHA)
            pygame.draw.circle(burst, (255, 255, 210, int(200 * (1 - k))), (r, r), r)
            screen.blit(burst, (fl["x"] - cam_x - r, fl["y"] - cam_y - r))

        for f in floats:
            shade = max(0, 255 - int(255 * f["age"] / 0.8))
            txt = dmg_font.render(f["text"], True, (255, 255, shade))
            screen.blit(txt, (f["x"] - cam_x - 8, f["y"] - cam_y))

        # ---------- HUD ----------
        h = game.hero
        pygame.draw.rect(screen, (60, 0, 0), (10, 10, 150, 12))
        pygame.draw.rect(screen, (220, 40, 40),
                         (10, 10, int(150 * max(0.0, h.hp / h.max_hp)), 12))
        need = rules.xp_needed(h.level)
        pygame.draw.rect(screen, (0, 0, 70), (10, 26, 150, 12))
        pygame.draw.rect(screen, (80, 130, 255),
                         (10, 26, int(150 * min(1.0, h.xp / need)), 12))
        screen.blit(font.render("Lv %d" % h.level, True, (255, 255, 255)), (168, 22))
        t = font.render(fmt_time(game.time), True, (255, 255, 255))
        screen.blit(t, (W - t.get_width() - 10, 10))
        weapons = "  ".join("%s %d" % (n, lv) for n, lv in game.weapons.items()) or "no weapon!"
        screen.blit(font.render(weapons, True, (255, 255, 200)), (10, H - 24))

        # ---------- overlays ----------
        card_rects = []
        if game.state == "levelup":
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 170))
            screen.blit(veil, (0, 0))
            title = big_font.render("LEVEL UP!", True, (255, 230, 80))
            screen.blit(title, (W // 2 - title.get_width() // 2, 130))
            card_rects = []
            for i, card in enumerate(game.cards):
                r = pygame.Rect(30, 200 + i * 130, W - 60, 110)
                pygame.draw.rect(screen, (245, 240, 225), r, border_radius=12)
                pygame.draw.rect(screen, (255, 200, 60), r, 3, border_radius=12)
                lvl = ("Lv %d" % card["level"]) if card["kind"] != "passive" else "passive"
                screen.blit(font.render(card["name"], True, (30, 30, 90)),
                            (r.x + 14, r.y + 14))
                screen.blit(font.render(lvl, True, (120, 120, 120)),
                            (r.right - 74, r.y + 14))
                screen.blit(font.render(card["text"], True, (60, 60, 60)),
                            (r.x + 14, r.y + 52))
                card_rects.append(r)
        elif paused and game.state == "running":
            s = big_font.render("PAUSED", True, (255, 255, 255))
            screen.blit(s, (W // 2 - s.get_width() // 2, H // 2))
        elif game.state in ("won", "lost"):
            veil = pygame.Surface((W, H), pygame.SRCALPHA)
            veil.fill((0, 0, 0, 170))
            screen.blit(veil, (0, 0))
            msg = "VICTORY!" if game.state == "won" else "GAME OVER"
            color = (120, 255, 120) if game.state == "won" else (255, 90, 90)
            s = big_font.render(msg, True, color)
            screen.blit(s, (W // 2 - s.get_width() // 2, 260))
            stats = font.render("time %s   kills %d   level %d"
                                % (fmt_time(game.time), game.kills, game.hero.level),
                                True, (255, 255, 255))
            screen.blit(stats, (W // 2 - stats.get_width() // 2, 310))
            again = font.render("click to play again", True, (200, 200, 200))
            screen.blit(again, (W // 2 - again.get_width() // 2, 350))

        pygame.display.flip()
        clock.tick(FPS)
        await asyncio.sleep(0)          # lets pygbag run this in a browser later

        frames += 1
        if max_frames and frames >= max_frames:
            print("headless ok: %d frames, state=%s, time=%s, enemies=%d, gems=%d, "
                  "kills=%d, level=%d" % (frames, game.state, fmt_time(game.time),
                                          len(game.enemies), len(game.gems),
                                          game.kills, game.hero.level))
            running = False

    pygame.quit()


if __name__ == "__main__":
    frames_arg = 0
    if "--frames" in sys.argv:
        frames_arg = int(sys.argv[sys.argv.index("--frames") + 1])
    asyncio.run(main(frames_arg))
