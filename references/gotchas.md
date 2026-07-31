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
`autofit` 을 다시 돌린다. 단 **병합 여부를 먼저 확인할 것** — 규칙 8은 그대로
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
