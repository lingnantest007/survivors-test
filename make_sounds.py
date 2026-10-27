"""Make short sound effects with the standard library only.

No audio files are downloaded and nothing is installed: each effect is
synthesised sample by sample (math + wave + struct) into sounds/*.wav.
raw_art/ and sounds/ are generated folders - run:  python make_sounds.py
"""

import math
import os
import random
import struct
import wave
from array import array

RATE = 22050           # samples per second, CD-ish but small files
VOL = 0.35             # keep headroom so overlapping sounds never crackle
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sounds")


def _wave_shape(kind, phase):
    p = phase % 1.0
    if kind == "sine":
        return math.sin(2 * math.pi * p)
    if kind == "square":
        return 1.0 if p < 0.5 else -1.0
    if kind == "saw":
        return 2.0 * p - 1.0
    raise ValueError(kind)


def tone(freq, dur, kind="sine", vol=1.0, decay=8.0, slide_to=None):
    """One note with an exponential fade; slide_to bends the pitch."""
    n = int(RATE * dur)
    out = array("f", bytes(4 * n))
    phase = 0.0
    for i in range(n):
        t = i / n
        f = freq if slide_to is None else freq + (slide_to - freq) * t
        phase += f / RATE
        env = math.exp(-decay * t)
        out[i] = vol * env * _wave_shape(kind, phase)
    return out


def noise(dur, vol=1.0, decay=30.0, seed=7):
    n = int(RATE * dur)
    rng = random.Random(seed)
    out = array("f", bytes(4 * n))
    for i in range(n):
        t = i / n
        out[i] = vol * math.exp(-decay * t) * rng.uniform(-1.0, 1.0)
    return out


def mix(*parts):
    n = max(len(p) for p in parts) if parts else 0
    out = array("f", bytes(4 * n))
    for p in parts:
        for i, v in enumerate(p):
            out[i] += v
    return out


def seq(*parts):
    out = array("f")
    for p in parts:
        out.extend(p)
    return out


# ---- the five effects -------------------------------------------------

def make_samples():
    return {
        # weapon connects: a short percussive "tock"
        "hit.wav": lambda: mix(
            tone(220, 0.06, "square", 0.8, decay=60),
            tone(660, 0.04, "sine", 0.5, decay=80),
            noise(0.03, 0.4, decay=120)),
        # gem picked up: quick rising sparkle "tink-tink"
        "gem.wav": lambda: seq(
            tone(1200, 0.05, "sine", 0.7, decay=40),
            tone(1800, 0.08, "sine", 0.8, decay=30)),
        # level up: happy little arpeggio
        "levelup.wav": lambda: mix(
            seq(*[tone(f, 0.12, "square", 0.4, decay=15)
                  for f in (523, 659, 784, 1046)]),
            tone(2093, 0.5, "sine", 0.3, decay=6)),
        # hero hurt: low angry growl
        "hurt.wav": lambda: mix(
            tone(180, 0.18, "saw", 0.9, decay=18, slide_to=80),
            noise(0.12, 0.5, decay=25)),
        # game over: falling sad notes
        "gameover.wav": lambda: seq(
            *[tone(f, 0.35, "sine", 0.8, decay=5)
              for f in (392, 311, 233)],
        ) + tone(116, 0.8, "saw", 0.4, decay=4),
    }


def write_wav(name, samples):
    os.makedirs(DST, exist_ok=True)
    path = os.path.join(DST, name)
    ints = array("h", bytes(2 * len(samples)))
    for i, v in enumerate(samples):
        s = int(v * VOL * 32767)
        ints[i] = max(-32768, min(32767, s))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(ints.tobytes())
    return path


def build():
    results = []
    for name, maker in make_samples().items():
        samples = maker()
        path = write_wav(name, samples)
        results.append((name, round(len(samples) / RATE, 3)))
    return results


def ensure():
    """Build any missing wav file (main.py calls this before loading)."""
    missing = [n for n in make_samples() if not os.path.exists(os.path.join(DST, n))]
    if missing:
        build()
    return [os.path.join(DST, n) for n in make_samples()]


if __name__ == "__main__":
    for name, seconds in build():
        size = os.path.getsize(os.path.join(DST, name))
        print("%-12s %.3f s  %5.1f kB" % (name, seconds, size / 1024))
    print("wrote %d sounds to %s" % (len(make_samples()), DST))
