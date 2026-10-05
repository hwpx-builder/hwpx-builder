# -*- coding: utf-8 -*-
"""문장 검토(hwpxkit.prose)와 줄 나눔(hwpxkit.wrap) 회귀 테스트.

실행:  .venv/Scripts/python.exe tests/test_prose.py
"""
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hwpx.document import HwpxDocument  # noqa: E402

from hwpxkit import (BoxDoc, Grid, bold_figures, estimate_lines,  # noqa: E402
                     review_blocks, review_document, review_text, verify)

OUT = ROOT / "out"
OUT.mkdir(exist_ok=True)
FAILED = 0


def check(name: str, ok: bool, detail: str = "") -> bool:
    global FAILED
    print(f"  {'OK  ' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILED += 1
    return ok


GOOD = ("대표자는 교내 학생지원팀에서 **2년간** 분실물 접수 업무를 맡았다. "
        "접수된 분실물의 **절반 이상**이 주인을 찾지 못한 채 폐기됐다. "
        "==원인은 물건이 없어서가 아니라 찾는 사람과 보관 장소가 서로를 모르기 때문이다.== "
        "이 격차를 좁히는 것이 출발점이다.")
BAD = ("본 서비스는 다양한 사용자에게 효과적으로 가치를 제공한다. "
       "이를 통해 시장에서 차별화된 경쟁력을 확보할 수 있을 것으로 기대된다. "
       "또한 매출이 크게 증가한다. 또한 지속 가능한 성장이 예상된다.")


def test_review_text() -> None:
    print("\n[1] review_text")
    bad = review_text(BAD, where="bad")
    kinds = {f.kind for f in bad}
    check("상투어를 잡는다", "cliche" in kinds, str(sorted(kinds)))
    check("빠져나가는 어미를 잡는다", "hedge" in kinds)
    check("숫자 없는 주장을 잡는다", "claim" in kinds)
    check("강조 없음을 잡는다", {"no-bold", "no-highlight"} <= kinds)
    good = review_text(GOOD, where="good")
    check("좋은 글은 FIX 가 없다", not [f for f in good if f.severity == "fix"],
          "; ".join(str(f) for f in good))
    heading = review_text("**1. 문제 인식 / Problem Recognition - 왜 지금 이 문제인가**")
    check("전부 굵은 제목은 강조 규칙에서 뺀다", not heading, str(heading))
    label = review_text("□ 아이템 개요\n(아이템 한줄소개) /\nIdea Overview (one line)")
    check("마침표 없는 짧은 줄 묶음(양식 라벨)은 뺀다", not label, str(label))


def test_review_blocks() -> None:
    print("\n[2] review_blocks — 만들기 전 검토")
    content = {"1. 문제": [("□ 배경", [GOOD, Grid(headers=["a"], rows=[["다양한 것"]])]),
                          ("□ 목표", [BAD])]}
    fs = review_blocks(content)
    check("dict/list/Grid 를 재귀로 돈다", bool(fs))
    check("경로에 절과 라벨이 들어간다", any("1. 문제/목표" in f.where for f in fs),
          str({f.where for f in fs}))
    check("Grid 칸은 짧으면 검토하지 않는다", not any("grid" in f.where for f in fs))


def test_bold_figures() -> None:
    print("\n[3] bold_figures")
    s = "임계값 두 개로 **93.0%**(318/342)를 맞춘다. 3개월마다 약 2억 원, 38.8 ± 2.7 mm. fig1 과 U300, https://x.com/a1 은 그대로."
    b = bold_figures(s)
    check("숫자에 굵게", "**318/342**" in b and "**3개월**" in b and "**2억 원**" in b, b)
    check("범위·오차도 한 덩어리", "**38.8 ± 2.7 mm**" in b, b)
    check("이미 강조된 것은 건드리지 않는다", b.count("**93.0%**") == 1 and "****" not in b)
    check("식별자·URL 은 건드리지 않는다", "fig1" in b and "U300" in b and "/a1" in b and "**1**" not in b, b)
    check("멱등", bold_figures(b) == b)
    hl = bold_figures("==부리 길이 두 값==을 조합하면 79.2%")
    check("형광펜 안은 그대로", hl == "==부리 길이 두 값==을 조합하면 **79.2%**", hl)


def test_wrap() -> None:
    print("\n[4] 줄 나눔 기준")
    from hwpx.form_fit.measure import estimate_lines as ref
    t = ("대표자는 교내 학생지원팀에서 근로장학생으로 2년간 분실물 접수 업무를 맡았다. "
         "접수된 분실물의 상당수가 주인을 찾지 못한 채 폐기되는 것을 반복해서 목격했다.")
    ok_eq = all(estimate_lines(t, w, 10) == ref(t, w, 10) for w in (6000, 8000, 12000, 20000, 34000))
    check("글자 단위는 python-hwpx 와 같다", ok_eq)
    ok_ge = all(estimate_lines(t, w, 10, keep_words=True) >= estimate_lines(t, w, 10)
                for w in (6000, 8000, 12000, 20000, 34000))
    check("어절 단위는 글자 단위보다 줄이 적지 않다", ok_ge)
    check("한 어절이 칸보다 길면 글자에서 강제로 끊는다",
          estimate_lines("가" * 40, 8000, 10, keep_words=True) > 1)


def test_boxdoc_keep_words() -> None:
    print("\n[5] BoxDoc 은 어절 단위로 만든다")
    doc = HwpxDocument.new()
    b = BoxDoc(doc, bold_figures=True)
    b.section_heading("1. 절")
    b.container_box([("□ 라벨 / Label", [GOOD, "매출은 3년차에 12억 원이다."])])
    b.label_value_box([("□ 팀명", "벳츄원 3명")])
    path = OUT / "prose_keep.hwpx"
    doc.save_to_path(str(path))
    header = zipfile.ZipFile(path).read("Contents/header.xml").decode("utf-8")
    check("저장된 헤더가 전부 KEEP_WORD", 'breakNonLatinWord="BREAK_WORD"' not in header
          and header.count('breakNonLatinWord="KEEP_WORD"') > 0)
    sec = zipfile.ZipFile(path).read("Contents/section0.xml").decode("utf-8")
    check("본문 숫자가 굵게 들어갔다 (bold_figures)", "12억 원" in sec)
    rep = verify(path)
    names = {r.name for r in rep.results}
    check("verify 에 korean word wrap / prose review 줄이 있다",
          {"korean word wrap", "prose review"} <= names, str(sorted(names)))
    wrap_line = next(r for r in rep.results if r.name == "korean word wrap")
    check("word wrap 줄이 어절 단위라고 말한다", "어절" in wrap_line.detail, wrap_line.detail)
    pr = review_document(path)
    check("라벨 행·제목은 강조 과다로 걸리지 않는다",
          not any(f.kind == "over-emphasis" for f in pr.findings),
          "; ".join(str(f) for f in pr.findings))

    doc2 = HwpxDocument.new()
    BoxDoc(doc2, keep_words=False)
    p2 = OUT / "prose_break.hwpx"
    doc2.save_to_path(str(p2))
    h2 = zipfile.ZipFile(p2).read("Contents/header.xml").decode("utf-8")
    check("keep_words=False 면 손대지 않는다", 'breakNonLatinWord="BREAK_WORD"' in h2)


def test_human_choices() -> None:
    print("\n[6] 사람이 안 하는 선택 — 줄표, 가운뎃점, 번호 굵게, 편집 흔적")
    from hwpxkit import humanize_punct, is_identifier
    from hwpxkit.richtext import parse_markup
    fs = review_text("**US20230399389A1** 은 청구항이 좁다 — 다만 기술·사업화 쪽은 다르다.")
    kinds = [f.kind for f in fs]
    check("줄표·가운뎃점을 잡는다", kinds.count("typography") == 2, str(kinds))
    check("특허 번호 굵게를 잡는다", "bold-id" in kinds, str(kinds))
    check("숫자 굵게는 식별자가 아니다",
          not any(is_identifier(x) for x in ("93.0%", "318/342", "2026.09.28", "U300", "12억 원")))
    check("출원·논문 번호는 식별자다",
          all(is_identifier(x) for x in ("US20230399389A1", "WO2024220398",
                                         "10-2023-0012345", "PMC7156987")))
    b = bold_figures("출원번호 10-2023-0012345, 매출 12억 원")
    check("bold_figures 는 출원번호를 굵게 하지 않는다",
          "**10-2023" not in b and "**12억 원**" in b, b)
    h = humanize_punct("A — B, 3–5개, 기술·사업화\n· 글머리표")
    check("humanize_punct", h == "A - B, 3-5개, 기술/사업화\n· 글머리표", h)
    spans = parse_markup("**기술·사업화** — 요약")
    text = "".join(sp.text for sp in spans)
    check("parse_markup 이 새 글에 적용한다", text == "기술/사업화 - 요약", text)
    trace = review_text("이번 개정에서 표현을 바꿨다. ※ 수정: 원가 행 삭제 (2026-09-29 확인)")
    check("편집 흔적을 잡는다", sum(f.kind == "edit-trace" for f in trace) >= 2,
          "; ".join(map(str, trace)))


def test_mode_and_register() -> None:
    print("\n[7] 문서 종류(mode)와 문체(register)")
    opinion = ("Virbac 특허는 키토산 소포체가 털에 남을 수 있다는 근거입니다. "
               "제형의 실제 잔류성은 **3회** 세척 실험으로 확인해야 하는 것으로 보입니다. "
               "==이 점이 가장 유력한 진보성 근거 중 하나인 것 같습니다.==")
    pitch = {f.kind for f in review_text(opinion)}
    research = {f.kind for f in review_text(opinion, mode="research")}
    check("pitch 는 낮춘 어미를 잡는다", "hedge" in pitch, str(pitch))
    check("research 는 의견을 낮춰 말하는 것을 허용한다", "hedge" not in research,
          str(research))
    strong = review_text("운반체가 털에 남는다는 전제는 이미 확인되어 있습니다. "
                         "IgG 와 IgY 는 같게 볼 수 있습니다.", mode="research")
    check("research 는 과잉 단정을 FIX 로", sum(f.kind == "overclaim" and f.severity == "fix"
                                             for f in strong) >= 2, str(strong))
    mixed = "우리는 수의사 답변만 보여줍니다. 검색 결과는 출처를 알 수 없다. 예약까지 이어집니다."
    reg = [f for f in review_text(mixed, register="합니다") if f.kind == "register"]
    check("합니다체 문서에서 한다체 문장을 잡는다", len(reg) == 1 and "출처" in reg[0].text,
          str(reg))
    auto = [f for f in review_blocks({"a": [mixed]}) if f.kind == "register"]
    check("원고 검토는 문체를 스스로 정해 섞인 문장을 잡는다", len(auto) == 1, str(auto))
    gaejo = review_text("- 수의사 인증 후 답변 공개\n- 병원 예약 연결", register="합니다")
    check("마침표 없는 개조식 줄은 합니다체 문서에서도 허용", not gaejo, str(gaejo))


def test_figure_and_pages() -> None:
    print("\n[8] 그림(크롭·출처)과 쪽수 검사")
    import glob
    from hwpxkit import Img
    from hwpxkit.boxdoc import caption_line, image_bytes
    imgs = sorted(glob.glob(str(ROOT / "docs" / "images" / "*.png")))
    if not imgs:
        check("표본 그림이 있다", False, "docs/images/*.png 없음")
        return
    data, fmt = image_bytes(imgs[0], (0, 0, 0.5, 0.5))
    from PIL import Image
    import io
    w0, h0 = Image.open(imgs[0]).size
    w1, h1 = Image.open(io.BytesIO(data)).size
    check("crop 비율로 자른다", (w1, h1) == (round(w0 / 2), round(h0 / 2)), f"{w0}x{h0} -> {w1}x{h1}")
    check("캡션과 출처는 한 줄", caption_line("[그림 1] 털 SEM", "Kim 2024")
          == "[그림 1] 털 SEM (출처: Kim 2024)")
    doc = HwpxDocument.new()
    b = BoxDoc(doc, bold_figures=True)
    b.figure(imgs[0], width_mm=60, caption="[그림 1] 시험", source="Satyaraj 2019")
    b.container_box([("□ 박스", ["설명 줄입니다.", Img(imgs[0], width_mm=50, source="자체 제작")])])
    path = OUT / "prose_figure.hwpx"
    doc.save_to_path(str(path))
    sec = zipfile.ZipFile(path).read("Contents/section0.xml").decode("utf-8")
    check("박스 안에도 그림이 들어간다", sec.count("<hp:pic") == 2, str(sec.count("<hp:pic")))
    check("출처 줄이 들어간다", "출처: Satyaraj 2019" in sec and "출처: 자체 제작" in sec)
    rep = verify(path, max_pages=1)
    names = {r.name: r for r in rep.results}
    check("page limit / page fill 줄이 있다", {"page limit", "page fill"} <= set(names),
          str(sorted(names)))
    tight = verify(path, max_pages=0, prose=False)
    check("제한을 넘으면 page limit 실패",
          not next(r for r in tight.results if r.name == "page limit").ok)


def main() -> int:
    test_review_text()
    test_review_blocks()
    test_bold_figures()
    test_wrap()
    test_boxdoc_keep_words()
    test_human_choices()
    test_mode_and_register()
    test_figure_and_pages()
    print("\n" + ("전부 통과" if not FAILED else f"{FAILED}건 실패"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
