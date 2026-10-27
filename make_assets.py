"""Make big, crisp sprites from the 16x16 art in raw_art/.

raw_art/ is never changed. Every PNG is copied into assets/ 3 times bigger
(the boss 6 times) with NEAREST scaling, so the little pixels stay square
and nothing blurs. gem.png also gets blue and purple copies for the XP
gem tiers. Run:  python make_assets.py
"""

import os

from PIL import Image

SRC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw_art")
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")

SCALE = 3
BIG_SCALE = {"demon.png": 6}          # the boss gets an extra-big copy

GEM_TIERS = {
    "gem_white.png": (230, 230, 240),
    "gem_blue.png": (90, 150, 255),
    "gem_purple.png": (190, 90, 240),
}


def upscale(img, factor):
    return img.resize((img.width * factor, img.height * factor), Image.NEAREST)


def tint(img, color):
    """Recolour a sprite but keep its shading: multiply the tint by brightness."""
    out = Image.new("RGBA", img.size)
    px = img.load()
    o = out.load()
    for y in range(img.height):
        for x in range(img.width):
            r, g, b, a = px[x, y]
            lum = (0.3 * r + 0.6 * g + 0.1 * b) / 255.0
            o[x, y] = (int(color[0] * (0.35 + 0.65 * lum)),
                       int(color[1] * (0.35 + 0.65 * lum)),
                       int(color[2] * (0.35 + 0.65 * lum)), a)
    return out


def build():
    os.makedirs(DST, exist_ok=True)
    made = []
    for name in sorted(os.listdir(SRC)):
        if not name.endswith(".png"):
            continue
        img = Image.open(os.path.join(SRC, name)).convert("RGBA")
        upscale(img, BIG_SCALE.get(name, SCALE)).save(os.path.join(DST, name))
        made.append(name)
    gem = Image.open(os.path.join(SRC, "gem.png")).convert("RGBA")
    for name, color in GEM_TIERS.items():
        upscale(tint(gem, color), SCALE).save(os.path.join(DST, name))
        made.append(name)
    return made


def expected_files():
    base = [f for f in sorted(os.listdir(SRC)) if f.endswith(".png")]
    return base + list(GEM_TIERS)


def ensure():
    """Build the assets only if something is missing (main.py calls this)."""
    missing = [n for n in expected_files() if not os.path.exists(os.path.join(DST, n))]
    if missing:
        build()
        return True
    return False


if __name__ == "__main__":
    for name in build():
        img = Image.open(os.path.join(DST, name))
        print("%-16s %3dx%-3d" % (name, img.width, img.height))
    print("made %d files in %s (raw_art/ untouched)" % (len(expected_files()), DST))
