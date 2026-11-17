"""Proof of concept: build a small COLRv0/CPAL color font from Source Han Sans.

Steps:
1. Subset the variable Source Han Sans SC font to a few characters.
2. Pin it to a static Regular instance (wght=400).
3. Color whole characters by radical (one layer = original outline).
4. Split selected left/right characters into two components by contour
   position and give each component its own color (two layers).
5. Build COLR (v0) + CPAL, rename the family, write the font and an HTML test page.

Usage:
    python build_poc_font.py [path-to-SourceHanSansSC-VF.ttf]
"""

import sys
from pathlib import Path

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.varLib import instancer

DEFAULT_SOURCE = Path.home() / "Downloads/02_SourceHanSans-VF/Variable/TTF/SourceHanSansSC-VF.ttf"
OUT_DIR = Path(__file__).parent / "out"
# Bump on every build you install: Windows/Office cache fonts by name.
VERSION = 3
FAMILY = f"Hanzi Color POC {VERSION}"
PS_NAME = f"HanziColorPOC{VERSION}-Regular"
FILE_NAME = f"HanziColorPOC{VERSION}.ttf"

# The 20 color groups. PoC uses one base color per group; all groups live in
# CPAL palette 0, because most apps (Office, browsers) only use palette 0.
COLOR_GROUPS = [
    ("Imperial Gold", "#D4A017"),
    ("Chinese New Year", "#D7263D"),
    ("Jade", "#00A86B"),
    ("Porcelain Blue", "#1F4E9C"),
    ("Dragon Fire", "#FF4500"),
    ("Lotus Pink", "#E75480"),
    ("Bamboo Green", "#5B8C2A"),
    ("Phoenix", "#FF8C00"),
    ("Cyberpunk", "#B000FF"),
    ("Chrome", "#8A9BA8"),
    ("Ocean", "#0077BE"),
    ("Sunset", "#FD5E53"),
    ("Royal Purple", "#6A0DAD"),
    ("Emerald", "#009B77"),
    ("Sakura", "#F4A7B9"),
    ("Autumn", "#C1440E"),
    ("Ice Crystal", "#5BC0EB"),
    ("Galaxy", "#2E1A47"),
    ("Bronze", "#CD7F32"),
    ("Rainbow", "#E91E63"),
]
GROUP_INDEX = {name: i for i, (name, _) in enumerate(COLOR_GROUPS)}

# Kept uncolored so normal text (spaces, Latin, punctuation) doesn't show as boxes.
PLAIN_TEXT = "".join(chr(c) for c in range(0x20, 0x7F)) + "，。！？、：；“”（）"

# Whole characters: one color by radical / meaning.
WHOLE = {
    "你": "Royal Purple",      # 亻 person
    "中": "Imperial Gold",
    "国": "Chinese New Year",
    "火": "Dragon Fire",       # 火 fire
    "心": "Sakura",            # 心 heart
}

# Left/right characters: contours whose center lies left of split * advance
# form the left component, the rest the right component.
SPLIT = {
    "好": (0.48, "Lotus Pink", "Porcelain Blue"),   # 女 + 子
    "妈": (0.45, "Lotus Pink", "Autumn"),           # 女 + 马
    "休": (0.36, "Royal Purple", "Bamboo Green"),   # 亻 + 木
    "明": (0.42, "Imperial Gold", "Ice Crystal"),   # 日 + 月
    "湖": (0.30, "Ocean", "Bronze"),                # 氵 + 胡
}


def hex_to_rgba(value):
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4)) + (1.0,)


def load_static_subset(source, text):
    font = TTFont(source)
    options = Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    # Keep the source's OS/2 code page bits (CP936 etc.). If they are recalculated
    # from the tiny subset, Word treats the font as Latin-only and never uses it
    # for Chinese text.
    options.prune_codepage_ranges = False
    options.prune_unicode_ranges = False
    subsetter = Subsetter(options)
    subsetter.populate(text=text)
    subsetter.subset(font)
    font = instancer.instantiateVariableFont(font, {"wght": 400})
    if "STAT" in font:
        del font["STAT"]
    insert_null_glyph(font)
    return font


def insert_null_glyph(font):
    """COLR spec: glyph ID 1 must be the empty .null glyph."""
    order = font.getGlyphOrder()
    if order[1] == ".null":
        return
    new_order = [order[0], ".null"] + order[1:]
    font["glyf"].glyphs[".null"] = Glyph()
    font["hmtx"][".null"] = (0, 0)
    if "vmtx" in font:
        font["vmtx"][".null"] = (font["vmtx"][order[0]][0], 0)
    font.setGlyphOrder(new_order)
    font["glyf"].setGlyphOrder(new_order)


def split_contours(font, glyph_name):
    """Return the glyph's contours as lists of recorded pen operations."""
    glyph_set = font.getGlyphSet()
    recording = RecordingPen()
    glyph_set[glyph_name].draw(recording)
    contours, current = [], []
    for op, args in recording.value:
        current.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(current)
            current = []
    return contours


def contour_center_x(contour):
    pen = ControlBoundsPen(None)
    for op, args in contour:
        getattr(pen, op)(*args)
    x_min, _, x_max, _ = pen.bounds
    return (x_min + x_max) / 2


def add_glyph(font, name, contours, metrics_source):
    pen = TTGlyphPen(None)
    for contour in contours:
        for op, args in contour:
            getattr(pen, op)(*args)
    glyph = pen.glyph()
    glyf = font["glyf"]
    glyf[name] = glyph  # also appends the name to the glyph order
    if name not in font.getGlyphOrder():
        font.setGlyphOrder(font.getGlyphOrder() + [name])
    glyph.recalcBounds(glyf)

    advance, _ = font["hmtx"][metrics_source]
    font["hmtx"][name] = (advance, getattr(glyph, "xMin", 0))
    if "vmtx" in font:
        font["vmtx"][name] = font["vmtx"][metrics_source]


def build_color_layers(font):
    cmap = font.getBestCmap()
    layers = {}

    for char, group in WHOLE.items():
        base = cmap[ord(char)]
        layers[base] = [(base, GROUP_INDEX[group])]

    for char, (split, left_group, right_group) in SPLIT.items():
        base = cmap[ord(char)]
        advance, _ = font["hmtx"][base]
        left, right = [], []
        for contour in split_contours(font, base):
            target = left if contour_center_x(contour) < split * advance else right
            target.append(contour)
        if not left or not right:
            print(f"  {char}: split found no two components, coloring as whole")
            layers[base] = [(base, GROUP_INDEX[left_group])]
            continue
        add_glyph(font, f"{base}.left", left, base)
        add_glyph(font, f"{base}.right", right, base)
        layers[base] = [
            (f"{base}.left", GROUP_INDEX[left_group]),
            (f"{base}.right", GROUP_INDEX[right_group]),
        ]
        print(f"  {char}: {len(left)} left / {len(right)} right contours")

    return layers


def rename(font):
    # Source Han Sans is OFL with Reserved Font Names: a modified font must be renamed.
    name = font["name"]
    for name_id in (16, 17, 21, 22, 25):
        name.removeNames(nameID=name_id)
    for name_id, value in {
        1: FAMILY,
        2: "Regular",
        3: f"{PS_NAME};POC",
        4: f"{FAMILY} Regular",
        6: PS_NAME,
    }.items():
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 1, 0, 0)


def write_test_page(path, font_file):
    text = "".join(WHOLE) + "".join(SPLIT)
    legend = "".join(
        f"<li><span style='background:{color}'></span>{i + 1:02d} {name}</li>"
        for i, (name, color) in enumerate(COLOR_GROUPS)
    )
    path.write_text(f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>Hanzi Color POC</title>
<style>
  @font-face {{ font-family: "HanziColorPOC"; src: url("{font_file}"); }}
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #fff; color: #222; }}
  .big {{ font-family: "HanziColorPOC"; font-size: 120px; line-height: 1.3; }}
  .ref {{ font-family: "Source Han Sans SC", "Microsoft YaHei", sans-serif; font-size: 40px; color: #888; }}
  ul {{ columns: 4; list-style: none; padding: 0; }}
  li span {{ display: inline-block; width: 1em; height: 1em; margin-right: .4em; vertical-align: middle; }}
</style>
</head>
<body>
<h1>Hanzi Color POC</h1>
<p>Should be colored. Split characters (好 妈 休 明 湖) show two colors.</p>
<div class="big">{text}</div>
<p class="ref">Reference (system font): {text}</p>
<h2>Color groups</h2>
<ul>{legend}</ul>
</body>
</html>
""", encoding="utf-8")


def main():
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SOURCE
    text = "".join(WHOLE) + "".join(SPLIT)
    OUT_DIR.mkdir(exist_ok=True)

    print(f"Source: {source}")
    print("Subsetting and instancing (wght=400)...")
    font = load_static_subset(source, text + PLAIN_TEXT)

    print("Building color layers...")
    layers = build_color_layers(font)
    font["COLR"] = buildCOLR(layers, version=0)
    font["CPAL"] = buildCPAL([[hex_to_rgba(color) for _, color in COLOR_GROUPS]])
    rename(font)

    out_font = OUT_DIR / FILE_NAME
    font.save(out_font)
    write_test_page(OUT_DIR / "test.html", out_font.name)

    check = TTFont(out_font)
    print(f"Written: {out_font} ({out_font.stat().st_size // 1024} KB)")
    print(f"  glyphs: {len(check.getGlyphOrder())}, COLR base glyphs: {len(check['COLR'].ColorLayers)}, "
          f"CPAL entries: {check['CPAL'].numPaletteEntries}")
    print(f"Test page: {OUT_DIR / 'test.html'}")


if __name__ == "__main__":
    main()
