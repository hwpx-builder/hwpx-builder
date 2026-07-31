"""*기존* HWPX 를 편집하는 일. 새로 만드는 것과는 다른 문제다.

새로 만들 때는 모든 요소를 우리가 소유한다. 편집은 그렇지 않다. 스타일, 병합
셀, 레이아웃 캐시, 형광펜 짝은 전부 한글이 써 놓은 것이고, 하나같이 안이한
쓰기를 응징한다. 실제 문서 두 건을 실측한 결과:

``doc.paragraphs`` 는 **표 안의 내용에 닿지 못한다.** 한 문서는 최상위 문단이
13개에 표가 26개였는데, 찾으려던 단어 7건이 전부 셀 안에 있었다. 그래서
``replace_text_in_runs`` 는 그중 **0건**을 치환했고 ``get_table_map()`` 은 표를
0개로 보고했다. 이런 문서를 편집한다는 것은 문단이 아니라 셀을 순회한다는
뜻이다. :func:`iter_cells` 가 그 일을 한다.

**형광펜이 칠해진 텍스트는 ``paragraph.text`` 에 보이지 않는다** (위 7건 중
2건이 그랬다). 그 텍스트는 ``markpenBegin`` 의 ``.tail`` 에 들어 있다.
``.text`` 기반 찾기/바꾸기는 이걸 조용히 건너뛰고, 형광펜 경계를 가로지르는
치환은 짝을 끊어서 문서 아래쪽까지 형광색을 번지게 한다. :func:`replace_text`
는 tail 까지 읽고, 짝을 가로질러 쓰는 것은 :attr:`EditReport.conflicts` 로
드러내며 거부한다.

**건드린 문단은 반드시 ``<hp:linesegarray>`` 를 잃어야 한다.** 낡은
``textpos`` 는 한글이 새 텍스트를 옛 줄 자리에 그리게 만든다. ``hwpxkit`` 의
``set_spans`` 는 이걸 지우지 *않는다*. 새로 만든 문단에는 애초에 캐시가 없기
때문이다. 이 모듈의 함수들은 전부 지운다.

**기존 표의 높이를 다시 맞추지 말 것.** ``autofit()`` 은 빌더가 만드는 기하를
가정한다. 행마다 열마다 셀 하나씩, 병합 없음. 실제 문서는 병합을 많이 쓴다
(실측 두 문서에서 각각 26개, 34개). 그래서 행 모델이 성립하지 않는다. 손대지
않은 실제 표에 돌려 봤더니 한 행이 16980 에서 124354 HWPUNIT 으로 부풀었다.
캐시만 지워 두면 한글이 문서를 열 때 알아서 다시 배치한다. 그렇게 두자.
:func:`refit_cell` 은 안 들어갈 것 같은 부분을 보고만 한다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Iterator, Sequence

from .richtext import HP, YELLOW, Span, parse_markup, paragraph_text, run_text
from .units import HWP_PER_MM as MM

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
#: ``<hp:margin>`` 의 자식이 ``hc:`` 인 것처럼, ``<hp:pic>`` 안의 이미지 참조도
#: ``hc:img`` 다. 네임스페이스를 잘못 골라 찾으면 오류 없이 ``None`` 만 나온다.
HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

#: 스타일 변형을 파생할 때 "같은 계열"인지 판별하는 속성들.
#: ``ensure_run_style(base_char_pr_id=...)`` 는 기준 스타일을 무시한다. charPr
#: 28(12 pt, fontRef 3)의 굵은 변형을 요청했더니 이미 있던 charPr 4(10 pt,
#: fontRef 5, DROP 그림자)를 돌려줬다. 이 속성들을 함께 맞추면 파생된 스타일이
#: 원래 run 과 같은 계열에 머문다.
IDENTITY_ATTRS = ("height", "textColor", "shadeColor")


# ------------------------------------------------------------------ 순회 --

def iter_tables(container) -> list:
    """*container* 아래의 모든 표(중첩 포함).

    섹션, 셀, 그 밖에 ``tables`` / ``paragraphs`` 를 노출하는 무엇이든 받는다.
    순서에는 의미가 없다. 안정적인 주소가 필요하면 :func:`iter_cells` 를 쓸 것.
    """
    stack = list(getattr(container, "tables", []) or [])
    for para in getattr(container, "paragraphs", []) or []:
        stack.extend(getattr(para, "tables", []) or [])
    seen: list = []
    while stack:
        table = stack.pop()
        seen.append(table)
        for row in table.rows:
            for cell in row.cells:
                for para in cell.paragraphs:
                    stack.extend(getattr(para, "tables", []) or [])
    return seen


@dataclass
class CellRef:
    """셀 하나와, 보고서에서 그 셀을 가리킬 때 필요한 주소."""

    cell: object
    table: object
    section: int
    table_index: int
    row: int
    col: int
    depth: int = 0

    @property
    def path(self) -> str:
        return f"s{self.section}/t{self.table_index}/r{self.row}c{self.col}"

    @property
    def text(self) -> str:
        return cell_text(self.cell)

    def __str__(self) -> str:
        return f"{self.path}: {self.text[:40]!r}"


def iter_cells(doc, *, section: int | None = None) -> Iterator[CellRef]:
    """문서의 모든 셀을 순회한다. 중첩 표 안으로도 들어간다.

    표는 각 단계마다 문서 순서대로 번호가 매겨진다. 그래서 같은 파일에 같은
    스크립트를 다시 돌려도 ``path`` 는 그대로다.
    """
    for si, sec in enumerate(doc.sections):
        if section is not None and si != section:
            continue
        counter = [0]
        for table in _ordered_tables(sec):
            yield from _walk_table(table, si, counter, depth=0)


def _ordered_tables(container) -> list:
    """container 의 최상위 표들. 문서 순서대로."""
    out = list(getattr(container, "tables", []) or [])
    if out:
        return out
    for para in getattr(container, "paragraphs", []) or []:
        out.extend(getattr(para, "tables", []) or [])
    return out


def _walk_table(table, section: int, counter: list, depth: int) -> Iterator[CellRef]:
    index = counter[0]
    counter[0] += 1
    for r, row in enumerate(table.rows):
        for c, cell in enumerate(row.cells):
            yield CellRef(cell, table, section, index, r, c, depth)
            for para in cell.paragraphs:
                for nested in getattr(para, "tables", []) or []:
                    yield from _walk_table(nested, section, counter, depth + 1)


def cell_text(cell) -> str:
    """셀 안의 모든 텍스트. markpen tail 포함, 문단마다 한 줄."""
    return "\n".join(paragraph_text(p) for p in cell.paragraphs)


def find_cells(doc, needle: str | re.Pattern, *,
               predicate: Callable[[CellRef], bool] | None = None) -> list[CellRef]:
    """markpen 까지 읽은 텍스트가 *needle* 과 맞는 셀들 (부분 문자열 또는 정규식)."""
    matcher = (needle.search if isinstance(needle, re.Pattern)
               else lambda t: needle in t)
    out = []
    for ref in iter_cells(doc):
        if matcher(ref.text) and (predicate is None or predicate(ref)):
            out.append(ref)
    return out


def find_label(doc, label: str, direction: str = "right") -> CellRef | None:
    """라벨 셀 옆의 값 셀. 실제로 동작하는 ``find_cell_by_label``.

    ``direction`` 은 ``"right"`` 또는 ``"below"``. 이웃 셀이 없으면 추측하지
    않고 ``None`` 을 돌려준다. 병합된 표에서 행 끝에 있는 라벨은 믿을 만한
    이웃이 없기 때문이다.
    """
    for ref in iter_cells(doc):
        if label not in ref.text:
            continue
        rows = list(ref.table.rows)
        if direction == "right":
            cells = list(rows[ref.row].cells)
            if ref.col + 1 < len(cells):
                return CellRef(cells[ref.col + 1], ref.table, ref.section,
                               ref.table_index, ref.row, ref.col + 1, ref.depth)
        elif direction == "below":
            if ref.row + 1 < len(rows):
                cells = list(rows[ref.row + 1].cells)
                if ref.col < len(cells):
                    return CellRef(cells[ref.col], ref.table, ref.section,
                                   ref.table_index, ref.row + 1, ref.col, ref.depth)
        else:
            raise ValueError(f"direction must be 'right' or 'below', got {direction!r}")
    return None


# ----------------------------------------------------------- layout cache --

def drop_layout_cache(paragraph) -> bool:
    """문단의 ``<hp:linesegarray>`` 를 제거한다. 원래 있었는지를 돌려준다.

    바꾼 문단에 **정확히** 이것만 호출할 것. 문서 전체에서 캐시를 걷어내면
    손대지 않은 페이지까지 한글이 다시 배치해서 페이지 수가 달라진다. 고치려던
    것과 정반대 결과다.
    """
    element = paragraph.element
    cache = element.find(f"{HP}linesegarray")
    if cache is None:
        return False
    element.remove(cache)
    return True


def cached_line_count(paragraph) -> int | None:
    """한글이 실제로 배치했던 줄 수. 캐시가 없으면 ``None``."""
    cache = paragraph.element.find(f"{HP}linesegarray")
    return None if cache is None else len(list(cache))


# ---------------------------------------------------------------- styling --

def _char_properties(doc):
    header = doc.headers[0]
    return header, header.element.find(f"{HH}refList/{HH}charProperties")


def derive_char_pr(doc, base_id: str | int | None, *, bold: bool = False,
                   color: str | None = None) -> str:
    """요청한 차이만 빼면 *base_id* 와 동일한 charPr.

    이 일에 ``ensure_run_style(base_char_pr_id=...)`` 는 쓸 수 없다. 그쪽
    조건식은 요청한 속성만 보기 때문에, 크기와 글꼴이 전혀 다른 기존 스타일을
    태연히 돌려준다. 여기서는 조건식이 :data:`IDENTITY_ATTRS` 와 글꼴 참조까지
    기준 스타일에 고정한다. 그래서 편집한 run 이 원래 텍스트의 크기와 서체를
    유지한다.

    *color* 를 주면 글자색만 바꾼 변형을 만든다. 배포 양식의 안내문은 파란색
    같은 눈에 띄는 색으로 되어 있어서(실측한 정부 서식은 ``#0000FF``), 그
    칸을 그대로 채우면 제출 문서 본문이 파랗게 나온다. 크기와 글꼴은 양식을
    따르되 색만 검정으로 돌리려면 ``color="#000000"`` 을 준다.
    """
    if base_id is None:
        return doc.ensure_run_style(bold=bold, color=color)
    header, char_props = _char_properties(doc)
    if char_props is None:
        return doc.ensure_run_style(bold=bold, color=color)
    base = char_props.find(f"{HH}charPr[@id='{base_id}']")
    if base is None:
        return doc.ensure_run_style(bold=bold, color=color)
    if not bold and (color is None or base.get("textColor") == color):
        return str(base_id)

    want = {a: base.get(a) for a in IDENTITY_ATTRS}
    if color is not None:
        want["textColor"] = color
    base_font = base.find(f"{HH}fontRef")
    want_font = base_font.get("hangul") if base_font is not None else None

    def predicate(element) -> bool:
        if any(element.get(a) != v for a, v in want.items()):
            return False
        font = element.find(f"{HH}fontRef")
        if (font.get("hangul") if font is not None else None) != want_font:
            return False
        return (element.find(f"{HH}bold") is not None) == bold

    def modifier(element) -> None:
        if color is not None:
            element.set("textColor", color)
        existing = element.find(f"{HH}bold")
        if bold and existing is None:
            # <hh:bold/> 는 스키마상 순서가 있다. <hh:offset> 뒤, <hh:underline>
            # 앞에 와야 한다. append 가 아니라 insert 할 것.
            underline = element.find(f"{HH}underline")
            node = element.makeelement(f"{HH}bold", {})
            if underline is not None:
                element.insert(list(element).index(underline), node)
            else:
                element.append(node)
        elif not bold and existing is not None:
            element.remove(existing)

    return header.ensure_char_property(
        predicate=predicate, modifier=modifier, base_char_pr_id=str(base_id)
    ).get("id")


def dominant_font_pt(doc, *, default: float = 10.0) -> float:
    """문서 본문에서 실제로 가장 많이 쓰인 글자 크기(pt).

    :func:`hwpxkit.boxdoc.autofit` 은 기본값이 10 pt 다. 우리가 만든 문서는 그
    크기를 쓰지만 **남의 양식은 다르다.** 실측한 정부 서식은 본문이 12 pt 였고,
    그대로 10 pt 로 계산하면 줄 수를 적게 잡아 행이 필요한 만큼 커지지 않는다.
    글자가 칸을 넘쳐 아래 칸과 겹쳐 보이는 원인이 이것이다.

        autofit(table, font_pt=dominant_font_pt(doc))

    문단이 실제로 참조하는 ``charPrIDRef`` 만 센다. 헤더에 정의만 되어 있고
    쓰이지 않는 스타일은 세지 않는다.
    """
    from collections import Counter

    _, char_props = _char_properties(doc)
    if char_props is None:
        return default

    heights: Counter = Counter()
    for ref in iter_cells(doc):
        for para in ref.cell.paragraphs:
            if not paragraph_text(para).strip():
                continue
            cid = paragraph_char_pr(para)
            if cid is None:
                continue
            e = char_props.find(f"{HH}charPr[@id='{cid}']")
            h = e.get("height") if e is not None else None
            if h and h.isdigit():
                heights[int(h)] += 1
    if not heights:
        return default
    return heights.most_common(1)[0][0] / 100.0


def flatten_indent(doc, paragraph, *, left: int = 0, intent: int = 0) -> bool:
    """문단의 왼쪽 여백과 들여쓰기를 없앤다. 바꿨으면 ``True``.

    배포 양식의 본문 칸은 문단 속성에 왼쪽 여백이 들어 있는 경우가 많다.
    실측한 서식은 ``margin/left`` 가 **2000 HWPUNIT**(약 7 mm)이었다. 안내문이
    그 여백을 쓰라고 만들어진 것이라, 칸을 채우면 넣은 글이 전부 오른쪽으로
    밀려 보인다. 반면 새로 만든 표의 문단은 여백이 0이라, 한 문서 안에서 어떤
    줄은 들여쓰여 있고 어떤 줄은 아닌 상태가 된다.

    ``ensure_paragraph_format(base_para_pr_id=…)`` 로 파생하므로 정렬·줄간격 등
    나머지 문단 속성은 그대로 유지된다. (같은 이름의 ``ensure_run_style`` 이
    기준 스타일을 무시하는 것과 달리, 이쪽은 실제로 기준을 지킨다 —
    확인함: 파생본과 원본의 속성 차이가 ``id`` 뿐이었다.)

    주의: ``margin`` 은 ``hh:`` 네임스페이스인데 그 자식 ``left`` / ``intent``
    는 ``hc:`` 다. 같은 네임스페이스로 찾으면 조용히 못 찾는다.
    """
    base = paragraph.element.get("paraPrIDRef")
    if base is None:
        return False
    header = doc.headers[0]
    new_id = header.ensure_paragraph_format(
        base_para_pr_id=base, margins={"left": left, "intent": intent})
    if new_id is None or str(new_id) == str(base):
        return False
    paragraph.element.set("paraPrIDRef", str(new_id))
    return True


def paragraph_char_pr(paragraph) -> str | None:
    """문단 첫 run 의 ``charPrIDRef``. 물려받을 스타일이다."""
    for run in paragraph.runs:
        ref = run.element.get("charPrIDRef")
        if ref is not None:
            return ref
    return None


# -------------------------------------------------------------- 텍스트 편집 --

@dataclass
class TextSlot:
    """문단 안에서 글씨를 쓸 수 있는 한 구간.

    run 의 ``<hp:t>`` 는 텍스트를 ``.text`` 에도 담고, 자식 요소들의 ``.tail``
    에도 담는다. markpen 이 텍스트를 밀어 넣는 곳이 바로 그 tail 이다. 각각이
    슬롯 하나이고, 슬롯과 슬롯 사이가 markpen 태그가 앉아 있는 자리다.
    """

    holder: object          # 문자열을 소유한 요소
    attr: str               # "text" 또는 "tail"
    start: int              # 문단 전체 텍스트에서의 오프셋
    text: str

    @property
    def end(self) -> int:
        return self.start + len(self.text)

    def read(self) -> str:
        return getattr(self.holder, self.attr) or ""

    def write(self, value: str) -> None:
        setattr(self.holder, self.attr, value or None)


def text_slots(paragraph) -> list[TextSlot]:
    """문단 안에서 쓸 수 있는 모든 텍스트 슬롯. 읽는 순서대로."""
    slots: list[TextSlot] = []
    pos = 0
    for run in paragraph.runs:
        for child in run.element:
            if child.tag != f"{HP}t":
                if child.tag == f"{HP}tab":
                    pos += 1
                continue
            if child.text:
                slots.append(TextSlot(child, "text", pos, child.text))
                pos += len(child.text)
            for sub in child:
                if sub.tail:
                    slots.append(TextSlot(sub, "tail", pos, sub.tail))
                    pos += len(sub.tail)
    return slots


@dataclass
class EditReport:
    """편집이 실제로 한 일. 하지 않기로 거부한 것까지 포함한다."""

    replaced: int = 0
    paragraphs: int = 0
    caches_dropped: int = 0
    conflicts: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [
            f"  replaced {self.replaced} occurrence(s) in "
            f"{self.paragraphs} paragraph(s)",
            f"  dropped {self.caches_dropped} layout cache(s)",
        ]
        for loc in self.locations:
            lines.append(f"    - {loc}")
        for c in self.conflicts:
            lines.append(f"  SKIPPED (markpen boundary): {c}")
        if self.conflicts:
            lines.append(
                "  A replacement spanning markpenBegin/End would orphan the pair;"
                " edit those by hand or via set_cell()."
            )
        return "\n".join(lines)


def replace_in_paragraph(paragraph, old: str, new: str, *,
                         report: EditReport | None = None) -> int:
    """문단 하나에서 *old* 를 *new* 로 바꾼다. run 스타일은 그대로 둔다.

    텍스트를 제자리에서 고쳐 쓰므로 ``charPrIDRef`` 가 바뀌지 않는다. 즉 바뀐
    글자가 원래 글자의 크기·글꼴·색을 그대로 물려받는다. 한글은 run 을 임의의
    지점에서 쪼개므로 찾은 문자열이 여러 run 에 걸칠 수 있다. 그럴 때는 새
    텍스트를 첫 슬롯에 넣고 나머지 슬롯에서는 해당 부분을 지운다.

    형광펜 경계를 가로지르는 경우에는 **건너뛰고** *report* 에 기록한다. 경계를
    넘어 고쳐 쓰면 끝이 없는 ``markpenBegin`` 이 남기 때문이다.
    """
    report = report if report is not None else EditReport()
    if not old:
        return 0

    count = 0
    # 매번 처음부터 다시 훑지 않고 치환한 *다음* 지점에서 이어서 찾는다. 새
    # 문자열이 찾던 문자열을 포함하면("사업" -> "사업(수정)") 자기 결과를 무한히
    # 다시 찾게 되기 때문이다.
    start = 0
    while True:
        slots = text_slots(paragraph)
        if not slots:
            break
        whole = "".join(s.text for s in slots)
        at = whole.find(old, start)
        if at < 0:
            break
        span = [s for s in slots if s.start < at + len(old) and s.end > at]
        if _crosses_markpen(span):
            report.conflicts.append(f"{old!r} in {whole[:40]!r}")
            start = at + len(old)
            continue

        first = span[0]
        head = first.text[: at - first.start]
        last = span[-1]
        tail = last.text[at + len(old) - last.start:]
        if len(span) == 1:
            first.write(head + new + tail)
        else:
            first.write(head + new)
            for middle in span[1:-1]:
                middle.write("")
            last.write(tail)
        count += 1
        start = at + len(new)

    if count:
        report.replaced += count
        report.paragraphs += 1
        if drop_layout_cache(paragraph):
            report.caches_dropped += 1
    return count


def _crosses_markpen(span: Sequence[TextSlot]) -> bool:
    """찾은 문자열이 markpen 태그 경계를 가로지르는가?

    ``tail`` 슬롯은 어떤 요소 바로 뒤에서 시작한다. 그 요소가 markpen 태그이고
    찾은 문자열이 그 앞에서 시작했다면, 형광펜 짝을 가로지른 것이다.
    """
    for slot in span[1:]:
        if slot.attr == "tail" and slot.holder.tag in (
            f"{HP}markpenBegin", f"{HP}markpenEnd"
        ):
            return True
    return False


def replace_text(doc, old: str, new: str, *, cells: bool = True,
                 paragraphs: bool = True) -> EditReport:
    """표 셀과 형광펜 텍스트까지 실제로 닿는 문서 전체 치환.

    ``replace_text_in_runs`` 가 원래 이랬어야 하는 함수다. 실측 문서에서
    라이브러리 쪽은 0건을 찾은 반면, 이쪽은 7건을 모두 찾았다. 그중 2건은
    markpen tail 에 실려 있던 것이다.
    """
    report = EditReport()
    seen = _VisitedSet()

    if paragraphs:
        for sec in doc.sections:
            for para in getattr(sec, "paragraphs", []) or []:
                if not seen.add(para):
                    continue
                if replace_in_paragraph(para, old, new, report=report):
                    report.locations.append(f"body: {paragraph_text(para)[:40]!r}")

    if cells:
        for ref in iter_cells(doc):
            for para in ref.cell.paragraphs:
                if not seen.add(para):
                    continue
                if replace_in_paragraph(para, old, new, report=report):
                    report.locations.append(f"{ref.path}: {paragraph_text(para)[:40]!r}")
    return report


class _VisitedSet:
    """lxml 요소 프록시에도 안전한 ``id()`` 기반 중복 제거.

    ``python-hwpx`` 는 lxml 로 파싱하는데, lxml 은 노드에 접근할 때마다 *새
    프록시 객체*를 만든다. 루프가 그 프록시를 놓는 순간 해제되고 CPython 이
    같은 주소를 재사용한다. 그래서 그냥 ``{id(p.element)}`` 집합을 쓰면 아무
    상관없는 뒤쪽 문단이 "이미 본 것"으로 잡힌다. 이론상의 이야기가 아니다.
    이것 때문에 ``replace_text`` 가 실측 문서에서 7건을 전부 건너뛰었다. 문단
    하나만 놓고 같은 함수를 부르면 잘 동작했는데도. 프록시마다 참조를 붙들고
    있으면 그 주소가 재사용 목록에 들어가지 않아서 ``id()`` 가 의미를 갖는다.
    """

    def __init__(self) -> None:
        self._ids: set[int] = set()
        self._keep: list = []

    def add(self, paragraph) -> bool:
        """문단을 등록한다. 이미 본 문단이면 ``False``."""
        element = paragraph.element
        if id(element) in self._ids:
            return False
        self._ids.add(id(element))
        self._keep.append(element)
        return True


def set_paragraph(doc, paragraph, markup: str, *, keep_style: bool = True,
                  color: str | None = None,
                  report: EditReport | None = None) -> EditReport:
    """문단 하나의 텍스트를 다시 쓴다. 스타일은 유지하고 캐시는 지운다.

    :func:`set_cell` 의 본문 텍스트판이다. 박스와 박스 *사이*에 놓이는 제목이나
    캡션을 위한 것. 그림이나 표를 붙들고 있는 문단은 건드리지 않는다. 그 run 을
    지우면 객체 자체가 사라지기 때문이다.
    """
    report = report if report is not None else EditReport()
    if has_nontext_runs(paragraph):
        report.conflicts.append(
            f"paragraph anchors a non-text run: {paragraph_text(paragraph)[:40]!r}")
        return report
    base = paragraph_char_pr(paragraph) if keep_style else None
    _clear_runs(paragraph)
    _write_spans(doc, paragraph, parse_markup(markup), base, color)
    if drop_layout_cache(paragraph):
        report.caches_dropped += 1
    report.paragraphs += 1
    return report


def set_cell(doc, cell, markup: str, *, keep_style: bool = True,
             color: str | None = None, flatten: bool = False,
             report: EditReport | None = None) -> EditReport:
    """셀 내용 전체를 *markup* 으로 교체한다. 셀의 겉모습은 유지한다.

    ``**굵게**`` 와 ``==형광펜==`` 은 새로 만들 때와 똑같이 동작한다.
    ``keep_style`` (기본값)이면 새 run 이 원래 텍스트의 ``charPrIDRef`` 를
    물려받는다. 그래서 12 pt 셀은 12 pt 로 남는다. ``BoxDoc`` 의 10 pt 기본값으로
    다시 만들어 넣는 것이, 편집한 서식에서 셀 하나만 크기가 어긋나는 전형적인
    경로다.

    *markup* 의 각 줄이 문단 하나가 된다. 중첩 표·이미지 등 텍스트 아닌 run 을
    붙들고 있는 문단은 덮어쓰지 않고 **통째로 건너뛴다**. 중첩된 ``<hp:tbl>`` 은
    ``<hp:run>`` *안에* 들어 있어서, 그 문단의 run 을 지우면 하위 표가 통째로
    사라지기 때문이다. 이 함수의 첫 버전이 실제로 중첩 표 다섯 개를 조용히
    날렸다. baseline 검사가 그걸 "문단 16개가 바뀌었다"로 잡아냈는데, 뒤쪽 표
    번호가 전부 밀렸기 때문이었다.
    """
    report = report if report is not None else EditReport()
    paras = list(cell.paragraphs)
    writable = [p for p in paras if not has_nontext_runs(p)]
    lines = markup.split("\n") if markup else [""]
    base = paragraph_char_pr(writable[0]) if writable and keep_style else None

    for i, line in enumerate(lines):
        if i < len(writable):
            para = writable[i]
        else:
            para = cell.add_paragraph("")
            writable.append(para)
        local_base = paragraph_char_pr(para) if keep_style else None
        if flatten:
            flatten_indent(doc, para)
        _clear_runs(para)
        _write_spans(doc, para, parse_markup(line), local_base or base, color)
        if drop_layout_cache(para):
            report.caches_dropped += 1
        report.paragraphs += 1

    for extra in writable[len(lines):]:
        if not _clear_runs(extra):
            continue
        if drop_layout_cache(extra):
            report.caches_dropped += 1
    return report


def fill_cell(doc, cell, blocks: Sequence, *, keep_style: bool = True,
              color: str | None = None, ratio: float = 1.0,
              flatten: bool = False,
              report: EditReport | None = None) -> EditReport:
    """셀 하나를 **글줄과 표가 섞인 블록**으로 채운다.

    :func:`set_cell` 은 문자열만 받으므로 칸 안에 표를 넣을 수 없다. 그런데
    배포 양식의 큰 칸은 원래 표로 채우라고 만들어 둔 자리인 경우가 많다. 글줄만
    넣으면 칸의 아래쪽이 크게 비어서 어색해진다 — 실측한 서식에서 어떤 칸은
    높이 18808 HWPUNIT 인데 넣은 글이 11766 어치였다.

    *blocks* 는 ``str`` 과 :class:`hwpxkit.boxdoc.Grid` 를 섞은 시퀀스다.
    :meth:`BoxDoc.container_box` 의 내용 어휘와 같으므로, 새로 만들 때 쓰던
    표현을 편집에서도 그대로 쓸 수 있다::

        fill_cell(doc, ref.cell, [
            "먼저 설명 한 줄.",
            Grid(headers=["구분", "내용"], rows=[["1단계", "..."]]),
        ])

    표는 셀 너비의 *ratio* 만큼 폭을 잡고, 기본값은 **1.0** — 칸을 꽉 채운다.

    실측하면 사람이 만든 문서는 오히려 조금 좁게 쓴다(온리브 0.952~0.978,
    U300 평균 0.939, 최대 1.002 로 칸보다 넓은 것도 하나 있었다). 그런데 그
    남는 폭은 표 오른쪽에 빈 띠로 보여서 눈에 거슬린다 — 칸 47950 에 표 46032
    면 1918 HWPUNIT, 약 6.8 mm 다. 기본값을 1.0 으로 둔 이유이고, 좁히고 싶으면
    ``ratio`` 를 낮추면 된다. 한글은 칸보다 넓은 표도 허용한다(위 1.002 사례).

    주의: 표는 자기 앵커 문단이 필요하므로, 글줄과 표를 준 **순서 그대로**
    내보낸다. 그리고 :func:`set_cell` 과 같은 이유로 이미 표·그림을 붙들고 있는
    문단은 건드리지 않는다.
    """
    from .boxdoc import BODY_PT, GREY_TABLE, Grid, _set_column_widths
    from .units import split_width

    report = report if report is not None else EditReport()
    paras = list(cell.paragraphs)
    writable = [p for p in paras if not has_nontext_runs(p)]
    base = paragraph_char_pr(writable[0]) if writable and keep_style else None
    inner_width = int((cell.width or 0) * ratio) or None

    used = 0
    for item in blocks:
        if isinstance(item, Grid):
            # 표는 앵커 문단 하나를 차지한다. 남은 문단이 없으면 새로 만든다.
            anchor = (writable[used] if used < len(writable)
                      else cell.add_paragraph(""))
            if used < len(writable):
                _clear_runs(anchor)
                drop_layout_cache(anchor)
            # 앵커의 왼쪽 여백이 **표 전체를 오른쪽으로 민다.** 글줄은
            # flatten 으로 정리해 놓고 앵커를 빼먹으면, 문단은 제자리인데 표만
            # 들여쓰여 보인다. 실측: 양식 본문 문단의 left 가 2000 HWPUNIT
            # (약 7 mm)이라 표만 그만큼 밀려 있었다.
            if flatten:
                flatten_indent(doc, anchor)
            used += 1
            ncols = len(item.headers)
            ratios = tuple(item.ratios or [1.0] * ncols)
            widths = split_width(inner_width or 40000, ratios)
            inner = anchor.add_table(len(item.rows) + 1, ncols,
                                     width=inner_width or 40000)
            _set_column_widths(inner, widths)
            # 표 셀은 새 문단이라 문서 기본 스타일을 쓰게 된다. 그러면 한
            # 문서 안에서 본문과 표의 글꼴·크기가 달라진다(실측: 본문 12 pt
            # 한양중고딕 vs 표 10 pt 함초롬바탕). 바깥 칸의 charPr 을 넘겨서
            # 같은 계열로 맞춘다.
            for c, head in enumerate(item.headers):
                inner.set_cell_shading(0, c, GREY_TABLE)
                _fill_inner(doc, inner.cell(0, c), str(head), base, color,
                            bold=True, report=report)
            for r, rowvals in enumerate(item.rows, start=1):
                for c, val in enumerate(rowvals):
                    _fill_inner(doc, inner.cell(r, c), str(val), base, color,
                                report=report)
        else:
            para = (writable[used] if used < len(writable)
                    else cell.add_paragraph(""))
            used += 1
            local = paragraph_char_pr(para) if keep_style else None
            if flatten:
                flatten_indent(doc, para)
            _clear_runs(para)
            _write_spans(doc, para, parse_markup(str(item)),
                         local or base, color)
            if drop_layout_cache(para):
                report.caches_dropped += 1
            report.paragraphs += 1

    # 남은 문단은 비운다. 표·그림 앵커는 손대지 않는다.
    for extra in writable[used:]:
        if _clear_runs(extra) and drop_layout_cache(extra):
            report.caches_dropped += 1
    return report


def _fill_inner(doc, cell, text: str, base: str | None, color: str | None,
                *, bold: bool = False, report: EditReport | None = None) -> None:
    """:func:`fill_cell` 이 만든 표의 셀 하나를 채운다.

    바깥 칸의 *base* charPr 을 물려받아, 새로 만든 표가 문서의 나머지와 다른
    글꼴로 튀지 않게 한다. 새 문단이라 레이아웃 캐시는 애초에 없다.

    문단 여백도 함께 평탄화한다. 새 표의 셀은 문서 기본 ``paraPr`` 을 쓰는데,
    실측한 문서의 기본값은 ``intent = -2620`` (내어쓰기)이었다. ``left`` 가 0
    이라 첫 줄이 왼쪽으로 나갈 자리가 없는데도 값이 남아 있어서, 표 안 글자만
    미묘하게 밀려 보인다. 바깥 칸을 ``flatten`` 으로 정리해도 이쪽을 빼먹으면
    표에만 여백이 남는다.
    """
    report = report if report is not None else EditReport()
    paras = list(cell.paragraphs)
    para = paras[0] if paras else cell.add_paragraph("")
    flatten_indent(doc, para)
    _clear_runs(para)
    spans = parse_markup(text)
    if bold:
        spans = [Span(text=s.text, bold=True, highlight=s.highlight) for s in spans]
    _write_spans(doc, para, spans, base, color)
    report.paragraphs += 1


def clear_guidance(doc, *, markers: Sequence[str] = ("※",),
                   report: EditReport | None = None) -> EditReport:
    """양식의 작성 안내문을 지운다.

    배포 서식은 보통 첫 장에 "제출 시 안내문과 음영은 삭제" 라고 적어 두고,
    그 안내문 자체를 ``※`` 같은 마커로 시작하는 문단으로 넣어 둔다. 채운 뒤에도
    남아 있으면 제출본에 그대로 실린다.

    *markers* 로 시작하는 **본문 문단**만 지운다. 표 안의 안내문은 어차피
    내용으로 덮어쓰게 되므로 건드리지 않는다. 문단을 삭제하지 않고 비우는
    이유는, 삭제하면 뒤따르는 문단의 스타일 참조가 흔들릴 수 있어서다.
    """
    report = report if report is not None else EditReport()
    for sec in doc.sections:
        for para in getattr(sec, "paragraphs", []) or []:
            if has_nontext_runs(para):
                continue
            text = paragraph_text(para).strip()
            if text and any(text.startswith(m) for m in markers):
                _clear_runs(para)
                drop_layout_cache(para)
                report.paragraphs += 1
                report.locations.append(f"안내문 제거: {text[:40]!r}")
    return report


#: 텍스트가 아닌 것을 담고 있는 run 자식 요소들. 문단을 "비운다"는 이유로
#: 이들을 담은 run 을 지워서는 절대 안 된다.
NONTEXT_RUN_CHILDREN = frozenset({
    f"{HP}tbl", f"{HP}pic", f"{HP}container", f"{HP}ctrl", f"{HP}rect",
    f"{HP}ellipse", f"{HP}line", f"{HP}equation", f"{HP}chart", f"{HP}ole",
})


def has_nontext_runs(paragraph) -> bool:
    """문단이 표·이미지·도형·컨트롤을 붙들고 있는지."""
    for run in paragraph.runs:
        for child in run.element:
            if child.tag in NONTEXT_RUN_CHILDREN:
                return True
    return False


def _clear_runs(paragraph) -> bool:
    """문단에서 텍스트만 있는 run 을 지운다. 지운 게 없으면 ``False``."""
    removed = False
    for run in list(paragraph.runs):
        if any(child.tag in NONTEXT_RUN_CHILDREN for child in run.element):
            continue
        paragraph.element.remove(run.element)
        removed = True
    return removed


def _write_spans(doc, paragraph, spans: Sequence[Span], base: str | None,
                 color: str | None = None) -> None:
    """span 을 써 넣는다. span 이 따로 지정하지 않은 부분은 *base* 를 물려받는다."""
    from .richtext import add_spans, apply_markpen

    if base is None:
        if color is not None:
            spans = [s.__class__(**{**s.__dict__, "color": color}) for s in spans]
        add_spans(doc, paragraph, spans)
        return

    for span in spans:
        if not span.text:
            continue
        char_id = derive_char_pr(doc, base, bold=span.bold, color=color)
        run = paragraph.add_run(span.text, char_pr_id_ref=char_id)
        if span.highlight:
            apply_markpen(run.element, span.highlight)


def highlight_cell(doc, cell, needle: str, color: str = YELLOW) -> int:
    """셀 안에 *needle* 이 나오는 곳마다 진짜 형광펜을 씌운다.

    형광펜이 찾은 문자열만 정확히 덮도록 원래 run 을 쪼개고, 짝이 끊길 수 없는
    자기완결형 begin/end 형태로 쓴다.
    """
    from .richtext import apply_markpen

    hits = 0
    for para in cell.paragraphs:
        for run in list(para.runs):
            text = run_text(run.element)
            if needle not in text or _has_markpen(run.element):
                continue
            head, _, tail = text.partition(needle)
            char_id = run.element.get("charPrIDRef")
            index = list(para.element).index(run.element)
            para.element.remove(run.element)
            made = []
            for piece, mark in ((head, False), (needle, True), (tail, False)):
                if not piece:
                    continue
                new = para.add_run(piece, char_pr_id_ref=char_id)
                para.element.remove(new.element)
                made.append((new, mark))
            for offset, (new, mark) in enumerate(made):
                para.element.insert(index + offset, new.element)
                if mark:
                    apply_markpen(new.element, color)
                    hits += 1
        if hits:
            drop_layout_cache(para)
    return hits


def _has_markpen(run_element) -> bool:
    for child in run_element:
        if child.tag == f"{HP}t":
            for sub in child:
                if sub.tag in (f"{HP}markpenBegin", f"{HP}markpenEnd"):
                    return True
    return False


# -------------------------------------------------------------- 높이 맞춤 --

# ---------------------------------------------------------------- 이미지 --

@dataclass
class PictureRef:
    """문서 안 그림 하나. *paragraph* 는 그림을 붙들고 있는 문단이다."""
    index: int
    section: int
    paragraph: object
    run: object
    element: object

    @property
    def binary_id(self) -> str | None:
        img = self.element.find(f"{HC}img")
        return None if img is None else img.get("binaryItemIDRef")

    @property
    def size(self) -> tuple[int, int]:
        """HWPUNIT 단위의 (폭, 높이). 배치된 크기이지 원본 화소가 아니다."""
        sz = self.element.find(f"{HP}sz")
        if sz is None:
            return (0, 0)
        return (int(sz.get("width", "0")), int(sz.get("height", "0")))

    @property
    def caption(self) -> str:
        """그림 **다음** 문단의 글. 이 빌더가 캡션을 놓는 자리다.

        캡션은 그림의 자식이 아니라 뒤따르는 별개의 문단이다. 그래서 글자만
        바꾸는 편집이 캡션을 고쳐도 그림은 그대로 남는다 —
        :func:`stale_pictures` 가 잡아내려는 바로 그 상황이다.
        """
        return _next_paragraph_text(self.paragraph)


def iter_pictures(doc, *, section: int | None = None) -> Iterator[PictureRef]:
    """문서의 모든 그림을 나오는 순서대로 넘겨준다.

    표 안에 들어 있는 그림도 포함한다. ``doc.paragraphs`` 는 표 안으로 들어가지
    않으므로 여기서는 요소 트리를 직접 훑는다.
    """
    counter = 0
    for si, sec in enumerate(doc.sections):
        if section is not None and si != section:
            continue
        for para in _all_paragraphs(sec):
            for run in para.runs:
                for child in run.element:
                    if child.tag == f"{HP}pic":
                        yield PictureRef(counter, si, para, run, child)
                        counter += 1


def replace_picture(doc, ref: PictureRef, image_path, *,
                    width_mm: float | None = None,
                    keep_width: bool = True) -> tuple[int, int]:
    """그림의 내용을 다른 이미지로 바꾼다. 새 (폭, 높이) 를 돌려준다.

    **기하값을 손으로 고치지 않는다.** ``<hp:pic>`` 안에는 서로 맞아야 하는
    크기 값이 여덟 군데 있다(``orgSz`` ``curSz`` ``sz`` ``imgRect`` 네 점
    ``imgClip`` ``imgDim`` ``rotationInfo`` 의 중심점). 하나라도 어긋나면 한글은
    그림을 늘리거나 잘라서 그린다. 그래서 :meth:`add_picture` 로 **새 그림을
    제대로 만들게 한 뒤 그 요소를 통째로 끼워 넣고**, 만들면서 생긴 빈 문단을
    치운다.

    높이는 새 이미지의 실제 종횡비로 다시 계산한다. 바이트만 갈아 끼우면 폭과
    높이는 옛 사진의 비율 그대로라, 종횡비가 다른 사진은 눌리거나 늘어난다.

    *keep_width* 가 참이면 원래 배치 폭을 유지한다(기본값). 문단 안에서 그림만
    폭이 달라지면 눈에 띄기 때문이다. *width_mm* 을 주면 그 값이 우선한다.
    """
    from pathlib import Path

    from .boxdoc import _aspect_ratio

    path = Path(image_path)
    data = path.read_bytes()
    fmt = path.suffix.lstrip(".").lower() or "png"

    if width_mm is None:
        old_w, _ = ref.size
        width_mm = (old_w / MM) if (keep_width and old_w) else 100.0
    height_mm = width_mm * _aspect_ratio(data, path)

    # add_picture 는 섹션 끝에 새 문단을 만들어 거기에 그림을 넣는다. 우리는
    # 그 그림 요소만 쓰고 문단은 버린다.
    section = doc.sections[ref.section]
    doc.add_picture(data, fmt, section=section,
                    width_mm=width_mm, height_mm=height_mm, align="CENTER")
    made_para = list(section.paragraphs)[-1]
    made_pic = None
    for run in made_para.runs:
        for child in run.element:
            if child.tag == f"{HP}pic":
                made_pic = child
    if made_pic is None:                    # add_picture 가 모양을 바꾼 경우
        raise RuntimeError("add_picture 가 <hp:pic> 을 만들지 않았다")

    made_pic.getparent().remove(made_pic)
    old = ref.element
    parent = old.getparent()
    made_pic.tail = old.tail
    parent.replace(old, made_pic)
    made_para.element.getparent().remove(made_para.element)

    ref.element = made_pic
    drop_layout_cache(ref.paragraph)        # 그림 크기가 바뀌면 줄 배치도 바뀐다
    return (int(width_mm * MM), int(height_mm * MM))


def drop_orphan_images(doc) -> list[str]:
    """어떤 그림도 가리키지 않는 ``BinData`` 항목을 지운다. 지운 이름들을 돌려준다.

    :func:`replace_picture` 는 옛 이미지의 참조만 끊는다. 바이트는 컨테이너에
    그대로 남는다. HWPX 는 ZIP 이므로 **압축을 풀면 바뀌기 전 사진이 그대로
    나온다.** 다른 사람에게 보내는 문서라면 그건 용량 문제가 아니라 정보가
    새는 문제다.

    참조는 모든 섹션에서 모아서 판단한다. 한 섹션만 보고 지우면 다른 섹션이
    쓰던 이미지를 지워 그림이 깨진다.
    """
    used = set()
    for si in range(len(doc.sections)):
        for ref in iter_pictures(doc, section=si):
            if ref.binary_id:
                used.add(ref.binary_id)

    pkg = doc.package
    removed = []
    for name in list(pkg.part_names()):
        if not name.startswith("BinData/"):
            continue
        stem = name.split("/")[-1].rsplit(".", 1)[0]
        if stem in used:
            continue
        pkg.delete(name)
        pkg.remove_manifest_item(name)
        removed.append(name)
    return removed


def stale_pictures(doc, *, subjects: Sequence[str]) -> list[PictureRef]:
    """캡션이 *subjects* 중 하나를 말하는데 그림은 그대로인 것들을 찾는다.

    글자만 바꾸는 편집의 조용한 실패를 잡는다. :func:`replace_text` 로 문서의
    주제를 바꾸면 캡션은 새 낱말을 갖게 되지만 그림 바이트는 손대지 않은
    그대로다. 결과는 강아지 사진 밑에 "햄스터" 라고 적힌 문서다 — 검사는 전부
    통과하는데 눈으로 보면 완전히 틀린 문서.

    자동으로 고칠 방법은 없다. 어떤 사진이 맞는지는 문서가 알지 못한다. 그래서
    바꿔야 할 후보를 돌려주기만 한다. :func:`replace_picture` 로 무엇을 넣을지는
    사람이 정한다.
    """
    hits = []
    for ref in iter_pictures(doc):
        caption = ref.caption
        if any(s in caption for s in subjects):
            hits.append(ref)
    return hits


def _all_paragraphs(container) -> Iterator:
    """표 안까지 포함해서 문단을 전부 넘겨준다.

    :func:`iter_tables` 를 쓰지 않는다. 그건 중첩된 표까지 한 번에 펼쳐 주는데,
    여기서는 셀 안으로 직접 재귀하므로 중첩 표를 두 번 방문하게 된다.
    """
    for para in getattr(container, "paragraphs", []) or []:
        yield para
        for table in getattr(para, "tables", []) or []:
            for row in table.rows:
                for cell in row.cells:
                    yield from _all_paragraphs(cell)


def _next_paragraph_text(paragraph) -> str:
    element = paragraph.element
    parent = element.getparent()
    if parent is None:
        return ""
    kids = list(parent)
    i = kids.index(element)
    for sib in kids[i + 1:]:
        if sib.tag == f"{HP}p":
            return "".join(sib.itertext()).strip()
    return ""


def has_merged_cells(table) -> bool:
    """한 셀이라도 여러 행 또는 여러 열에 걸쳐 있는지.

    빌더는 병합을 만들지 않지만, 실제 문서에는 병합이 가득하다(실측 두 문서에서
    각각 26개, 34개). 그런 표에서는 ``autofit`` 의 "행 높이 = 그 행 셀 높이의
    최댓값" 모델이 성립하지 않는다. :func:`refit_cell` 이 직접 고치지 않고
    보고만 하는 이유다.
    """
    for row in table.rows:
        for cell in row.cells:
            span = cell.element.find(f"{HP}cellSpan")
            if span is None:
                continue
            if span.get("colSpan", "1") != "1" or span.get("rowSpan", "1") != "1":
                return True
    return False


@dataclass
class FitWarning:
    path: str
    was_lines: int | None
    now_lines: int
    detail: str

    def __str__(self) -> str:
        was = "?" if self.was_lines is None else self.was_lines
        return f"  {self.path}: {was} -> {self.now_lines} line(s); {self.detail}"


def refit_cell(ref: CellRef, *, font_pt: float = 10.0,
               grow: bool = False) -> list[FitWarning]:
    """편집한 텍스트가 아직 들어가는지 확인하고, 원하면 행을 키운다.

    캐시된 ``linesegarray`` 에는 편집 *이전*에 한글이 배치했던 줄 수가 들어
    있다. 표 전체를 다시 추정하는 것보다 훨씬 나은 기준선이다. 그런데 이 모듈의
    편집 함수들은 전부 그 캐시를 지운다. 그러니 **셀을 편집하기 전에 호출할
    것.** 편집 후에는 :func:`cached_line_count` 가 ``None`` 을 돌려주므로 비교할
    대상이 없다.

    ``grow=True`` 면 늘어난 줄 수만큼 행 높이를 키운다. 병합된 표에서는
    거부한다. 거기서 셀 높이는 병합 구간의 높이라서, 고쳐 쓰면 배치가 망가진다.
    기본값은 보고만 하는 것이다. 캐시를 지워 두면 한글이 문서를 열 때 그 행을
    다시 배치하는데, 그게 여기서 계산하는 어떤 값보다 정확하다.
    """
    from hwpx.form_fit.measure import estimate_lines

    from .boxdoc import CELL_PAD, LINE_RATIO

    cell = ref.cell
    inner = max((cell.width or 0) - 2 * CELL_PAD, 1000)
    warnings: list[FitWarning] = []
    extra_lines = 0
    for para in cell.paragraphs:
        text = paragraph_text(para)
        if not text.strip():
            continue
        was = cached_line_count(para)
        now = estimate_lines(text, inner, font_pt)
        if was is not None and now > was:
            extra_lines += now - was
            warnings.append(FitWarning(
                ref.path, was, now,
                f"text grew; row may need +{(now - was)} line(s)"))
    if grow and extra_lines:
        if has_merged_cells(ref.table):
            warnings.append(FitWarning(
                ref.path, None, extra_lines,
                "REFUSED to grow: table has merged cells, "
                "row height is not a per-row value here"))
        else:
            pitch = int(font_pt * 100 * LINE_RATIO)
            for c in list(ref.table.rows)[ref.row].cells:
                c.set_size(height=(c.height or 0) + extra_lines * pitch)
    return warnings
