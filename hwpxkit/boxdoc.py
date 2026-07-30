"""박스형 문서 빌더.

국내 제출 서식은 문단이 죽 이어지는 구조가 아니다. 서로 무관한 실제 문서 두
건을 실측한 결과, 본문은 **최상위 표 5개**에 내용이 한 단계 중첩된 형태였고
**최대 중첩 깊이는 2**였다. 절 제목은 박스와 박스 *사이*에 평범한 문단으로
놓인다.

이 모듈은 그 고정된 박스 연산 어휘만 노출한다. 그래서 호출하는 쪽이 XML 을
직접 쓸 일이 없고, 같은 함정을 두 번 밟지 않는다:

``section_heading``   박스 사이에 놓이는 "1. 문제 인식 / Problem Recognition"
``container_box``     colCnt=1 껍데기. 회색 라벨 행과 내용 행이 번갈아 온다
``label_value_box``   colCnt=2. 왼쪽에 짧은 라벨, 오른쪽에 값
``content_table``     colCnt>=3 격자. 머리글 행에 음영
``bullets``           □ · ❶ ▪ ※ 마커를 자동 번호가 아니라 문자 그대로
``picture``           이미지. 여섯 개 기하값을 서로 맞춰서 넣는다
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from .richtext import HP, Span, add_spans, paragraph_text, parse_markup, set_spans
from .units import A4_WIDTH, body_width, split_width

HP_NS_TAG = HP

BODY_PT = 10.0        # height=1000. 두 실측 문서 모두에서 본문 크기의 최빈값
HEADING_PT = 13.0
TITLE_PT = 16.0

GREY_HEADER = "#F2F2F2"   # container_box 의 라벨 행
GREY_TABLE = "#D9D9D9"    # content_table 의 머리글 행

#: 라벨/소제목 문단을 여는 마커 문자들. 실제 문서에서 이들은 전부 평범한
#: 텍스트다. 한글의 자동 번호 매기기가 **아니다**.
MARKERS = "□·❶❷❸❹▪※○▶◦-"


@dataclass
class Grid:
    """container_box 의 내용 행 안에 중첩되는 표.

    실제 서식은 정확히 한 단계만 중첩된다(실측 최대 깊이 2). Grid 안에 Grid 를
    넣지 말 것. 깊이 3은 실제 문서에서 관측된 적이 없고 어떤 렌더러로도
    검증되지 않았다.
    """

    headers: Sequence[str]
    rows: Sequence[Sequence[str]]
    ratios: Sequence[float] | None = None


@dataclass
class BoxDoc:
    """작성 중인 문서. A4 기준 페이지 기하를 쓴다."""

    doc: object
    width: int = field(default_factory=lambda: body_width())

    # ------------------------------------------------------------- 텍스트 --

    def paragraph(self, markup: str = "", *, size: float = BODY_PT,
                  bold: bool = False, align: str | None = None):
        """본문 문단을 덧붙인다. ``**굵게**`` 와 ``==형광펜==`` 을 지원한다."""
        para = self.doc.add_paragraph("")
        if markup:
            set_spans(self.doc, para, parse_markup(markup, size=size, bold=bold))
        return para

    def section_heading(self, text: str):
        """박스 사이에 놓이는 번호 붙은 절 제목.

        이 문서들에서는 굵기만으로 제목을 판별할 수 없다. 본문도 강조에 굵기를
        쓰기 때문이다. 제목은 **굵고 AND 본문 크기보다 큰** 것이다.
        """
        return self.paragraph(text, size=HEADING_PT, bold=True)

    def title(self, text: str):
        return self.paragraph(text, size=TITLE_PT, bold=True)

    def spacer(self):
        """빈 문단. 박스를 연달아 놓으면 서로 붙어버린다."""
        return self.doc.add_paragraph("")

    # --------------------------------------------------------------- 박스 --

    def label_value_box(self, pairs: Sequence[tuple[str, str]],
                        ratios: tuple[float, float] = (0.28, 0.72)):
        """colCnt=2 박스. 왼쪽에 짧은 라벨, 오른쪽에 값."""
        widths = split_width(self.width, ratios)
        table = self.doc.add_table(len(pairs), 2, width=self.width)
        _set_column_widths(table, widths)
        for row, (label, value) in enumerate(pairs):
            self._fill_cell(table, row, 0, label, bold=True, shade=GREY_HEADER)
            self._fill_cell(table, row, 1, value)
        autofit(table)
        return table

    def container_box(self, blocks: Sequence[tuple[str, Sequence]]):
        """colCnt=1 껍데기. 블록 하나는 회색 라벨 행 + 내용 행 한 쌍이다.

        가장 많이 쓰이는 형태다. 실측 문서에서 최상위 표 5개 중 4개가 정확히
        이 구조였다. 블록의 내용은 ``str`` 줄과 :class:`Grid` 중첩 표를 섞은
        시퀀스다.
        """
        rows = len(blocks) * 2
        table = self.doc.add_table(rows, 1, width=self.width)
        _set_column_widths(table, (self.width,))
        for i, (label, content) in enumerate(blocks):
            self._fill_cell(table, i * 2, 0, label, bold=True, shade=GREY_HEADER)
            self._fill_content(table, i * 2 + 1, 0, content)
        autofit(table)
        return table

    def _fill_content(self, table, row: int, col: int, content: Sequence) -> None:
        """container 의 내용 셀을 텍스트 줄과 중첩 표로 채운다."""
        cell = table.cell(row, col)
        existing = list(cell.paragraphs)
        used = 0
        # 중첩 표는 자기만의 앵커 문단이 필요하므로, 텍스트와 표를 한꺼번에
        # 몰아 넣지 않고 순서대로 내보낸다.
        for item in content:
            if isinstance(item, Grid):
                # 칸을 꽉 채운다. 예전에는 0.96 을 썼는데, 남는 4% 가 표 오른쪽에
                # 빈 띠로 보인다(48190 기준 약 1900 HWPUNIT, 6.8 mm).
                inner_width = self.width
                ncols = len(item.headers)
                ratios = tuple(item.ratios or [1.0] * ncols)
                widths = split_width(inner_width, ratios)
                inner = cell.add_table(len(item.rows) + 1, ncols, width=inner_width)
                _set_column_widths(inner, widths)
                for c, head in enumerate(item.headers):
                    self._fill_cell(inner, 0, c, head, bold=True, shade=GREY_TABLE)
                for r, rowvals in enumerate(item.rows, start=1):
                    for c, val in enumerate(rowvals):
                        self._fill_cell(inner, r, c, val)
            else:
                para = existing[used] if used < len(existing) else cell.add_paragraph("")
                used += 1
                set_spans(self.doc, para, parse_markup(str(item), size=BODY_PT))

    def content_table(self, headers: Sequence[str], rows: Sequence[Sequence[str]],
                      ratios: Sequence[float] | None = None,
                      width: int | None = None):
        """머리글 행에 음영이 들어간 colCnt>=3 격자 (재무·일정·비교표 등)."""
        total = width or self.width
        ncols = len(headers)
        ratios = tuple(ratios or [1.0] * ncols)
        widths = split_width(total, ratios)
        table = self.doc.add_table(len(rows) + 1, ncols, width=total)
        _set_column_widths(table, widths)
        for col, head in enumerate(headers):
            self._fill_cell(table, 0, col, head, bold=True, shade=GREY_TABLE)
        for r, row in enumerate(rows, start=1):
            for c, cell in enumerate(row):
                self._fill_cell(table, r, c, cell)
        autofit(table)
        return table

    def bullets(self, items: Iterable[str], marker: str = "·",
                size: float = BODY_PT):
        """마커를 앞에 붙인 줄들. 마커는 자동 번호가 아니라 그냥 텍스트다."""
        out = []
        for item in items:
            out.append(self.paragraph(f"{marker} {item}", size=size))
        return out

    # ------------------------------------------------------------- 이미지 --

    def picture(self, image_path: str | Path, *, width_mm: float = 150,
                height_mm: float | None = None):
        """이미지를 넣는다. 높이는 실제 종횡비에서 계산한다.

        여섯 개 기하값(``sz``/``orgSz``/``curSz``/``imgRect``/``imgClip``/
        ``imgDim``)은 ``add_picture`` 가 서로 맞춰서 써 준다. ``<hp:pic>`` 을
        직접 조립하지 말 것.
        """
        path = Path(image_path)
        data = path.read_bytes()
        fmt = path.suffix.lstrip(".").lower() or "png"
        if height_mm is None:
            height_mm = width_mm * _aspect_ratio(data, path)
        return self.doc.add_picture(
            data, fmt, width_mm=width_mm, height_mm=height_mm, align="CENTER"
        )

    def image_placeholder(self, message: str):
        """이미지가 없을 때 눈에 보이는 빈칸을 남긴다.

        제출 문서에서 틀린 이미지는 빈칸보다 나쁘다. 절대 지어내지 말고
        여기에 무엇이 들어가야 하는지 적어 둘 것.
        """
        return self.paragraph(f"[ 이미지 자리 — {message} ]", size=BODY_PT, bold=True)

    # -------------------------------------------------------------- 내부 --

    def _fill_cell(self, table, row: int, col: int, markup: str,
                   *, bold: bool = False, shade: str | None = None,
                   size: float = BODY_PT):
        if shade:
            table.set_cell_shading(row, col, shade)
        cell = table.cell(row, col)
        paragraphs = list(cell.paragraphs)
        lines = markup.split("\n") if markup else [""]
        for i, line in enumerate(lines):
            if i < len(paragraphs):
                para = paragraphs[i]
            else:
                para = cell.add_paragraph("")
            set_spans(self.doc, para, parse_markup(line, size=size, bold=bold))


#: 셀 안쪽에서 한글이 선언된 여백 외에 추가로 잡는 가로 여백.
CELL_PAD = 283          # 약 1 mm
#: 줄 간격 160%(한글 기본값) 기준으로 한 줄이 차지하는 세로 길이.
LINE_RATIO = 1.6


def _cell_tables(cell) -> list:
    """셀의 문단들 안에 들어 있는 중첩 표."""
    found = []
    for para in cell.paragraphs:
        found.extend(getattr(para, "tables", []) or [])
    return found


def table_height(table) -> int:
    """표의 행 높이 합계 (HWPUNIT)."""
    total = 0
    for row in table.rows:
        heights = [c.height for c in row.cells if c.height]
        total += max(heights) if heights else 0
    return total


def autofit(table, font_pt: float = BODY_PT) -> int:
    """모든 행을 내용에 맞게 키우고 표 전체 높이를 돌려준다.

    새로 만든 표는 행 높이가 고정이라, 긴 텍스트가 조용히 넘쳐서 옆 행과
    겹친다. 한글은 문서를 열 때 다시 배치하지만 여기서 쓸 수 있는 렌더러는
    그렇게 하지 않고, 넘치는 제출 문서는 어차피 결함이다. 줄 수는
    ``hwpx.form_fit.measure`` 에서 얻는다. 이 모듈의 글자 폭은 실제 한글이
    남긴 줄 캐시에 맞춰 보정돼 있다.

    중첩 표를 먼저 재귀 처리한다. 바깥 행은 그 안의 표를 담을 만큼 높아야
    하기 때문이다.

    주의: **직접 만들지 않은 표에는 쓰지 말 것.** 병합 셀이 있는 표에서는
    행 높이 모델이 성립하지 않는다 (:func:`hwpxkit.edit.refit_cell` 참고).
    """
    from hwpx.form_fit.measure import estimate_lines

    pitch = int(font_pt * 100 * LINE_RATIO)
    total = 0
    for row in table.rows:
        needed = pitch
        for cell in row.cells:
            inner = max((cell.width or 0) - 2 * CELL_PAD, 1000)
            used = 0
            for para in cell.paragraphs:
                text = paragraph_text(para)
                if text.strip():
                    used += estimate_lines(text, inner, font_pt) * pitch
                elif not _cell_tables(cell):
                    used += pitch
            for nested in _cell_tables(cell):
                # 중첩 표는 자기 앵커 문단을 차지하고, 그 문단도 한 줄을
                # 잡아먹는다. 이걸 빼먹으면 표의 마지막 행이 다음 행에 잘린다.
                used += autofit(nested, font_pt) + pitch
            needed = max(needed, used + 2 * CELL_PAD)
        for cell in row.cells:
            cell.set_size(height=needed)
        total += needed

    # 표 자신의 <hp:sz> 도 행 높이 합계와 일치해야 한다. 어긋나면 테두리가
    # 내용을 잘라낸다.
    sz = table.element.find(f"{HP_NS_TAG}sz")
    if sz is not None:
        sz.set("height", str(total))
    return total


def _set_column_widths(table, widths: Sequence[int]) -> None:
    """열 너비 합계가 표 너비와 맞도록 각 셀의 너비를 써 넣는다.

    표 너비는 표 자체 *그리고* 모든 셀 양쪽에 선언해야 한다. 둘 중 하나만
    설정하면 그려지는 테두리와 텍스트 줄바꿈 폭이 서로 달라져서, 텍스트가
    보이는 테두리 밖으로 삐져나간다. DOCX 의 이중 너비 함정과 같은 구조다.

    ``cell.width`` 는 읽기 전용이라 대입하면 예외가 난다. 여기에 그냥
    ``except`` 를 씌우면 모든 열이 기본값 7200 에 머무는 것을 조용히 넘기게
    된다. ``set_size`` 를 쓰고, 오류는 그대로 드러나게 둘 것.
    """
    for row in table.rows:
        for col, cell in enumerate(row.cells):
            if col < len(widths):
                cell.set_size(width=widths[col])


def _aspect_ratio(data: bytes, path: Path) -> float:
    """이미지의 높이/너비. Pillow 가 없으면 3:4 로 가정한다."""
    try:
        import io

        from PIL import Image

        with Image.open(io.BytesIO(data)) as im:
            w, h = im.size
        if w:
            return h / w
    except Exception:
        pass
    return 0.75
