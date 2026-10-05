---
name: hwpx-builder
description: Author, edit and verify Korean HWPX (한글) documents - reports, comparisons, submission forms. Box-shaped layouts with nested tables, highlighter pen, merged cells, and images. Use when creating, filling, revising, or checking .hwpx files, or when the user mentions 한글/HWPX/보고서/사업계획서/제출 서류.
---

# HWPX Builder

Builds and edits Korean HWPX documents on top of `python-hwpx` (Apache-2.0), adding
the parts it does not cover: real highlighter-pen markup, the box vocabulary these
documents actually use, row autofit, cell-level editing of existing files, and an
honest verification loop.

**Scope.** The vocabulary was measured on two unrelated government-form 사업계획서, which
is where the structural claims below come from. It is not limited to that genre — the
same builders produce research reports and comparison write-ups (see `examples/`), and
the editing layer works on any HWPX that opens. What it does *not* attempt is arbitrary
general-purpose HWPX authoring: the operation set is deliberately small, because each
builder encodes a gotcha that cost a debugging cycle.

**Authoring and editing are different jobs.** Authoring owns every element it emits.
Editing inherits Hancom's styles, merged cells, layout cache and markpen pairs, and
several rules below invert. Building a new document: read to "Verification".
Changing an existing one: read "Editing an existing document" first.

## Setup

Install from a clone — not on PyPI, where the name `hwpxkit` belongs to an
unrelated project.

```bash
pip install <skill dir>             # core: author, edit, structural verify (Apache-2.0)
pip install '<skill dir>[hwp]'      # + old-binary .hwp conversion (NONCOMMERCIAL)
```

The two profiles are one codebase. Core carries no licence restriction and
may be hosted, sold, or open-sourced — previews, PDF export, and the render
pass in `verify()` are all core (built-in layout engine). `[hwp]` pulls in
PolyForm-Noncommercial `pyhwpxlib` for old-binary `.hwp` conversion and the
`to_hwp` read-back verification; a hosted build must not carry it. Per-profile
detail is in `NOTICE`.

Import path: add the skill directory to `sys.path`, then `import hwpxkit`.

## The shape of these documents

Do not model one of these documents as a stream of paragraphs. Measured across two
unrelated real samples, the body is **5 top-level tables**, content nested one level
inside them, **max nesting depth 2**. Section headings sit *between* the boxes as
ordinary paragraphs. Build with that vocabulary:

| Builder | Shape |
|---|---|
| `b.section_heading(text)` | "1. 문제 인식 / Problem Recognition" between boxes |
| `b.label_value_box(pairs)` | colCnt=2, short label left, value right |
| `b.container_box(blocks)` | colCnt=1 shell, grey label row + content row (the dominant shape) |
| `Grid(headers, rows, ratios)` | a table nested inside a container content row |
| `b.content_table(..., repeat_header=True)` | standalone colCnt>=3 grid; `repeat_header` re-shows the header row when the table crosses a page (제목 줄 반복) |
| `set_repeat_header(table, header_rows=1)` | same flag on any top-level table built another way |
| `make_splittable(table)` | anchors a table in body flow (자리 차지) so pages can split it — the builders above already apply it; call it yourself only on tables built another way. A 글자처럼-취급 table never splits, whatever `pageBreak` says |
| `b.picture(path)` / `b.image_placeholder(msg)` | images |
| `fit_pictures(path)` / `analyze_gaps(path)` | post-build pass: a picture taller than the space left on its page gets pushed whole to the next page, leaving a large gap — this simulates layout arithmetically and shrinks the offending pictures (aspect kept, never below 55%; display size only, orgSz/imgDim/imgClip untouched). Pictures sharing the same original width — a comparison series — are grouped and always scaled together by the same factor, so side-by-side pictures never end up mismatched |

```python
import sys; sys.path.insert(0, "<skill dir>")
from hwpx.document import HwpxDocument
from hwpxkit import BoxDoc, Grid, verify

doc = HwpxDocument.new()
b = BoxDoc(doc)
b.title("2026 학생 창업유망팀 300+ 사업계획서")
b.section_heading("0. 사업 아이템 개요 / Business Item Overview")
b.label_value_box([("□ 팀명 / Team name", "벳츄원")])
b.container_box([
    ("□ 창업 배경 및 개발동기", [
        "대표자는 **2년차 근무**하며 비효율을 경험함.",
        Grid(headers=["구분", "규모"], rows=[["1차 타겟", "약 800개소"]], ratios=(0.3, 0.7)),
    ]),
])
doc.save_to_path("out.hwpx")
print(verify("out.hwpx").render())
```

Inline markup inside any text: `**bold**`, `==highlight==`.

Full builds are in `examples/build_research_report.py` and
`examples/build_comparison_report.py`.

## Writing the text — the feedback loop

Structure is caught by `verify()`. Prose is not, and prose is what the reviewer
reads. Generated text fails in predictable ways — clichés (다양한, 효과적으로,
이를 통해), claims without a number, hedged endings (기대된다), triple lists
ending in 등, uniform sentence rhythm, and **no emphasis, so nothing tells the
reader where to look**. `hwpxkit.prose` catches the mechanical part; the rest is
a re-read from the reviewer's seat. The full procedure and the style table are in
`references/writing.md`. Do not skip it.

0. **Decide the document kind and the register before writing a line**, and pass
   them to every review call:
   - `mode="pitch"` (지원서·사업계획서, default) — state what you checked; hedged
     endings (기대된다, 것으로 보입니다) are FIX.
   - `mode="research"` (연구·특허 검토, 교수·변리사에게 가는 글) — the risk is the
     opposite: **saying more than the evidence**. An opinion written as
     "~인 것 같습니다" is fine; "이미 확인되어 있다", "같게 볼 수 있다", "가장 강한",
     reading a patent claim as if you were the attorney are FIX.
   - `register="합니다"` / `"한다"` / `"개조식"` — the user usually wants 합니다체
     and has had to ask for it four times. Ask once if it is not obvious, then
     enforce it: a sentence in another register is FIX. Unset, `review_blocks`
     takes the majority register of the draft and flags the rest.
1. **Draft the content in a Python structure first** (dict/list of the
   `container_box` blocks), not inline in builder calls — you cannot review what
   you cannot iterate over.
2. **`review_blocks(content, mode=…, register=…)`** → fix until it reports no
   `FIX`. Each finding carries the direction (`'다양한' — 무엇이 몇 가지인지 쓴다`).
   Deleting is a fix.
3. Build with **`BoxDoc(doc, bold_figures=True)`** — every figure in body lines
   (`93.0%`, `318/342`, `3개월`) is bolded automatically; table cells are left alone.
   When filling a form, wrap the strings you pass to `set_cell`/`fill_cell` in
   `bold_figures()` yourself.
4. **`verify(path, mode=…, register=…)`** — its `prose review` line re-runs the
   review on the saved file and FAILs on any `FIX`. This is what makes the loop a loop.
5. **`python -m hwpxkit.prose out.hwpx --dump`** — read the plain text from the
   reviewer's seat with the question table in `references/writing.md`
   (first sentence = the conclusion? bold alone readable? one highlight = the
   thing to remember?). Fix, go to 2.
6. Render a PNG and skim **only** the bold and highlighted text. If that skim does
   not say what the business is, why now, and how big — the emphasis is in the
   wrong places.

**Be generous with emphasis, and deliberate about where.** Reviewers skim bold
and highlight first and read the body only where the skim caught them. Bold: every
figure with its unit, proper nouns (product, institution, competitor, technology),
the subject–verb core of each paragraph. Highlight (`==…==`): the one sentence per
box the reviewer must remember — one, at most two. A figure inside a highlight is
written `**==93.0%==**`; do not nest `**` *inside* `==…==` the other way round, the
parser is deliberately flat. Never emphasize inside table cells (they are all
figures), and never more than half a cell — the checker fails both.

**Choices a person typing in Hangul would not make.** Recipients (심사자,
교수) pointed these out, and they give generated text away faster than any
cliché. The checker FAILs on all of them, and `parse_markup` — the funnel every
builder and `set_cell`/`fill_cell` write through — normalizes the punctuation, so
built text never carries it. Fix the draft anyway: a mechanical `-` is rarely as
good as a comma or a split sentence.

| Not this | A person writes | Kind |
|---|---|---|
| `A — B`, `3–5` (줄표) | a comma, parentheses, two sentences; at most `A - B`, `3-5` | `typography` |
| `기술·사업화` (가운뎃점) | `기술/사업화`, `기술과 사업화` | `typography` |
| `**US20230399389A1**`, `**10-2023-0012345**` | the number plain; bold the finding, not the ID | `bold-id` |
| `※ 수정:`, `이번 개정에서`, `(2026-09-29 확인)`, `v2 대비` | nothing — editing history is noise to the reader | `edit-trace` |
| `이 글은 ~를 다룬다`, `~를 목적으로 한다`, `살펴보자`, `바로 이 지점이다` | delete; let the next sentence state the conclusion | `meta` |
| `(출처: 나무위키)`, `(출처: OO 블로그)` | the paper, review or agency page one tier up; else `(3차 자료)` | `source-tier` |

`bold_figures()` skips identifiers (patent, application, PMC, DOI numbers) for the
same reason. A leading `· ` bullet (개조식 marker) is left alone.

```python
from hwpxkit import review_blocks, review_document, dump_text, bold_figures
for f in review_blocks(content, mode="research", register="합니다"):
    print(f)                                     # FIX [3. 경쟁/Pacagen] overclaim: '직접 경쟁' — …
print(review_document("out.hwpx", mode="research", register="합니다").render())
```

## Figures

What the user has asked for, every time it came up:

- **Real material over drawn diagrams.** A paper figure, a patent drawing, a
  screenshot of the article that shows the problem — with its source. Generated
  concept diagrams (flows, layer stacks, roadmaps) were rejected as "별로"; write
  those as numbered text instead. Draw a chart only for **numbers with a source**
  (TAM/SAM/SOM, survey results) and say under it which figures are assumptions.
- **Crop to the part that matters.** An article capture keeps the headline and the
  sentence that proves the point, not the menu and the ads. A multi-panel paper
  figure keeps the panel you discuss.
- **Clean around the picture.** When a figure is "난잡", the photo was usually fine
  and the decoration around it was not: white/black, minimal text, no callouts.
- **Never invent an image** (rule 4). No real picture → `image_placeholder()`.
- **Source one tier up.** Primary (paper, patent, statistics office) over secondary
  (article, report) over tertiary (wiki, blog). A wiki source FAILs `source-tier`
  unless the figure *is* the blog page. Page numbers only from the original;
  otherwise leave `[ ]`. A re-quotation says so in the sentence ("샌델에 따르면").

```python
b.figure("fig/hair_sem.png", width_mm=110,
         caption="[그림 3] 키토좀 처리 후 털 표면 SEM",
         source="Satyaraj et al., Allergy 2019 (CC BY-NC)",
         crop=(0.0, 0.08, 1.0, 0.92))          # 왼/위/오른/아래, 1 이하면 비율
b.container_box([("□ 문제", ["설명 줄", Img("cap.png", width_mm=90,
                                         caption="[그림 1] 블로그 글", source="네이버 블로그",
                                         crop=(0, 120, 1080, 900))])])   # 픽셀
```

Caption and source go in **one** paragraph, `[그림 1] 제목 (출처: …)` — as two
paragraphs the source line alone fell to the next page. Cropping writes new
pixels (Pillow); it does not use `imgClip`, which the `.hwp` converter mis-maps.

## Editing an existing document

The library's edit surface does not reach these documents. Measured on 온리브:
`doc.paragraphs` sees 13 top-level paragraphs and none of the 26 tables, so
`replace_text_in_runs("온리브", …)` replaced **0** of the 7 occurrences (all in
cells, 2 of them carried as markpen tails). `get_table_map()` reported 0 tables and
`find_cell_by_label` 0 matches. Use `hwpxkit.edit`, which walks cells:

```python
from hwpx.document import HwpxDocument
from hwpxkit import find_label, find_cells, set_cell, replace_text, highlight_cell, verify

doc = HwpxDocument.open(src)
team = find_label(doc, "팀명", direction="right")   # -> CellRef, path "s0/t0/r0c1"
set_cell(doc, team.cell, "벳츄원 컨소시엄")          # keeps the cell's own size/font
print(replace_text(doc, "온리브", "ONLIVE").render())   # 7/7, cells + markpen tails
highlight_cell(doc, find_cells(doc, "핵심")[0].cell, "핵심")
doc.save_to_path(dest)
print(verify(dest, baseline=src).render())          # baseline= enables the edit checks
```

| Builder | Editor |
|---|---|
| `b.container_box(...)` builds a box | `find_cells` / `find_label` → `CellRef` locates one |
| `set_spans` writes a paragraph | `set_cell` writes a cell, keeping its charPr |
| `==highlight==` at author time | `highlight_cell` wraps text already there |
| `autofit(table)` sizes new rows | `refit_cell(ref)` *reports*; Hancom re-flows |
| `Grid(ratios=…)` guessed by hand | `autofit_columns(table)` derives them from content |
| `Span(bold=…)` at author time | `char_style(doc, base, pt=, face=, bold=)` — size and typeface too |
| — | `restyle(doc, cell, pt=, face=)` — every run in a cell, keeping bold |
| — | `set_align(doc, para, "LEFT", line_spacing_percent=130)` |
| — | `keep_korean_words(doc)` — 한글 줄 나눔을 어절 단위로 |
| `b.picture(path)` | `fill_cell(doc, cell, ["설명", Img(path, width_mm=95)])` |
| `verify(path)` | `verify(path, baseline=src)` |

`char_style` exists because `derive_char_pr` only reaches bold and colour. Changing
size or typeface needs the font tables too: **`<hh:fontfaces>` is per language**
(HANGUL/LATIN/HANJA/…) and each list is a different length, so one id does not work
across them — `ensure_face()` registers the face in all of them and returns the map.

`autofit_columns` replaces guessing ratios blind. Measured on a real submission: the
recipient re-tuned every column of both tables the ratios were guessed for (팀 구성
순번 3504→2655, 관련 경력 26746→28161) and then hand-broke lines inside the cells to
undo the bad wrapping. Deriving widths from content load removes that step.

Worked example: `examples/edit_existing.py`.

### 분석 틀 템플릿

사업계획서에 반복해서 나오는 틀은 `hwpxkit.templates` 에서 가져다 쓴다. 전부
`Grid` 를 돌려주므로 새로 만들 때(`container_box`)나 양식을 채울 때(`fill_cell`)나
똑같이 들어간다.

| 함수 | 내용 |
|---|---|
| `tam_sam_som(tam=, sam=, som=)` | 시장 규모 3단계. **산출 근거 칸이 따로 있다** |
| `swot(strengths=, weaknesses=, opportunities=, threats=)` | 2×2 SWOT |
| `business_model_canvas(**blocks)` | BMC 9칸. 모르는 칸 이름은 `ValueError` |
| `milestones(rows)` | 추진 일정. 마지막 열이 **완료 기준** |
| `budget(rows)` | 사업비. 합계를 대신 계산하지 **않는다** |
| `competitor_matrix(criteria=, us=, competitors=)` | 경쟁 비교. 열 길이가 다르면 `ValueError` |

두 가지 설계 원칙이 있다. **근거 칸을 반드시 만든다** — 숫자만 있고 출처가 없는
표가 심사에서 가장 먼저 지적받는다. 그리고 **계산을 대신하지 않는다** — 합계를
자동으로 내면 틀렸을 때 조용히 틀리고, 제출 서류에서 그건 가장 나쁜 실패다.

BMC 는 원래 특유의 격자 배치지만 여기서는 2열 목록으로 편다. 그 배치를 한글 표로
재현하면 병합 셀이 잔뜩 생기고, **병합 표는 높이를 다시 계산할 수 없다**(규칙 9).

### 구식 `.hwp` 를 받았다면

```python
from hwpxkit import open_any, is_hwp, hwp_to_hwpx

doc = open_any("form.hwp")     # .hwp 면 변환 후, .hwpx 면 그냥 열기
```

`[hwp]` 부가 설치가 필요하다. `hwp2hwpx.py` 가 Apache-2.0 이라고 해서
상업적으로 쓸 수 있는 것이 아니다. 실행하면 PolyForm 모듈 56개가 함께
로드된다. `hwpxkit/convert.py` 참고. 반대 방향(HWPX → HWP)은 아래
`to_hwp` 가 맡는다.

## Previewing, exporting PDF, and the feedback loop

`hwpxkit.preview` is a self-contained layout engine (stdlib + Apache-2.0
`form_fit` only). Unlike rhwp it does **not** replay the lineseg cache — it
lays the document out itself, so freshly generated files get real pagination:
tables split at row boundaries (repeat-header drawn), pictures push with the
gap **visible**, markpen actually renders. Measured accuracy: page counts
match Hangul 2010 exactly or +1 conservative.

```python
from hwpxkit import render_html, render_png, render_pdf, lint

render_html("doc.hwpx", "preview.html")   # self-contained, double-click to view
render_png("doc.hwpx", "preview.png")     # one tall PNG (headless Chrome)
render_pdf("doc.hwpx", "doc.pdf")         # vector PDF, exact paper size
print(lint("doc.hwpx"))                    # layout smells, human sentences
```

**The page count is only as honest as the heights it adds up.** For a text row the
engine trusts the declared cell height — right for a file Hangul saved, wrong for one
we just wrote, where that number is our own guess. It decides **per paragraph** using
`<hp:linesegarray>`: a paragraph Hangul has laid out is trusted, one without a cache is
measured. `render_html()` returns `measured` (how many paragraphs it had to measure) so
you can tell which kind of answer you got. Before this split, a document that really
needed 8 pages reported 6 — on a form with a 5-page limit.

**Two page counts, on purpose.** `render_html()["pages"]` is the Python estimate that
imitates Hangul — `verify`, `lint` and `fit_pictures` use it. The *drawn* HTML/PNG/PDF is
paginated in the browser by measuring what Chrome actually drew (`hwpxkit.paginate`):
tables — including tables inside container boxes — split at row boundaries with the
header row repeated, boxes are closed on every page, and headings/grey labels stay
with what follows. `render_pdf()["pdf_pages"]` is the printed count. Estimating in
Python and drawing in Chrome was what broke PDFs (text spilling into the margin, box
borders stopping mid-page, 40%-empty pages); `render_html(..., paginate="engine")`
still draws the old way for comparison.

**Work with your eyes open.** After building or editing a document, render a
PNG and *look at it* before declaring the work done — then fix what you see
and render again. This loop caught, in one session: tables silently 20mm into
the right margin, orphaned grey label rows at page bottoms, and mismatched
comparison-photo sizes. `lint()` automates the mechanical part (width
overflow, oversized picture gaps, empty pages); your eyes catch the rest.
PNG/PDF need a local Chrome; `render_html`/`lint` need nothing.

## Exporting .hwp for recipients on old Hangul

Hangul 2010 cannot open HWPX at all (`Open()` still returns `True` — it reads
the ZIP as a text file). When the recipient needs binary `.hwp`:

```python
from hwpxkit import to_hwp
print(to_hwp("사업계획서.hwpx").render())   # writes 사업계획서.hwp alongside
```

`to_hwp` tries routes in order and reports which one ran:

1. **jar** — [vsdn/hwpConverter](https://github.com/vsdn/hwpConverter)
   (Apache-2.0, Java 8+): a real HWPX→HWP writer on hwplib/hwpxlib. No
   Hancom needed, keeps tables and images as real objects. Preferred; found
   via `HWPCONVERTER_HOME` or `ref/hwpConverter`. Apply
   `patches/hwpconverter-fixes.patch` to your clone and build with the three
   javac/jar lines in its README — stock hwpConverter drops markpen, breaks
   image references/crop, and mis-maps the table split mode.
2. **direct** — Hangul 2014+ COM `SaveAs`.
3. **html** — Hangul 2010 COM via CP949 HTML. Last resort: text and table
   structure survive but layout degrades badly — avoid when the jar is
   available.

Every export is verified two ways. Text coverage comes from re-reading the `.hwp`;
**structure is counted straight out of the binary** by `hwpxkit.hwpbin`, which walks the
HWP records with nothing but `olefile`. The report line reads
`구조 대조: 그림 3->3, 표 14->14, 형광펜 8->8, BinData 3->3`, and a drop in any of them
makes the report not-ok.

Counting through a reader instead would lie in both directions: `pyhwpxlib` collapses
every picture reference to the first image, and `hwp2hwpx` returns zero markpen because
HWP stores 형광펜 as `PARA_RANGE_TAG`, not as a character property. A file with 8 intact
highlights and 3 distinct pictures reads back as 0 and 1.

Reading a `.hwp` back in (`hwp_to_hwpx`, `open_any`) prefers the jar when it is built,
then repairs what the jar still gets wrong from the same binary: table page-break mode
(binary 2 is `CELL`, not `TABLE`) and markpen. That is what makes "take the edited `.hwp`
the recipient sent back and keep working" lossless.

## Line breaking and other viewers (Polaris Office)

`HwpxDocument.new()` inherits Hangul's default `breakNonLatinWord="BREAK_WORD"`:
Korean wraps at **any character**, so a narrow cell breaks "실험" into "실 / 험".
Hancom-authored forms use `KEEP_WORD` (어절 단위) for body text, and viewers with
different font metrics — Polaris Office substitutes the 함초롬 faces — land those
character breaks in different, uglier places, and clip a row's last line when the
declared height was computed for fewer lines. `BoxDoc` therefore sets `KEEP_WORD`
document-wide (`keep_words=True`) and sizes rows with the word-level estimator in
`hwpxkit.wrap`; `fit_rows` reads the document's mode. For a form you are filling,
call `keep_korean_words(doc)` once. The `korean word wrap` line in `verify()`
reports which mode a file is in. Rendering in Polaris itself is **NOT VERIFIED**
here — if a Polaris screenshot still shows broken text, keep the screenshot and
the file; the next suspects are substitute-font width and declared cell heights.

## Non-negotiable rules

1. **Never hand-write `<hp:...>` XML.** Use the builders. Every one of them
   encodes a gotcha that cost a debugging cycle.
2. **Highlight means markpen, never `shadeColor`.** `python-hwpx`'s
   `ensure_run_style(highlight=...)` sets `shadeColor`, which is cell *shading*
   (음영), a visibly different thing. Use `==text==` or `Span(highlight=...)`.
3. **Never hardcode a `charPrIDRef` / `borderFillIDRef` / `paraPrIDRef` from
   another document.** They are renumbered per file. Classify by shape, not id.
4. **Never invent a missing image.** Call `image_placeholder()`. A wrong image in
   a submission document is worse than a visible gap.
5. **Run `verify()` before reporting done**, and read the NOT VERIFIED lines
   aloud rather than treating them as passes. When editing, pass
   `baseline=<original>` — the stale-cache and scope checks cannot run without
   the before-and-after pair, and it is what separates a defect you introduced
   from one the form arrived with (both samples overflow a cell untouched).
6. **Never shrink a row you did not create, and never measure one with a
   document-wide font size.** `autofit()` takes a single `font_pt`; on a form whose
   title rows are 17 pt and body 10 pt that collapses the title row and Hangul draws
   the text as a black bar. Use each cell's own `charPr/@height`, and grow only.
   `verify(baseline=…)` now fails on any row that shrank.
7. **Do not swallow exceptions around geometry setters.** `cell.width` is
   read-only; a bare `except` there silently leaves every column at its default
   and the failure only shows up as text spilling past the border.

### Rules that apply only when editing

8. **Drop the `<hp:linesegarray>` of every paragraph you touch, and no others.**
   Stale `textpos` makes Hancom draw new text into the old line slots. Everything
   in `hwpxkit.edit` does this; `set_spans` does not, because an authored
   paragraph has no cache. Never strip the cache document-wide.
9. **Never run `autofit()` on a table you did not build.** Its row model assumes
   no merged cells; real forms merge heavily (26 in 온리브, 34 in U300), and on an
   untouched sample table it inflated a row from 16980 to 124354 HWPUNIT. Once
   the cache is gone Hancom re-lays-out the row correctly on open. Use
   `refit_cell()`, which reports and refuses to resize a merged table.
10. **Never clear a paragraph's runs to empty it.** A nested `<hp:tbl>` lives
   *inside* an `<hp:run>`, so clearing runs deletes the sub-table and every image
   in it. Use `set_cell`, which skips paragraphs anchoring non-text runs.
11. **Inherit the style you are replacing.** `ensure_run_style(base_char_pr_id=…)`
    ignores the base — asked for a bold variant of a 12 pt run it returned an
    unrelated 10 pt style. Use `derive_char_pr()`, or an edited cell silently
    changes size and typeface.

### Rules for the text itself

12. **Run the prose loop (`review_blocks` → `verify` → `--dump` re-read) before
    reporting done.** A `prose review` FAIL is a real failure. Zero findings means
    "nothing mechanical is left", not "well written" — the re-read is mandatory.
13. **Emphasize generously and on purpose.** Every content cell gets bold on its
    figures and key nouns (`bold_figures=True` does the figures); every cell of
    three or more sentences gets exactly one highlighted sentence. A cell with no
    emphasis and a cell that is more than half emphasized both fail.
14. **Never invent a figure to satisfy the checker.** `(근거 미기재)` is an
    honest answer; a made-up number is worse than any cliché.
15. **Write like a person typing in Hangul.** No `—`, no `·` between words, no
    bold on patent/paper/document numbers, no editing traces. Keep one register
    for the whole document (usually 합니다체) and match claims to the evidence
    (`mode="research"` for anything a professor or patent attorney will read).
16. **Read the folder's `project.md` first** when working in a project folder
    (`hanuel-bio/`, `sdu/`, …). It records who the applicant is, which file is the
    current source, the register, and what the user already corrected — the
    user has had to correct a wrong name or a stale source document five times.
    Update it when the user corrects a fact.

## Verification: what is and is not checkable here

`verify(path)` runs cheapest-first and labels anything it could not check as
**NOT VERIFIED** rather than passing it silently.

**Page budget.** Forms say "1페이지 내외", "5쪽 이내"; pass it:
`verify(path, max_pages=5)` adds a `page limit` line (one page over → it tells you
how full the last page is, i.e. how much to cut; exactly at the limit with a >90%
full last page → it warns that Hangul may spill). `max_pages` counts the whole
file, so for a form whose 요약 is page 1 of 4, check that section's pages yourself.
Every run also has a `page fill` line: a page other than the last that is under
60% full means a big table or picture was pushed whole to the next page — the
"빈 공간이 너무 많다" complaint. Pages ended by a forced page break (표지, 붙임) are
excluded.

Checkable without a renderer:
- ZIP integrity, required parts, `mimetype` first + stored
- Korean word-wrap mode (`korean word wrap`, informational): authored files are
  어절 단위 (`KEEP_WORD`); a form left on `BREAK_WORD` is reported, not failed
- prose review (`prose review`): clichés, unquantified claims, hedges, missing or
  excessive emphasis — FAILs on any FIX; see `references/writing.md`
- markpen begin/end pairing (an orphaned begin bleeds highlight down the page)
- `binaryItemIDRef` -> `BinData/` resolution
- unbreakable cell overflow, via `hwpx.form_fit.measure` (advances calibrated on
  real Hancom line caches)

Checkable with the built-in layout engine (`check_layout`): page count,
empty pages, body-width overflow, picture push gaps, markpen render pairing.

Checkable by geometry (`check_row_geometry`): whether any row is shorter than the
largest glyph it holds. Real Hangul files have plenty of those (온리브 18, U300 23) —
cell height is a minimum hint and Hangul grows the row on open — so this is reported
split into pre-existing and newly introduced, never as a flat count.

Checkable only with `baseline=` (an edit against the file it started from):
- a changed paragraph that kept its layout cache — invisible inside a single file
- how many cells the edit actually reached, vs how many you meant to touch
- markpen balance relative to the original, and whether an overflow is new or inherited
- **a row that got shorter than the form made it** — the check that reproduces the
  black-bar accident, which every other layer passed

**Not checkable here at all** — say so, do not imply otherwise:
- *Highlight rendering.* rhwp ignores markpen completely. Verified by A/B:
  stripping all 31 markpen tags from a real document changed its SVG output not
  at all. XML pairing is the only available signal.
- *Line breaking, wrap position, page count fidelity.* rhwp largely **replays a
  document's cached `<hp:linesegarray>`** instead of laying text out. Stripping
  that cache from a real document changed its page count 6→5. A freshly generated
  file has no cache, so rhwp's wrapping of it means little — long cell text will
  look like it overlaps the next column even when the file is fine.
- *Pixel-exact output.* Needs the Hancom COM oracle.

### The Hancom oracle is a trap on this machine

`HWPFrame.HwpObject` registers and `Open()` returns `True`, which looks like
success. It is not: the installed build is **Hangul 2010 (8.0.0.466)**, and HWPX
arrived in Hangul 2014. It opens the ZIP as a *text file* — `SaveAs(...,"HTML")`
emits `<TITLE>PK</TITLE>` plus garbage, `PageCount` returns 3311 for a 6-page
document, and PDF export never finishes. **Never build a gate on it.** A real
oracle needs Hangul 2014+, realistically 2020/2022.

## Rendering for a visual check

No extra install — the built-in engine renders directly:

```bash
python scripts/render_png.py out.hwpx            # -> out_preview.png (+린트)
python scripts/render_png.py out.hwpx out.pdf    # vector PDF
```

Then actually look at the output. PNG/PDF run a local headless Chrome;
`render_html`/`lint` need nothing beyond the core install.

## Licence

`NOTICE` carries the per-profile summary and the per-component attributions,
each read from the installed distribution rather than from documentation.

- **Core** (`hwpxkit` + `python-hwpx`) is **Apache-2.0** throughout. Authoring,
  editing and every structural check live here. No restriction on hosting,
  selling, or open-sourcing.
- **`pyhwpxlib`** is **PolyForm Noncommercial**: free for personal, academic and
  nonprofit use, never for commercial use. Its *No Other Rights* clause forbids
  sublicensing, so a permissive release of this package cannot pass its rights
  downstream — that is why it is an extra and not a dependency.
- **`pymupdf`** (PNG output only) is **AGPL-3.0** or Artifex commercial, and
  AGPL §13 *does* reach network users. Independent reason not to host `preview`.
- **`rhwp_bg.wasm`**, the renderer binary itself, is **MIT** (Edward Kim). A
  commercial build can drive it directly through `wasmtime` (Apache-2.0) —
  write that bridge against the wasm's exported interface. Do not copy
  `pyhwpxlib` source.

`hwpxkit/render.py` is the only module that imports the restricted packages, and
`verify.check_render` imports it lazily. In the core profile `import hwpxkit`
loads none of them — verified, not assumed:

```bash
python -c "import hwpxkit, sys; print([m for m in sys.modules if 'pyhwpx' in m])"
```

## Further reading

- `references/gotchas.md` — the accumulated failure list; add to it every time a
  render breaks
- `references/writing.md` — the prose loop: what makes text read as generated,
  the emphasis policy, the re-read questions, document kind and register
- `hwpxkit/richtext.py` — markpen implementation and why the pair may straddle runs
- `hwpxkit/edit.py` — cell traversal, cache invalidation, style inheritance
- `hwpxkit/verify.py` — the layered checks
