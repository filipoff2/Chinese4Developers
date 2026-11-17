# Chinese Color Font: Proof of Concept Results

**Status: works.** A color font built from Source Han Sans renders in color in
**Microsoft Word** and **Edge**, including characters split into two colored components.

Spec for the full project: [ChineseColorFontGenerator.md](ChineseColorFontGenerator.md)

---

## 1. What the PoC does

Script: [poc/build_poc_font.py](poc/build_poc_font.py)

1. Loads `SourceHanSansSC-VF.ttf` (variable font from `Downloads\02_SourceHanSans-VF\Variable\TTF`).
2. Subsets it to 10 Chinese characters, plus uncolored ASCII and Chinese punctuation.
3. Pins it to a static Regular instance (`wght=400`).
4. Colors the characters:
   - **One color per character** (5 characters, chosen by radical):

     | Char | Color group |
     | ---- | ----------- |
     | 你 | Royal Purple (亻 person) |
     | 中 | Imperial Gold |
     | 国 | Chinese New Year |
     | 火 | Dragon Fire |
     | 心 | Sakura |

   - **Two components per character** (5 left/right characters): each outline contour goes left
     or right depending on whether its center is left of `split × advance width`:

     | Char | Split | Left | Right |
     | ---- | ----- | ---- | ----- |
     | 好 | 0.48 | 女 Lotus Pink | 子 Porcelain Blue |
     | 妈 | 0.45 | 女 Lotus Pink | 马 Autumn |
     | 休 | 0.36 | 亻 Royal Purple | 木 Bamboo Green |
     | 明 | 0.42 | 日 Imperial Gold | 月 Ice Crystal |
     | 湖 | 0.30 | 氵 Ocean | 胡 Bronze |

5. Builds **COLRv0** (layers) and **CPAL** (one palette, 20 color group entries).
6. Renames the family to `Hanzi Color POC <VERSION>` (required by the Source Han Sans OFL license).
7. Writes the font and an HTML test page.

### Output

| File | Content |
| ---- | ------- |
| `poc/out/HanziColorPOC3.ttf` | The color font (75 KB, 513 glyphs, 10 color glyphs, 20 palette entries) |
| `poc/out/test.html` | Browser test page using the font via `@font-face` |
| `poc/out/preview.png` | Headless Edge screenshot of the test page |

---

## 2. How to run

From `C:\dev\cloude_fun_fonts`:

```bash
python -m venv .venv                 # once
.venv\Scripts\python -m pip install fonttools   # once
.venv\Scripts\python poc\build_poc_font.py [path-to-SourceHanSansSC-VF.ttf]
```

Without an argument the script uses `%USERPROFILE%\Downloads\02_SourceHanSans-VF\Variable\TTF\SourceHanSansSC-VF.ttf`.

### Testing in Word

1. **Bump `VERSION`** in the script before each build you want to install.
2. Close Word completely (no `WINWORD.EXE` left in Task Manager).
3. Right-click the `.ttf` and choose **Install**.
4. Open Word, select the text, press **Ctrl+D**, and set **Asian text font** to `Hanzi Color POC <VERSION>`.
5. Type `你中国火心好妈休明湖`.

---

## 3. Results

| Target | Result |
| ------ | ------ |
| Edge (`@font-face` test page) | Color, both modes (whole and split) |
| Word (Microsoft 365, Windows 11) | Color, both modes, from build 3 on |
| PowerPoint, Chrome | Not tested yet |

Build history:

| Build | Edge | Word | Problem |
| ----- | ---- | ---- | ------- |
| POC 1 | color | black, missing-glyph boxes | Glyph 1 was a color glyph; no space/Latin glyphs |
| POC 2 | color | font not used for Chinese text (fell back to Microsoft JhengHei) | OS/2 code page bits pruned to Latin-1 only |
| POC 3 | color | **color** | none |

---

## 4. Lessons learned (must-haves for the real generator)

1. **Keep the OS/2 code page and Unicode range bits** of the source font.
   The fontTools subsetter recalculates them from the subset by default. With few characters
   CP936 (Simplified Chinese) gets dropped, Word then treats the font as Latin-only and never
   uses it for Chinese text. Fix:

   ```python
   options.prune_codepage_ranges = False
   options.prune_unicode_ranges = False
   ```

   Check: `OS/2.ulCodePageRange1` bit 18 (CP936) must be set (`602e0107` like the source).

2. **Glyph ID 1 must be an empty `.null` glyph.** The COLR spec requires it. Edge rendered
   fine without it, so only Word catches this.

3. **Include uncolored basic glyphs:** space, ASCII and Chinese punctuation. Otherwise Word shows
   missing-glyph boxes (⌧) for spaces and line ends.

4. **Use a new font name for every installed build.** Windows and Office cache fonts by name;
   reusing a name gives stale results, and an installed font file can't be overwritten.

5. **Restart Word after installing a font.** Word reads the font list only on startup.

6. **Word uses separate Latin and Asian fonts.** The ribbon font box mostly sets the Latin font;
   set the **Asian text font** in the Font dialog (Ctrl+D).

7. **One CPAL palette is enough.** All 20 color groups are entries in palette 0, which is what
   Word and browsers use.

8. **Edge passing doesn't mean Word will.** Browsers are more lenient. Always test in Word.

### Technical details

- Layer glyphs must have the **same advance width** as the base glyph (and the same vertical
  metrics, since Source Han Sans has `vmtx`). The script copies `hmtx`/`vmtx` from the base glyph.
- `glyf[name] = glyph` already appends the name to the glyph order; appending it again breaks
  saving (`AssertionError` in `maxp`).
- The source TTF uses `post` format 3, so glyph names aren't stored; `.null` shows up as
  `glyph00001` when the font is reloaded. That's fine.
- Variable source: subset first, then instance (`instancer.instantiateVariableFont`), and drop
  the leftover `STAT` table.

---

## 5. Limits of the PoC

- **The component split is a heuristic:** contours split left/right with a hand-picked ratio per
  character. It works for these 5 left/right characters but not for top/bottom (思),
  enclosing (国) or more complex structures, or for contours that cross the split line.
- Uses the variable SC font, not `01_SourceHanSans.ttc`.
- Only one color per component (no border/highlight layers yet).
- Not yet tested whether an explicit Word font color overrides the font's colors (it was
  `Automatic` in the test).

---

## 6. Next steps

1. **Phase 2:** 2000 most frequent characters, all 20 color groups, sequential assignment.
   Needs a frequency list.
2. **Phase 3:** radical-based assignment from Unihan (`kRSUnicode`).
3. **Component coloring at scale:** a split rule per structure (left/right, top/bottom, enclosing)
   from decomposition data (e.g. CJK decomposition / Make Me a Hanzi), with manual fixes.
4. Test PowerPoint and Chrome; test an explicit font color in Word.
5. Later: border/highlight layers, then the C# .NET 8 UI.
