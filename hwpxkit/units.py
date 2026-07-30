"""HWPUNIT 단위 변환.

1 inch = 7200 HWPUNIT, 1 pt = 100 HWPUNIT, 1 mm = 7200/25.4 HWPUNIT.
글자 크기도 같은 단위를 쓰므로 10 pt 텍스트는 height="1000" 이다.

예외: 줄 간격만은 HWPUNIT 이 아니라 **퍼센트**다. 한글의 기본값은 160%.
"""
from __future__ import annotations

HWP_PER_INCH = 7200
HWP_PER_PT = 100
HWP_PER_MM = 7200 / 25.4

#: A4 세로. 국내 제출 서식이 실무에서 쓰는 사실상 유일한 용지 크기.
A4_WIDTH = 59528
A4_HEIGHT = 84188


def mm(value: float) -> int:
    """밀리미터 -> HWPUNIT."""
    return round(value * HWP_PER_MM)


def pt(value: float) -> int:
    """포인트 -> HWPUNIT. 글자 크기(height) 에도 같은 값을 쓴다."""
    return round(value * HWP_PER_PT)


def inch(value: float) -> int:
    """인치 -> HWPUNIT."""
    return round(value * HWP_PER_INCH)


def to_mm(value: int) -> float:
    """HWPUNIT -> 밀리미터."""
    return value / HWP_PER_MM


def body_width(page_width: int = A4_WIDTH, margin_lr: int = 5669) -> int:
    """본문에 쓸 수 있는 폭 = 용지 폭 - 좌우 여백.

    기본값은 좌우 20 mm(5669 HWPUNIT) 여백이라 48190 이 된다. 표의 열 너비
    합계가 이 값을 넘으면 안 된다.
    """
    return page_width - 2 * margin_lr


def split_width(total: int, ratios: tuple[float, ...]) -> tuple[int, ...]:
    """*total* 을 *ratios* 비율의 정수 열 너비로 나눈다.

    반올림 오차는 마지막 열이 흡수해서 합계가 항상 정확히 *total* 이 되도록
    한다. 열 너비 합계가 표 너비와 어긋나면 한글이 오른쪽 끝을 눈에 띄게
    들쭉날쭉하게 그린다.
    """
    scale = sum(ratios)
    widths = [int(total * r / scale) for r in ratios[:-1]]
    widths.append(total - sum(widths))
    return tuple(widths)
