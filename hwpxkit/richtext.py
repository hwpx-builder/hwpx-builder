"""서식 있는 run 과 진짜 형광펜(markpen) 지원.

``python-hwpx`` 도 ``pyhwpxlib`` 도 제대로 하지 못하는 유일한 연산이다.

``python-hwpx`` 의 ``ensure_run_style(highlight=...)`` 는 ``charPr/@shadeColor``
를 설정하는데, 이건 형광펜이 아니라 셀 **음영**이라 눈에 띄게 다르게 보인다.
실제 한글 문서는 형광펜을 ``<hp:t>`` **안에 들어가는 빈 태그 한 쌍**으로 표시한다::

    <hp:run charPrIDRef="53"><hp:t><hp:markpenBegin color="#FFFF00"/>핵심 지표:</hp:t></hp:run>
    <hp:run charPrIDRef="29"><hp:t><hp:markpenEnd/> 전년 대비 32% 개선 ...</hp:t></hp:run>

위 예에서 한 쌍이 run 두 개에 걸쳐 있는 점에 주의. ``markpenEnd`` 가 *다음* run
을 여는 형태다. begin/end 는 run 경계와 무관하게 잡히고, 바로 이 성질 때문에
단순 텍스트 치환이 짝을 깨뜨린다.

우리가 새로 쓸 때는 run 생성을 우리가 통제하므로, 형광펜이 run 경계를 넘을
필요가 없는 자기완결형(한 ``<hp:t>`` 안에 begin 과 end 가 모두 있는 형태)으로
쓴다::

    <hp:t><hp:markpenBegin color="#FFFF00"/>텍스트<hp:markpenEnd/></hp:t>

두 형태의 렌더 결과는 같지만, 자기완결형은 짝이 끊길 수가 없다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET

HP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
HP = f"{{{HP_NS}}}"

#: 국내 문서에서 형광펜 색으로 관례적으로 쓰이는 노란색.
YELLOW = "#FFFF00"


@dataclass(frozen=True)
class Span:
    """문단 안에서 하나의 서식이 적용되는 텍스트 조각.

    ``highlight`` 에는 ``"#FFFF00"`` 같은 색을 넣는다. ``shadeColor`` 가 아니라
    진짜 markpen 쌍을 만든다.
    """

    text: str
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str | None = None
    size: float | None = None          # 포인트 단위
    font: str | None = None
    highlight: str | None = None

    def with_text(self, text: str) -> "Span":
        return Span(
            text=text,
            bold=self.bold,
            italic=self.italic,
            underline=self.underline,
            color=self.color,
            size=self.size,
            font=self.font,
            highlight=self.highlight,
        )


def _find_text_element(run_element: ET.Element) -> ET.Element | None:
    for child in run_element:
        if child.tag == f"{HP}t":
            return child
    return None


def apply_markpen(run_element: ET.Element, color: str = YELLOW) -> None:
    """run 의 기존 ``<hp:t>`` 내용을 markpen begin/end 쌍으로 감싼다.

    멱등이다. 이미 ``markpenBegin`` 을 달고 있는 run 은 그대로 두므로, 빌드
    단계를 다시 실행해도 형광펜이 중첩되지 않는다.
    """
    t = _find_text_element(run_element)
    if t is None:
        return
    for child in t:
        if child.tag == f"{HP}markpenBegin":
            return  # 이미 형광펜이 칠해져 있음

    # 요소를 만들 때는 부모의 팩토리를 쓴다. python-hwpx 는 lxml 이 설치돼 있으면
    # lxml 로 파싱하는데, lxml 은 표준 ElementTree 노드를 거부한다.
    begin = t.makeelement(f"{HP}markpenBegin", {"color": color})
    # 텍스트가 markpenBegin 의 tail 로 옮겨간다. 형광펜이 칠해진 텍스트를
    # `<hp:t>.text` 로 읽으면 놓치는 이유가 이것이다 (references/gotchas.md 참고).
    begin.tail = t.text
    t.text = None
    t.insert(0, begin)
    t.append(t.makeelement(f"{HP}markpenEnd", {}))


def run_text(run_element: ET.Element) -> str:
    """markpen tail 에 실린 텍스트까지 **포함해서** run 의 텍스트를 읽는다.

    ``HwpxOxmlParagraph.text`` 는 ``<hp:t>.text`` 만 읽기 때문에 형광펜이 칠해진
    run 에서는 빈 문자열을 돌려준다. 검증할 때는 이 함수를 쓸 것.
    """
    out: list[str] = []
    for child in run_element:
        if child.tag == f"{HP}t":
            if child.text:
                out.append(child.text)
            for sub in child:
                if sub.tail:
                    out.append(sub.tail)
        elif child.tag == f"{HP}tab":
            out.append("\t")
    return "".join(out)


def paragraph_text(paragraph) -> str:
    """``paragraph.text`` 를 대체하는, markpen 을 인식하는 읽기."""
    return "".join(run_text(r.element) for r in paragraph.runs)


def add_spans(doc, paragraph, spans: Iterable[Span]) -> None:
    """*spans* 를 문단에 하나씩 run 으로 덧붙이고, 필요하면 markpen 을 적용한다.

    텍스트가 빈 span 은 건너뛴다. ``<hp:t>`` 가 없는 run 을 남기면 한글이
    의도치 않은 빈 줄로 그린다.
    """
    for span in spans:
        if not span.text:
            continue
        char_id = doc.ensure_run_style(
            bold=span.bold,
            italic=span.italic,
            underline=span.underline,
            color=span.color,
            font=span.font,
            size=span.size,
        )
        run = paragraph.add_run(span.text, char_pr_id_ref=char_id)
        if span.highlight:
            apply_markpen(run.element, span.highlight)


def clear_runs(paragraph) -> None:
    """문단의 run 을 모두 제거한다. 문단 자체의 스타일 참조는 남는다."""
    for run in paragraph.runs:
        paragraph.element.remove(run.element)


def set_spans(doc, paragraph, spans: Sequence[Span]) -> None:
    """문단 내용을 *spans* 로 교체한다."""
    clear_runs(paragraph)
    add_spans(doc, paragraph, spans)


def parse_markup(text: str, **base) -> list[Span]:
    """아주 작은 인라인 마크업을 span 목록으로 파싱한다.

    ``**텍스트**`` 는 굵게, ``==텍스트==`` 는 노란 형광펜. ``**==텍스트==**`` 처럼
    겹쳐 쓸 수 있다. 나머지는 전부 문자 그대로이고 이스케이프 문법은 없다.
    생성된 내용을 다룰 때 파서가 예측 가능하도록 일부러 단순하게 두었다.

    키워드 인자는 만들어지는 모든 span 의 기본 서식이 된다 (예: ``size=10``).
    """
    import re

    spans: list[Span] = []
    pattern = re.compile(r"(\*\*==.+?==\*\*|==\*\*.+?\*\*==|\*\*.+?\*\*|==.+?==)")
    for chunk in pattern.split(text):
        if not chunk:
            continue
        bold = base.get("bold", False)
        highlight = base.get("highlight")
        body = chunk
        changed = True
        while changed:
            changed = False
            if body.startswith("**") and body.endswith("**") and len(body) > 4:
                body, bold, changed = body[2:-2], True, True
            elif body.startswith("==") and body.endswith("==") and len(body) > 4:
                body, highlight, changed = body[2:-2], YELLOW, True
        kwargs = dict(base)
        kwargs["bold"] = bold
        kwargs["highlight"] = highlight
        spans.append(Span(text=body, **kwargs))
    return spans
