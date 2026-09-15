#!/usr/bin/env bash
# Encode and install everything gen.py produced into the tree.
#
# Encoding is lossy on purpose. Lossless WebP puts the five densities x four layers at
# 750 kB; -q 90/92 with -alpha_q 100 lands at 260 kB and measures PSNR 40.7/45.7 dB,
# which is invisible at icon scale. The three in-app PNGs are quantised to 255 colours
# so the APK footprint matches the ~70 kB each they replaced. composeApp/icon's 1024
# stays 24-bit: it is the Conveyor source and never enters the APK.
set -euo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
root="$(cd "$here/../.." && pwd)"
out="${1:-$here/work/out}"

cd "$out"

for d in mdpi hdpi xhdpi xxhdpi xxxhdpi; do
    m="$root/androidApp/src/main/res/mipmap-$d"
    cwebp -quiet -q 90 -alpha_q 100        "bg_$d.png"     -o "$m/ic_launcher_background.webp"
    cwebp -quiet -q 92 -alpha_q 100 -exact "fg_$d.png"     -o "$m/ic_launcher_foreground.webp"
    cwebp -quiet -q 92 -alpha_q 100 -exact "legacy_$d.png" -o "$m/ic_launcher.webp"
    cwebp -quiet -q 92 -alpha_q 100 -exact "round_$d.png"  -o "$m/ic_launcher_round.webp"
done

quant() { magick "$1" -dither FloydSteinberg -colors 255 "PNG8:$2"; }

quant app_icon.png            "$root/androidApp/src/main/res/drawable/app_icon.png"
quant app_icon.png            "$root/composeApp/src/commonMain/composeResources/drawable/app_icon.png"
quant circle_app_icon_432.png "$root/composeApp/src/commonMain/composeResources/drawable/circle_app_icon.png"
# packageConveyorAppImage only copies circle_app_icon.png over this one when it is
# ABSENT, and it never is — so this file is the icon Linux users actually get.
quant appimage_256.png        "$root/composeApp/appimage/simpmusic.png"

cp circle_app_icon_1024.png "$root/composeApp/icon/circle_app_icon.png"
cp circle_app_icon.icns     "$root/composeApp/icon/circle_app_icon.icns"
cp circle_app_icon.ico      "$root/composeApp/icon/circle_app_icon.ico"

# Play Store listing icon: 512x512, opaque, square — Google rejects alpha here.
cp store_icon.png "$root/fastlane/metadata/android/en-US/images/icon.png"
cp store_icon.png "$root/fastlane/metadata/android/vi-VN/images/icon.png"

# The three mono.xml copies and the two monochrome.xml copies must stay byte-identical.
# core/ is a git submodule: its copy needs its own commit.
for dst in "$root/androidApp/src/main/res/drawable/mono.xml" \
           "$root/composeApp/src/commonMain/composeResources/drawable/mono.xml" \
           "$root/core/media/media3/src/main/res/drawable/mono.xml"; do
    cp "$here/work/mono.xml" "$dst"
done
for dst in "$root/androidApp/src/main/res/drawable/monochrome.xml" \
           "$root/composeApp/src/commonMain/composeResources/drawable/monochrome.xml"; do
    cp "$here/work/monochrome.xml" "$dst"
done

echo "installed"
