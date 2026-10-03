"""이번 판에서 고치려는 결함들을 먼저 실패로 고정한다.

실제 문서로 돌린다. `C:/hwpx` 의 표본이 기준이다 —
  - 온리브_사업계획서_배포용.hwp.hwpx   (한/글이 저장한 문서: 레이아웃 캐시 있음)
  - [2차 진행] U300+ 사업계획서.hwp.hwpx (같음, 그림 13장)
  - 양식...300+.hwp.hwpx                (빈 배포 양식)
합성 문서는 `_build_filled()` 로 그 자리에서 만든다 (캐시 없음).

    python tests/test_regressions.py
"""
from __future__ import annotations

import io
import os
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

#: 표본 문서가 있는 곳. 이 저장소 **밖**이다 — 남의 사업계획서라 커밋할 수 없다.
#: 다른 기계에서는 ``HWPX_CORPUS`` 로 알려 주거나, 없으면 이 파일 전체를 건너뛴다.
#: 기본값은 저장소 안의 ``hwpx/`` (gitignore 됨), 없으면 예전 자리 ``C:/hwpx``.
CORPUS = Path(os.environ.get("HWPX_CORPUS") or next(
    (p for p in (ROOT / "hwpx", Path("C:/hwpx")) if p.is_dir()), Path("C:/hwpx")))
ONLIVE = CORPUS / "온리브_사업계획서_배포용.hwp.hwpx"
U300 = CORPUS / "[2차 진행] U300+ 사업계획서.hwp.hwpx"
FORM = CORPUS / ("양식. 사업계획서(Business Plan, hwp)_2026 학생 창업유망팀 300+"
                 "(2026 Promising Student Startup Team 300+).hwp.hwpx")
OUT = CORPUS / "next" / "out"
OUT.mkdir(parents=True, exist_ok=True)

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

_results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((ok, name, detail))
    print(f"  {'PASS' if ok else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))
    return ok


def _build_filled(path: Path, repeat: int = 1) -> Path:
    """양식을 채운 문서를 하나 만든다. 레이아웃 캐시가 없는 쪽 표본이다."""
    from hwpx.document import HwpxDocument
    from hwpxkit import Grid, find_cells, fill_cell

    doc = HwpxDocument.open(str(FORM))
    hits = find_cells(doc, "창업 배경 및 개발동기")
    body = hits[0] if hits else None
    if body is not None:
        below = list(body.table.rows)[body.row + 1].cells[body.col] \
            if body.row + 1 < len(list(body.table.rows)) else body.cell
        fill_cell(doc, below, [
            "이 문단은 표본을 만들기 위한 것이다. " * (12 * repeat),
            Grid(headers=["구분", "내용"],
                 rows=[[f"항목 {i}", "설명 " * 20] for i in range(6 * repeat)],
                 ratios=(0.2, 0.8)),
        ])
    doc.save_to_path(str(path))
    return path


# ---------------------------------------------------------------------------
# 1. 쪽 수 정직성 — 캐시 없는 문서는 선언 높이를 믿으면 안 된다
# ---------------------------------------------------------------------------
def test_page_count_honest() -> None:
    print("\n[1] 쪽 수 계산이 레이아웃 캐시 유무를 구분하는가")
    from hwpxkit import render_html

    src = _build_filled(OUT / "filled.hwpx")
    info = render_html(src, OUT / "filled.html")
    check("채운 문단을 직접 측정한다", bool(info.get("measured")),
          f"measured={info.get('measured')} pages={info['pages']}")

    # 같은 내용을 두 배로 넣으면 쪽 수가 늘어야 한다 — 선언 높이만 믿으면 안 는다.
    big = _build_filled(OUT / "filled_big.hwpx", repeat=4)
    grew = render_html(big, OUT / "filled_big.html")["pages"]
    check("내용이 늘면 쪽 수도 는다", grew > info["pages"],
          f"기본 {info['pages']}쪽 -> 4배 {grew}쪽")

    # 한/글이 저장한 문서는 선언 높이를 그대로 믿어야 한다 (6쪽 실측)
    onlive = render_html(ONLIVE, OUT / "onlive.html")
    check("온리브(캐시 있음) 쪽 수가 실측 6쪽과 같다", onlive["pages"] == 6,
          f"pages={onlive['pages']}")


# ---------------------------------------------------------------------------
# 2. 행 높이 축소 회귀 — verify(baseline=) 가 잡아야 한다
# ---------------------------------------------------------------------------
def test_shrink_regression() -> None:
    print("\n[2] 행 높이를 줄인 편집을 verify 가 잡는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import iter_cells, verify

    dst = OUT / "shrunk.hwpx"
    doc = HwpxDocument.open(str(FORM))
    hit = None
    for ref in iter_cells(doc):
        if (ref.cell.height or 0) > 2500:
            hit = ref
            break
    if hit is None:
        check("축소할 행을 찾았다", False)
        return
    before = hit.cell.height
    for cell in list(hit.table.rows)[hit.row].cells:
        cell.set_size(height=1200)
    doc.save_to_path(str(dst))

    rep = verify(str(dst), baseline=str(FORM))
    text = rep.render()
    check("축소를 결함으로 보고한다", "행 높이" in text or "축소" in text,
          f"{before} -> 1200 인데 보고 없음" if "행 높이" not in text else "")


# ---------------------------------------------------------------------------
# 3. 행이 자기 글자 크기를 담는가
# ---------------------------------------------------------------------------
def test_row_fits_font() -> None:
    print("\n[3] 글자 크기보다 낮은 행을 잡는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import iter_cells, verify

    dst = OUT / "tinyrow.hwpx"
    doc = HwpxDocument.open(str(FORM))
    for ref in iter_cells(doc):
        if ref.text.strip():
            for cell in list(ref.table.rows)[ref.row].cells:
                cell.set_size(height=400)      # 1.4mm — 어떤 글자도 안 들어간다
            break
    doc.save_to_path(str(dst))
    check("글자가 안 들어가는 행을 보고한다",
          "행 높이" in verify(str(dst), baseline=str(FORM)).render())


# ---------------------------------------------------------------------------
# 4. 미리보기가 문단 줄간격을 반영하는가
# ---------------------------------------------------------------------------
def _fresh_doc():
    """한/글이 조판한 적 없는 문서. 선언 높이를 믿을 수 없는 쪽 표본."""
    from hwpx.document import HwpxDocument
    from hwpxkit import BoxDoc

    doc = HwpxDocument.new()
    b = BoxDoc(doc)
    b.title("줄간격 표본")
    for i in range(12):
        b.paragraph(f"{i}. " + "본문 글줄을 채워 넣는다. " * 14)
    return doc


def test_preview_line_spacing() -> None:
    print("\n[4] 미리보기가 문단별 줄간격을 반영하는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import render_html

    # 캐시 있는 문서는 선언 높이를 쓰는 것이 맞으므로, 새로 만든 문서로 잰다.
    tall, short = OUT / "ls200.hwpx", OUT / "ls100.hwpx"
    for path, pct in ((tall, 200), (short, 100)):
        doc = _fresh_doc()
        header = doc.headers[0]
        for para in doc.sections[0].paragraphs:
            base = para.element.get("paraPrIDRef")
            if base is None:
                continue
            new = header.ensure_paragraph_format(base_para_pr_id=base,
                                                 line_spacing_percent=pct)
            if new:
                para.element.set("paraPrIDRef", str(new))
        doc.save_to_path(str(path))
    a = render_html(tall, OUT / "ls200.html")["pages"]
    b = render_html(short, OUT / "ls100.html")["pages"]
    check("줄간격 200% 가 100% 보다 쪽이 많다", a > b, f"200%={a}쪽 100%={b}쪽")


# ---------------------------------------------------------------------------
# 5. 한 문단의 그림을 모두 그리는가
# ---------------------------------------------------------------------------
def test_preview_multi_picture() -> None:
    print("\n[5] 한 문단에 그림 두 장을 나란히 그리는가")
    from hwpx.document import HwpxDocument
    from hwpx._document.media import add_image
    from hwpxkit import render_html

    png = next((p for p in CORPUS.glob("*.png") if p.stat().st_size < 200_000), None)
    if png is None:
        check("표본 이미지가 있다", False)
        return
    dst = OUT / "twopic.hwpx"
    doc = HwpxDocument.new()
    para = doc.add_paragraph("")
    data = png.read_bytes()
    for _ in range(2):
        para.add_picture(str(add_image(doc, data, "png")), width=14400, height=10000)
    doc.save_to_path(str(dst))
    html = render_html(dst, OUT / "twopic.html")["pages"]
    with io.open(OUT / "twopic.html", encoding="utf-8") as fh:
        drawn = fh.read().count("<img")
    check("그림 2장이 모두 그려진다", drawn == 2, f"{drawn}장 그려짐")


# ---------------------------------------------------------------------------
# 6. .hwp 내보내기가 쪽 나눔 설정을 지키는가
# ---------------------------------------------------------------------------
def test_hwp_keeps_split_mode() -> None:
    print("\n[6] .hwp 내보내기가 '셀 단위로 나눔' 을 지키는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import find_converter_jar, make_splittable, to_hwp

    if find_converter_jar() is None:
        check("변환기 jar 이 있다", False, "ref/hwpConverter 빌드 필요 — 건너뜀")
        return
    src = OUT / "split.hwpx"
    doc = HwpxDocument.open(str(FORM))
    seen = set()
    for ref in __import__("hwpxkit").iter_cells(doc):
        if ref.depth == 0 and id(ref.table) not in seen:
            seen.add(id(ref.table))
            make_splittable(ref.table)
            ref.table.element.set("pageBreak", "CELL")
    doc.save_to_path(str(src))
    to_hwp(str(src))
    # 한컴이 만든 파일과 그 짝 HWPX 를 대조한 결과 바이너리 2 가 CELL 이다
    # (양식.hwp 표 5개·온리브.hwp 표 26개 모두 2 ↔ pageBreak="CELL").
    modes = _hwp_table_split_modes(src.with_suffix(".hwp"))
    check("표가 CELL(바이너리 2) 로 저장된다",
          bool(modes) and set(modes) == {2}, f"모드 분포 {modes}")
    # 그리고 다시 읽었을 때도 CELL 로 돌아와야 한다 (예전엔 TABLE 로 뒤집혔다)
    from hwpxkit import hwp_to_hwpx
    back = hwp_to_hwpx(src.with_suffix(".hwp"), OUT / "split_back.hwpx")
    import re as _re
    with zipfile.ZipFile(back) as z:
        got = set(_re.findall(r'<hp:tbl [^>]*pageBreak="(\w+)"',
                              z.read("Contents/section0.xml").decode()))
    check("다시 읽어도 CELL 이다", got == {"CELL"}, f"{got}")


def _hwp_table_split_modes(path: Path) -> list[int]:
    import struct
    import zlib

    import olefile

    ole = olefile.OleFileIO(str(path))
    comp = bool(ole.openstream("FileHeader").read()[36] & 0x01)
    raw = ole.openstream("BodyText/Section0").read()
    data = zlib.decompress(raw, -15) if comp else raw
    out, i = [], 0
    while i + 4 <= len(data):
        (h,) = struct.unpack_from("<I", data, i)
        tag, size = h & 0x3FF, (h >> 20) & 0xFFF
        i += 4
        if size == 0xFFF:
            (size,) = struct.unpack_from("<I", data, i)
            i += 4
        if tag == 0x10 + 61 and size >= 4:
            out.append(struct.unpack_from("<I", data, i)[0] & 0x3)
        i += size
    ole.close()
    return out


# ---------------------------------------------------------------------------
# 7. .hwp 왕복에서 형광펜이 살아 오는가
# ---------------------------------------------------------------------------
def test_hwp_markpen_roundtrip() -> None:
    print("\n[7] .hwp 를 다시 읽을 때 형광펜이 살아 오는가")
    from hwpxkit import find_converter_jar, hwp_to_hwpx, to_hwp
    from hwpx.document import HwpxDocument
    from hwpxkit import find_cells, highlight_cell

    if find_converter_jar() is None:
        check("변환기 jar 이 있다", False, "건너뜀")
        return
    src = OUT / "mark.hwpx"
    doc = HwpxDocument.open(str(ONLIVE))
    hits = find_cells(doc, "온리브")
    if hits:
        highlight_cell(doc, hits[0].cell, "온리브")
    doc.save_to_path(str(src))
    with zipfile.ZipFile(src) as z:
        n_before = z.read("Contents/section0.xml").decode().count("markpenBegin")
    to_hwp(str(src))
    back = hwp_to_hwpx(src.with_suffix(".hwp"), OUT / "mark_back.hwpx")
    with zipfile.ZipFile(back) as z:
        n_after = z.read("Contents/section0.xml").decode().count("markpenBegin")
    check("형광펜이 왕복에서 살아남는다", n_after >= n_before,
          f"{n_before} -> {n_after}")


# ---------------------------------------------------------------------------
# 8. .hwp 를 읽을 때 그림 참조가 뒤섞이지 않는가
# ---------------------------------------------------------------------------
def test_hwp_picture_refs() -> None:
    print("\n[8] .hwp 를 읽을 때 그림 참조가 각각 유지되는가")
    from hwpxkit import hwp_to_hwpx

    hwp = CORPUS / "[2차 진행] U300+ 사업계획서.hwp"
    if not hwp.exists():
        check("표본 .hwp 가 있다", False, "건너뜀")
        return
    back = hwp_to_hwpx(hwp, OUT / "u300_back.hwpx")
    with zipfile.ZipFile(back) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        refs = [img.get("binaryItemIDRef")
                for img in sec.iter("{http://www.hancom.co.kr/hwpml/2011/core}img")]
        bins = [n for n in z.namelist() if "BinData" in n]
    check("그림마다 참조가 다르다", len(refs) > 1 and len(set(refs)) == len(refs),
          f"참조 {len(refs)}개 중 고유 {len(set(refs))}종 / BinData {len(bins)}개")


# ---------------------------------------------------------------------------
# 9~12. 편집 기본기
# ---------------------------------------------------------------------------
def test_primitives() -> None:
    print("\n[9] 크기·서체·정렬·줄나눔·열너비 기본기")
    import hwpxkit

    for name in ("char_style", "ensure_face", "set_align", "keep_korean_words",
                 "autofit_columns", "Img"):
        check(f"hwpxkit.{name} 가 있다", hasattr(hwpxkit, name))


def test_set_cell_newline_font() -> None:
    print("\n[10] set_cell 이 줄바꿈 뒤 문단에도 서체를 물려주는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import find_cells, set_cell

    doc = HwpxDocument.open(str(FORM))
    hits = find_cells(doc, "창업 배경")
    if not hits:
        check("대상 칸이 있다", False)
        return
    cell = hits[0].cell
    set_cell(doc, cell, "첫 줄\n둘째 줄\n셋째 줄")
    ids = {r.element.get("charPrIDRef")
           for p in cell.paragraphs for r in p.runs
           if "".join(t.text or "" for t in r.element.iter(f"{HP}t")).strip()}
    check("모든 줄이 같은 charPr 을 쓴다", len(ids) == 1, f"charPr {sorted(ids)}")


def test_fill_cell_picture() -> None:
    print("\n[11] fill_cell 이 그림 블록을 받는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import Img, fill_cell, find_cells

    png = next((p for p in CORPUS.glob("*.png") if p.stat().st_size < 200_000), None)
    doc = HwpxDocument.open(str(FORM))
    hits = find_cells(doc, "창업 배경")
    if not hits or png is None:
        check("대상 칸과 이미지가 있다", False)
        return
    try:
        fill_cell(doc, hits[0].cell, ["설명", Img(png, width_mm=60)])
    except Exception as exc:
        check("그림 블록을 받는다", False, f"{type(exc).__name__}: {exc}")
        return
    dst = OUT / "fillpic.hwpx"
    doc.save_to_path(str(dst))
    with zipfile.ZipFile(dst) as z:
        n = z.read("Contents/section0.xml").decode().count("<hp:pic ")
    check("그림이 들어갔다", n >= 1, f"{n}장")


# ---------------------------------------------------------------------------
# 12~13. 내보내기 구조 대조 / 열 너비 자동 배분
# ---------------------------------------------------------------------------
def test_export_structure_report() -> None:
    print("\n[12] .hwp 내보내기가 구조를 대조해 보고하는가")
    from hwpxkit import find_converter_jar, to_hwp

    if find_converter_jar() is None:
        check("변환기 jar 이 있다", False, "건너뜀")
        return
    rep = to_hwp(str(OUT / "mark.hwpx"), str(OUT / "mark_s.hwp"))
    check("구조 대조 항목이 보고된다", bool(rep.structure), f"{rep.structure}")
    check("그림·형광펜이 줄지 않았다", not rep.structure_losses,
          f"{rep.structure_losses}")
    # 손실을 실제로 잡는지 — 원본에만 있는 것처럼 꾸며서 확인
    rep.structure["형광펜"] = (99, 3)
    check("손실이 있으면 ok 가 False 가 된다", not rep.ok)
    check("손실이 보고문에 드러난다", "구조 손실" in rep.render())


def test_autofit_columns() -> None:
    print("\n[13] 열 너비를 내용량에 맞춰 나누는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import BoxDoc, Grid, autofit_columns

    doc = HwpxDocument.new()
    b = BoxDoc(doc)
    tbl = b.content_table(["번호", "아주 긴 설명이 들어가는 열", "비고"],
                          [[str(i), "설명 " * 30, "짧음"] for i in range(4)])
    before = [c.width for c in list(tbl.rows)[0].cells]
    widths = autofit_columns(tbl)
    check("너비를 다시 나눈다", bool(widths), f"{before} -> {widths}")
    if not widths:
        return
    check("표 전체 너비는 그대로다", sum(widths) == sum(before),
          f"{sum(before)} -> {sum(widths)}")
    check("글 많은 열이 가장 넓다", widths[1] == max(widths), f"{widths}")
    check("어떤 열도 6% 아래로 안 간다",
          min(widths) >= sum(widths) * 0.055, f"{widths}")


# ---------------------------------------------------------------------------
# 14. 실제로 있었던 사고 재현 — 큰 글자 행을 본문 크기로 재서 찌그러뜨리기
# ---------------------------------------------------------------------------
def test_black_bar_scenario() -> None:
    print("\n[14] '검은 띠' 사고를 재현하고 잡는가")
    from hwpx.document import HwpxDocument
    from hwpxkit import iter_cells, verify
    from hwpx.form_fit.measure import estimate_lines

    # 사고 당시 코드: 문서 전체를 본문 10 pt 로 재서 행 높이를 다시 쓴다.
    # 표제부는 15~17 pt 라 행이 절반으로 줄고, 한/글이 큰 글자를 욱여넣어
    # 글자가 겹친 검은 띠로 그렸다.
    # 사고가 난 그 양식(대학리그)에는 15~17 pt 표제부가 있다. 없으면 U300 양식으로
    # 대신하는데, 그쪽은 본문이 12 pt 라 '글자보다 낮은 행' 쪽은 재현되지 않는다.
    real = next((p for p in (ROOT / "hanuel-bio" / "work").glob("form.hwpx")), None) \
        or CORPUS / "next" / "hanuel-bio" / "work" / "form.hwpx"
    form = real if real is not None and real.exists() else FORM
    big_font = form is real
    dst = OUT / "blackbar.hwpx"
    doc = HwpxDocument.open(str(form))
    pitch = int(10 * 100 * 1.3)
    seen = set()
    for ref in iter_cells(doc):
        if ref.depth != 0 or id(ref.table.element) in seen:
            continue
        seen.add(id(ref.table.element))
        for row in ref.table.rows:
            need = pitch
            for cell in row.cells:
                text = " ".join(p_.text or "" for p_ in [])
                need = max(need, pitch)
            for cell in row.cells:
                cell.set_size(height=need)      # 축소를 허용한 옛 동작
    doc.save_to_path(str(dst))

    text = verify(str(dst), baseline=str(form)).render()
    check("축소를 잡는다", "행 높이 축소" in text and "FAIL" in text,
          "" if "행 높이 축소" in text else text[:120])
    if big_font:
        check("큰 글자가 안 들어가는 행을 잡는다", "새로 글자보다 낮아졌다" in text,
              "" if "새로 글자보다 낮아졌다" in text else "보고 없음")
    else:
        print("       (표제부가 큰 양식이 없어 두 번째 항목은 건너뜀)")


def main() -> int:
    missing = [p for p in (ONLIVE, FORM) if not p.exists()]
    if missing:
        # 실패로 찍으면 "고쳐야 할 결함"으로 읽힌다. 표본이 없는 것은 결함이
        # 아니라 이 기계에 표본이 없는 것뿐이다.
        print(f"표본 문서가 없어 건너뛴다 (HWPX_CORPUS 로 위치를 알려 줄 것):\n"
              + "\n".join(f"  없음: {p}" for p in missing))
        return 0

    tests = [test_page_count_honest, test_shrink_regression, test_row_fits_font,
             test_preview_line_spacing, test_preview_multi_picture,
             test_hwp_keeps_split_mode, test_hwp_markpen_roundtrip,
             test_hwp_picture_refs, test_primitives,
             test_set_cell_newline_font, test_fill_cell_picture,
             test_export_structure_report, test_autofit_columns,
             test_black_bar_scenario]
    for fn in tests:
        try:
            fn()
        except Exception as exc:            # noqa: BLE001 — 실패도 결과다
            import traceback
            check(fn.__name__, False, f"{type(exc).__name__}: {exc}")
            traceback.print_exc(limit=3)
    passed = sum(1 for ok, _, _ in _results if ok)
    print(f"\n{'=' * 60}\n합계: {passed}/{len(_results)} 통과")
    for ok, name, detail in _results:
        if not ok:
            print(f"  남은 결함: {name}" + (f" — {detail}" if detail else ""))
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
