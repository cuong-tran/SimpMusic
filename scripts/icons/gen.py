#!/usr/bin/env python3
"""Generate every Musikku icon raster from the masters extract.py produced.

  work/emblem_2x.png           the keyed emblem (leaf + note + ring + blossoms)
  work/bg_wave.png             the navy seigaiha field, 1024x1024
  work/emblem_geometry.json    its measured enclosing circle

Output lands in work/out/. install.sh encodes and copies it into the tree.

The emblem is placed by its MINIMAL ENCLOSING CIRCLE, not its bounding box: the mark is
a circular badge whose stem pokes below the ring, so a bbox-centred placement sits
visibly high the moment a circular mask is applied.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.join(HERE, "work")
OUT = os.path.join(WORK, "out")

# Emblem geometry is MEASURED by extract.py and read here, never restated: the two
# would otherwise drift the moment the artwork is re-exported at a different size, and
# the failure is silent — every icon simply places the emblem slightly wrong.
with open(os.path.join(WORK, "emblem_geometry.json")) as _fh:
    _G = json.load(_fh)
# emblem_2x.png is the native master at 200%.
EM_W, EM_H = _G["width"] * 2.0, _G["height"] * 2.0
EM_CX, EM_CY, EM_R = _G["cx"] * 2.0, _G["cy"] * 2.0, _G["r"] * 2.0

# Mask geometry, not taste: 66dp safe circle of a 108dp adaptive canvas.
ADAPTIVE_FRACTION = 66.0 / 108.0
# Framing choices, safe to move.
BLEED_FRACTION = 0.74
DISC_FRACTION = 0.78


def run(args):
    subprocess.run(args, check=True)


def place(canvas, fraction):
    """(resize_width, offset_x, offset_y) placing the emblem on a square canvas of
    `canvas` px so its enclosing circle spans `fraction` of that canvas."""
    s = (fraction * canvas) / (2.0 * EM_R)
    return (int(round(EM_W * s)),
            int(round(canvas / 2.0 - EM_CX * s)),
            int(round(canvas / 2.0 - EM_CY * s)))


def emblem_layer(canvas, fraction, dst):
    w, ox, oy = place(canvas, fraction)
    run(["magick", "emblem_2x.png", "-filter", "Lanczos", "-resize", f"{w}x",
         "-background", "none", "-extent", f"{canvas}x{canvas}-{ox}-{oy}", dst])


def bg_layer(canvas, dst, shape="square", radius_pct=0.0):
    run(["magick", "bg_wave.png", "-filter", "Lanczos", "-resize", f"{canvas}x{canvas}!",
         "-alpha", "set", dst])
    if shape == "circle":
        r = canvas / 2.0
        draw = f"circle {r - 0.5},{r - 0.5} {r - 0.5},-0.5"
    elif shape == "rounded":
        rad = canvas * radius_pct
        draw = f"roundrectangle 0,0 {canvas - 1},{canvas - 1} {rad},{rad}"
    else:
        return
    run(["magick", dst,
         "(", "-size", f"{canvas}x{canvas}", "xc:black", "-fill", "white",
         "-draw", draw, "-alpha", "off", ")",
         "-compose", "CopyOpacity", "-composite", dst])


def icon(canvas, fraction, dst, shape="square", radius_pct=0.0, flatten=False):
    bg, fg = os.path.join(OUT, "_bg.png"), os.path.join(OUT, "_fg.png")
    bg_layer(canvas, bg, shape, radius_pct)
    emblem_layer(canvas, fraction, fg)
    args = ["magick", bg, fg, "-compose", "Over", "-composite"]
    if flatten:
        args += ["-background", "#4D5170", "-alpha", "remove", "-alpha", "off"]
    run(args + [dst])


def native_icons():
    """macOS .icns and Windows .ico, each frame rendered at its own size rather than
    downscaled from 1024, so the emblem's linework survives at 16-32 px."""
    iconset = os.path.join(OUT, "Musikku.iconset")
    os.makedirs(iconset, exist_ok=True)
    sizes = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
    for size in sizes:
        icon(size, DISC_FRACTION, os.path.join(OUT, f"disc_{size}.png"), shape="circle")
    mac = {16: ["16x16"], 32: ["16x16@2x", "32x32"], 64: ["32x32@2x"],
           128: ["128x128"], 256: ["128x128@2x", "256x256"],
           512: ["256x256@2x", "512x512"], 1024: ["512x512@2x"]}
    for size, names in mac.items():
        for n in names:
            run(["cp", os.path.join(OUT, f"disc_{size}.png"),
                 os.path.join(iconset, f"icon_{n}.png")])
    run(["iconutil", "-c", "icns", iconset, "-o", os.path.join(OUT, "circle_app_icon.icns")])
    run(["magick"] + [os.path.join(OUT, f"disc_{s}.png")
                      for s in (16, 24, 32, 48, 64, 128, 256)]
        + ["-colors", "256", os.path.join(OUT, "circle_app_icon.ico")])


def main():
    os.makedirs(OUT, exist_ok=True)
    os.chdir(WORK)

    # Android adaptive icon: 108dp canvas, content inside the 66dp safe circle.
    for dpi, size in (("mdpi", 108), ("hdpi", 162), ("xhdpi", 216),
                      ("xxhdpi", 324), ("xxxhdpi", 432)):
        emblem_layer(size, ADAPTIVE_FRACTION, os.path.join(OUT, f"fg_{dpi}.png"))
        bg_layer(size, os.path.join(OUT, f"bg_{dpi}.png"))

    # Android legacy launcher icons.
    for dpi, size in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96),
                      ("xxhdpi", 144), ("xxxhdpi", 192)):
        icon(size, BLEED_FRACTION, os.path.join(OUT, f"legacy_{dpi}.png"),
             shape="rounded", radius_pct=0.22)
        icon(size, BLEED_FRACTION, os.path.join(OUT, f"round_{dpi}.png"), shape="circle")

    # app_icon is clipped to a circle by CreditScreen, so it stays a full-bleed square.
    icon(432, BLEED_FRACTION, os.path.join(OUT, "app_icon.png"))
    icon(432, DISC_FRACTION, os.path.join(OUT, "circle_app_icon_432.png"), shape="circle")
    icon(1024, DISC_FRACTION, os.path.join(OUT, "circle_app_icon_1024.png"), shape="circle")
    icon(256, DISC_FRACTION, os.path.join(OUT, "appimage_256.png"), shape="circle")
    # Play Store listing icon: 512x512, opaque — Google rejects alpha here.
    icon(512, BLEED_FRACTION, os.path.join(OUT, "store_icon.png"), flatten=True)

    native_icons()

    for tmp in ("_bg.png", "_fg.png"):
        p = os.path.join(OUT, tmp)
        if os.path.exists(p):
            os.remove(p)
    print("generated into", OUT)


if __name__ == "__main__":
    sys.exit(main())
