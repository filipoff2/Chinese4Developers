"""Build a COLRv0/CPAL color font for every Chinese character used in this repo.

Characters: every CJK character found in the repo's text files (.md, .json, .txt and files
without extension; the cloude_fun_fonts folder is skipped). Other characters in those files
(Latin, pinyin, punctuation) are kept uncolored.

Coloring (--scheme components, the default): the goal is to see the parts of a character.
  - Every character is split into its top-level parts (Make Me a Hanzi decomposition, e.g.
    想 = 相 + 心). The Source Han Sans outline pieces are assigned to the parts with the
    Make Me a Hanzi stroke data.
  - Each part gets the color of that component, the same everywhere: radicals (心 忄 亻 氵 ...)
    their meaning-based group, other components a fixed group of their own. If two parts of
    one character would get the same color, the non-radical part moves to the next color.
  - Characters with one part, or whose outline can't be split cleanly, get one color.

--scheme roles: the earlier coloring. hanzi-120.json characters in the lesson's role colors
(semantic / phonetic / neutral), all others one color by radical.

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
import zlib
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

GROUP_COLOR = dict(COLOR_GROUPS)

# Component split: sample grid (font units) and the minimum share of votes one part needs for
# an outline piece (0 = the majority always wins; low shares are listed in report.md).
GRID_STEP = 12
MIN_SHARE = 0.0
# Minimum color distance between different parts of one character (see color_distance).
MIN_CONTRAST = 160
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
    """Unihan kRSUnicode: character -> (Kangxi radical number, additional strokes), first value."""
    radicals = {}
    with zipfile.ZipFile(zip_path) as archive:
        for name in archive.namelist():
            for line in archive.read(name).decode("utf-8").splitlines():
                if "\tkRSUnicode\t" not in line:
                    continue
                code, _, value = line.split("\t")
                match = re.match(r"(\d+)'*\.(-?\d+)", value)
                radicals[chr(int(code[2:], 16))] = (int(match.group(1)), int(match.group(2)))
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


def mmah_parts(char, mmah_dict):
    """Top-level parts of a character from Make Me a Hanzi, or None if it has none."""
    info = mmah_dict.get(char)
    if not info:
        return None
    tree, _ = parse_ids(info["decomposition"])
    if isinstance(tree, str):
        return None
    return [flatten(child) for child in tree[1]]


def map_json_components(components, parts):
    """hanzi-120.json component index -> Make Me a Hanzi part index: same glyph first, rest in order."""
    if len(parts) != len(components):
        raise SplitFailed(f"decomposition has {len(parts)} parts, hanzi-120.json has {len(components)}")
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
    return mapping


def split_parts(char, parts, mmah_dict, mmah_graphics, contours, glyph_set):
    """Assign the glyph's outline pieces to the character's top-level parts.

    Returns ({part index: [contours]}, lowest vote share).
    """
    info, graphics = mmah_dict.get(char), mmah_graphics.get(char)
    if not info or not graphics:
        raise SplitFailed("no Make Me a Hanzi data")

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
    return pieces, lowest_share


def component_group(component, radicals):
    """Color group of a component: the same component always gets the same color.

    Components that are radicals themselves (Unihan: radical + 0 strokes, e.g. 心 忄 亻 氵)
    use the radical's group; all others get a fixed group derived from the component.
    """
    if "？" in component:
        return "Chrome", False
    for form in (component, canonical(component)):
        radical = radicals.get(form)
        if radical and radical[1] == 0:
            return group_for_radical(radical[0])[0], True
    return COLOR_GROUPS[zlib.crc32(canonical(component).encode()) % len(COLOR_GROUPS)][0], False


def color_distance(a, b):
    """'Redmean' RGB distance between two group colors (0 = same, ~765 = black/white)."""
    (r1, g1, b1), (r2, g2, b2) = ([int(GROUP_COLOR[g][i:i + 2], 16) for i in (1, 3, 5)] for g in (a, b))
    mean = (r1 + r2) / 2
    return ((2 + mean / 256) * (r1 - r2) ** 2 + 4 * (g1 - g2) ** 2
            + (2 + (255 - mean) / 256) * (b1 - b2) ** 2) ** 0.5


def part_groups(parts, radicals):
    """Groups for the parts of one character.

    Different parts must be clearly different colors (MIN_CONTRAST); a part whose color is too
    close to an earlier part's moves on to the next group. Radical parts go first, so they keep
    their color; the same component twice (林 = 木 + 木) keeps one color.
    """
    wanted = [component_group(part, radicals) for part in parts]
    groups = [None] * len(parts)
    chosen = []  # (group, component)
    for i in sorted(range(len(parts)), key=lambda i: not wanted[i][1]):
        component = canonical(parts[i])
        index = GROUP_INDEX[wanted[i][0]]
        for _ in range(len(COLOR_GROUPS)):
            group = COLOR_GROUPS[index][0]
            if all(c == component or color_distance(group, g) >= MIN_CONTRAST for g, c in chosen):
                break
            index = (index + 1) % len(COLOR_GROUPS)
        chosen.append((group, component))
        groups[i] = group
    return groups


def build_color_layers(font, chars, hanzi, radicals, mmah_dict, mmah_graphics, scheme, neutral_mode):
    cmap = font.getBestCmap()
    glyph_set = font.getGlyphSet()
    layers, report = {}, []

    def radical_layer(char, base):
        radical = radicals.get(char)
        if radical is None:
            group, how = COLOR_GROUPS[ord(char) % len(COLOR_GROUPS)][0], "no radical data"
        else:
            group, mapped = group_for_radical(radical[0])
            how = f"radical {radical[0]} {chr(0x2F00 + radical[0] - 1)}" + ("" if mapped else " (default group)")
        layers[base] = [(base, GROUP_INDEX[group])]
        return group, how

    def role_index(char, role):
        if role == "neutral" and neutral_mode == "radical":
            group, _ = group_for_radical(radicals.get(char, (1, 0))[0])
            return GROUP_INDEX[group]
        return ROLE_INDEX[role]

    def add_layers(base, pieces, colors):
        layer_list = []
        for i, (contours, color) in enumerate(zip(pieces, colors)):
            name = f"{base}.p{i}"
            add_glyph(font, name, contours, base)
            layer_list.append((name, color))
        layers[base] = layer_list

    for char in chars:
        base = cmap.get(ord(char))
        if base is None:
            report.append({"char": char, "mode": "missing", "note": "not in source font"})
            continue
        parts = mmah_parts(char, mmah_dict)

        if scheme == "roles":
            entry = hanzi.get(char)
            if entry and len(entry["components"]) == 1:
                role = entry["components"][0]["role"]
                layers[base] = [(base, role_index(char, role))]
                report.append({"char": char, "mode": "single", "note": f"{role} (hanzi-120.json)"})
                continue
            if not entry:
                group, how = radical_layer(char, base)
                report.append({"char": char, "mode": "radical", "note": f"{group} by {how}"})
                continue
            try:
                if not parts:
                    raise SplitFailed("no decomposition")
                mapping = map_json_components(entry["components"], parts)
                pieces, share = split_parts(char, parts, mmah_dict, mmah_graphics,
                                            glyph_contours(glyph_set, base), glyph_set)
            except SplitFailed as failure:
                group, how = radical_layer(char, base)
                report.append({"char": char, "mode": "fallback", "note": f"{failure}; {group} by {how}"})
                continue
            components = entry["components"]
            add_layers(base, [pieces[mapping[i]] for i in range(len(components))],
                       [role_index(char, c["role"]) for c in components])
            note = ", ".join(f"{c['glyph']} {c['role']}" for c in components)
            report.append({"char": char, "mode": "parts", "note": f"{note} (lowest share {share:.0%})"})
            continue

        # scheme == "components": every part in its own component color.
        # Radicals themselves (氵 讠 月 ...) and characters without known parts stay whole.
        is_radical = radicals.get(char, (0, -1))[1] == 0
        if not parts or is_radical or all("？" in p for p in parts):
            group, mapped = component_group(char, radicals)
            layers[base] = [(base, GROUP_INDEX[group])]
            report.append({"char": char, "mode": "single", "note": f"{group} (component {char})"})
            continue
        try:
            pieces, share = split_parts(char, parts, mmah_dict, mmah_graphics,
                                        glyph_contours(glyph_set, base), glyph_set)
        except SplitFailed as failure:
            group, how = radical_layer(char, base)
            report.append({"char": char, "mode": "fallback",
                           "note": f"{'+'.join(parts)}: {failure}; {group} by {how}"})
            continue
        groups = part_groups(parts, radicals)
        add_layers(base, [pieces[j] for j in range(len(parts))], [GROUP_INDEX[g] for g in groups])
        note = ", ".join(f"{p} {g}" for p, g in zip(parts, groups))
        report.append({"char": char, "mode": "parts", "note": f"{note} (lowest share {share:.0%})"})

    return layers, report


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

MODES = [
    ("parts", "Split into parts, each part in its own color"),
    ("single", "One part only: one color"),
    ("fallback", "Split failed: one radical color"),
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
    parser.add_argument("--scheme", choices=["components", "roles"], default="components",
                        help="components: split every character, each part in its own color (default); "
                             "roles: lesson role colors for hanzi-120.json, radical color for the rest")
    parser.add_argument("--neutral", choices=["black", "radical"], default="black",
                        help="roles scheme only: color of 'neutral' components")
    parser.add_argument("--min-share", type=float, default=MIN_SHARE,
                        help="minimum share of one part in an outline piece; below that the character "
                             f"stays one color (default {MIN_SHARE})")
    parser.add_argument("--preview", action="store_true", help="also write preview.png (headless Edge)")
    args = parser.parse_args()
    globals()["MIN_SHARE"] = args.min_share

    family = f"Hanzi4Dev Color {args.build}"
    ps_name = f"Hanzi4DevColor{args.build}-Regular"
    out_font = OUT_DIR / f"Hanzi4DevColor{args.build}.ttf"
    OUT_DIR.mkdir(exist_ok=True)

    chars, plain, files = collect_repo_text(REPO_DIR)
    print(f"Repo: {REPO_DIR}\n  {len(files)} text files, {len(chars)} Chinese characters")

    hanzi = json.loads(HANZI_JSON.read_text(encoding="utf-8"))["characters"]
    radicals = load_radicals(DATA_DIR / "unihan/Unihan.zip")
    wanted = set(chars) | set(hanzi)
    mmah_dict = load_jsonl(DATA_DIR / "makemeahanzi/dictionary.txt", wanted)
    mmah_graphics = load_jsonl(DATA_DIR / "makemeahanzi/graphics.txt", wanted)

    print(f"Source: {args.source}\nSubsetting and instancing (wght=400)...")
    font = load_static_subset(args.source, "".join(chars) + "".join(sorted(plain)) + BASE_PLAIN)

    print("Building color layers...")
    layers, report = build_color_layers(font, chars, hanzi, radicals, mmah_dict, mmah_graphics,
                                        args.scheme, args.neutral)
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
