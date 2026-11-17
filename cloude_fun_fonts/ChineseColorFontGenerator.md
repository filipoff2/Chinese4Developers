# Chinese Color Font Generator

Specification and development process for a tool that turns an existing Chinese font
(e.g. `01_SourceHanSans.ttc`) into an installable multicolor OpenType font.

Distilled from a Copilot chat session. Use it as the starting point for future coding.

---

## 1. Goal

Build a tool that does this:

```text
Input:   C:\Fonts\01_SourceHanSans.ttc
Click:   Generate
Output:  C:\Fonts\ChineseColorFont.otf
```

After installing the font, typing `你好中国` in Word shows each character in color, with the
original Source Han Sans glyph shapes kept.

### Requirements

The generated font must:

- Cover at least the **2000 most frequently used Chinese characters**
- Keep the original glyph outlines, metrics, spacing and baseline
- Keep valid Unicode mappings (`cmap`)
- Color glyphs using **20 predefined color groups**
- Install on **Windows 11** and render in **Microsoft Office (Word, PowerPoint)**, **Edge** and **Chrome**

---

## 2. Original idea: coloring components (radicals)

The first idea was to color the **components** of a character so the user can see its structure:

```text
好 = 女 + 子      女 -> Pink,  子 -> Blue
妈 = 女 + 马
休 = 亻 + 木      亻 -> Purple, 木 -> Green
明 = 日 + 月
湖 = 氵 + 胡      氵 -> Ocean Blue
```

The point is to help users recognize radicals and how characters are built.

> Coloring individual components inside one glyph needs the glyph split into separate
> outline pieces (one layer per component). Source fonts don't ship that split, so it is the
> hardest part. See [7. Technical notes](#7-technical-notes).

---

## 3. Color groups

Twenty color groups (palettes), each with a few colors (base, highlight, border, ...):

| #  | Name             | #  | Name          |
| -- | ---------------- | -- | ------------- |
| 01 | Imperial Gold    | 11 | Ocean         |
| 02 | Chinese New Year | 12 | Sunset        |
| 03 | Jade             | 13 | Royal Purple  |
| 04 | Porcelain Blue   | 14 | Emerald       |
| 05 | Dragon Fire      | 15 | Sakura        |
| 06 | Lotus Pink       | 16 | Autumn        |
| 07 | Bamboo Green     | 17 | Ice Crystal   |
| 08 | Phoenix          | 18 | Galaxy        |
| 09 | Cyberpunk        | 19 | Bronze        |
| 10 | Chrome           | 20 | Rainbow       |

Example definition:

```json
{
  "Name": "Imperial Gold",
  "Colors": [ "#FFD700", "#FFA500", "#B8860B", "#FFF8DC" ]
}
```

---

## 4. Color assignment strategies

### A. Sequential

```text
Glyph 1  -> Group 1
Glyph 2  -> Group 2
...
Glyph 20 -> Group 20
Glyph 21 -> Group 1
```

### B. Unicode range

```text
U+4E00-U+4EFF -> Group 1
U+4F00-U+4FFF -> Group 2
...
```

### C. By radical (preferred)

```text
氵 Water   -> Ocean
火 Fire    -> Dragon Fire
木 Wood    -> Bamboo Green
钅 Metal   -> Imperial Gold
女 Female  -> Lotus Pink
心 Heart   -> Sakura
```

Benefits: the grouping means something, the colors stay consistent across related
characters, and the font looks better.

Needs a character -> radical data source (e.g. Unihan `kRSUnicode`).

---

## 5. Processing pipeline

```text
01_SourceHanSans.ttc
        │
        ▼
   Load font
        │
        ▼
 Select top 2000 characters
        │
        ▼
   Extract glyphs
        │
        ▼
   Assign color group
        │
        ▼
   Generate color layers
        │
        ▼
   Build COLR table
        │
        ▼
   Build CPAL table
        │
        ▼
   Assemble font
        │
        ▼
 ChineseColorFont.otf
        │
        ▼
 Install & test on Windows
```

### Step 1: Load the source font

- Input formats: `.ttc`, `.ttf`, `.otf`
- A `.ttc` is a collection, so pick the right face (e.g. SC Regular)
- Read metadata, glyph count, Unicode mappings and tables:
  `cmap`, `head`, `hhea`, `hmtx`, `name`, `OS/2`, `glyf` or `CFF`/`CFF2`
- Output: a loaded font object

### Step 2: Select the characters

- Use a frequency list of the top 2000 most common Chinese characters
- Examples: `的 一 是 不 了 人 我 在 有 他 这 中 大 来 上 国 个 到 说 们`
- Output: `List<UnicodeCodePoint>`

### Step 3: Extract the glyph data

For each character: `Unicode -> Glyph ID -> Outline`

- Extract the outline, advance width, bearings and metrics
- Keep the shape, spacing and baseline

### Step 4: Define the color palettes

- Load the 20 color groups (JSON config)
- Output: `PaletteCollection`

### Step 5: Assign colors

- Apply strategy A, B or C (section 4)
- Output: a glyph -> color group mapping

### Step 6: Create the color layers

For each glyph, build the layers from the original outline:

```text
Layer 1 = Base fill
Layer 2 = Highlight
Layer 3 = Border
```

Example: `国` could get a gold border, a red fill and an orange highlight.

Output: colorized glyph layers

### Step 7: Build the COLR table

Store the base glyph ID, the layer glyph IDs, the layer count and order, and the
palette entry index for each layer.

### Step 8: Build the CPAL table

Store the color definitions (see the CPAL note in section 7).

### Step 9: Assemble the font

- Combine the original tables, the subsetted glyph data, `COLR` and `CPAL`
- Keep the Unicode mappings, metrics, kerning and widths
- Rename the font family (see the license note)
- Write `ChineseColorFont.otf`

### Step 10: Validate

- The font installs correctly on Windows 11
- Rendering in Word, PowerPoint, Edge and Chrome
- Check character rendering, Unicode coverage, font loading and color rendering

### Step 11: Optimize

- Subset glyphs (only the selected characters plus required ones)
- Reuse palettes and layers
- Optimize COLR
- Goal: smaller file, less memory, faster loading

---

## 6. Technology

### Why not pure C#

.NET has no built-in library that can build a COLR/CPAL font from a TTC. Writing a font
engine from scratch in C# would take thousands of lines. The usual tools are:

- **FontTools** (Python): reads and writes all OpenType tables, `fontTools.colorLib` builds COLR/CPAL
- **nanoemoji**: builds color fonts from SVGs
- FontForge, FontLab

### Options discussed

| Option | Description | Real installable font? |
| ------ | ----------- | ---------------------- |
| A | C# UI wrapper around Python FontTools/nanoemoji | Yes |
| B | Pure C#, exports 2000 colored SVG/PNG glyphs | No (images only) |
| **C** | **C# (.NET 8) front end + bundled Python scripts, one-click build** | **Yes, recommended** |

### Recommended setup (option C)

- **Front end:** C# .NET 8, where the user picks the source font path, the output path and the color strategy
- **Font processing:** Python + FontTools (`colorLib`, `subset`), optionally nanoemoji
- **Imaging (if needed for previews):** SkiaSharp instead of `System.Drawing`

### Lessons from the session

- The first generated ZIP was an empty stub. Don't accept a "project" without real font processing in it.
- Make the font-building part work first (a Python script that produces a valid colored `.otf`
  for a few characters), then add the C# UI.

---

## 7. Technical notes

- **CPAL palettes vs. color groups:** CPAL can hold several palettes, but most apps
  (Office, browsers) only use **palette 0**. The 20 color groups should therefore be
  **entries in one palette** (20 groups x ~4 colors), with each glyph's layers pointing at
  its group's entries. Extra CPAL palettes are only alternative themes.
- **COLRv0 vs. COLRv1:** COLRv0 means flat colored layers and has the widest support (Windows,
  Office, browsers). COLRv1 adds gradients but has weaker support in Office. Start with **COLRv0**.
- **Layers need separate outlines:** each COLR layer is its own glyph outline. A single-color
  glyph is easy (one layer = the original outline). Fill + border + highlight, or one color
  per radical, needs extra outlines: offset/stroke paths for borders, or splitting a character
  into its components (stroke/component data such as CJK decomposition sets or a manual split).
- **Outline format:** Source Han Sans uses CFF outlines (OTF/OTC). Decide whether to keep CFF
  or convert to TrueType `glyf` (simpler with FontTools `colorLib` + TTF output).
- **License:** Source Han Sans uses the SIL Open Font License with **Reserved Font Names**.
  A modified font must **not** use the name "Source Han Sans" and must be renamed
  (`name` table) before distribution.
- **Office support:** check early that COLR/CPAL fonts render in color in the installed Office
  version. This is the riskiest assumption.

---

## 8. Final deliverable

| Item     | Value |
| -------- | ----- |
| Input    | `C:\Fonts\01_SourceHanSans.ttc` |
| Output   | `C:\Fonts\ChineseColorFont.otf` |
| Content  | 2000+ Chinese characters, 20 color groups |
| Format   | OpenType with COLR/CPAL |
| Targets  | Windows 11, Office, Edge, Chrome |

---

## 9. Suggested next steps

1. Python proof of concept: subset 10 characters, give each one a COLRv0 layer in one color, check it in Word and Edge.
2. Add the 20-group palette and sequential assignment, then scale to 2000 characters.
3. Add radical-based assignment (Unihan data).
4. Add multi-layer effects (border/highlight) or component coloring.
5. Wrap it in the C# .NET 8 UI with a one-click build.
