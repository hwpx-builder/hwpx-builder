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
    autofit,
    table_height,
)
from .convert import hwp_to_hwpx, is_hwp, open_any
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
    highlight_cell,
    iter_cells,
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

__all__ = [
    "A4_HEIGHT", "A4_WIDTH", "BODY_PT", "BoxDoc", "CellRef", "EditReport",
    "Grid", "HEADING_PT", "MARKERS", "PictureRef", "Report", "Span",
    "TITLE_PT", "YELLOW",
    "apply_markpen", "autofit", "body_width", "cached_line_count", "cell_text",
    "derive_char_pr", "dominant_font_pt", "drop_layout_cache",
    "drop_orphan_images", "find_cells", "find_label",
    "clear_guidance", "fill_cell", "flatten_indent", "has_merged_cells",
    "highlight_cell",
    "hwp_to_hwpx", "inch", "is_hwp",
    "iter_cells", "iter_pictures", "iter_tables", "open_any",
    "mm", "paragraph_text", "parse_markup", "pt", "refit_cell",
    "replace_in_paragraph", "replace_picture", "replace_text",
    "set_cell", "set_paragraph", "stale_pictures",
    "split_width", "table_height", "verify",
    # 분석 틀 템플릿
    "budget", "business_model_canvas", "competitor_matrix", "milestones",
    "swot", "tam_sam_som",
]
