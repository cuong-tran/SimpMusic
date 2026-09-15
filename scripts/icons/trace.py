#!/usr/bin/env python3
"""Trace the Musikku emblem's leaf silhouette (with the music note knocked out)
into an Android vector-drawable path.

Input : alpha.pgm / rgb.ppm exported from emblem_native.png by ImageMagick.
Output: path data on stdout, or a full vector drawable when given an output path.
"""
import math
import sys
from collections import deque

import numpy as np


def read_pnm(path):
    with open(path, "rb") as fh:
        data = fh.read().split()
    magic = data[0].decode()
    w, h, maxv = int(data[1]), int(data[2]), int(data[3])
    vals = np.array([int(v) for v in data[4:]], dtype=np.int32)
    if magic == "P2":
        return vals.reshape(h, w)
    if magic == "P3":
        return vals.reshape(h, w, 3)
    raise ValueError("unsupported " + magic)


def largest_component(mask):
    """4-connected largest blob of a boolean mask."""
    h, w = mask.shape
    labels = np.zeros((h, w), dtype=np.int32)
    best, best_size = 0, 0
    cur = 0
    for sy in range(h):
        for sx in range(w):
            if not mask[sy, sx] or labels[sy, sx]:
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
            if size > best_size:
                best, best_size = cur, size
    return labels == best, best_size


def fill_holes(mask):
    """Flood the outside from the border; anything unreached becomes solid."""
    h, w = mask.shape
    outside = np.zeros((h, w), dtype=bool)
    q = deque()
    for x in range(w):
        for y in (0, h - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y, x] and not outside[y, x]:
                outside[y, x] = True
                q.append((y, x))
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True
                q.append((ny, nx))
    return ~outside


def erode(mask, iters=1):
    out = mask
    for _ in range(iters):
        nxt = out.copy()
        nxt[1:, :] &= out[:-1, :]
        nxt[:-1, :] &= out[1:, :]
        nxt[:, 1:] &= out[:, :-1]
        nxt[:, :-1] &= out[:, 1:]
        out = nxt
    return out


def dilate(mask, iters=1):
    out = mask
    for _ in range(iters):
        nxt = out.copy()
        nxt[1:, :] |= out[:-1, :]
        nxt[:-1, :] |= out[1:, :]
        nxt[:, 1:] |= out[:, :-1]
        nxt[:, :-1] |= out[:, 1:]
        out = nxt
    return out


def blur_threshold(mask, sigma=1.4, level=0.5):
    """Round off the pixel staircase before tracing."""
    radius = int(math.ceil(sigma * 3))
    xs = np.arange(-radius, radius + 1)
    kernel = np.exp(-(xs ** 2) / (2 * sigma ** 2))
    kernel /= kernel.sum()
    img = mask.astype(np.float64)
    pad = np.pad(img, ((0, 0), (radius, radius)), mode="edge")
    img = np.apply_along_axis(lambda r: np.convolve(r, kernel, mode="valid"), 1, pad)
    pad = np.pad(img, ((radius, radius), (0, 0)), mode="edge")
    img = np.apply_along_axis(lambda c: np.convolve(c, kernel, mode="valid"), 0, pad)
    return img >= level


def trace_loops(mask):
    """Crack-following contour trace: every boundary pixel edge, linked into loops.

    Edges are emitted so the filled region always sits to the right of travel, which
    is what disambiguates the checkerboard corners an 8-connected blob can produce.
    """
    h, w = mask.shape
    padded = np.zeros((h + 2, w + 2), dtype=bool)
    padded[1:-1, 1:-1] = mask
    edges = {}

    def add(a, b):
        edges.setdefault(a, []).append(b)

    ys, xs = np.nonzero(padded)
    for y, x in zip(ys.tolist(), xs.tolist()):
        if not padded[y - 1, x]:
            add((x, y), (x + 1, y))
        if not padded[y, x + 1]:
            add((x + 1, y), (x + 1, y + 1))
        if not padded[y + 1, x]:
            add((x + 1, y + 1), (x, y + 1))
        if not padded[y, x - 1]:
            add((x, y + 1), (x, y))

    loops = []
    while edges:
        start = next(iter(edges))
        loop = [start]
        cur = start
        prev_dir = None
        while True:
            outs = edges.get(cur)
            if not outs:
                break
            if len(outs) == 1 or prev_dir is None:
                nxt = outs[0]
            else:
                # Ambiguous vertex: take the sharpest clockwise turn so the walk
                # stays on this loop instead of jumping to the touching one.
                def turn(p):
                    d = (p[0] - cur[0], p[1] - cur[1])
                    ang = math.atan2(d[1], d[0]) - math.atan2(prev_dir[1], prev_dir[0])
                    return (ang + 2 * math.pi) % (2 * math.pi)

                nxt = min(outs, key=turn)
            outs.remove(nxt)
            if not outs:
                del edges[cur]
            prev_dir = (nxt[0] - cur[0], nxt[1] - cur[1])
            cur = nxt
            if cur == start:
                break
            loop.append(cur)
        if len(loop) > 8:
            loops.append([(px - 1.0, py - 1.0) for px, py in loop])
    return loops


def rdp(points, eps):
    if len(points) < 3:
        return points
    ax, ay = points[0]
    bx, by = points[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    best_i, best_d = 0, -1.0
    for i in range(1, len(points) - 1):
        px, py = points[i]
        if norm == 0:
            d = math.hypot(px - ax, py - ay)
        else:
            d = abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > best_d:
            best_i, best_d = i, d
    if best_d > eps:
        return rdp(points[: best_i + 1], eps)[:-1] + rdp(points[best_i:], eps)
    return [points[0], points[-1]]


def simplify_loop(loop, eps):
    closed = loop + [loop[0]]
    out = rdp(closed, eps)
    if out[0] == out[-1]:
        out = out[:-1]
    return out


def polygon_area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


RESAMPLE_STEP = 5.0     # px between contour samples, at the 446px master's scale
CORNER_WINDOW = 5       # samples each side used to measure a turn
CORNER_DEG = 58.0       # turn above which a vertex is a real corner, not wobble
CONTOUR_SIGMA = 6.5     # Gaussian sigma ALONG the contour, in samples
RDP_EPS = 1.6
TENSION = 0.45


def resample_closed(loop, step):
    """Re-space a closed contour at uniform arc length.

    trace_loops returns pixel-edge crack points, so consecutive points are 1px apart
    and every run of them is axis-aligned. Smoothing or measuring angles on that
    directly measures the staircase, not the shape."""
    n = len(loop)
    seg = [math.dist(loop[i], loop[(i + 1) % n]) for i in range(n)]
    total = sum(seg)
    count = max(8, int(round(total / step)))
    step = total / count
    out, i, acc = [], 0, 0.0
    for k in range(count):
        target = k * step
        while i < n - 1 and acc + seg[i] < target:
            acc += seg[i]
            i += 1
        t = 0.0 if seg[i] == 0 else (target - acc) / seg[i]
        x0, y0 = loop[i]
        x1, y1 = loop[(i + 1) % n]
        out.append((x0 + (x1 - x0) * t, y0 + (y1 - y0) * t))
    return out


def turn_degrees(pts, i, window):
    """Turn at i measured across +/-window samples, not between neighbours: a
    per-vertex angle on a resampled contour is mostly quantisation noise."""
    n = len(pts)
    a, b, c = pts[(i - window) % n], pts[i], pts[(i + window) % n]
    v1 = (b[0] - a[0], b[1] - a[1])
    v2 = (c[0] - b[0], c[1] - b[1])
    n1, n2 = math.hypot(*v1), math.hypot(*v2)
    if n1 == 0 or n2 == 0:
        return 0.0
    cos = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
    return math.degrees(math.acos(cos))


def detect_corners(pts, window, thresh_deg):
    """Indices of genuine corners — the lobe tips and the valleys between them —
    as local maxima of the windowed turn, so one corner yields one vertex."""
    n = len(pts)
    ang = [turn_degrees(pts, i, window) for i in range(n)]
    keep = []
    for i in range(n):
        if ang[i] < thresh_deg:
            continue
        if any(ang[(i + d) % n] > ang[i] for d in range(-window, window + 1)):
            continue
        if keep and min((i - keep[-1]) % n, (keep[-1] - i) % n) < window:
            continue
        keep.append(i)
    return keep


def _gauss(sigma):
    rad = max(1, int(math.ceil(3 * sigma)))
    xs = np.arange(-rad, rad + 1).astype(float)
    k = np.exp(-(xs ** 2) / (2 * sigma ** 2))
    return k / k.sum(), rad


def smooth_open(seg, sigma):
    """Gaussian-smooth a run of points with both ENDS PINNED. The ends are corners,
    and pinning them is what lets the sigma go high enough to erase the artwork's
    hand-drawn wobble without also melting the lobe tips."""
    if len(seg) < 3 or sigma <= 0:
        return seg
    kernel, rad = _gauss(sigma)
    arr = np.asarray(seg, dtype=float)
    out = arr.copy()
    last = len(seg) - 1
    for i in range(1, last):
        idx = np.clip(np.arange(i - rad, i + rad + 1), 0, last)
        out[i] = (arr[idx] * kernel[:, None]).sum(0)
    return [tuple(p) for p in out]


def smooth_closed(pts, sigma):
    """Same, wrapped — for a loop with no corners at all (the note's head)."""
    if sigma <= 0:
        return pts
    kernel, rad = _gauss(sigma)
    arr = np.asarray(pts, dtype=float)
    n = len(pts)
    idx = (np.arange(n)[:, None] + np.arange(-rad, rad + 1)[None, :]) % n
    return [tuple(p) for p in (arr[idx] * kernel[None, :, None]).sum(1)]


def smooth_loop(raw):
    """One traced loop -> (points, corner_flags), smoothed and decimated."""
    pts = resample_closed(raw, RESAMPLE_STEP)
    corners = detect_corners(pts, CORNER_WINDOW, CORNER_DEG)
    if not corners:
        dec = rdp(smooth_closed(pts, CONTOUR_SIGMA) + [pts[0]], RDP_EPS)[:-1]
        return dec, [False] * len(dec)
    n = len(pts)
    out, flags = [], []
    for a, b in zip(corners, corners[1:] + [corners[0] + n]):
        seg = smooth_open([pts[i % n] for i in range(a, b + 1)], CONTOUR_SIGMA)
        dec = rdp(seg, RDP_EPS)
        for j, point in enumerate(dec[:-1]):
            out.append(point)
            flags.append(j == 0)
    return out, flags


def to_bezier(pts, flags, tension=TENSION):
    """Catmull-Rom through the points, broken at the flagged corners."""
    n = len(pts)
    segs = []
    for i in range(n):
        p0, p1, p2, p3 = pts[(i - 1) % n], pts[i], pts[(i + 1) % n], pts[(i + 2) % n]
        c1 = p1 if flags[i] else (p1[0] + (p2[0] - p0[0]) * tension / 2,
                                  p1[1] + (p2[1] - p0[1]) * tension / 2)
        c2 = p2 if flags[(i + 1) % n] else (p2[0] - (p3[0] - p1[0]) * tension / 2,
                                            p2[1] - (p3[1] - p1[1]) * tension / 2)
        segs.append((c1, c2, p2))
    return segs


def fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


def emit(loops, sx, sy, ox, oy):
    def T(p):
        return (p[0] * sx + ox, p[1] * sy + oy)

    out = []
    for loop, flags in loops:
        segs = to_bezier(loop, flags)
        start = T(loop[0])
        out.append(f"M{fmt(start[0])},{fmt(start[1])}")
        for c1, c2, p in segs:
            a, b, c = T(c1), T(c2), T(p)
            out.append(
                f"C{fmt(a[0])},{fmt(a[1])} {fmt(b[0])},{fmt(b[1])} {fmt(c[0])},{fmt(c[1])}"
            )
        out.append("Z")
    return "".join(out)


def main():
    alpha = read_pnm("alpha.pgm")
    rgb = read_pnm("rgb.ppm")
    h, w = alpha.shape

    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]

    # The leaf is selected by COLOUR, not by "largest opaque blob". The gold ring touches
    # the leaf, so an alpha-only blob is leaf + ring + blossoms and traces as a scribble.
    # Red separates them with room to spare: every leaf tone from the bright face
    # (226,74,60) to the dark outline (64,4,6) clears these margins, while the gold ring
    # (217,196,138) has r-g = 21 and the cream note r-g = 4. Transparent pixels are
    # (0,0,0) here because rgb.ppm is flattened on black, so they fail the test too.
    leafish = ((r - g) > 25) & ((r - b) > 20) & (r > 45) & (alpha >= 115)
    # The ring's own dark stroke is red enough to pass that test, and the ring touches
    # the leaf — so the largest blob still arrives with an arc hanging off the stem.
    # An opening removes it: the arc is ~3px wide and the leaf is 400, so eroding 3 and
    # dilating back is invisible on the leaf, and leaves the arc with nothing to grow
    # back from.
    core, size = largest_component(erode(leafish, 3))
    leaf = fill_holes(dilate(core, 3) & leafish)
    sys.stderr.write(f"leaf blob: {size} px, bbox rows {np.nonzero(leaf.any(1))[0][[0,-1]]}\n")

    cream = leaf & (r > 195) & (g > 185) & (b > 160) & (np.abs(r - b) < 80)
    note, note_size = largest_component(cream)
    note = fill_holes(note)
    sys.stderr.write(f"note blob: {note_size} px\n")

    # Raster blur only removes the PIXEL staircase, and it is isotropic — pushed far
    # enough to erase the artwork's hand-drawn edge wobble it also melts the lobe tips,
    # which is exactly the trade the earlier sigma 3.2 / eps 1.9 pass was stuck in. The
    # wobble is removed in CONTOUR space instead (smooth_loop), where corners can be
    # pinned, so this stays light.
    final = blur_threshold(leaf, sigma=2.6) & ~blur_threshold(note, sigma=2.0)

    loops = []
    for raw in trace_loops(final):
        if len(raw) < 24:
            continue
        pts, flags = smooth_loop(raw)
        if len(pts) >= 6 and abs(polygon_area(pts)) > 60:
            loops.append((pts, flags))
    loops.sort(key=lambda lf: -abs(polygon_area(lf[0])))
    sys.stderr.write(
        f"loops: {[(len(l), sum(f)) for l, f in loops]} (points, corners)\n")

    # Fit inside a circle, not a box: both consumers clip the mark to a circle
    # (the nav-rail logo with CircleShape, the adaptive <monochrome> layer with the
    # 66dp safe zone), so a box-fit would slice the outer lobes off.
    viewport = float(sys.argv[1]) if len(sys.argv) > 1 else 108.0
    radius = float(sys.argv[2]) if len(sys.argv) > 2 else 48.0
    out_xml = sys.argv[3] if len(sys.argv) > 3 else None
    fill = sys.argv[4] if len(sys.argv) > 4 else "#000000"
    size_dp = sys.argv[5] if len(sys.argv) > 5 else "108"
    pts = [p for loop, _ in loops for p in loop]
    cx = (min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0
    cy = (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0
    for _ in range(200):  # shift the centre toward the farthest point to shrink the hull
        far = max(pts, key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
        cx += (far[0] - cx) * 0.02
        cy += (far[1] - cy) * 0.02
    rmax = max(math.hypot(p[0] - cx, p[1] - cy) for p in pts)
    scale = radius / rmax
    sys.stderr.write(f"enclosing circle: c=({cx:.1f},{cy:.1f}) r={rmax:.1f} scale={scale:.4f}\n")
    ox = viewport / 2.0 - cx * scale
    oy = viewport / 2.0 - cy * scale
    data = emit(loops, scale, scale, ox, oy)
    if out_xml is None:
        print(data)
        return
    with open(out_xml, "w") as fh:
        fh.write(
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="{size_dp}dp"\n'
            f'    android:height="{size_dp}dp"\n'
            f'    android:viewportWidth="{viewport:g}"\n'
            f'    android:viewportHeight="{viewport:g}">\n'
            '    <path\n'
            f'        android:fillColor="{fill}"\n'
            '        android:fillType="evenOdd"\n'
            f'        android:pathData="{data}" />\n'
            '</vector>\n'
        )
    sys.stderr.write(f"wrote {out_xml}\n")


if __name__ == "__main__":
    main()
