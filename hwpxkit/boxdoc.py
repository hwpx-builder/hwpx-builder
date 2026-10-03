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

HH_NS_TAG = "{http://www.hancom.co.kr/hwpml/2011/head}"

HP_NS_TAG = HP

BODY_PT = 10.0        # height=1000. 두 실측 문서 모두에서 본문 크기의 최빈값
HEADING_PT = 13.0
TITLE_PT = 16.0
SOURCE_PT = 8.5       # 그림 출처 줄. 본문보다 작고 캡션과 구분된다

GREY_HEADER = "#F2F2F2"   # container_box 의 라벨 행
GREY_TABLE = "#D9D9D9"    # content_table 의 머리글 행

#: 라벨/소제목 문단을 여는 마커 문자들. 실제 문서에서 이들은 전부 평범한
#: 텍스트다. 한글의 자동 번호 매기기가 **아니다**.
MARKERS = "□·❶❷❸❹▪※○▶◦-"


@dataclass
class Img:
    """칸 안에 넣을 그림 블록. ``Grid`` 와 같은 자리에 섞어 쓴다.

    *path* 는 **실제로 있는 파일**이어야 한다. 없으면 :func:`fill_cell` 이
    예외를 낸다 — 제출 문서에서 잘못된 그림은 빈칸보다 나쁘고(규칙 4),
    조용히 건너뛰면 빠진 줄도 모른다.

    *height_mm* 을 비우면 실제 종횡비로 계산한다.

    *source* 는 그림 아래 작은 글씨 "출처: …" 줄이 된다. 남의 그림(논문
    figure, 기사 캡처, 특허 도면)에는 반드시 단다. *crop* 은 원본에서 쓸 부분
    ``(왼, 위, 오른, 아래)`` — 모두 1 이하면 비율, 아니면 픽셀이다. 기사 캡처의
    광고·메뉴, 논문 figure 의 다른 패널을 잘라 낼 때 쓴다(Pillow 필요).
    """
    path: "str | Path"
    width_mm: float = 105.0
    height_mm: float | None = None
    caption: str = ""
    source: str = ""
    crop: "tuple[float, float, float, float] | None" = None


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
    """작성 중인 문서. A4 기준 페이지 기하를 쓴다.

    *keep_words* (기본 참)는 한글 줄 나눔을 **어절 단위**로 둔다.
    ``HwpxDocument.new()`` 스켈레톤은 한/글 기본값인 글자 단위
    (``BREAK_WORD``)라, 좁은 칸에서 "실험"이 "실 / 험"으로 갈라진다. 한컴이
    만든 배포 양식의 본문 문단은 전부 어절 단위이고, 글꼴 폭이 다른 뷰어
    (폴라리스 오피스 등)에서는 글자 단위 끊김이 훨씬 자주, 더 어색한 자리에서
    난다. 행 높이도 같은 기준으로 잰다(:mod:`hwpxkit.wrap`).

    *bold_figures* 가 참이면 본문 글줄의 숫자(``93.0%``, ``318/342``,
    ``3개월``)를 자동으로 굵게 한다 — 표 칸과 라벨은 제외. 심사자가 훑어
    읽을 때 눈이 멈추는 자리를 숫자로 만들기 위한 것이다.
    """

    doc: object
    width: int = 0
    keep_words: bool = True
    bold_figures: bool = False

    def __post_init__(self):
        # 본문 폭은 문서의 실제 페이지 여백에서 읽는다. 예전에는 U300 상수
        # (여백 20mm 기준 48190)를 썼는데, HwpxDocument.new() 스켈레톤의
        # 여백은 30mm(본문 42520)라 모든 표가 오른쪽 여백을 20mm 침범했다 —
        # preview 렌더러가 발굴하기 전까지 아무 도구도 이를 보지 못했다.
        if not self.width:
            self.width = _doc_body_width(self.doc) or body_width()
        if self.keep_words:
            from .edit import keep_korean_words

            keep_korean_words(self.doc)

    def _markup(self, text: str) -> str:
        """본문 글줄에 적용하는 자동 강조."""
        if self.bold_figures:
            from .prose import bold_figures

            return bold_figures(text)
        return text

    # ------------------------------------------------------------- 텍스트 --

    def paragraph(self, markup: str = "", *, size: float = BODY_PT,
                  bold: bool = False, align: str | None = None):
        """본문 문단을 덧붙인다. ``**굵게**`` 와 ``==형광펜==`` 을 지원한다."""
        para = self.doc.add_paragraph("")
        if markup:
            if not bold:
                markup = self._markup(markup)
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
            self._fill_cell(table, row, 1, self._markup(value))
        autofit(table, keep_words=self.keep_words)
        make_splittable(table)
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
        autofit(table, keep_words=self.keep_words)
        make_splittable(table)
        return table

    def _fill_content(self, table, row: int, col: int, content: Sequence) -> None:
        """container 의 내용 셀을 텍스트 줄과 중첩 표로 채운다."""
        cell = table.cell(row, col)
        existing = list(cell.paragraphs)
        used = 0
        # 중첩 표는 자기만의 앵커 문단이 필요하므로, 텍스트와 표를 한꺼번에
        # 몰아 넣지 않고 순서대로 내보낸다.
        for item in content:
            if isinstance(item, Img):
                from .edit import set_align
                from .units import mm

                path = Path(item.path)
                if not path.exists():
                    raise FileNotFoundError(f"그림 파일이 없다: {path}")
                from hwpx._document.media import add_image

                data, fmt = image_bytes(path, item.crop)
                width = mm(item.width_mm)
                height = (mm(item.height_mm) if item.height_mm is not None
                          else round(width * _aspect_ratio(data, path)))
                para = existing[used] if used < len(existing) else cell.add_paragraph("")
                used += 1
                set_align(self.doc, para, "CENTER", left=0, intent=0)
                para.add_picture(str(add_image(self.doc, data, fmt)),
                                 width=width, height=height, align="CENTER")
                text = caption_line(item.caption, item.source)
                if text:
                    para = cell.add_paragraph("")
                    set_spans(self.doc, para, parse_markup(
                        text, size=BODY_PT if item.caption else SOURCE_PT))
                    set_align(self.doc, para, "CENTER", left=0, intent=0)
                continue
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
                set_spans(self.doc, para,
                          parse_markup(self._markup(str(item)), size=BODY_PT))

    def content_table(self, headers: Sequence[str], rows: Sequence[Sequence[str]],
                      ratios: Sequence[float] | None = None,
                      width: int | None = None,
                      repeat_header: bool = False):
        """머리글 행에 음영이 들어간 colCnt>=3 격자 (재무·일정·비교표 등).

        쪽을 넘길 만큼 긴 표라면 ``repeat_header=True`` 를 줘서 다음 쪽에
        머리글 행이 다시 나오게 한다 ("제목 줄 반복").
        """
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
        autofit(table, keep_words=self.keep_words)
        make_splittable(table)
        if repeat_header:
            set_repeat_header(table)
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
                height_mm: float | None = None, crop=None):
        """이미지를 넣는다. 높이는 실제 종횡비에서 계산한다.

        여섯 개 기하값(``sz``/``orgSz``/``curSz``/``imgRect``/``imgClip``/
        ``imgDim``)은 ``add_picture`` 가 서로 맞춰서 써 준다. ``<hp:pic>`` 을
        직접 조립하지 말 것. *crop* 은 :class:`Img` 와 같다 — 잘라 낸 픽셀로
        새 그림을 만든다(``imgClip`` 으로 자르면 .hwp 변환에서 틀어진다).
        """
        data, fmt = image_bytes(image_path, crop)
        if height_mm is None:
            height_mm = width_mm * _aspect_ratio(data, Path(image_path))
        return self.doc.add_picture(
            data, fmt, width_mm=width_mm, height_mm=height_mm, align="CENTER"
        )

    def figure(self, image_path: str | Path, *, width_mm: float = 150,
               caption: str = "", source: str = "", crop=None,
               height_mm: float | None = None):
        """그림 + 캡션 + 출처 줄. 남의 그림을 넣을 때는 이것을 쓴다.

        그림 바로 아래 가운데에 ``[그림 1] 제목 (출처: …)`` 한 문단으로 쓴다.
        캡션과 출처를 두 문단으로 나누면 출처 줄만 다음 쪽으로 떨어진다(미리보기
        에서 실제로 그랬다). 캡션 번호("[그림 1]")는 호출자가 붙인다 — 문서마다
        체계가 달라서다. 그림 지침은 SKILL.md "Figures" 절.
        """
        from .edit import set_align

        pic = self.picture(image_path, width_mm=width_mm, height_mm=height_mm, crop=crop)
        text = caption_line(caption, source)
        if text:
            # self.paragraph 를 쓰지 않는다 — bold_figures 가 출처의 연도까지 굵게 한다.
            para = self.doc.add_paragraph("")
            set_spans(self.doc, para,
                      parse_markup(text, size=BODY_PT if caption else SOURCE_PT))
            set_align(self.doc, para, "CENTER", left=0, intent=0)
        return pic

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


def _doc_body_width(doc) -> int | None:
    """문서의 pagePr 에서 본문 폭(용지 - 좌우 여백)을 읽는다."""
    for sec in getattr(doc, "sections", []):
        for page in sec.element.iter(f"{HP_NS_TAG}pagePr"):
            m = page.find(f"{HP_NS_TAG}margin")
            if m is None:
                continue
            try:
                return (int(page.get("width"))
                        - int(m.get("left")) - int(m.get("right")))
            except (TypeError, ValueError):
                return None
    return None


def apply_u300_page(doc) -> None:
    """U300 제출 양식의 실측 페이지 지오메트리를 적용한다.

    A4 세로, 좌우 20mm(5669) · 상하/머리말/꼬리말 10mm(2834) → 본문
    48190×72852. 공식 배포 양식(양식. 사업계획서 hwpx)의 pagePr 을 그대로
    옮긴 값이다. BoxDoc 을 만들기 **전에** 호출해야 본문 폭이 이 여백으로
    계산된다.
    """
    margins = {"left": "5669", "right": "5669", "top": "2834",
               "bottom": "2834", "header": "2834", "footer": "2834",
               "gutter": "0"}
    for sec in doc.sections:
        for page in sec.element.iter(f"{HP_NS_TAG}pagePr"):
            m = page.find(f"{HP_NS_TAG}margin")
            for k, v in margins.items():
                m.set(k, v)
        # python-hwpx 는 패치 저장 — dirty 표시 없는 직접 변형은 버려진다.
        sec.mark_dirty()


def make_splittable(table) -> None:
    """표를 본문 흐름에 앉혀서(자리 차지) 쪽 경계에서 나뉠 수 있게 한다.

    python-hwpx 는 모든 표를 ``treatAsChar="1"`` (글자처럼 취급)로 내보내는데,
    한글은 그런 표를 하나의 거대한 "글자"로 배치하므로 ``pageBreak`` 값과
    무관하게 쪽 경계에서 절대 나누지 않는다 — 표가 통째로 다음 쪽으로 밀리고
    앞에 큰 공백이 남는다. 한컴이 만든 실제 양식들은 최상위 표를
    ``treatAsChar="0"`` 으로 앉히고, 같은 문서에서 이 비트 하나만 바꿔도
    5쪽(공백 포함)이 4쪽(흐름)이 되는 것을 실측했다.

    최상위 표 전용이다. 셀 안에 중첩된 표는 인라인이 맞다.
    """
    pos = table.element.find(f"{HP_NS_TAG}pos")
    if pos is not None:
        pos.set("treatAsChar", "0")


def set_repeat_header(table, header_rows: int = 1) -> None:
    """첫 *header_rows* 행을 매 쪽마다 반복시킨다 ("제목 줄 반복").

    한글은 플래그 두 개를 모두 요구한다: ``<hp:tbl>`` 의 ``repeatHeader="1"``
    과 머리글 행 셀들의 ``header="1"``. 표 속성만으로는 아무 행도 반복되지
    않는다 — 한컴 산출 실측 문서 둘 다 ``repeatHeader="1"`` 에 header 셀
    표시가 없고, 실제로 아무것도 반복되지 않는다.

    ``pageBreak="CELL"`` (기본값)인 최상위 표에서만 의미가 있다. 셀 안에
    중첩된 표는 쪽을 넘지 않으므로 반복될 다음 쪽도 없다.
    """
    table.element.set("repeatHeader", "1")
    for row in table.rows[:header_rows]:
        for cell in row.cells:
            cell.element.set("header", "1")


def table_height(table) -> int:
    """표의 행 높이 합계 (HWPUNIT)."""
    total = 0
    for row in table.rows:
        heights = [c.height for c in row.cells if c.height]
        total += max(heights) if heights else 0
    return total


def autofit(table, font_pt: float = BODY_PT, *, keep_words: bool = False) -> int:
    """모든 행을 내용에 맞게 키우고 표 전체 높이를 돌려준다.

    새로 만든 표는 행 높이가 고정이라, 긴 텍스트가 조용히 넘쳐서 옆 행과
    겹친다. 한글은 문서를 열 때 다시 배치하지만 여기서 쓸 수 있는 렌더러는
    그렇게 하지 않고, 넘치는 제출 문서는 어차피 결함이다. 줄 수는
    :mod:`hwpxkit.wrap` 에서 얻는다 — 글자 폭은 실제 한글이 남긴 줄 캐시에
    맞춰 보정된 python-hwpx 표를 쓰고, 끊는 자리는 *keep_words* 를 따른다.
    문서가 어절 단위(``KEEP_WORD``)인데 글자 단위로 재면 줄 수가 모자라
    선언 높이를 그대로 믿는 뷰어에서 마지막 줄이 잘린다. :class:`BoxDoc` 은
    자기 설정을 넘겨 준다.

    중첩 표를 먼저 재귀 처리한다. 바깥 행은 그 안의 표를 담을 만큼 높아야
    하기 때문이다.

    주의: **직접 만들지 않은 표에는 쓰지 말 것.** 병합 셀이 있는 표에서는
    행 높이 모델이 성립하지 않는다 (:func:`hwpxkit.edit.refit_cell` 참고).
    """
    from .wrap import estimate_lines

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
                    used += estimate_lines(text, inner, font_pt,
                                           keep_words=keep_words) * pitch
                elif not _cell_tables(cell):
                    used += pitch
            for nested in _cell_tables(cell):
                # 중첩 표는 자기 앵커 문단을 차지하고, 그 문단도 한 줄을
                # 잡아먹는다. 이걸 빼먹으면 표의 마지막 행이 다음 행에 잘린다.
                used += autofit(nested, font_pt, keep_words=keep_words) + pitch
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


def caption_line(caption: str = "", source: str = "") -> str:
    """``[그림 1] 제목 (출처: …)``. 둘 중 하나만 있으면 그것만."""
    if source and not source.startswith("출처"):
        source = f"출처: {source}"
    if caption and source:
        return f"{caption} ({source})"
    return caption or source


def image_bytes(path: "str | Path", crop=None) -> tuple[bytes, str]:
    """그림 파일의 (바이트, 형식). *crop* 이 있으면 잘라 낸 PNG/JPEG 를 만든다.

    *crop* = ``(왼, 위, 오른, 아래)``. 넷 다 1 이하면 비율, 아니면 픽셀.
    """
    path = Path(path)
    data = path.read_bytes()
    fmt = path.suffix.lstrip(".").lower() or "png"
    if not crop:
        return data, fmt
    try:
        import io

        from PIL import Image
    except ImportError as exc:                       # pragma: no cover
        raise ImportError("crop 에는 Pillow 가 필요하다: pip install \".[images]\"") from exc
    with Image.open(io.BytesIO(data)) as im:
        w, h = im.size
        if all(0 <= v <= 1 for v in crop):
            box = (round(crop[0] * w), round(crop[1] * h),
                   round(crop[2] * w), round(crop[3] * h))
        else:
            box = tuple(int(v) for v in crop)
        if not (0 <= box[0] < box[2] <= w and 0 <= box[1] < box[3] <= h):
            raise ValueError(f"crop {crop} 이 그림 {w}×{h} 밖이다")
        out = im.crop(box)
        buf = io.BytesIO()
        if fmt in ("jpg", "jpeg"):
            out.convert("RGB").save(buf, "JPEG", quality=92)
            fmt = "jpg"
        else:
            out.save(buf, "PNG")
            fmt = "png"
    return buf.getvalue(), fmt


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


def autofit_columns(table, *, min_frac: float = 0.06, damp: float = 0.5,
                    weights: "Sequence[float] | None" = None) -> list[int]:
    """열 너비를 내용량에 맞춰 다시 나눈다. 새 너비 목록을 돌려준다.

    ``Grid(ratios=...)` 는 비율을 **눈 감고 정하게** 만든다. 실제로 그렇게 정한
    비율은 짧은 라벨 열에 너무 넉넉하고 글이 많은 열에 빡빡해서, 받아 본 사람이
    칸마다 손으로 줄바꿈을 넣어 고쳤다(실측: 팀 구성 표 순번 3504->2655,
    경력 26746->28161). 그 조정을 글자 수로 대신한다.

    *damp* 는 글자 수 차이를 그대로 너비로 옮기지 않기 위한 감쇠다 (0.5 면
    제곱근 비례). 1.0 이면 글자 수에 정비례하는데, 그러면 라벨 열이 읽지 못할
    만큼 좁아진다. *min_frac* 은 어떤 열도 그 아래로는 못 가는 하한이다.

    표 전체 너비는 유지한다 — 늘리면 본문 폭을 넘겨서 오른쪽 여백을 침범한다.
    병합 셀이 있으면 열 모델이 성립하지 않으므로 손대지 않고 빈 목록을 돌려준다.
    """
    from .edit import has_merged_cells

    rows = list(table.rows)
    if not rows or has_merged_cells(table):
        return []
    ncols = len(list(rows[0].cells))
    total = sum(c.width or 0 for c in rows[0].cells)
    if not total or ncols < 2:
        return []

    if weights is None:
        load = [0.0] * ncols
        for row in rows:
            for i, cell in enumerate(row.cells):
                if i >= ncols:
                    continue
                text = " ".join(paragraph_text(p_) for p_ in cell.paragraphs)
                # 한 칸의 부담은 '가장 긴 행'이 아니라 평균에 가깝다. 합으로 잡되
                # 머리글 한 줄이 열 전체를 지배하지 않도록 행 수로 나눈다.
                load[i] += len(text.strip())
        load = [x / max(len(rows), 1) for x in load]
        weights = [max(x, 1.0) ** damp for x in load]

    ssum = sum(weights) or 1.0
    frac = [w / ssum for w in weights]
    # 하한을 적용하고 남은 몫을 다시 비례 배분한다.
    for _ in range(4):
        short = [i for i, f in enumerate(frac) if f < min_frac]
        if not short:
            break
        spare = 1.0 - min_frac * len(short)
        rest = sum(frac[i] for i in range(ncols) if i not in short) or 1.0
        frac = [min_frac if i in short else frac[i] / rest * spare
                for i in range(ncols)]

    widths = [int(total * f) for f in frac]
    widths[-1] += total - sum(widths)          # 합계를 표 너비에 정확히 맞춘다
    _set_column_widths(table, widths)
    return widths


def cell_font_pt(doc, cell, default: float = BODY_PT) -> float:
    """셀에서 실제로 쓰인 가장 큰 글자 크기(pt)."""
    header = doc.headers[0].element
    best = 0.0
    for para in cell.paragraphs:
        for run in para.runs:
            cid = run.element.get("charPrIDRef")
            if cid is None:
                continue
            cp = header.find(f".//{HH_NS_TAG}charPr[@id='{cid}']")
            if cp is None:
                continue
            try:
                best = max(best, int(cp.get("height", "1000")) / 100)
            except ValueError:
                pass
    return best or default


def fit_rows(doc, table, *, ratio: float = LINE_RATIO, grow_only: bool = True) -> int:
    """행 높이를 내용에 맞춘다. ``autofit`` 의 안전판. 표 전체 높이를 돌려준다.

    ``autofit`` 과 세 가지가 다르다.

    1. **셀마다 자기 글자 크기로 잰다.** ``autofit`` 은 표 하나에 ``font_pt`` 를
       하나만 쓴다. 표제부가 17 pt 이고 본문이 10 pt 인 배포 양식에서 10 pt 로
       재면 표제부 행이 3179 에서 1866 HWPUNIT 으로 줄고, 한/글은 그 칸에 큰
       글자를 욱여넣어 **글자가 겹친 검은 띠**로 그린다. 실제로 제출 직전
       문서에서 그렇게 났다.
    2. **그림을 높이에 센다.** ``autofit`` 은 ``<hp:pic>`` 을 빼먹는다.
    3. **줄이지 않는다** (*grow_only*). 남의 양식에 높이를 다시 쓰는 일이므로
       (규칙 6·9) 키우기만 한다. 계산이 틀렸을 때 조용히 망가지는 쪽은 늘 축소다.

    ``verify(baseline=…)`` 의 "행 높이 축소" 검사와 짝이다 — 이걸 쓰면 그 검사가
    울릴 일이 없고, 울린다면 진짜 결함이다.
    """
    from .wrap import doc_keeps_words, estimate_lines

    # 남의 양식은 대개 어절 단위다. 문서의 실제 기준으로 재야 행이 모자라지 않는다.
    keep_words = doc_keeps_words(doc)
    total = 0
    for row in table.rows:
        needed = 0
        for cell in row.cells:
            pt = cell_font_pt(doc, cell)
            pitch = int(pt * 100 * ratio)
            inner = max((cell.width or 0) - 2 * CELL_PAD, 1000)
            used = 0
            for para in cell.paragraphs:
                pics = [pic for run in para.runs
                        for pic in run.element.iter(f"{HP_NS_TAG}pic")]
                if pics:
                    # 한 문단의 그림은 글자처럼 나란히 놓이므로 높이는 최댓값.
                    used += max(int(x.find(f"{HP_NS_TAG}sz").get("height", "0"))
                                for x in pics)
                    continue
                text = paragraph_text(para)
                if text.strip():
                    used += estimate_lines(text, inner, pt,
                                           keep_words=keep_words) * pitch
                elif not _cell_tables(cell):
                    used += pitch
            for nested in _cell_tables(cell):
                # 중첩 표는 우리가 만든 것이므로 줄여도 된다.
                used += fit_rows(doc, nested, ratio=ratio, grow_only=False) + pitch
            needed = max(needed, used + 2 * CELL_PAD, pitch)
            if grow_only:
                needed = max(needed, cell.height or 0)
        for cell in row.cells:
            cell.set_size(height=needed)
        total += needed
    sz = table.element.find(f"{HP_NS_TAG}sz")
    if sz is not None:
        sz.set("height", str(total))
    return total
