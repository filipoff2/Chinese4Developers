"""Build a COLRv0/CPAL color font for every Chinese character used in this repo.

Characters: every CJK character found in the repo's text files (.md, .json, .txt and files
without extension; the cloude_fun_fonts folder is skipped). Other characters in those files
(Latin, pinyin, punctuation) are kept uncolored.

Coloring:
  1. Characters in hanzi-120.json get the role colors of the lesson (semantic / phonetic /
     neutral, see 120_Common_Chinese_Characters_Component_Colored.md):
     - one component: the whole character in that role color;
     - several components: each component in its own role color. The Source Han Sans
       outline pieces are assigned to components with the stroke data of Make Me a Hanzi.
       If that is not clean, the character falls back to 2.
  2. All other characters: one color by radical (Unihan kRSUnicode -> one of 20 color groups).

Usage (from the cloude_fun_fonts folder):
    .venv\\Scripts\\python generator\\fetch_data.py                 # once
    .venv\\Scripts\\python generator\\build_repo_font.py --build 1 --preview

Writes generator/out/Hanzi4DevColor<build>.ttf, test.html, report.md (and preview.png).
"""

import argparse
import html
import json
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from fontTools.colorLib.builder import buildCOLR, buildCPAL
from fontTools.pens.areaPen import AreaPen
from fontTools.pens.boundsPen import ControlBoundsPen
from fontTools.pens.pointInsidePen import PointInsidePen
from fontTools.pens.recordingPen import RecordingPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.subset import Options, Subsetter
from fontTools.ttLib import TTFont
from fontTools.ttLib.tables._g_l_y_f import Glyph
from fontTools.varLib import instancer

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))  # colors.py; needed when run with python -I
from colors import COLOR_GROUPS, COMPONENT_VARIANTS, ROLE_COLORS, group_for_radical  # noqa: E402

REPO_DIR = HERE.parent.parent
DATA_DIR = HERE / "data"
OUT_DIR = HERE / "out"
HANZI_JSON = REPO_DIR / "hanzi-120.json"
DEFAULT_SOURCE = Path.home() / "Downloads/02_SourceHanSans-VF/Variable/TTF/SourceHanSansSC-VF.ttf"
# Bump on every build you install: Windows/Office cache fonts by name.
DEFAULT_BUILD = 1

TEXT_SUFFIXES = {".md", ".json", ".txt", ""}
SKIP_DIRS = {"cloude_fun_fonts", ".git", ".venv"}
CJK = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
# Always kept (uncolored), so spaces and punctuation never show as missing-glyph boxes.
BASE_PLAIN = "".join(chr(c) for c in range(0x20, 0x7F)) + "，。！？、：；“”‘’（）《》【】…—·"

GROUP_INDEX = {name: i for i, (name, _) in enumerate(COLOR_GROUPS)}
ROLE_INDEX = {role: len(COLOR_GROUPS) + i for i, (role, _) in enumerate(ROLE_COLORS)}

# Component split: sample grid (font units) and the minimum share of votes one component
# needs for an outline piece. Below that the piece belongs to several components.
GRID_STEP = 12
MIN_SHARE = 0.6
IDC_TERNARY = "⿲⿳"


# ---------------------------------------------------------------------------
# Input data
# ---------------------------------------------------------------------------

def collect_repo_text(repo_dir):
    """Return (CJK characters in order of first use, other printable characters, files)."""
    chars, plain, files = {}, set(), []
    for path in sorted(repo_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(repo_dir).parts):
            continue
        files.append(path)
        for ch in path.read_text(encoding="utf-8", errors="ignore"):
            if CJK.match(ch):
                chars.setdefault(ch, len(chars))
            elif ch.isprintable():
                plain.add(ch)
    return list(chars), plain, files


def load_radicals(zip_path):
    """Unihan kRSUnicode: character -> Kangxi radical number (first value)."""
    radicals = {}
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            for line in archive.read(name).decode("utf-8").splitlines():
                if "\tkRSUnicode\t" not in line:
                    continue
                code, _, value = line.split("\t")
                radicals[chr(int(code[2:], 16))] = int(re.match(r"\d+", value).group())
    return radicals


def load_jsonl(path, wanted):
    result = {}
    with open(path, encoding="utf-8") as lines:
        for line in lines:
            entry = json.loads(line)
            if entry["character"] in wanted:
                result[entry["character"]] = entry
    return result


def parse_ids(text, i=0):
    """Parse an ideographic description sequence: leaf = str, node = (operator, [children])."""
    ch = text[i]
    if 0x2FF0 <= ord(ch) <= 0x2FFF:
        arity = 3 if ch in IDC_TERNARY else 2
        children, i = [], i + 1
        for _ in range(arity):
            child, i = parse_ids(text, i)
            children.append(child)
        return (ch, children), i
    return ch, i + 1


def flatten(node):
    return node if isinstance(node, str) else "".join(flatten(c) for c in node[1])


def canonical(component):
    return COMPONENT_VARIANTS.get(component, component)


# ---------------------------------------------------------------------------
# Font helpers (lessons from the PoC, see POC_RESULTS.md section 4)
# ---------------------------------------------------------------------------

def load_static_subset(source, text):
    font = TTFont(source)
    options = Options()
    options.layout_features = ["*"]
    options.name_IDs = ["*"]
    options.notdef_outline = True
    # Keep the source's OS/2 code page bits (CP936 etc.), otherwise Word treats the
    # font as Latin-only and never uses it for Chinese text.
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
    """COLR spec: glyph ID 1 must be the empty .null glyph (Word needs it)."""
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


def add_glyph(font, name, contours, metrics_source):
    pen = TTGlyphPen(None)
    replay(contours, pen)
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


def rename(font, family, ps_name):
    # Source Han Sans is OFL with Reserved Font Names: a modified font must be renamed.
    name = font["name"]
    for name_id in (16, 17, 21, 22, 25):
        name.removeNames(nameID=name_id)
    for name_id, value in {
        1: family,
        2: "Regular",
        3: f"{ps_name};Hanzi4Dev",
        4: f"{family} Regular",
        6: ps_name,
    }.items():
        name.setName(value, name_id, 3, 1, 0x409)
        name.setName(value, name_id, 1, 0, 0)


# ---------------------------------------------------------------------------
# Outline geometry
# ---------------------------------------------------------------------------

def replay(contours, pen):
    for contour in contours:
        for op, args in contour:
            getattr(pen, op)(*args)


def glyph_contours(glyph_set, name):
    recording = RecordingPen()
    glyph_set[name].draw(recording)
    contours, current = [], []
    for op, args in recording.value:
        current.append((op, args))
        if op in ("closePath", "endPath"):
            contours.append(current)
            current = []
    return contours


def first_point(contour):
    for _, args in contour:
        for point in args:
            if point is not None:
                return point
    return (0, 0)


def contour_area(contour):
    pen = AreaPen()
    replay([contour], pen)
    return pen.value


def bounds(contours):
    pen = ControlBoundsPen(None)
    replay(contours, pen)
    return pen.bounds


def inside(contours, point, glyph_set):
    pen = PointInsidePen(glyph_set, point)
    replay(contours, pen)
    return pen.getResult()


def group_contours(contours, glyph_set):
    """Group each counter (hole, e.g. inside 口) with the outline around it.

    Holes run the other way than outlines. Overlapping outlines (the variable font keeps
    strokes as separate overlapping contours) stay separate groups.
    """
    areas = [contour_area(c) for c in contours]
    largest = max(range(len(areas)), key=lambda i: abs(areas[i]))
    outer_sign = 1 if areas[largest] > 0 else -1
    outers = [i for i, a in enumerate(areas) if a * outer_sign > 0]
    groups = {i: [contours[i]] for i in outers}
    for i, area in enumerate(areas):
        if area * outer_sign > 0:
            continue
        point = first_point(contours[i])
        parents = [j for j in outers if inside([contours[j]], point, glyph_set)]
        if parents:
            groups[min(parents, key=lambda j: abs(areas[j]))].append(contours[i])
        else:
            groups[i] = [contours[i]]
    return list(groups.values())


def sample_points(group, glyph_set):
    x_min, y_min, x_max, y_max = bounds(group)
    points = []
    y = y_min + GRID_STEP / 2
    while y < y_max:
        x = x_min + GRID_STEP / 2
        while x < x_max:
            if inside(group, (x, y), glyph_set):
                points.append((x, y))
            x += GRID_STEP
        y += GRID_STEP
    if not points:  # very thin piece: use its own points
        points = [p for _, args in group[0] for p in args if p is not None]
    return points


def stroke_points(path):
    numbers = [float(n) for n in re.findall(r"-?\d+(?:\.\d+)?", path)]
    return list(zip(numbers[0::2], numbers[1::2]))


def segment_distance2(point, a, b):
    px, py = point
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length2 = dx * dx + dy * dy
    t = 0.0 if length2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / length2))
    cx, cy = ax + t * dx - px, ay + t * dy - py
    return cx * cx + cy * cy


# ---------------------------------------------------------------------------
# Coloring
# ---------------------------------------------------------------------------

class SplitFailed(Exception):
    pass


def split_into_components(char, entry, mmah_dict, mmah_graphics, contours, glyph_set):
    """Assign the glyph's outline pieces to the components of hanzi-120.json.

    Returns ({json component index: [contours]}, lowest vote share).
    """
    components = entry["components"]
    info, graphics = mmah_dict.get(char), mmah_graphics.get(char)
    if not info or not graphics:
        raise SplitFailed("no Make Me a Hanzi data")
    tree, _ = parse_ids(info["decomposition"])
    if isinstance(tree, str):
        raise SplitFailed(f"no decomposition ({info['decomposition']})")
    parts = [flatten(child) for child in tree[1]]
    if len(parts) != len(components):
        raise SplitFailed(f"decomposition {info['decomposition']} has {len(parts)} parts, "
                          f"hanzi-120.json has {len(components)}")

    # hanzi-120.json component -> Make Me a Hanzi part: same glyph first, rest in order.
    mapping, free_parts = {}, list(range(len(parts)))
    for i, component in enumerate(components):
        for j in free_parts:
            if canonical(parts[j]) == canonical(component["glyph"]):
                mapping[i] = j
                free_parts.remove(j)
                break
    for i in range(len(components)):
        if i not in mapping:
            mapping[i] = free_parts.pop(0)

    # Stroke -> top-level part. Unmatched strokes go to the one part without strokes.
    stroke_part = [match[0] if match else None for match in info["matches"]]
    empty = [j for j in range(len(parts)) if j not in stroke_part]
    if len(empty) == 1 and None in stroke_part:
        stroke_part = [empty[0] if p is None else p for p in stroke_part]
    missing = [parts[j] for j in range(len(parts)) if j not in stroke_part]
    if missing:
        raise SplitFailed(f"no strokes for part {'/'.join(missing)}")

    # Scale Make Me a Hanzi coordinates onto the Source Han Sans glyph (bounding boxes).
    all_points = [p for path in graphics["strokes"] for p in stroke_points(path)]
    mx0, my0 = min(p[0] for p in all_points), min(p[1] for p in all_points)
    mx1, my1 = max(p[0] for p in all_points), max(p[1] for p in all_points)
    tx0, ty0, tx1, ty1 = bounds(contours)
    sx = (tx1 - tx0) / max(mx1 - mx0, 1)
    sy = (ty1 - ty0) / max(my1 - my0, 1)

    segments = []  # (a, b, part)
    for median, part in zip(graphics["medians"], stroke_part):
        if part is None:
            continue
        points = [(tx0 + (x - mx0) * sx, ty0 + (y - my0) * sy) for x, y in median]
        segments += [(a, b, part) for a, b in zip(points, points[1:])]

    pieces = defaultdict(list)
    lowest_share = 1.0
    for group in group_contours(contours, glyph_set):
        votes = Counter()
        for point in sample_points(group, glyph_set):
            _, part = min((segment_distance2(point, a, b), part) for a, b, part in segments)
            votes[part] += 1
        part, count = votes.most_common(1)[0]
        share = count / sum(votes.values())
        lowest_share = min(lowest_share, share)
        if share < MIN_SHARE:
            raise SplitFailed(f"one outline piece belongs to several parts "
                              f"({' + '.join(parts[p] for p in votes)}, best share {share:.0%})")
        pieces[part] += group

    empty_parts = [parts[j] for j in range(len(parts)) if j not in pieces]
    if empty_parts:
        raise SplitFailed(f"part {'/'.join(empty_parts)} has no own outline piece")
    return {i: pieces[j] for i, j in mapping.items()}, lowest_share


def build_color_layers(font, chars, hanzi, radicals, mmah_dict, mmah_graphics, neutral_mode):
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    layers, report = {}, []

    def radical_layer(char, base):
        radical = radicals.get(char)
        if radical is None:
            group, how = COLOR_GROUPS[ord(char) % len(COLOR_GROUPS)][0], "no radical data"
        else:
            group, mapped = group_for_radical(radical)
            how = f"radical {radical} {chr(0x2F00 + radical - 1)}" + ("" if mapped else " (default group)")
        layers[base] = [(base, GROUP_INDEX[group])]
        return group, how

    def role_index(char, role):
        if role == "neutral" and neutral_mode == "radical":
            group, _ = group_for_radical(radicals.get(char, 1))
            return GROUP_INDEX[group]
        return ROLE_INDEX[role]

    for char in chars:
        base = cmap.get(ord(char))
        if base is None:
            report.append({"char": char, "mode": "missing", "note": "not in source font"})
            continue
        entry = hanzi.get(char)

        if entry and len(entry["components"]) == 1:
            role = entry["components"][0]["role"]
            layers[base] = [(base, role_index(char, role))]
            report.append({"char": char, "mode": "role-whole", "note": role})
            continue

        if entry:
            try:
                pieces, share = split_into_components(
                    char, entry, mmah_dict, mmah_graphics, glyph_contours(glyph_set, base), glyph_set)
            except SplitFailed as failure:
                group, how = radical_layer(char, base)
                report.append({"char": char, "mode": "fallback", "note": f"{failure}; {group} by {how}"})
                continue
            layer_list = []
            for i, component in enumerate(entry["components"]):
                name = f"{base}.p{i}"
                add_glyph(font, name, pieces[i], base)
                layer_list.append((name, role_index(char, component["role"])))
            layers[base] = layer_list
            parts = ", ".join(f"{c['glyph']} {c['role']}" for c in entry["components"])
            report.append({"char": char, "mode": "role-parts", "note": f"{parts} (lowest share {share:.0%})"})
            continue

        group, how = radical_layer(char, base)
        report.append({"char": char, "mode": "radical", "note": f"{group} by {how}"})

    return layers, report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

MODES = [
    ("role-parts", "Components in role colors (hanzi-120.json)"),
    ("role-whole", "One component, role color (hanzi-120.json)"),
    ("fallback", "hanzi-120.json, split failed: radical color"),
    ("radical", "Radical color"),
    ("missing", "Not in the source font"),
]


def write_test_page(path, font_file, family, report, sample_lines):
    by_mode = defaultdict(list)
    for row in report:
        by_mode[row["mode"]].append(row)
    sections = []
    for mode, title in MODES:
        rows = by_mode.get(mode)
        if not rows:
            continue
        cells = "".join(f"<span title='{html.escape(r['char'] + ': ' + r['note'], quote=True)}'>{r['char']}</span>"
                        for r in rows)
        sections.append(f"<h2>{title} ({len(rows)})</h2><div class='grid'>{cells}</div>")
    legend = "".join(f"<li><i style='background:{color}'></i>{name}</li>" for name, color in COLOR_GROUPS)
    roles = "".join(f"<li><i style='background:{color}'></i>{role}</li>" for role, color in ROLE_COLORS)
    samples = "".join(f"<p>{html.escape(line)}</p>" for line in sample_lines)
    path.write_text(f"""<!doctype html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{family}</title>
<style>
  @font-face {{ font-family: "Hanzi4DevTest"; src: url("{font_file}"); }}
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #fff; color: #222; }}
  .grid {{ font-family: "Hanzi4DevTest"; font-size: 56px; line-height: 1.25; word-break: break-all; }}
  .grid span {{ cursor: help; }}
  .sample {{ font-family: "Hanzi4DevTest"; font-size: 28px; }}
  .sample p {{ margin: .2em 0; }}
  ul {{ columns: 5; list-style: none; padding: 0; }}
  li i {{ display: inline-block; width: 1em; height: 1em; margin-right: .4em; vertical-align: middle; }}
</style>
</head>
<body>
<h1>{family}</h1>
<p>Hover a character to see how it was colored. Details: report.md</p>
{''.join(sections)}
<h2>Sample text from the repo</h2>
<div class="sample">{samples}</div>
<h2>Role colors</h2><ul>{roles}</ul>
<h2>Color groups</h2><ul>{legend}</ul>
</body>
</html>
""", encoding="utf-8")


def write_report(path, family, files, report, radicals):
    counts = Counter(row["mode"] for row in report)
    lines = [f"# {family}: build report", "",
             f"Source files scanned: {len(files)}  ", f"Characters: {len(report)}", "",
             "| Mode | Characters |", "| ---- | ---------- |"]
    lines += [f"| {title} | {counts.get(mode, 0)} |" for mode, title in MODES]
    for mode, title in MODES:
        rows = [r for r in report if r["mode"] == mode]
        if not rows or mode == "radical":
            continue
        lines += ["", f"## {title}", "", "| Char | Details |", "| ---- | ------- |"]
        lines += [f"| {r['char']} | {r['note']} |" for r in rows]
    group_counts = Counter(r["note"].split(" by ")[0] for r in report if r["mode"] in ("radical", "fallback"))
    lines += ["", "## Radical colors: characters per group", "", "| Group | Characters |", "| ----- | ---------- |"]
    lines += [f"| {name} | {group_counts.get(name, 0)} |" for name, _ in COLOR_GROUPS]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sample_text(files, limit=12):
    lines = []
    for path in files:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            clean = re.sub(r"<[^>]+>|[#*`>|]", "", line).strip(" -")
            if len(CJK.findall(clean)) >= 4 and len(clean) < 80:
                lines.append(clean)
                break
        if len(lines) >= limit:
            break
    return lines


def screenshot(page, png):
    for edge in (Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
                 Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")):
        if edge.exists():
            subprocess.run([str(edge), "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--window-size=1400,6000", "--virtual-time-budget=5000",
                            f"--screenshot={png}", page.as_uri()], check=False, timeout=120)
            return png.exists()
    print("Edge not found, no preview")
    return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="SourceHanSansSC-VF.ttf")
    parser.add_argument("--build", type=int, default=DEFAULT_BUILD,
                        help="build number in the font name; bump it for every build you install")
    parser.add_argument("--neutral", choices=["black", "radical"], default="black",
                        help="color of 'neutral' components: black as in the lesson, or the radical color")
    parser.add_argument("--preview", action="store_true", help="also write preview.png (headless Edge)")
    args = parser.parse_args()

    family = f"Hanzi4Dev Color {args.build}"
    ps_name = f"Hanzi4DevColor{args.build}-Regular"
    out_font = OUT_DIR / f"Hanzi4DevColor{args.build}.ttf"
    OUT_DIR.mkdir(exist_ok=True)

    chars, plain, files = collect_repo_text(REPO_DIR)
    print(f"Repo: {REPO_DIR}\n  {len(files)} text files, {len(chars)} Chinese characters")

    hanzi = json.loads(HANZI_JSON.read_text(encoding="utf-8"))["characters"]
    radicals = load_radicals(DATA_DIR / "unihan/Unihan.zip")
    wanted = set(hanzi)
    mmah_dict = load_jsonl(DATA_DIR / "makemeahanzi/dictionary.txt", wanted)
    mmah_graphics = load_jsonl(DATA_DIR / "makemeahanzi/graphics.txt", wanted)

    print(f"Source: {args.source}\nSubsetting and instancing (wght=400)...")
    font = load_static_subset(args.source, "".join(chars) + "".join(sorted(plain)) + BASE_PLAIN)

    print("Building color layers...")
    layers, report = build_color_layers(font, chars, hanzi, radicals, mmah_dict, mmah_graphics, args.neutral)
    font["COLR"] = buildCOLR(layers, version=0)
    palette = [color for _, color in COLOR_GROUPS] + [color for _, color in ROLE_COLORS]
    font["CPAL"] = buildCPAL([[tuple(int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)) + (1.0,) for c in palette]])
    rename(font, family, ps_name)
    font.save(out_font)

    page = OUT_DIR / "test.html"
    write_test_page(page, out_font.name, family, report, sample_text(files))
    write_report(OUT_DIR / "report.md", family, files, report, radicals)

    check = TTFont(out_font)
    counts = Counter(row["mode"] for row in report)
    print(f"Written: {out_font} ({out_font.stat().st_size // 1024} KB)")
    print(f"  glyphs: {len(check.getGlyphOrder())}, color glyphs: {len(check['COLR'].ColorLayers)}, "
          f"palette entries: {check['CPAL'].numPaletteEntries}")
    print("  " + ", ".join(f"{mode}: {counts[mode]}" for mode, _ in MODES if counts[mode]))
    print(f"Test page: {page}\nReport:    {OUT_DIR / 'report.md'}")
    if args.preview and screenshot(page, OUT_DIR / "preview.png"):
        print(f"Preview:   {OUT_DIR / 'preview.png'}")


if __name__ == "__main__":
    main()
