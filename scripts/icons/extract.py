#!/usr/bin/env python3
"""Turn the two design layers into the masters the rest of the pipeline consumes.

  composeApp/icon/logo_transparent.png  the emblem, with a real alpha channel
  composeApp/icon/background.png        the navy seigaiha field, 1024x1024

Writes into work/:
  emblem_native.png / emblem_2x.png   the emblem, trimmed, with real alpha
  bg_wave.png                         the field, unchanged
  alpha.pgm / rgb.ppm                 ASCII dumps trace.py reads (numpy, no PIL here)
  emblem_geometry.json                the measured enclosing circle gen.py places by

**Always check that the emblem layer's alpha is real before trusting it.** An earlier
export of this layer (logo_only.png) had alpha 1.0 everywhere with the transparency
checkerboard PAINTED into the pixels (#454545 / #757575, ~25px tiles) — it looks
identical in any viewer and silently produces an emblem with a grey checkerboard baked
behind it. This script detects that case and keys it by chroma instead; the fallback is
kept because the failure is invisible until an icon ships.

**A global colour fuzz cannot do that keying**, which is why the fallback is not simply
`-fuzz`. The leaf's dark maroon outline (74,31,38) sits 19% from #454545 in RGB distance,
so the fuzz that finally crosses the checkerboard (18%) also eats the outline and punches
holes through the leaf. Chroma separates them with room to spare: the checkerboard is
exactly neutral, no emblem colour is, and the one low-chroma emblem colour (the cream
note) is far too bright to collide with either grey.
"""
import json
import math
import os
import subprocess
import sys
from collections import deque

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")

# The checkerboard is neutral (chroma 0) and mid-dark. Nothing in the emblem is both.
MAX_BG_CHROMA = 14
BG_LUMA_RANGE = (50, 140)


def run(args):
    subprocess.run(args, check=True)


def read_binary_pnm(path):
    with open(path, "rb") as fh:
        raw = fh.read()
    fields, pos = [], 2
    while len(fields) < 3:
        while pos < len(raw) and raw[pos : pos + 1].isspace():
            pos += 1
        if raw[pos : pos + 1] == b"#":
            while raw[pos : pos + 1] not in (b"\n", b""):
                pos += 1
            continue
        start = pos
        while pos < len(raw) and not raw[pos : pos + 1].isspace():
            pos += 1
        fields.append(int(raw[start:pos]))
    pos += 1
    w, h = fields[0], fields[1]
    depth = 3 if raw[:2] == b"P6" else 1
    arr = np.frombuffer(raw, dtype=np.uint8, count=w * h * depth, offset=pos)
    return arr.reshape((h, w, depth)) if depth == 3 else arr.reshape((h, w))


def label_components(mask):
    """4-connected labelling, returned as (labels, sizes)."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    sizes = [0]
    cur = 0
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if labels[sy, sx]:
            continue
        cur += 1
        size = 0
        q = deque([(sy, sx)])
        labels[sy, sx] = cur
        while q:
            y, x = q.popleft()
            size += 1
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not labels[ny, nx]:
                    labels[ny, nx] = cur
                    q.append((ny, nx))
        sizes.append(size)
    return labels, sizes


def flood_from_border(mask):
    """The subset of `mask` reachable from the image border, so a genuinely neutral
    pixel enclosed by the emblem is never keyed out."""
    h, w = mask.shape
    seen = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if mask[y, x] and not seen[y, x]:
                seen[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                seen[ny, nx] = True
                q.append((ny, nx))
    return seen


def blur(img, sigma):
    radius = int(math.ceil(sigma * 3))
    xs = np.arange(-radius, radius + 1)
    k = np.exp(-(xs ** 2) / (2 * sigma ** 2))
    k /= k.sum()
    out = np.apply_along_axis(
        lambda r: np.convolve(r, k, mode="valid"), 1,
        np.pad(img.astype(np.float64), ((0, 0), (radius, radius)), mode="edge"))
    return np.apply_along_axis(
        lambda c: np.convolve(c, k, mode="valid"), 0,
        np.pad(out, ((radius, radius), (0, 0)), mode="edge"))


def erode(mask):
    out = mask.copy()
    out[1:, :] &= mask[:-1, :]
    out[:-1, :] &= mask[1:, :]
    out[:, 1:] &= mask[:, :-1]
    out[:, :-1] &= mask[:, 1:]
    return out


def main():
    os.makedirs(WORK, exist_ok=True)
    logo = os.path.join(ROOT, "composeApp", "icon", "logo_transparent.png")
    field = os.path.join(ROOT, "composeApp", "icon", "background.png")
    for p in (logo, field):
        if not os.path.exists(p):
            sys.exit(f"missing design layer: {p}")

    run(["magick", logo, "-alpha", "extract", "-depth", "8",
         os.path.join(WORK, "src_alpha.pgm")])
    src_alpha = read_binary_pnm(os.path.join(WORK, "src_alpha.pgm"))
    has_real_alpha = int(src_alpha.min()) == 0 and int(src_alpha.max()) == 255

    if has_real_alpha:
        sys.stderr.write("alpha: real, used as-is\n")
        solid = src_alpha >= 40
        keyed_alpha = src_alpha.astype(np.float64) / 255.0
    else:
        # See the module docstring: a flat alpha means the checkerboard is painted in.
        sys.stderr.write("alpha: FLAT — keying the painted checkerboard by chroma\n")
        run(["magick", logo, "-depth", "8", os.path.join(WORK, "logo.ppm")])
        rgb = read_binary_pnm(os.path.join(WORK, "logo.ppm")).astype(np.int16)
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        luma = (0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2])
        checker = ((chroma <= MAX_BG_CHROMA)
                   & (luma >= BG_LUMA_RANGE[0]) & (luma <= BG_LUMA_RANGE[1]))
        solid = ~flood_from_border(checker)
        keyed_alpha = None
    h, w = solid.shape

    # Guard against stray background decoration leaking into the emblem layer: an
    # earlier export carried a lone sparkle in the bottom-right corner, ~400px from the
    # emblem. It has to go BEFORE anything is measured, because an enclosing circle that
    # includes it is nearly twice the right radius and every icon would then place the
    # emblem at half its intended size — with no error anywhere. The current layer is
    # clean, so this drops nothing; it stays because the failure is silent.
    labels, sizes = label_components(solid)
    main_label = int(np.argmax(sizes))
    ys, xs = np.nonzero(labels == main_label)
    lcx, lcy = xs.mean(), ys.mean()
    lr = math.hypot(xs.max() - xs.min(), ys.max() - ys.min()) / 2.0
    keep = np.zeros_like(solid)
    dropped = 0
    for lab in range(1, len(sizes)):
        cy_, cx_ = np.nonzero(labels == lab)
        if len(cx_) == 0:
            continue
        # Ring arcs and blossoms are their own components, so proximity decides, not size.
        if math.hypot(cx_.mean() - lcx, cy_.mean() - lcy) <= lr * 1.35:
            keep |= labels == lab
        else:
            dropped += len(cx_)
    sys.stderr.write(f"components: {len(sizes) - 1}, dropped {dropped}px of strays\n")

    if keyed_alpha is not None:
        # Real alpha: keep the artist's own anti-aliasing untouched and only apply the
        # stray mask. Eroding it here would visibly thin the ring and the blossoms.
        alpha = keyed_alpha * keep
    else:
        # Keyed: cut the grey-contaminated rim, then feather. At 1024 a 1px rim is
        # 0.42px once the adaptive foreground is resized to 432, so nothing is lost.
        alpha = np.clip(blur(erode(keep).astype(np.float64), 0.7), 0.0, 1.0)
    alpha8 = (alpha * 255.0 + 0.5).astype(np.uint8)

    apath = os.path.join(WORK, "alpha_full.pgm")
    with open(apath, "wb") as fh:
        fh.write(b"P5\n%d %d\n255\n" % (w, h))
        fh.write(alpha8.tobytes())

    run(["magick", logo, apath, "-alpha", "off", "-compose", "CopyOpacity", "-composite",
         os.path.join(WORK, "emblem_full.png")])
    run(["magick", os.path.join(WORK, "emblem_full.png"), "-trim", "+repage",
         os.path.join(WORK, "emblem_native.png")])
    run(["magick", os.path.join(WORK, "emblem_native.png"),
         "-filter", "Lanczos", "-resize", "200%", "-unsharp", "0x0.8+0.35+0.02",
         os.path.join(WORK, "emblem_2x.png")])
    run(["magick", field, "-resize", "1024x1024!", os.path.join(WORK, "bg_wave.png")])

    # Geometry is measured here and read by gen.py, so the two can never drift apart.
    run(["magick", os.path.join(WORK, "emblem_native.png"), "-alpha", "extract",
         "-depth", "8", os.path.join(WORK, "alpha_native.pgm")])
    na = read_binary_pnm(os.path.join(WORK, "alpha_native.pgm"))
    nys, nxs = np.nonzero(na >= 40)
    pts = np.stack([nxs, nys], 1).astype(float)
    cx, cy = pts[:, 0].mean(), pts[:, 1].mean()
    for _ in range(400):
        i = int((((pts[:, 0] - cx) ** 2) + ((pts[:, 1] - cy) ** 2)).argmax())
        cx += (pts[i, 0] - cx) * 0.01
        cy += (pts[i, 1] - cy) * 0.01
    r = math.sqrt((((pts[:, 0] - cx) ** 2) + ((pts[:, 1] - cy) ** 2)).max())
    nh, nw = na.shape
    geom = {"width": nw, "height": nh, "cx": round(cx, 2), "cy": round(cy, 2),
            "r": round(r, 2)}
    with open(os.path.join(WORK, "emblem_geometry.json"), "w") as fh:
        json.dump(geom, fh, indent=2)
    sys.stderr.write(f"emblem {nw}x{nh}, enclosing circle {geom}\n")

    # ASCII dumps for trace.py.
    run(["magick", os.path.join(WORK, "emblem_native.png"), "-alpha", "extract",
         "-depth", "8", "-compress", "none", os.path.join(WORK, "alpha.pgm")])
    run(["magick", os.path.join(WORK, "emblem_native.png"), "-background", "black",
         "-alpha", "remove", "-alpha", "off", "-depth", "8", "-compress", "none",
         os.path.join(WORK, "rgb.ppm")])

    for tmp in ("logo.ppm", "alpha_full.pgm", "alpha_native.pgm", "emblem_full.png"):
        p = os.path.join(WORK, tmp)
        if os.path.exists(p):
            os.remove(p)
    print("masters written to", WORK)


if __name__ == "__main__":
    main()
