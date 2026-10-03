"""hwpxkit — 한글(HWPX) 문서를 만들고 편집하기 위한 도구 모음.

``python-hwpx`` (Apache-2.0) 위에 얹어서, 그쪽이 다루지 않는 부분을 채운다.
진짜 형광펜 마크업, 이런 문서들이 실제로 쓰는 박스형 어휘, 층으로 나눈 검증
루프, 그리고 :mod:`hwpxkit.edit` 의 셀 단위 순회와 레이아웃 캐시 무효화다.
마지막 것은 기존 파일을 편집할 때 반드시 필요한데 원 라이브러리의 문단 단위
API 로는 되지 않는다.
"""
from .boxdoc import (
    BODY_PT,
    HEADING_PT,
    MARKERS,
    TITLE_PT,
    BoxDoc,
    Grid,
    Img,
    autofit_columns,
    cell_font_pt,
    fit_rows,
    apply_u300_page,
    autofit,
    make_splittable,
    set_repeat_header,
    table_height,
)
from .convert import hwp_to_hwpx, is_hwp, open_any
from .gapfit import GapReport, analyze_gaps, fit_pictures
from .preview import lint, render_html, render_pdf, render_png
from .hwp_export import (
    ExportReport,
    HwpExportError,
    find_converter_jar,
    hancom_opens_hwpx,
    hancom_version,
    to_hwp,
)
from .edit import (
    CellRef,
    clear_guidance,
    fill_cell,
    flatten_indent,
    EditReport,
    cached_line_count,
    cell_text,
    derive_char_pr,
    dominant_font_pt,
    drop_layout_cache,
    drop_orphan_images,
    find_cells,
    find_label,
    PictureRef,
    has_merged_cells,
    char_style,
    ensure_face,
    highlight_cell,
    iter_cells,
    keep_korean_words,
    restyle,
    set_align,
    iter_pictures,
    iter_tables,
    refit_cell,
    replace_in_paragraph,
    replace_picture,
    replace_text,
    stale_pictures,
    set_cell,
    set_paragraph,
)
from .richtext import (
    YELLOW,
    Span,
    apply_markpen,
    paragraph_text,
    parse_markup,
    set_spans,
)
from .templates import (budget, business_model_canvas, competitor_matrix,
                        milestones, swot, tam_sam_som)
from .units import A4_HEIGHT, A4_WIDTH, body_width, inch, mm, pt, split_width
from .verify import Report, verify
from .wrap import doc_keeps_words, estimate_lines

#: 문장 검토는 지연 import 한다. ``python -m hwpxkit.prose`` 가 CLI 인데, 패키지가
#: 먼저 하위 모듈을 import 해 두면 runpy 가 "이미 sys.modules 에 있다"고 경고한다.
_PROSE_NAMES = {"Finding", "ProseReport", "bold_figures", "dump_text",
                "review_blocks", "review_document", "review_text",
                "humanize_punct", "is_identifier", "detect_register"}


def __getattr__(name):
    if name in _PROSE_NAMES:
        from . import prose

        return getattr(prose, name)
    raise AttributeError(f"module 'hwpxkit' has no attribute {name!r}")

__all__ = [
    "A4_HEIGHT", "A4_WIDTH", "BODY_PT", "BoxDoc", "CellRef", "EditReport",
    "ExportReport", "GapReport", "Grid", "HEADING_PT", "HwpExportError", "MARKERS", "PictureRef", "Report", "Span",
    "TITLE_PT", "YELLOW",
    "Img", "apply_markpen", "apply_u300_page", "autofit", "autofit_columns",
    "cell_font_pt", "char_style", "ensure_face", "fit_rows", "keep_korean_words", "restyle", "set_align", "body_width", "cached_line_count", "cell_text",
    "derive_char_pr", "dominant_font_pt", "drop_layout_cache",
    "drop_orphan_images", "find_cells", "find_label",
    "clear_guidance", "fill_cell", "flatten_indent", "has_merged_cells",
    "highlight_cell",
    "analyze_gaps", "find_converter_jar", "fit_pictures",
    "hancom_opens_hwpx", "hancom_version",
    "hwp_to_hwpx", "inch", "is_hwp", "make_splittable",
    "iter_cells", "iter_pictures", "iter_tables", "open_any",
    "mm", "paragraph_text", "parse_markup", "pt", "refit_cell",
    "lint", "render_html", "render_pdf", "render_png",
    "replace_in_paragraph", "replace_picture", "replace_text",
    "set_cell", "set_paragraph", "stale_pictures",
    "set_repeat_header", "split_width", "table_height", "to_hwp", "verify",
    # 분석 틀 템플릿
    "budget", "business_model_canvas", "competitor_matrix", "milestones",
    "swot", "tam_sam_som",
    # 문장 검토 · 줄 나눔
    "Finding", "ProseReport", "bold_figures", "dump_text", "review_blocks",
    "review_document", "review_text", "humanize_punct", "is_identifier",
    "detect_register", "doc_keeps_words", "estimate_lines",
]
