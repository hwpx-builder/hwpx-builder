"""검증. 구조 검사를 먼저 하고, 그 다음 렌더 검사를 한다.

일부러 싼 것부터 층을 쌓았다:

1. **패키지 + 기하** — 렌더러 불필요, 밀리초 단위. 깨진 ZIP, 끊어진
   ``binaryItemIDRef``, 표 너비와 안 맞는 열 너비 합계를 잡는다.
2. **자체 조판 렌더** (:mod:`hwpxkit.preview`) — 문서당 0.02~0.3초. 쪽수,
   빈 쪽, 본문 폭 초과, 사진 밀림 공백, 형광펜 렌더 짝을 잡는다. lineseg
   캐시를 재생하지 않고 직접 조판하므로 갓 만든 문서에도 유효하다.
3. **한글 COM** — 픽셀 단위 결과에 대한 유일한 권위. 다만 한글 **2014 이상**이
   필요하다. 한글 2010 은 HWPX 를 아예 파싱하지 못하면서도 ``Open()`` 이
   ``True`` 를 돌려주므로 *가짜* 오라클이다. 쓰지 않는다.

정직성 규칙: 어떤 층이 실행되지 못했으면 결과는 ``checked=False`` —
"아무것도 검증하지 않았다" — 이지, 조용한 통과가 아니다.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

#: 예전에 이 이름을 import 하던 코드를 위해 남겨 둔다. 실제 메시지는 이제


@dataclass
class CheckResult:
    name: str
    ok: bool
    checked: bool = True
    detail: str = ""

    def __str__(self) -> str:
        if not self.checked:
            return f"  ~  {self.name}: NOT VERIFIED ({self.detail})"
        mark = "OK " if self.ok else "FAIL"
        return f"  {mark} {self.name}{': ' + self.detail if self.detail else ''}"


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, *results: CheckResult) -> None:
        self.results.extend(results)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.checked and not r.ok]

    @property
    def unverified(self) -> list[CheckResult]:
        return [r for r in self.results if not r.checked]

    @property
    def ok(self) -> bool:
        return not self.failed

    def render(self) -> str:
        lines = [str(r) for r in self.results]
        lines.append("")
        if self.failed:
            lines.append(f"RESULT: {len(self.failed)} check(s) FAILED")
        elif self.unverified:
            lines.append(
                f"RESULT: structural checks passed; "
                f"{len(self.unverified)} check(s) NOT VERIFIED"
            )
        else:
            lines.append("RESULT: all checks passed")
        return "\n".join(lines)


def check_package(path: str | Path) -> list[CheckResult]:
    """ZIP 무결성과 모든 HWPX 가 반드시 가져야 하는 파트."""
    path = Path(path)
    out: list[CheckResult] = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            bad = z.testzip()
            out.append(CheckResult("zip integrity", bad is None,
                                   detail="" if bad is None else f"corrupt: {bad}"))
            required = ["mimetype", "version.xml", "Contents/content.hpf",
                        "Contents/header.xml", "META-INF/manifest.xml"]
            missing = [n for n in required if n not in names]
            out.append(CheckResult("required parts", not missing,
                                   detail="" if not missing else f"missing {missing}"))
            sections = [n for n in names if n.startswith("Contents/section")]
            out.append(CheckResult("section parts", bool(sections),
                                   detail=f"{len(sections)} section(s)"))
            # mimetype 은 ZIP 의 첫 엔트리이면서 무압축이어야 한다 (ODF 관례).
            info = z.infolist()
            first_ok = bool(info) and info[0].filename == "mimetype"
            stored_ok = bool(info) and info[0].compress_type == zipfile.ZIP_STORED
            out.append(CheckResult(
                "mimetype first+stored", first_ok and stored_ok,
                detail="" if first_ok and stored_ok
                else f"first={info[0].filename if info else None} "
                     f"stored={stored_ok}"))
    except zipfile.BadZipFile as exc:
        out.append(CheckResult("zip integrity", False, detail=str(exc)))
    return out


def check_markpen_pairs(path: str | Path) -> CheckResult:
    """``markpenBegin`` 과 ``markpenEnd`` 는 모든 섹션에서 짝이 맞아야 한다.

    짝 잃은 ``markpenBegin`` 하나가 문서 나머지 전체에 형광색을 번지게 한다.
    추출한 텍스트만 봐서는 보이지 않는 결함이다.
    """
    begins = ends = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("Contents/section") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "replace")
                begins += xml.count("<hp:markpenBegin")
                ends += xml.count("<hp:markpenEnd")
    return CheckResult(
        "markpen pairing", begins == ends,
        detail=f"{begins} begin / {ends} end",
    )


def check_binary_refs(path: str | Path) -> CheckResult:
    """모든 ``binaryItemIDRef`` 가 실제 ``BinData/`` 항목으로 이어져야 한다."""
    import re

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        bindata = {n.split("/")[-1].split(".")[0].lower()
                   for n in names if n.startswith("BinData/")}
        manifest = ""
        if "META-INF/manifest.xml" in names:
            manifest = z.read("META-INF/manifest.xml").decode("utf-8", "replace")
        refs: set[str] = set()
        for name in names:
            if name.startswith("Contents/section") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "replace")
                refs.update(re.findall(r'binaryItemIDRef="([^"]+)"', xml))

    if not refs:
        return CheckResult("binary refs", True, detail="no images")

    unresolved = [r for r in refs
                  if r.lower() not in bindata and r not in manifest]
    return CheckResult(
        "binary refs", not unresolved,
        detail=f"{len(refs)} ref(s)" if not unresolved
        else f"unresolved: {unresolved}",
    )


def check_cell_overflow(path: str | Path, *, font_pt: float = 10.0) -> CheckResult:
    """렌더러 없이 셀의 가로 넘침을 예측한다.

    ``hwpx.form_fit.measure`` 를 쓴다. 이 모듈의 글자 폭은 실제 한글이 남긴 줄
    캐시에 맞춰 보정돼 있다(한글/전각은 정확, 라틴은 근사). 여기서 쓸 수 있는
    넘침 신호 중 신뢰할 수 있는 것은 이것뿐이다. rhwp 는 문서에 캐시된
    ``linesegarray`` 를 재생하는 쪽에 가까워서, 새로 만든 파일은 판단하지
    못한다.

    한 셀에서 끊을 수 없는 단어가 하나라도 있으면 실패로 본다. 한글이 줄을
    나눌 수 없어 셀 경계를 밀고 나가는 텍스트이기 때문이다.
    """
    try:
        offenders = _overflow_offenders(path, font_pt=font_pt)
    except Exception as exc:
        return CheckResult("cell overflow", False, checked=False, detail=str(exc))

    words = [w for _, w in offenders]
    return CheckResult(
        "cell overflow", not offenders,
        detail="no unbreakable overflow" if not offenders
        else f"{len(offenders)} cell(s) overflow, e.g. {words[:3]}",
    )


def _overflow_offenders(path: str | Path, *, font_pt: float = 10.0
                        ) -> list[tuple[str, str]]:
    """텍스트가 안 들어가는 셀마다 ``(셀 경로, 문제 단어)``."""
    from hwpx.document import HwpxDocument
    from hwpx.form_fit.measure import estimate_text_width

    from .boxdoc import CELL_PAD
    from .edit import iter_cells

    doc = HwpxDocument.open(str(path))
    offenders: list[tuple[str, str]] = []
    for ref in iter_cells(doc):
        inner = (ref.cell.width or 0) - 2 * CELL_PAD
        if inner <= 0:
            continue
        for para in ref.cell.paragraphs:
            hit = None
            for word in _longest_words(para):
                if estimate_text_width(word, font_pt) > inner:
                    hit = word[:28]
                    break
            if hit:
                offenders.append((ref.path, hit))
                break
    return offenders


def _iter_tables(section):
    """섹션 안의 모든 표(중첩 포함).

    별칭으로 남겨 둔다. 이 순회 함수는 :mod:`hwpxkit.edit` 로 옮겨갔다.
    편집 쪽에서 같은 순회를 안정적인 주소와 함께 쓰기 때문이다.
    """
    from .edit import iter_tables

    return iter_tables(section)


def _longest_words(paragraph) -> list[str]:
    from .richtext import paragraph_text

    text = paragraph_text(paragraph)
    # 한글은 음절 사이에서 줄이 바뀌므로, 공백으로 구분된 라틴/숫자 덩어리만
    # 진짜로 끊을 수 없는 단어다.
    return [w for w in text.split() if w and not any("가" <= c <= "힣" for c in w)]


def check_against_baseline(path: str | Path, baseline: str | Path) -> list[CheckResult]:
    """편집한 파일을 그 원본과 비교한다.

    편집에는 새로 만들 때는 있을 수 없는 실패 방식이 하나 있다. 텍스트는
    바뀌었는데 ``<hp:linesegarray>`` 가 그대로 남은 문단이다. 그러면 한글이 새
    텍스트를 옛 줄 자리에 그려서 글자가 겹친다. 파일 하나만 봐서는 이걸 알 수
    없고 편집 전후 쌍이 필요하다. 그래서 이 검사만 baseline 을 받는다.

    얼마나 바뀌었는지도 함께 보고한다. 의도보다 많은 셀을 건드린 편집이
    묻히지 않고 눈에 보이도록.
    """
    try:
        from hwpx.document import HwpxDocument

        from .edit import cached_line_count, iter_cells
        from .richtext import paragraph_text
    except Exception as exc:
        return [CheckResult("baseline diff", False, checked=False, detail=str(exc))]

    def snapshot(p):
        doc = HwpxDocument.open(str(p))
        out: dict[str, list[tuple[str, bool]]] = {}
        for ref in iter_cells(doc):
            out[ref.path] = [
                (paragraph_text(par), cached_line_count(par) is not None)
                for par in ref.cell.paragraphs
            ]
        body = [paragraph_text(par)
                for sec in doc.sections for par in (sec.paragraphs or [])]
        return out, body

    try:
        before, before_body = snapshot(baseline)
        after, after_body = snapshot(path)
    except Exception as exc:
        return [CheckResult("baseline diff", False, checked=False,
                            detail=f"{type(exc).__name__}: {exc}")]

    stale: list[str] = []
    changed = 0
    for path_key, paras in after.items():
        old = before.get(path_key)
        if old is None:
            continue
        for i, (text, has_cache) in enumerate(paras):
            if i >= len(old):
                continue
            if text != old[i][0]:
                changed += 1
                # 원래 캐시를 *가지고 있던* 문단만 낡은 캐시를 남길 수 있다.
                if has_cache and old[i][1]:
                    stale.append(f"{path_key}#{i}")

    body_changed = sum(1 for a, b in zip(after_body, before_body) if a != b)
    out = [CheckResult(
        "edit scope", True,
        detail=f"{changed} cell paragraph(s), {body_changed} body paragraph(s) changed")]
    out.append(CheckResult(
        "layout cache invalidated", not stale,
        detail="all edited paragraphs re-flow"
        if not stale else f"{len(stale)} stale: {stale[:3]}"))

    # 편집이 형광펜 균형을 어느 방향으로도 바꾸면 안 된다.
    b_pairs = check_markpen_pairs(baseline)
    a_pairs = check_markpen_pairs(path)
    out.append(CheckResult(
        "markpen preserved", a_pairs.ok,
        detail=f"baseline {b_pairs.detail} -> edited {a_pairs.detail}"))

    # 실제 제출 서식은 결함을 이미 안고 온다. 실측한 두 문서 모두 손대기 전부터
    # 셀 하나가 넘쳐 있었다. 그걸 편집 탓으로 돌리면 사용자가 이 검사를 무시하게
    # 되므로, 원래 있던 것인지 새로 생긴 것인지 구분해서 알려 준다.
    try:
        was = {p for p, _ in _overflow_offenders(baseline)}
        now = _overflow_offenders(path)
        introduced = [(p, w) for p, w in now if p not in was]
        inherited = len(now) - len(introduced)
        out.append(CheckResult(
            "overflow introduced", not introduced,
            detail=f"{inherited} pre-existing, none added" if not introduced
            else f"{len(introduced)} new: {introduced[:3]}"))
    except Exception as exc:
        out.append(CheckResult("overflow introduced", False, checked=False,
                               detail=str(exc)))
    return out


def _row_geometry(path):
    """문서의 행 높이와 그 행이 담은 최대 글자 크기.

    반환: ``{"s0/t3/r1": (행높이, 최대pt)}``. 행을 키로 잡는 이유는 한/글이
    행 단위로 높이를 맞추기 때문이다.
    """
    from hwpx.document import HwpxDocument

    from .edit import iter_cells

    doc = HwpxDocument.open(str(path))
    header = doc.headers[0].element
    sizes: dict[str, float] = {}
    out: dict[str, tuple[int, float]] = {}
    for cp in header.iter(f"{HH}charPr"):
        try:
            sizes[cp.get("id")] = int(cp.get("height", "1000")) / 100
        except (TypeError, ValueError):
            pass
    # **최상위 표만** 본다. `table_index` 는 중첩 표까지 번호를 매기므로, 우리가
    # 칸 안에 표를 넣으면 그 뒤 번호가 전부 밀린다 — 원본의 t5 와 결과의 t5 가
    # 서로 다른 표가 되어, 멀쩡한 편집이 "행 높이 축소"로 잡혔다(실측).
    # 최상위 표 순서로 다시 번호를 매기면 중첩 표를 몇 개 넣든 짝이 유지된다.
    # 한 번만 순회한다. `iter_cells` 는 돌 때마다 래퍼 객체를 새로 만들어서
    # `id(ref.table)` 이 순회 사이에 유지되지 않는다 — 두 번 돌면 KeyError 다.
    order: dict[int, int] = {}
    for ref in iter_cells(doc):
        if ref.depth != 0:
            continue
        seq = order.setdefault(id(ref.table.element), len(order))
        key = f"s{ref.section}/T{seq}/r{ref.row}"
        pt = 0.0
        for para in ref.cell.paragraphs:
            for run in para.runs:
                pt = max(pt, sizes.get(run.element.get("charPrIDRef"), 0.0))
        height, _ = out.get(key, (0, 0.0))
        out[key] = (max(height, ref.cell.height or 0), max(pt, _))
    return out


def check_row_geometry(path: str | Path,
                       baseline: str | Path | None = None) -> list[CheckResult]:
    """행 높이가 (a) 원본보다 줄지 않았고 (b) 자기 글자를 담는가.

    이 검사가 없어서 실제로 제출 직전 문서를 한 번 망가뜨렸다. 행 높이를 다시
    계산하면서 표제부의 17 pt 줄을 본문 10 pt 기준으로 재는 바람에 행이 3179
    에서 1866 HWPUNIT 으로 줄었고, 한/글은 그 칸에 큰 글자를 욱여넣어 **글자가
    서로 겹친 검은 띠**로 그렸다. 구조 검사도 미리보기도 통과했다 — 미리보기는
    행을 내용에 맞춰 늘려 그리므로 오히려 멀쩡해 보였다.

    **축소 금지가 본 검사다.** 남의 양식을 채우면서 행을 원본보다 낮출 이유는
    없다. 내용이 늘었으면 키우는 것이 맞고, 줄어드는 쪽은 대개 계산 실수다.
    *baseline* 이 있을 때만 볼 수 있고, 실제 결함을 정확히 재현한다.

    절대 기준(글자가 물리적으로 안 들어가는 높이)도 함께 보지만 **한/글이 저장한
    실문서에도 그런 행이 흔하다** — 셀 높이는 최소값 힌트고 한/글이 열면서
    늘리기 때문이다. 실측: 온리브 18행, U300 23행이 pt·줄간격 기준에 못 미친다.
    그래서 기준을 "글자 몸통도 안 들어가는 높이"까지 낮추고, ``overflow
    introduced`` 와 같은 방식으로 **원본에 있던 것과 새로 생긴 것을 나눠서**
    보고한다. 원래 그랬던 것을 우리 결함으로 세면 검사를 아무도 안 믿게 된다.
    """
    out: list[CheckResult] = []
    try:
        now = _row_geometry(path)
    except Exception as exc:                       # noqa: BLE001
        return [CheckResult("행 높이", False, checked=False, detail=str(exc))]

    def too_tight(geo):
        # 글자 몸통(pt * 100 HWPUNIT)조차 안 들어가는 행. 여백·줄간격은 뺀다 —
        # 그것까지 요구하면 실문서가 무더기로 걸린다.
        return {k for k, (h, pt) in geo.items() if pt and h and h < pt * 100}

    tight_now = too_tight(now)
    if baseline is None:
        out.append(CheckResult(
            "행 높이 대 글자 크기", not tight_now,
            detail="모든 행이 자기 글자를 담는다" if not tight_now
            else f"{len(tight_now)}행이 글자보다 낮다 (원본부터 그런지는 "
                 f"baseline 없이 알 수 없다): " + ", ".join(sorted(tight_now)[:3])))
        return out

    try:
        was = _row_geometry(baseline)
    except Exception as exc:                       # noqa: BLE001
        out.append(CheckResult("행 높이 축소", False, checked=False, detail=str(exc)))
        return out

    shrunk = [(k, was[k][0], now[k][0]) for k in now
              if k in was and now[k][0] < was[k][0]]
    out.append(CheckResult(
        "행 높이 축소", not shrunk,
        detail="원본보다 낮아진 행 없음" if not shrunk
        else f"{len(shrunk)}행 축소: " + ", ".join(
            f"{k} {a}->{b}" for k, a, b in shrunk[:3])))

    inherited = tight_now & too_tight(was)
    introduced = tight_now - inherited
    out.append(CheckResult(
        "행 높이 대 글자 크기", not introduced,
        detail=f"{len(inherited)}행은 원본부터, 새로 생긴 것 없음" if not introduced
        else f"{len(introduced)}행이 새로 글자보다 낮아졌다: "
             + ", ".join(sorted(introduced)[:3])))
    return out


#: 마지막 쪽이 아닌 쪽이 본문 높이의 이 비율도 못 채우면 "빈 공간" 으로 본다.
MIN_PAGE_FILL = 0.6


def check_layout(path: str | Path, *, min_pages: int = 1,
                 max_pages: int | None = None) -> list[CheckResult]:
    """자체 조판 엔진(:mod:`hwpxkit.preview`)으로 배치를 검사한다.

    rhwp 와 달리 lineseg 캐시를 재생하지 않고 직접 조판하므로, **캐시가 없는
    새 문서**의 쪽수·표 분할·사진 배치를 실제로 판단할 수 있다. 실측 대조
    (한글 2010): 쪽수는 정확 일치 또는 +1 보수. 형광펜도 이 엔진은 실제로
    그리므로 렌더 레벨 짝 검사가 가능하다.

    표준 라이브러리 + Apache-2.0 재료만 쓴다 — 어느 프로파일에서든 돈다.
    """
    import re as _re
    import zipfile as _zip

    from .preview import render_html

    out: list[CheckResult] = []
    try:
        info = render_html(path, out=None)
    except Exception as exc:
        return [CheckResult("layout engine", False, detail=f"조판 실패: {exc}")]

    fill = info.get("page_fill") or []
    last = f", 마지막 쪽 {fill[-1]:.0%}" if fill else ""
    out.append(CheckResult(
        "layout renders", info["pages"] >= min_pages,
        detail=f"{info['pages']} page(s){last}, 자체 조판 (한컴 대비 ±1쪽 가능)"))

    # 쪽수 제한 ("1페이지 내외", "5쪽 이내"). 엔진이 ±1쪽 틀릴 수 있으므로
    # 경계에 걸리면 detail 에 적는다 — 통과여도 마지막 쪽이 거의 찼으면
    # 한컴에서 넘칠 수 있다.
    if max_pages is not None:
        n = info["pages"]
        if n > max_pages:
            hint = (f"마지막 쪽 {fill[-1]:.0%} — 그만큼만 줄이면 된다"
                    if n - max_pages == 1 and fill else "분량을 줄인다")
            detail = f"{n}쪽 > 제한 {max_pages}쪽: {hint}"
        else:
            edge = n == max_pages and fill and fill[-1] > 0.9
            detail = f"{n}쪽 ≤ {max_pages}쪽" + (
                f" — 마지막 쪽이 {fill[-1]:.0%} 라 한컴에서 넘칠 수 있다" if edge else "")
        out.append(CheckResult("page limit", n <= max_pages, detail=detail))

    # 쪽 중간의 빈 공간. 통째로 넘어가는 표/그림이 앞 쪽 아래를 비운다.
    # 강제 쪽 나눔으로 끝난 쪽(표지, 붙임)은 의도한 것이라 뺀다.
    forced = set(info.get("forced_breaks") or [])
    sparse = [(i, f) for i, f in enumerate(fill[:-1], 1)
              if f < MIN_PAGE_FILL and i not in forced]
    out.append(CheckResult(
        "page fill", not sparse,
        detail=(f"마지막 쪽 말고는 모두 {MIN_PAGE_FILL:.0%} 이상 찼다" if not sparse
                else "빈 공간이 큰 쪽: " + ", ".join(f"{i}쪽 {f:.0%}" for i, f in sparse[:5])
                + " — 뒤의 큰 표/그림이 통째로 밀렸다. 그림을 줄이거나(fit_pictures), "
                  "표를 나뉘게 하거나(make_splittable), 순서를 바꾼다")))
    out.append(CheckResult(
        "no empty pages", info["empty_pages"] == 0,
        detail="all pages carry content" if not info["empty_pages"]
        else f"{info['empty_pages']} empty page(s)"))
    out.append(CheckResult(
        "body width respected", not info["warnings"],
        detail="no table exceeds the text body"
        if not info["warnings"] else "; ".join(info["warnings"])))

    gaps = [p for p in info["pictures"]
            if p["gap_before"] > 0.12 * info["body_height"]]
    out.append(CheckResult(
        "picture push gaps", not gaps,
        detail="no oversized page-bottom gaps" if not gaps
        else f"{len(gaps)} gap(s) over 12% of body — fit_pictures() 로 조정 가능"))

    # 형광펜 렌더 짝: 원본 markpenBegin 수와 렌더된 <mark 수가 같아야 한다.
    try:
        begins = 0
        with _zip.ZipFile(path) as z:
            for n in z.namelist():
                if _re.match(r"Contents/section\d+\.xml", n):
                    begins += z.read(n).decode("utf-8", "replace").count("markpenBegin")
        marks = info.get("html", "").count("<mark")
        out.append(CheckResult(
            "highlight renders", marks == begins,
            detail=f"{marks}/{begins} markpen run(s) drawn (자체 엔진)"))
    except Exception as exc:
        out.append(CheckResult("highlight renders", False, checked=False,
                               detail=str(exc)))
    return out


def check_word_wrap(path: str | Path) -> CheckResult:
    """한글 줄 나눔 기준을 보고한다. 실패는 아니고 **알려 주는** 검사다.

    ``BREAK_WORD`` (글자 단위)는 한/글 기본값이라 틀린 것은 아니지만, 좁은
    칸에서 어절이 "실 / 험"처럼 갈라지고, 글꼴 폭이 다른 뷰어(폴라리스 오피스
    등)에서는 그 자리가 더 자주, 더 어색하게 난다. 새로 만드는 문서는
    :class:`hwpxkit.boxdoc.BoxDoc` 이 어절 단위로 두고, 남의 양식은
    :func:`hwpxkit.edit.keep_korean_words` 로 바꿀 수 있다.
    """
    import xml.etree.ElementTree as _ET

    try:
        with zipfile.ZipFile(path) as z:
            header = _ET.fromstring(z.read("Contents/header.xml"))
    except Exception as exc:
        return CheckResult("korean word wrap", False, checked=False, detail=str(exc))
    counts: dict[str, int] = {}
    for node in header.iter(f"{HH}breakSetting"):
        v = node.get("breakNonLatinWord", "BREAK_WORD")
        counts[v] = counts.get(v, 0) + 1
    keep = counts.get("KEEP_WORD", 0)
    total = sum(counts.values())
    if total and keep == total:
        return CheckResult("korean word wrap", True,
                           detail=f"어절 단위 (KEEP_WORD {keep}/{total} paraPr)")
    return CheckResult(
        "korean word wrap", True,
        detail=f"글자 단위 paraPr {total - keep}/{total} — 좁은 칸에서 어절이 갈라진다; "
               f"keep_korean_words(doc) 로 어절 단위로")


def check_prose(path: str | Path, *, mode: str = "pitch",
                register: str | None = None) -> CheckResult:
    """문장 검토(:mod:`hwpxkit.prose`). 상투어·숫자 없는 주장·강조 없는 칸.

    FIX 항목이 하나라도 있으면 실패다 — 구조가 멀쩡해도 심사자가 읽는 것은
    문장이고, 고치지 않고 넘어가는 것을 막으려면 결과 줄이 빨간불이어야 한다.
    자세한 목록은 ``python -m hwpxkit.prose <file>``.
    """
    from .prose import review_document

    try:
        rep = review_document(path, mode=mode, register=register)
    except Exception as exc:
        return CheckResult("prose review", False, checked=False, detail=str(exc))
    detail = rep.summary()
    if not rep.ok:
        detail += " — python -m hwpxkit.prose <file> 로 목록 확인"
    return CheckResult("prose review", rep.ok, detail=detail)


def verify(path: str | Path, *, render: bool = True, min_pages: int = 1,
           max_pages: int | None = None, baseline: str | Path | None = None,
           prose: bool = True, mode: str = "pitch",
           register: str | None = None) -> Report:
    """가능한 모든 층을 돌려서 보고서 하나로 돌려준다.

    편집을 시작한 원본 파일을 *baseline* 으로 넘기면, 편집에만 존재하는
    검사들이 추가된다. 바뀐 문단의 낡은 레이아웃 캐시, 편집 범위, 원본 대비
    형광펜 균형이다.

    *prose* (기본 참)는 문장 검토를 함께 돌린다. 남이 쓴 양식의 안내문까지
    검토하고 싶지 않을 때만 끈다. *mode* (``"pitch"`` 지원서 / ``"research"``
    연구/특허 검토)와 *register* (``"합니다"`` / ``"한다"`` / ``"개조식"``)는
    :func:`hwpxkit.prose.review_text` 로 그대로 간다.

    *max_pages* 는 양식의 쪽수 제한("1페이지 내외", "5쪽 이내")이다. 주면
    "page limit" 줄이 생긴다.
    """
    report = Report()
    report.add(*check_package(path))
    report.add(check_markpen_pairs(path))
    report.add(check_binary_refs(path))
    report.add(check_cell_overflow(path))
    report.add(check_word_wrap(path))
    report.add(*check_row_geometry(path, baseline))
    if baseline is not None:
        report.add(*check_against_baseline(path, baseline))
    if render:
        report.add(*check_layout(path, min_pages=min_pages, max_pages=max_pages))
    if prose:
        report.add(check_prose(path, mode=mode, register=register))
    # 아래 항목은 여기서 쓸 수 있는 어떤 수단으로도 확인할 수 없다. 이름을
    # 붙여 두면 "안 봤다"가 "보니 괜찮더라"로 읽히지 않는다. (렌더 검사는
    # 자체 조판 엔진이 맡는다 — 예전 rhwp 기반의 NOT VERIFIED 두 줄은
    # check_layout 의 실검사로 바뀌었다.)
    report.add(CheckResult(
        "Hancom-exact rendering", False, checked=False,
        detail="자체 조판은 한컴과 ±1쪽·줄바꿈 차이가 있을 수 있다; "
               "실기 확인은 한컴오피스에서"))
    return report
