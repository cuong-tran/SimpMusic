#!/usr/bin/env python3
"""Generate the two branded banners that are not icons.

  fastlane/metadata/android/<locale>/images/featureGraphic.png   1024x500
  composeApp/icon/dmg-background.png                             2800x1600

Run scripts/icons/extract.py first: this reads work/emblem_2x.png and work/bg_wave.png,
and lifts the wordmark straight out of composeApp/icon/logo_source.png so the banners are
set in the brand's own lettering rather than an approximation of it.

The two have opposite backgrounds on purpose. The feature graphic is just an image, so it
gets the navy field. The DMG background stays LIGHT: Finder draws the icon labels
("SimpMusic", "Applications") itself in the system appearance's text colour, which no
background image can influence — dark text on a navy ground is what a light-mode Mac
would render, and that is most of them.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORK = os.path.join(HERE, "work")
OUT = os.path.join(WORK, "banner")

# Rounded, and — unlike Futura, which renders "Không chỉ là miễn phí" with three glyphs
# silently missing — it covers Vietnamese.
FONT = "/System/Library/Fonts/SFNSRounded.ttf"
FONT_MONO = "/System/Library/Fonts/Menlo.ttc"

NAVY_DARK = "#3B3F5A"
CREAM = "#F5EFE2"
RED = "#C73535"

TAGLINES = {
    "en-US": "Feel free when playing music",
    "vi-VN": "Không chỉ là miễn phí khi nghe nhạc",
}

# create-dmg geometry from scripts/wrap-mac-dmg.sh, in its 1400x800 logical window.
# The asset is authored at 2x and the workflow resizes it back down, so every number
# here is doubled on the canvas. Both icon slots must stay clear of artwork.
DMG_SCALE = 2
DMG_W, DMG_H = 1400, 800
APP_ICON = (350, 380)
APP_DROP = (1080, 360)
ICON_SIZE = 192


def run(args):
    subprocess.run(args, check=True)


def wordmark():
    """Crop the 'Musikku / ムジック' lockup out of the full artwork and key it.

    The crop starts below y=648 because the leaf's stem tip reaches y=637 and would
    otherwise ride along as a red sliver above the M.

    Keying is by BLUE-MINUS-RED, not by colour fuzz. A corner flood fill at 20% leaves a
    rectangular patch of the source's navy sitting behind the letters — it survives
    because the field is subtly graded and the fill runs out of tolerance before it gets
    there, and on the finished banner it reads as a box around the wordmark. The three
    colours here separate cleanly on b-r instead (navy +35, cream -13, maroon outline
    -52), and because it is a ramp rather than a threshold the glyph edges stay
    anti-aliased."""
    dst = os.path.join(OUT, "wordmark.png")
    src = os.path.join(ROOT, "composeApp", "icon", "logo_source.png")
    run(["magick", src, "-crop", "620x180+200+648", "+repage",
         "-alpha", "set", "-channel", "A",
         "-fx", "max(0, min(1, (0.06-(u.b-u.r))/0.12))", "+channel",
         "-trim", "+repage", dst])
    return dst


def label_width(text, pointsize, font):
    out = subprocess.run(
        ["magick", "-background", "none", "-font", font, "-pointsize", str(pointsize),
         "label:" + text, "-format", "%w", "info:"],
        check=True, capture_output=True, text=True)
    return int(out.stdout.strip())


def text_layer(dst, text, pointsize, color, font=FONT, fit=None, min_size=22):
    """One line, always. `fit` is the width it must not exceed; the size steps down
    until it does. Letting it wrap instead is what orphaned "nhạc" onto a second line
    in the Vietnamese banner — the tagline is one phrase and reads as one."""
    if fit:
        while pointsize > min_size and label_width(text, pointsize, font) > fit:
            pointsize -= 1
    run(["magick", "-background", "none", "-fill", color, "-font", font,
         "-pointsize", str(pointsize), "label:" + text, dst])
    return dst


def feature_graphic(locale, tagline):
    """1024x500. Play Store overlays and crops the outer edges on some surfaces, so
    nothing meaningful goes near them."""
    canvas = os.path.join(OUT, f"feature_{locale}.png")
    # A straight band out of the 1024-square field: no rescale, so the seigaiha arcs
    # stay circular and stay sharp.
    run(["magick", os.path.join(WORK, "bg_wave.png"), "-crop", "1024x500+0+262",
         "+repage", canvas])

    emblem = os.path.join(OUT, "_fg_emblem.png")
    run(["magick", os.path.join(WORK, "emblem_2x.png"),
         "-filter", "Lanczos", "-resize", "300x", emblem])
    run(["magick", canvas, emblem, "-gravity", "NorthWest",
         "-geometry", "+120+100", "-composite", canvas])

    wm = os.path.join(OUT, "_fg_wm.png")
    run(["magick", wordmark(), "-filter", "Lanczos", "-resize", "370x", wm])
    run(["magick", canvas, wm, "-gravity", "NorthWest",
         "-geometry", "+470+140", "-composite", canvas])

    tag = text_layer(os.path.join(OUT, f"_fg_tag_{locale}.png"), tagline, 32,
                     CREAM, fit=505)
    run(["magick", canvas, tag, "-gravity", "NorthWest",
         "-geometry", "+472+300", "-composite", canvas])

    # No alpha at all: PNG8 will attach a tRNS chunk if the alpha channel is merely
    # opaque rather than absent, and Play rejects a feature graphic with transparency.
    run(["magick", canvas, "-background", NAVY_DARK, "-alpha", "remove", "-alpha", "off",
         "-dither", "FloydSteinberg", "-colors", "255", "-strip",
         "-define", "png:color-type=3", "-define", "png:exclude-chunk=tRNS",
         "PNG8:" + os.path.join(ROOT, "fastlane", "metadata", "android", locale,
                                "images", "featureGraphic.png")])


def dmg_background(app_label, links):
    """2800x1600 (2x of create-dmg's 1400x800 window)."""
    W, H = DMG_W * DMG_SCALE, DMG_H * DMG_SCALE
    S = DMG_SCALE
    canvas = os.path.join(OUT, "dmg.png")

    # Cream ground with the seigaiha field laid over it faintly: the pattern reads as a
    # watermark instead of a surface, which keeps Finder's own icon labels legible.
    run(["magick", "-size", f"{W}x{H}", f"xc:{CREAM}", canvas])
    field = os.path.join(OUT, "_dmg_field.png")
    # Scale to COVER, never to fit: the field is square and this canvas is 1.75:1, so a
    # plain resize would squash every wave into an ellipse.
    run(["magick", os.path.join(WORK, "bg_wave.png"),
         "-filter", "Lanczos", "-resize", f"{W}x{H}^",
         "-gravity", "center", "-extent", f"{W}x{H}",
         "-alpha", "set", "-channel", "A", "-evaluate", "multiply", "0.16", "+channel",
         field])
    run(["magick", canvas, field, "-compose", "Over", "-composite", canvas])

    # The wordmark is cream with a maroon outline — it is drawn for a dark ground and
    # nearly vanishes on this one. It gets a navy plate rather than being recoloured, so
    # the brand's own lettering survives. The plate sits well above y=284, where the
    # icon slots and their Finder labels begin.
    px0, py0, px1, py1 = 390 * S, 28 * S, 1010 * S, 218 * S
    run(["magick", canvas, "-fill", NAVY_DARK, "-stroke", "none",
         "-draw", f"roundrectangle {px0},{py0} {px1},{py1} {26 * S},{26 * S}", canvas])

    emblem = os.path.join(OUT, "_dmg_emblem.png")
    run(["magick", os.path.join(WORK, "emblem_2x.png"),
         "-filter", "Lanczos", "-resize", f"{136 * S}x", emblem])
    run(["magick", canvas, emblem, "-gravity", "NorthWest",
         "-geometry", f"+{412 * S}+{55 * S}", "-composite", canvas])

    wm = os.path.join(OUT, "_dmg_wm.png")
    run(["magick", wordmark(), "-filter", "Lanczos", "-resize", f"{330 * S}x", wm])
    run(["magick", canvas, wm, "-gravity", "NorthWest",
         "-geometry", f"+{600 * S}+{70 * S}", "-composite", canvas])

    # Arrow across the gap between the two icon slots, at their own height.
    x0 = (APP_ICON[0] + ICON_SIZE // 2 + 34) * S
    x1 = (APP_DROP[0] - ICON_SIZE // 2 - 34) * S
    y0 = (APP_ICON[1] - 6) * S
    y1 = (APP_DROP[1] - 16) * S
    ctrl = ((x0 + x1) // 2, int((y0 + y1) / 2) + 46 * S)
    # Arrowhead along the curve's end tangent (P2 - P1 for a quadratic), so it points
    # where the stroke actually arrives instead of flat right.
    dx, dy = x1 - ctrl[0], y1 - ctrl[1]
    n = max(1.0, (dx * dx + dy * dy) ** 0.5)
    ux, uy = dx / n, dy / n
    hl, hw = 30 * S, 15 * S
    tip = (x1, y1)
    back = (x1 - ux * hl, y1 - uy * hl)
    head = (f"polygon {tip[0]:.0f},{tip[1]:.0f} "
            f"{back[0] - uy * hw:.0f},{back[1] + ux * hw:.0f} "
            f"{back[0] + uy * hw:.0f},{back[1] - ux * hw:.0f}")
    run(["magick", canvas,
         "-stroke", NAVY_DARK, "-strokewidth", str(5 * S), "-fill", "none",
         "-draw", f"path 'M {x0},{y0} Q {ctrl[0]},{ctrl[1]} "
                  f"{back[0] + ux * hl * 0.3:.0f},{back[1] + uy * hl * 0.3:.0f}'",
         "-stroke", "none", "-fill", NAVY_DARK, "-draw", head,
         canvas])

    code = text_layer(os.path.join(OUT, "_dmg_code.png"),
                      f"{app_label}.dragTo(Applications)", 30 * S, NAVY_DARK,
                      font=FONT_MONO)
    run(["magick", canvas, code, "-gravity", "North",
         "-geometry", f"+0+{562 * S}", "-composite", canvas])

    y = 648 * S
    for i, line in enumerate(links):
        lay = text_layer(os.path.join(OUT, f"_dmg_link{i}.png"), line, 21 * S, "#6B7185")
        run(["magick", canvas, lay, "-gravity", "North", "-geometry", f"+0+{y}",
             "-composite", canvas])
        y += 36 * S

    # Quantised like the in-app PNGs: the ground is flat cream under a faint pattern, so
    # 255 colours is indistinguishable and keeps the file near the one it replaces.
    run(["magick", canvas, "-background", CREAM, "-alpha", "remove", "-alpha", "off",
         "-dither", "FloydSteinberg", "-colors", "255", "-strip",
         "-define", "png:color-type=3", "-define", "png:exclude-chunk=tRNS",
         "PNG8:" + os.path.join(ROOT, "composeApp", "icon", "dmg-background.png")])


def main():
    if not os.path.exists(os.path.join(WORK, "emblem_2x.png")):
        sys.exit("run scripts/icons/extract.py first")
    os.makedirs(OUT, exist_ok=True)
    # Must match Conveyor's app.display-name, which names the .app bundle the DMG
    # window actually shows. Both are "Musikku"; app.fsname stays "simpmusic".
    app_label = sys.argv[1] if len(sys.argv) > 1 else "Musikku"
    links = sys.argv[2:] or ["GitHub: https://github.com/cuong-tran/SimpMusic/"]

    for locale, tagline in TAGLINES.items():
        feature_graphic(locale, tagline)
    dmg_background(app_label, links)
    print("banners written")


if __name__ == "__main__":
    main()
