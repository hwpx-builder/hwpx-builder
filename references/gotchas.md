# HWPX Gotchas

The real asset of this project. Every entry cost a debugging cycle. Add to it
whenever a render breaks. ✅ = verified on this machine, 📋 = from source
analysis, ⚠️ = known-unverifiable here.

---

## Highlighter pen (형광펜)

✅ **Highlight is a pair of empty tags inside `<hp:t>`, not a run attribute.**

```xml
<hp:run charPrIDRef="53"><hp:t><hp:markpenBegin color="#FFFF00"/>지역 고유성:</hp:t></hp:run>
<hp:run charPrIDRef="29"><hp:t><hp:markpenEnd/> 충주 수안보는 ...</hp:t></hp:run>
```

✅ **`charPr/@shadeColor` is NOT a highlighter.** It renders as shading (음영).
`python-hwpx`'s `ensure_run_style(highlight=...)` does exactly this
(`oxml/document_parts.py:110`), so it is the wrong tool. In the 온리브 sample 159
of 162 `shadeColor` values are `none` — real documents do not use it for emphasis.

✅ **The begin/end pair may straddle runs.** `markpenEnd` commonly opens the
*next* run rather than closing the current one. Highlight range and run boundaries
are independent, which is what naive text replacement breaks. We author the
self-contained form (both tags in one `<hp:t>`) so a pair can never be orphaned.

✅ **Highlighted text disappears from `paragraph.text`.** The text moves to the
`.tail` of `markpenBegin`, and `HwpxOxmlParagraph.text` reads only `<hp:t>.text`.
Use `hwpxkit.richtext.paragraph_text()` when verifying.

⚠️ **No renderer available here shows markpen.** A/B confirmed: removing all 31
markpen tags from 온리브 produced byte-identical SVG output from rhwp. Highlight
correctness can only be checked at the XML level.

---

## Editing an existing file

✅ **`doc.paragraphs` does not reach table content.** 온리브: 13 top-level
paragraphs, 26 tables, and all 7 occurrences of "온리브" inside cells.
`replace_text_in_runs("온리브", …)` therefore replaced **0** of them;
`hwpxkit.edit.replace_text` replaces 7/7. Same file: `get_table_map()` returned 0
tables against 26 from the cell walker, and `find_cell_by_label("팀명")` returned
`{'matches': [], 'count': 0}` where `find_label` returns the value cell.

✅ **A nested `<hp:tbl>` lives inside an `<hp:run>`.** Clearing a paragraph's runs
to blank it deletes the sub-table and its images with it. First version of
`set_cell` did exactly that: five nested grids vanished and `binary refs` fell
from 6 to 3. The symptom in the baseline diff is bizarre — sixteen unrelated
paragraphs reported as "changed", because every table index downstream shifted.
Skip paragraphs where `has_nontext_runs()` is true.

✅ **배포 양식의 안내문은 색이 입혀져 있다. 그대로 채우면 본문이 파랗게 나온다.**
실측한 정부 배포 서식(사업계획서)의 안내문 칸은 `charPr` 의 `textColor` 가
`#0000FF` 였다. `set_cell(..., keep_style=True)` 는 크기·글꼴과 함께 **이 색까지**
물려받으므로, 안내문 자리를 채운 제출 문서의 본문이 전부 파란색이 된다. 양식 첫
장에 "안내문과 음영은 삭제하고 제출" 이라고 적혀 있는 바로 그 안내문이다.
크기·글꼴은 양식을 따르되 색만 되돌리려면 `set_cell(..., color="#000000")` 을 쓴다
(`derive_char_pr(..., color=…)` 로 내려간다). `keep_style=False` 로 꺼 버리면 색은
해결되지만 양식의 글자 크기(12 pt)까지 잃는다.

✅ **`ensure_run_style(base_char_pr_id=…)` does not derive from the base.** Its
predicate matches on the requested attributes alone. Asked for a bold variant of
charPr 28 (height 1200, fontRef 3) it returned the pre-existing charPr 4 (height
1000, fontRef 5, DROP shadow) — an edited cell silently changes size, typeface and
shadow. `derive_char_pr()` pins height/colour/font to the base in the predicate
and clones through `header.ensure_char_property(modifier=…)`, which does honour
the base.

✅ **`id(element)` is not a usable identity for lxml nodes.** lxml builds a fresh
proxy on every access; the proxy is freed as the loop moves on and CPython reuses
the address, so a `{id(p.element)}` visited-set reports unrelated later paragraphs
as already seen. This silently made `replace_text` skip all 7 matches while the
same call on one paragraph worked. Hold a reference to every element you record
(`_VisitedSet` does), or do not dedup at all.

✅ **A replacement containing its own search string loops forever** if the scan
restarts at 0 after each hit ("사업" → "사업(수정)"). Resume from `at + len(new)`.

📋 **A replacement spanning a markpen boundary orphans the pair.** Begin/end are
independent of run boundaries, so a match can start before `markpenBegin` and end
after it; rewriting across it leaves an unclosed highlight. `replace_in_paragraph`
detects this (`tail` slot whose holder is a markpen tag) and records it in
`EditReport.conflicts` instead of writing.

---

## Layout cache (`<hp:linesegarray>`)

✅ **The built-in layout engine's accuracy claims are measured, not hoped.**
`hwpxkit.preview` lays out with calibrated `form_fit` line counts + declared
table/picture geometry. Verified against Hangul 2010 openings: 강아지 4=4,
제목줄반복 4=4, 온리브 6=6 pages exact; U300 +1 conservative. Two rules made
that possible: trust the *declared* row heights of Hancom-saved documents for
text (estimating them inflated 6-page docs to 8-10), but add cell-content
estimates for images/nested tables, which Hancom does **not** fold into
declared heights (a 13-image document carried two pages of pictures invisible
to declared geometry). PDF page size must come from the document's own pagePr,
and Chrome's @page print CSS reproduces the pagination exactly (4쪽 조판 →
4-page A4 PDF).

✅ **rhwp largely replays this cache instead of laying out text.** Stripping every
`linesegarray` from 온리브 changed rhwp's page count 6→5 and pushed glyphs further
off-page. Consequence: **rhwp cannot judge line breaking or page count on a
freshly generated document**, which has no cache at all. Long cell text will
render as one overlapping line even when the file is correct.

✅ **When editing existing text, drop the cache for exactly the paragraphs you
touched.** Stale `textpos` makes Hancom render new text into old line slots →
overlapping glyphs. `python-hwpx`'s own mutating APIs do this (a
`replace_text_in_runs` edit took the sample from 362 `linesegarray` blocks to
361), but **`hwpxkit.set_spans` does not** — authored paragraphs never have a
cache, so it never needed to. Every function in `hwpxkit.edit` drops it, and
`verify(..., baseline=…)` fails the file if a changed paragraph kept one.

📋 **Do not strip every cache document-wide.** That forces Hancom to re-lay-out
untouched pages, which shifts page counts and stacks glyphs — the opposite of the
intended fix.

---

## Tables

✅ **`cell.width` is a read-only property.** Assigning to it raises. Use
`cell.set_size(width=...)`. A bare `try/except` around the assignment silently
leaves every column at the 7200 default, and the only symptom is text running
past the drawn border.

✅ **Declare width on the table *and* every cell.** If they disagree, the drawn
border and the text-wrapping width diverge. Same dual-width trap as DOCX.

✅ **New tables do not grow to fit content.** Rows keep a fixed height, so long
text overflows and rows overlap. `hwpxkit.autofit()` sizes rows from
`hwpx.form_fit.measure` line counts; run it after filling any table.

✅ **Column widths must sum to the table width**, and the table width to the body
width (`page − 2×margin` = 48190 for the U300 A4/20 mm layout). Use
`units.split_width()`, which puts the rounding remainder in the last column.

📋 **Nesting depth is 2 in practice.** Both samples top out there. Depth 3 is
unattested and untested — do not emit it.

✅ **`repeatHeader="1"` on `<hp:tbl>` alone repeats nothing.** Hancom repeats
only rows whose cells carry `header="1"` — both real samples ship
`repeatHeader="1"` with zero header cells marked, so no row repeats. Use
`set_repeat_header(table)` (or `content_table(..., repeat_header=True)`), which
sets both flags. Page splitting itself is separate: `pageBreak="CELL"` is the
default but is inert while the table is 글자처럼 취급 — see the treatAsChar
gotcha; `make_splittable()` (applied by the builders) is what actually lets
pages break through. Generated tables already
carry `pageBreak="CELL"` (여러 쪽 지원 — 셀 단위로 나눔), but a table nested
inside a cell never splits, and no renderer here paginates a fresh file —
Hancom does on open.

✅ **Real forms merge cells; the builder never does.** 26 merged cells in 온리브,
34 in U300 (`cellSpan` up to `rowSpan="8"`). `autofit`'s "row height = max cell
height in that row" model does not hold there: on an untouched 온리브 table it took
a row from 16980 to 124354 HWPUNIT. Declared cell heights in a real document do
not even sum to the table's own `<hp:sz>` (39050 vs 29065), because a merged
cell's height spans rows. **Never autofit a table you did not build** — drop the
layout cache and let Hancom re-flow. `refit_cell()` reports the shortfall and
refuses to resize a merged table.

---

## Images

✅ **Without Pillow every picture silently becomes 4:3 — distortion and
phantom margins.** `BoxDoc.picture` derives display height from the real image
aspect via Pillow, and falls back to 3:4 when it is missing (`images` extra).
The failure is invisible at build time: a landscape 3:2 dog photo and a
portrait 5:6 cat photo both got identical 4:3 frames, so Hangul showed the dog
with blank bands inside its frame and the two "same-size" pictures looked
wildly different. If sample pictures look distorted or letterboxed, check
`python -c "import PIL"` in the venv that built them before debugging XML.

✅ **Balance comparison pictures by height, not width.** A landscape and a
portrait photo given the same `width_mm` differ almost 2× in displayed area.
Side-by-side subjects read as equals only when their *heights* match — pick
each `width_mm` as `target_height_mm / (img_h/img_w)`. `gapfit` groups a
comparison series by width **or** height matching within tolerance, so
height-balanced pairs still shrink together.

✅ **A picture taller than the remaining page space leaves a page-bottom gap.**
Pictures cannot split at a page boundary the way cell-split tables do: Hangul
pushes the whole object to the next page and the previous page keeps the
leftover space as blank. `gapfit.fit_pictures` simulates the layout
arithmetically (calibrated `form_fit.measure` line counts + declared
table/picture heights) and shrinks only pictures whose push-gap exceeds the
threshold (default 12% of body height), keeping aspect and never going below
55% of the original — a too-small picture is worse than the gap. Pictures with
the same original width form a comparison series and are always scaled
together by one factor: shrinking only the pushed one leaves siblings visibly
mismatched, which readers notice before they notice the gap. If the group
cannot fit above the floor, nobody shrinks. It rescales
display size only (`sz`/`curSz`/`imgRect`); `orgSz`/`imgDim`/`imgClip` live in
original-image space and touching them corrupts the crop after `.hwp` export.

✅ **python-hwpx saves by patching: mutate an element directly and the change
is silently discarded.** Untouched parts are rewritten from their original
bytes, so an edit made straight on `section.element` (bypassing python-hwpx's
own mutating APIs) never reaches the file — the saved copy still shows the old
values while the in-memory tree shows the new ones, which is maximally
confusing. Call `section.mark_dirty()` after any direct element mutation;
every function in `hwpxkit.edit` and `gapfit` does.


✅ **The "six geometry values" worry is overstated.** `python-hwpx`'s
`_create_picture_element()` writes `sz`/`orgSz`/`curSz`/`imgRect`/`imgClip`/
`imgDim` as the **same HWPUNIT value**, and those files open in real Hancom
12.30. For an uncropped image there are not two unit systems. Use `add_picture`;
do not hand-build `<hp:pic>`.

📋 **`binaryItemIDRef` must resolve three ways**: the reference, the `BinData/`
entry, and the manifest registration. `verify.check_binary_refs` checks this.

**Never invent a missing image.** Emit a labelled placeholder.

---

## Units

✅ 1 inch = 7200 HWPUNIT, **1 pt = 100**, 1 mm ≈ 283.46. Font height shares the
unit, so 10 pt text is `height="1000"`.

✅ **Line spacing is a percent, not HWPUNIT.** Hancom's default is 160%, so a line
occupies ~1.6 em.

✅ A4 = 59528 × 84188. U300 margins: 20 mm sides, 10 mm top/bottom → body 48190.

---

## Text and structure

📋 **List markers (`□ · ❶ ▪ ※`) are literal characters**, not auto-numbering.
Whitelist them for detection; emit them as plain text.

📋 **Bold alone does not identify a heading** — body text uses bold for emphasis.
A heading is `bold AND height > mode(height)`. Body size is the modal 1000 (10 pt)
in both samples.

📋 **Style ids are renumbered per document.** Never carry a `charPrIDRef`,
`borderFillIDRef` or `paraPrIDRef` across files. Classify by shape.

📋 `<hp:lineBreak/>` vs. new paragraph is author-dependent: 65 uses in U300, zero
in 온리브. Do not assume either.

✅ **`HwpxDocument.new()` wraps Korean at any character (`BREAK_WORD`); Hancom
forms use `KEEP_WORD` for body text.** Measured: U300's body paraPr (115+39+38
paragraphs) and 양식's are `KEEP_WORD`; only label/heading paraPr are
`BREAK_WORD`. Authored files had all 208 paragraphs on the skeleton's single
`BREAK_WORD` paraPr, so narrow cells broke "실험" into "실 / 험". The user first
saw it in Polaris Office, whose substitute fonts move the break points. `BoxDoc`
now applies `keep_korean_words()` at construction, and
`hwpxkit.wrap.estimate_lines(keep_words=)` replaces
`hwpx.form_fit.measure.estimate_lines` (character-level only) wherever a row
height or page count is computed — word-level wrapping needs more lines, and a
viewer that trusts declared heights clips the last one. Character-level results
are identical to python-hwpx's. Polaris rendering itself: ⚠️ not reproducible
here (not installed) — keep the screenshot + file if it recurs.

📋 **Prose review is a verify() check now.** It fails on `FIX` findings from
`hwpxkit.prose` (clichés, unquantified claims, hedges, no/too-much emphasis,
over-long sentences). Calibrated on the three examples plus one real submission:
label rows, headings, captions, citation/contact cells and short-line label
blocks are exempt — without that every grey label row came back as "100% 강조".
Thresholds: sentence 100 chars, 개조식 line 150, emphasis ratio 0.5, highlights
per cell 2. Nested `**` inside `==…==` prints literal asterisks: the markup parser
is flat, write `**==…==**` or keep the highlight plain.

---

## Packaging

✅ **`mimetype` must be the first ZIP entry and stored uncompressed** (ODF
convention). Checked by `verify.check_package`.

📋 Encrypted HWPX and HWP 5.x binary are rejected, not silently mishandled.

---

## Environment

✅ **Hangul 2010 cannot parse HWPX, but `Open()` still returns `True`.** It opens
the ZIP as a text file: `SaveAs(...,"HTML")` yields `<TITLE>PK</TITLE>`,
`PageCount` returns 3311 for a 6-page document, PDF export never completes. A
gate built on it is a silent-pass generator. Needs Hangul 2014+.

## HWPX → HWP conversion (hwp_export + hwpConverter)

✅ **Detect HWPX capability from `hwp.Version`, never by opening a probe file.**
A probe HWPX on Hangul 2010 chews the ZIP as text past any sane timeout; killing
the stuck PowerShell leaves hwp.exe alive holding a document, and every later
COM launch then blocks on the recovery dialog — one bad probe poisoned two
subsequent runs. `$hwp.Version` answers instantly (`8,0,0,466` = 2010; major ≥ 9
= 2014+ = HWPX-capable). `hwp_export._run_com` also kills any hwp.exe it
spawned when a call times out.

✅ **This COM interface has no 1-arg `Open()` overload.** PS 5.1 late binding
fails with "인수 개수 1"; call `Open(path, "", "")` and `SaveAs(path, "HWP", "")`.

✅ **Hangul 2010's HTML import assumes EUC-KR regardless of the charset meta.**
UTF-8 HTML arrives as mojibake, and CP949 lead bytes swallow the `<` of closing
tags, so raw `</td>` fragments leak into the document text. `hwp_export` encodes
the HTML as CP949 with `xmlcharrefreplace` before handing it to COM — after
that, a 162-token document round-tripped at 100% coverage.

✅ **The COM routes are inherently fragile on Hangul 2010 — prefer the jar.**
After one timed-out COM call was killed, every later COM `Open()` on this
machine hung on files that had opened fine minutes earlier, surviving process
kills, with no recovery `.asv` files or registry entries to clear (cause never
found). vsdn/hwpConverter (Apache-2.0, Java, on hwplib/hwpxlib) converts
HWPX→HWP with no Hancom at all and preserved 100% of text tokens, all tables
as real table controls, and images as embedded pictures on both test
documents — far better than the HTML route, which wrecks layout. Caveats: it
writes HWP v5.1.1.0 (whether Hangul 2010 itself opens that is unverified —
COM was wedged; check by hand), and the project is young (5 commits), so keep
the coverage verification on.

✅ **HWP binary 형광펜 = PARA_RANGE_TAG sort=2, data=24-bit BGR.** The public
5.0 spec (표 63) defines the record but never enumerates the kind values, and
no open-source parser (hwplib, pyhwp, hwp-rs, hwp2hwpx) maps it. Ground truth
came from driving Hangul 2010 itself: `CreateAction("MarkPenShape")` +
`SetItem("Color", 65535)` on a new document (COM `Open()` was wedged but
document *creation* still worked), then decoding the saved .hwp:
`#FFFF00` → `0x0200FFFF` (sort 2, BGR `00FFFF`). Positions are WCHAR indices
into the full paragraph text **including 8-WCHAR extended control chars**,
end-exclusive. Stock hwpConverter dropped markpen entirely; our patch
(`patches/hwpconverter-fixes.patch`, applied in `ref/hwpConverter`) parses
`hp:markpenBegin/End` inside `hp:t` and emits the range tags — 10/10 markpen
runs survived on the 햄스터 document. Re-cloning the repo loses the patch:
re-apply it and rebuild before trusting markpen output.

✅ **A 글자처럼 취급(treatAsChar) table NEVER splits at a page boundary,
whatever `pageBreak` says.** Hangul lays an inline table out as one giant
"character", so `pageBreak="CELL"` is inert and the table is pushed whole to
the next page, leaving the big gap the user kept reporting. This was the true
root cause — the split-mode bits were a second, independent bug. Proof by
A/B on the same converted document in Hangul 2010: flipping only the
CTRL_HEADER treatAsChar bit took it from 5 pages (gap) to 4 (flowing).
Hancom-authored forms and Hangul's own TableCreate both emit top-level tables
with treatAsChar=0 (자리 차지) — but python-hwpx and pyhwpxlib both hardcode
`treatAsChar="1"`. Fixed in two layers: `boxdoc.make_splittable()` (applied
by every top-level builder) sets `hp:pos treatAsChar="0"` at authoring time,
and the hwpConverter patch clears the bit for depth-1 tables whose pageBreak
is not NONE. Nested tables stay inline — a table inside a cell genuinely
cannot split.

✅ **HWP binary table split mode: NONE=0, TABLE=1, CELL=2 — and the official
spec's own table is wrong.** Spec 표 76 lists bits 0-1 as "0 나누지 않음 /
1 셀 단위로 나눔 / 2 나누지 않음" (value 2 duplicated, clearly a typo).
Reality, from the Hancom-authored 양식.hwp ↔ its own .hwpx pair: binary 2 ↔
`pageBreak="CELL"`. hwpConverter followed the spec (CELL→1) and Hangul 2010
then pushed every table whole onto the next page, leaving the "big gap before
the table" the user first reported. Fixed in `parsePageBreakType`
(NONE→0, TABLE→1, CELL→2, same patch file). When a converted table refuses to
split across pages, read bits 0-1 of the first UINT32 of HWPTAG_TABLE (tag
77): it must be 2.

✅ **HWP binary picture crop is in image-pixel space (px × 75), not display
space.** HWPX's `hp:imgClip` is relative to `hp:imgDim`, and python-hwpx
writes all six geometry values as the same display HWPUNIT (28346 = 100mm).
Copy that crop into the binary verbatim and Hangul interprets it against the
image's *natural* size — a 1280×783px picture displayed at 28346×17340 shows
only its top-left ~30% ("사진이 짤려 있어"). Hangul 2010 ground truth: crop
right = 1280×75 = 96000 regardless of display size (96dpi, 1px = 75 HWPUNIT).
Fix in the same patch: `fixPictureCropSpace` decodes the PNG/JPEG/GIF/BMP
header for real pixel dims and rescales the crop from imgDim space; the
display rect stays in display space.

✅ **hwpConverter wrote dangling picture binItemIDs — images silently blank.**
Its reader renumbers BinData streams sequentially from 1 (`BIN0002.png` in
the HWPX becomes stream `BIN0001.png`, DocInfo ID 1) but the picture record
keeps the numeric suffix of the original reference (`binaryItemIDRef=
"BIN0002"` → binItemID 2). Hangul finds no bin item 2 and draws nothing —
every other byte of the picture chain was correct, so text checks all pass.
Sections parse *before* BinData extraction, so the fix is a post-pass
(`remapPictureBinIds`, in the same patch) that maps original-name digits to
assigned IDs, recursing into table cells. When a converted image is blank,
diff the picture record's binItemID (offset 71 of SHAPE_COMPONENT_PICTURE)
against the DocInfo BIN_DATA IDs first.

✅ **hwpConverter's CLI never overwrites — it silently writes `name(1).hwp`.**
`OutputNaming.unique()` uniquifies every output path, so converting onto an
existing file leaves the old file at the requested path and the real result
beside it. Our wrapper then "verified" the stale old file: an HTML-route .hwp
from two days prior passed at 100% text coverage while the user opened it and
saw wrecked tables — text coverage cannot distinguish which conversion
produced a file. The jar output itself was geometry-perfect all along (table
sz and cell widths byte-identical to the source HWPX, picture at its declared
28346×17340, not its pixel size). Fix: `_export_jar_route` converts into a
fresh empty temp dir and `shutil.move`s over dest. When diagnosing "the jar
corrupts geometry", first confirm the file you are reading was actually
written by the jar.

✅ **Hangul 2010's HTML import silently drops base64 `data:` images** (a
1-image document converted with zero picture controls) **but follows relative
`<img src="BinData/…">`.** `hwp_export` therefore converts with
`embed_images=False` and unpacks the HWPX's `BinData/` next to the HTML — the
image then arrives as a real embedded picture. This also means the HTML must be
opened in place (`_run_com(..., staged=True)`), not copied alone to a fresh
temp dir, or the relative references break again.


✅ **`GetTextFile("TEXT","")` opens a modal dialog** (텍스트 문서 종류) that blocks
COM until dismissed by hand. Avoid it in automation.

✅ **`cairosvg` does not work on stock Windows** (`libcairo-2.dll` missing). Use
PyMuPDF for SVG→PNG.

✅ **Korean font names in rhwp's SVG do not resolve** — substitute `font-family`
or every CJK glyph rasterises as tofu. The substitution changes glyph widths, so
wrap positions in the PNG are approximate.

✅ **Do not round-trip source files through PowerShell `Get-Content`/`Set-Content`.**
It corrupted a Korean path to `[2李?吏꾪뻾]`. Use the file tools.

✅ **lxml rejects stdlib ElementTree nodes.** `python-hwpx` parses with lxml when
installed, so build new elements with `parent.makeelement(...)`, not
`ET.Element(...)`.

---

## 양식 채우기

✅ **양식 본문 칸에는 왼쪽 여백이 들어 있다.** 실측한 정부 서식의 안내문 칸은
`paraPr` 의 `margin/left` 가 **2000 HWPUNIT**(약 7 mm)이었다. 안내문이 그 여백을
쓰라고 만들어진 것이라, 칸을 채우면 넣은 글이 전부 오른쪽으로 밀려 보인다. 반면
새로 만든 표의 문단은 여백이 0이라 한 문서 안에서 어떤 줄은 들여쓰이고 어떤 줄은
아닌 상태가 된다. `set_cell(..., flatten=True)` / `fill_cell(..., flatten=True)`
가 `flatten_indent()` 로 여백 없는 `paraPr` 를 파생해 붙인다.

⚠️ **`margin` 은 `hh:` 인데 그 자식 `left`/`intent` 는 `hc:` 네임스페이스다.**
같은 네임스페이스로 찾으면 예외 없이 조용히 `None` 이 나온다. 이것 때문에 첫 진단이
"들여쓰기 없음" 이라는 잘못된 결론을 냈다.

✅ **`ensure_paragraph_format(base_para_pr_id=…)` 은 기준을 실제로 지킨다.**
같은 이름 규칙의 `ensure_run_style(base_char_pr_id=…)` 이 기준을 무시하는 것과
다르다. 확인함: `margins={"left":0,"intent":0}` 로 파생한 결과가 원본과 `id` 만
달랐다. 그래서 문단 쪽은 `derive_char_pr` 같은 우회 구현이 필요 없다.

✅ **셀 안에 새로 만든 표는 문서 기본 스타일을 쓴다.** 그대로 두면 본문과 글꼴이
갈린다 — 실측에서 본문은 charPr 49(12 pt 한양중고딕), 새 표는 charPr 0(10 pt
함초롬바탕)이었다. `fill_cell` 은 바깥 칸의 `charPr` 을 표 셀에 물려준다.

✅ **`refit_cell` 은 채운 *뒤에는* 쓸 수 없다.** 편집 전 레이아웃 캐시와 비교하는
방식인데, 채우는 순간 그 캐시가 지워진다. 표를 넣어 높이가 달라졌으면 표 단위로
`autofit` 을 다시 돌린다. 단 **병합 여부를 먼저 확인할 것** — 규칙 9은 그대로
유효하고, 병합이 없는 양식이라 안전한 경우일 뿐이다.

✅ **표 안의 새 셀은 `intent` 를 물려받는다.** 문서 기본 `paraPr` 의
`margin/intent` 가 실측에서 **-2620**(내어쓰기)이었다. `left` 가 0이라 첫 줄이
왼쪽으로 나갈 자리가 없는데도 값이 남아, 표 안 글자만 미묘하게 밀려 보인다.
바깥 칸을 `flatten` 으로 정리해도 `_fill_inner` 를 빼먹으면 표에만 여백이 남는다.

✅ **`autofit` 의 기본 글자 크기는 10 pt 다. 남의 양식은 대개 다르다.**
실측한 정부 서식은 본문이 12 pt 라, 10 pt 로 줄 수를 계산하면 필요한 높이를
적게 잡는다. 채운 칸이 아래 칸과 겹쳐 보이는 원인이 이것이다.
`autofit(table, font_pt=dominant_font_pt(doc))` 로 문서의 실제 크기를 넘긴다.
실측 예: 팀 구성 칸이 6966 → 14006 HWPUNIT 으로 바뀌었다.

✅ **높이 재계산은 모든 편집이 끝난 *뒤*에 한 번만.** 채우고 → 높이 맞추고 →
한 칸 더 고치면, 마지막 수정이 반영되지 않은 높이가 남는다. 순서는
채우기 → 수정 → `autofit` 이다.

✅ **중첩 표를 칸보다 좁게 만들면 오른쪽에 빈 띠가 남는다.** 예전 기본값
`ratio=0.96` 은 칸 47950 에 표 46032 를 만들어 **1918 HWPUNIT(약 6.8 mm)** 를
남겼다. 실측하면 사람이 만든 문서도 비슷하게 좁다 — 온리브 0.952~0.978, U300
평균 0.939 이고 최대 1.002 로 칸보다 넓은 것도 있다. 즉 한글은 칸과 같거나 넓은
표도 허용한다. 그래도 그 띠가 눈에 거슬리므로 기본값을 **1.0** 으로 두었다.
`BoxDoc._fill_content` 와 `fill_cell` 양쪽 모두 해당한다.

✅ **표를 붙들고 있는 앵커 문단의 왼쪽 여백이 표 전체를 민다.** 글줄을
`flatten` 으로 정리해 놓고 앵커 문단을 빼먹으면, 문단은 제자리인데 **표만**
들여쓰여 보인다. 증상이 "표만 탭만큼 밀려 있다" 로 나타나서 셀 안쪽 여백 문제로
오인하기 쉽다. 실측: 양식 본문 문단의 `margin/left` 가 2000 HWPUNIT(약 7 mm)
이라 표가 그만큼 밀려 있었다. 새로 만든 문서에서는 앵커 `paraPr` 이 기본값
(여백 없음)이라 이 증상이 나타나지 않는다 — **양식을 채울 때만** 보인다.

---

## Pictures in an edited document

✅ **A text rewrite leaves the pictures behind, and every check still passes.**
`replace_text(doc, "강아지", "햄스터")` rewrote 14 paragraphs including the caption
`[그림 1] 햄스터`, but the frame above it still held `dog.jpg`. Structural
verification was fully green: zip integrity, markpen pairing, binary refs, cell
overflow, layout cache, edit scope. Nothing in the file is malformed — the
document is just wrong. `stale_pictures(doc, subjects=[...])` reports captions
that name a new subject so a human can decide; it never picks a replacement,
because the document cannot know which photo is right.

✅ **Swapping the bytes alone distorts the image.** Eight geometry values inside
`<hp:pic>` must agree: `orgSz`, `curSz`, `sz`, the four `imgRect` points,
`imgClip`, `imgDim`, and the `rotationInfo` centre. They encode the *old* aspect
ratio. dog.jpg is 1400×933 (1.50) and hamster.jpg is 1400×1088 (1.29), so reusing
the frame squashes the new photo. `replace_picture()` builds a correct `<hp:pic>`
via `add_picture()` and transplants the element instead of patching the eight
values by hand.

✅ **The replaced image stays in the container.** Dropping the reference does not
remove `BinData/BIN0001.jpg`; it sat unreferenced at 197 KB in the saved file.
HWPX is a ZIP, so anyone who unpacks the document still sees the photo that was
replaced. For a document you send to someone that is a disclosure, not bloat.
`drop_orphan_images()` collects refs across **all** sections before deleting —
scanning one section would delete an image another still uses.

📋 **`<hc:img>`, not `<hp:img>`.** The picture element is `hp:` but its image
reference is `hc:`, the same trap as `<hh:margin>` holding `<hc:left>`. Searching
the wrong namespace returns `None` with no error.

---

## Row heights and font size (행 높이)

✅ **Never measure a row with a document-wide font size.** `autofit()` takes one
`font_pt` for the whole table. On a distributed form whose title rows are 15–17 pt
and whose body is 10 pt, measuring everything at 10 pt collapsed the title row from
3179 to 1866 HWPUNIT. Hangul then crammed 17 pt text into 6.6 mm and drew it as
**overlapping glyphs — a solid black bar** with the title invisible. `fit_table()`
now reads each cell's own `charPr/@height`.

✅ **Growing a foreign form's rows is fine; shrinking is almost always a bug.**
There is no reason to make a distributed form's row shorter than its author made it.
`verify(baseline=…)` now reports any row that shrank — that single rule reproduces
the black-bar accident exactly, where every structural check and the preview passed.

⚠️ **A too-short declared height is normal in real Hangul files.** Cell height is a
minimum hint and Hangul grows the row on open. 온리브 has 18 such rows, U300 has 23.
So an absolute "row must fit its font" rule cries wolf; report it split into
pre-existing vs newly introduced, the way `overflow introduced` does.

---

## Preview fidelity (미리보기가 거짓말하는 방식)

✅ **The Python page estimate ignored `pageBreak="1"` paragraphs.** The browser
paginator honoured them, the estimate did not — so `verify` counted fewer pages than
the PDF (14 vs 16 on a lab report) and reported `picture push gaps` against the
*previous* page's leftover space for pictures that actually sat under their heading
on a fresh page. Two separate sessions wrote the false FAIL into a memo instead of
fixing it. The estimate now breaks there too, and `render_html()["forced_breaks"]`
lists pages ended on purpose so `page fill` does not flag a cover page.

✅ **The preview grew rows to fit text while paginating on declared heights.** HTML
tables auto-grow, so a document with collapsed rows *looked* perfect in the PNG while
the page count came from the (wrong) declared numbers. Looking at the render gave
false confidence. Height arithmetic and drawing must come from the same numbers.

✅ **Declared heights are trustworthy only where Hangul actually laid the text out.**
`<hp:linesegarray>` is the signal: a paragraph that has one was measured by Hangul; one
that doesn't is our own guess. A filled form has both in the same table, so decide
**per paragraph**, not per file. Trusting declared heights everywhere made a document
that really needed 8 pages report 6 — on a form with a 5-page limit.

✅ **`<hh:lineSpacing>` is not a direct child of `<hh:paraPr>`.** `find()` misses it;
you need `iter()`. The preview hardcoded `LINE_RATIO = 1.6` for years, so changing a
document's line spacing moved the preview page count by exactly zero.

✅ **Only the first `<hp:pic>` of a paragraph was drawn.** Two inline pictures in one
paragraph sit side by side like glyphs (that is how you get a figure row without a
borderless table) — the preview drew one and counted one, so the layout could not be
checked. Their row height is the **max**, not the sum.

✅ **The PDF drew every run in one serif face.** `<hh:fontRef>` was never read, so a
맑은 고딕 body and an HY헤드라인M title all came out as 함초롬바탕 (the PDF embedded
only HCRBatang). `fontRef` ids index **per-language** lists (`<hh:fontface lang=…>`),
so resolve latin and hangul separately. Quote font names but never the generics:
`'sans-serif'` in quotes is a font called "sans-serif".

✅ **자간 (`<hh:spacing>`) is a percentage of the glyph's *width*, not of the em.**
Hangul glyphs are full-width, so −10% ≈ −0.1em; Latin letters are about half as wide.
Copying the value straight into `letter-spacing` made a −25% English label in the
startup-plan sample ("(One line Item Introduction)") collapse into overlapping
letters. Latin-dominant runs use half the `latin` value.

✅ **Chrome cannot use the 2002 HY fonts (HY헤드라인M, HY중고딕, HY견고딕).** They are
installed and Windows lists them, but Chrome measures them exactly like a nonexistent
font — by local name, by English name (`HYHeadLine-Medium`), and even embedded with
`@font-face` (`status: error`, rejected by the font sanitizer). The preview maps
headline faces to bold gothic; do not expect the exact face in a PDF.

✅ **The drawn line height was not the estimated one, so pages overflowed their body.**
Pagination estimated each paragraph at its own `lineSpacing` (150%), but the HTML drew
every line at a fixed 160%. Worse, a unitless `line-height` multiplies the *div's* font
size — the page default 16px — not the 11 pt span inside, so every table line grew by
2px. Filled 12 pt form: page 5 spilled 44px into the bottom margin. Draw with the same
ratio and set the div's `font-size` to the paragraph's size. `<td>` also ignores
`min-height`; use `height` (a table cell treats it as a minimum).

✅ **Chrome's 맑은 고딕 is wider than the Hangul metrics the estimate uses.** Even with
matching line heights, a cell that wraps one line more than predicted pushes the page
over. The HTML now carries a synchronous fit script that shrinks only an overflowing
page's body (floor 0.92, logged to the console) before `--print-to-pdf` runs. A page
that needs more than that means the estimate is wrong — fix the estimate, not the floor.

✅ **Estimating in Python and drawing in Chrome is two typesetters — the PDF broke in
the gap.** After line heights and fonts were matched, the filled 12 pt form still
showed box-fragment borders stopping mid-page (the fragment's height came from the
estimate, not its content), tables in boxes moving whole and leaving 25–40% of a page
empty, and boxes ending open. The drawn output is now paginated in the browser by
measurement (`hwpxkit/paginate.py`); the Python estimate only feeds the Hangul-like
page count. Traps hit while writing it: `scrollHeight` never drops below
`clientHeight` (compare the content's bottom edge instead); a keep-with-next carry
loop that reads `lastElementChild` must *remove* it or it spins forever (Chrome hangs,
`--print-to-pdf` times out); a split-off fragment must drop the source's
`data-break`; and a fixed-layout table ignores `max-width` and uses the sum of its
cell widths as its minimum — write cell widths as % and cap the table width instead.

✅ **A heading could be stranded at the bottom of a page** while the nested table
under it moved whole to the next page. When a container cell is split into page
fragments, a one-line text block directly before a table or picture now moves with it.
Blank-line padding does not work as a fix: the split uses *estimated* heights, so
padding computed from the rendered PDF pushed the heading off the page instead.

---

## HWP export/import (.hwp 왕복)

✅ **Table page-break mode: binary 2 ↔ `pageBreak="CELL"`.** Verified against Hancom's
own matched pairs — 양식.hwp (5 tables) and 온리브.hwp (26 tables) are all binary 2, and
the HWPX Hancom saved from them says `CELL` for every one. The official spec table 76
lists value 2 as "나누지 않음", which is an error in the spec. `hwp2hwpx` reads 2 as
`TABLE`, so a round-trip silently flips every container box to "don't split".

✅ **Highlights survive in `.hwp` but no reader gives them back.** HWP stores 형광펜 as
`PARA_RANGE_TAG` (sort=2, 24-bit BGR), not as a character property. Both readers return
zero markpen, which reads as "the export lost the highlights" when the file is fine.
Verify by scanning the records, and restore markpen from them when reading back.

✅ **`pyhwpxlib` collapses every picture reference to the first image.** U300 (13
pictures) comes back with 13 BinData streams and every `<hc:img>` pointing at image 1 —
the whole document looks like the same picture repeated. Prefer the hwpConverter jar
for reading; it resolves them individually.

✅ **hwpConverter numbers pictures by the digits in `binaryItemIDRef`.** `SectionParser`
does `replaceAll("[^0-9]", "")` + `parseInt`, so a form converted from `.hwp` (logos
`image1`, `image2`) plus pictures added by `add_image` (`BIN0001`, `BIN0002`) gives two
pictures each number 1 and 2. 실측 (요건검토 서류): 신분증·국세 증명서가 양식 로고를
가리켰고, 아무도 안 가리키는 BinData 2개는 한글 2010 이 열면서 버렸다. 사용자가 그
파일에 서명을 넣고 저장하자 서명이 빈 번호 BIN0003 을 받았다. 구조 대조(그림 9->9,
BinData 9->9)는 개수만 세서 **통과했다**. `to_hwp` 의 jar 경로가 이제 번호가
겹치면 `image1..N` 으로 다시 매긴 사본을 변환한다(`_unique_bin_ids`).

✅ **`open_any(.hwp)` can hand back undecoded BinData.** The same form's logos came
back as raw-deflate bytes (BMP) and as garbage (PNG) under their original names — Hangul
and the preview both draw an empty box. Check with `PIL.Image.open` before trusting a
converted form's pictures; `hanuel-bio/build_yogeon.py:fix_logos` restores them from the
OLE streams (PNG stored, BMP raw-deflate — try both).

✅ **Editing the ET tree directly does not mark the part dirty.** `python-hwpx` writes
the untouched original bytes on save, so the repairs vanish with no error. Call
`doc.sections[0].mark_dirty()` after any raw XML surgery.

---

## Index spaces (표 번호는 파일마다 다르다)

✅ **`CellRef.table_index` counts nested tables.** Put a `Grid` inside a container box
and every later table's number shifts, so `t5` in the source form and `t5` in the filled
document are different tables. Comparing geometry by that key reported "2 rows shrank"
for an edit that shrank nothing. Compare top-level tables by their own order.

✅ **`iter_cells()` builds fresh wrapper objects each walk.** `id(ref.table)` is not
stable between two iterations — key on `ref.table.element` or collect in a single pass.

