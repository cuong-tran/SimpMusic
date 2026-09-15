# Icon pipeline

Regenerates every Musikku icon from the two design layers in `composeApp/icon/`:
`logo_transparent.png` (the emblem) and `background.png` (the navy seigaiha field).
`logo_source.png` is the full lockup — emblem over the field with the wordmark under it
— and is kept only as the reference and as the source of the wordmark.

```sh
scripts/icons/extract.py                     # masters + ASCII dumps -> scripts/icons/work/
cd scripts/icons/work
/opt/homebrew/bin/python3 ../trace.py 108 45 ../work/mono.xml       "#C73535" 48   # in-app logo
/opt/homebrew/bin/python3 ../trace.py 108 33 ../work/monochrome.xml "#000000" 108  # adaptive <monochrome>
/opt/homebrew/bin/python3 ../gen.py                               # every raster -> work/out/
scripts/icons/install.sh                     # encode + copy into the tree
scripts/icons/banner.py [AppName] [links...] # featureGraphic + dmg-background
```

Requires ImageMagick 7, `cwebp`, `iconutil` (macOS), and a Python with **numpy**
(on this machine only `/opt/homebrew/bin/python3` has it — the pyenv/conda ones do not).
`trace.py` reads ASCII PGM/PPM rather than using PIL, which is not installed anywhere.

`work/` is scratch; nothing in it is committed.

## The things that are easy to get wrong

**Check that the emblem layer's alpha is real before trusting it.** An earlier export
(`logo_only.png`) had alpha 1.0 everywhere with the transparency checkerboard PAINTED
into the pixels (#454545 / #757575, ~25 px tiles). It looks identical in any viewer and
silently bakes a grey checkerboard behind the emblem. `extract.py` detects that and falls
back to keying by chroma; the current layer has real alpha and is used as-is, with the
artist's own anti-aliasing untouched.

**That fallback is not `-fuzz`, and cannot be.** The leaf's dark maroon outline (74,31,38)
sits 19% from #454545 in RGB distance, so the fuzz that finally crosses the checkerboard
(18%) also eats the outline and punches holes through the leaf — plausible enough to
ship. Chroma separates them: the checkerboard is exactly neutral, no emblem colour is,
and the one low-chroma emblem colour (the cream note) is far too bright to collide.

**Stray background decoration is dropped before anything is measured.** An earlier export
carried a lone sparkle in the bottom-right corner, ~400 px from the emblem; an enclosing
circle that includes it is nearly twice the right radius, and every icon would then place
the emblem at half its intended size with no error anywhere. Components are kept by
PROXIMITY, not by size — the ring arcs and blossoms are each their own component too.

**The emblem is placed by its minimal enclosing circle, never its bounding box.** It is a
circular badge whose leaf stem pokes below the ring, so the bbox centre sits ~7 px high
and the mark visibly drifts up the moment a circular mask is applied. `extract.py`
measures the circle into `work/emblem_geometry.json` and `gen.py` reads it — never
restate it in `gen.py`, or the two drift silently on the next re-export.

**The wordmark is not in any icon.** It is illegible below ~96 px; every asset carries the
emblem alone.

**Fractions are mask geometry, not taste.** `0.611` for the adaptive foreground is the
66 dp safe circle of a 108 dp canvas — content outside it is clipped by some launcher
masks. `0.74` full-bleed and `0.78` on a disc are framing choices and can move.

**`trace.py` picks the leaf by COLOUR, then opens the mask.** "Largest opaque blob" does
not work: the gold ring touches the leaf, so the blob is leaf + ring + blossoms and traces
as a scribble. Red separates them (every leaf tone clears `r-g > 25`; the ring is 21 and
the cream note 4) — but the ring's own dark stroke is red enough to pass, so a 3 px
erode/dilate opening drops the ~3 px arc that still hangs off the stem. On a 400 px leaf
the opening is invisible.

**The wobble is removed in CONTOUR space, not by raster blur.** Raster blur only takes
out the pixel staircase and it is isotropic: pushed far enough to erase the source art's
sketchy edge wobble it also melts the lobe tips, so the old σ 3.2 / ε 1.9 pass was stuck
between a faceted outline and a blobby one. `trace.py` now resamples each contour at
uniform arc length (5 px), finds the genuine corners as local maxima of the turn measured
across ±5 samples (≥58°), and Gaussian-smooths each run BETWEEN corners with the ends
pinned (σ 6.5 samples). Pinning is the whole trick — it lets σ go high enough to erase the
wobble while the lobe tips and the valleys between them stay sharp. Raster blur is then
only σ 2.6 / 2.0.

Measuring the turn across a window rather than between neighbours matters: on a resampled
contour a per-vertex angle is mostly quantisation noise, which is what made the old 48°
test fire on smooth edges and produce the facets.

**Both vectors fit the mark to a circle, not the viewport box**, because both consumers
clip to one: `mono` at r 45/54 (the nav-rail logo is `Image` + `CircleShape`, and it
doubles as the notification small icon where the system reads only alpha), `monochrome`
at r 33/54 (the adaptive 66 dp safe zone).

**`core/` is a git submodule.** `core/media/media3/src/main/res/drawable/mono.xml` needs
its own commit in `cuong-tran/simpmusic_core` before the superproject pointer can move.

**`composeApp/appimage/simpmusic.png` is the icon Linux users actually get.**
`packageConveyorAppImage` copies `circle_app_icon.png` over it only `if (!iconDst.exists())`,
and it does exist.

## Banners

`banner.py` builds the two branded images that are not icons, and they take opposite
grounds on purpose. The feature graphic is only ever an image, so it gets the navy field.
The DMG background stays LIGHT: Finder draws the icon labels ("SimpMusic",
"Applications") itself in the system appearance's text colour, which no background image
can influence — dark text on a navy ground is what a light-mode Mac renders. The
wordmark, cream with a maroon outline, therefore gets a navy plate instead of being
recoloured.

Its layout is `scripts/wrap-mac-dmg.sh`'s geometry, not a free composition: icon slots at
(350,380) and (1080,360) at 192 px in the 1400x800 window, so artwork must stay above
y=284 and below y=500.

**The wordmark is keyed on blue-minus-red.** A corner flood fill at 20% leaves a
rectangular patch of the source's navy behind the letters, which reads as a box around
the wordmark; navy (+35), cream (-13) and the maroon outline (-52) separate cleanly on
b-r, and a ramp keeps the glyph edges anti-aliased.

**Futura silently drops Vietnamese diacritics.** `SFNSRounded` covers them and matches
the wordmark. Taglines are fitted to one line by stepping the point size down rather than
wrapping.

**A PNG8 write attaches a tRNS chunk** if the alpha channel is merely opaque rather than
absent, and Play rejects a feature graphic with transparency. Check the chunk list, not
`%[channels]` — that reports the in-memory representation and says `srgb 4.0` either way.

The `<name>.dragTo(Applications)` line names the real bundle. Conveyor still builds
**SimpMusic.app**, so `banner.py` defaults to that; pass a different name only alongside
renaming `app.display-name`/`fsname`, the create-dmg volname, `composeResources`
`app_name.xml`, and the `.dmg` filenames in both workflows.
