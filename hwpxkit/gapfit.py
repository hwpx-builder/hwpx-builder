# -*- coding: utf-8 -*-
"""페이지 공백 검사 + 사진 크기 자동 조정.

문제: 사진은 표와 달리 쪽 경계에서 나뉠 수 없다. 남은 공간보다 큰 사진은
통째로 다음 쪽으로 밀리고, 이전 쪽 하단에 큰 공백이 남는다 — 제출 문서에서
심사자가 가장 싫어하는 모양이다.

해법: 렌더러 없이 배치를 산술로 시뮬레이션한다. 텍스트 줄 수는
``hwpx.form_fit.measure``(실제 한글 줄 캐시로 보정됨), 표 높이는 autofit 이
써 둔 ``hp:sz``, 사진 높이는 선언된 ``hp:sz`` 를 쓴다. 표는 셀 단위로
나뉘므로(자리 차지 + pageBreak=CELL) 공백을 만들지 않는 "흐름" 블록,
사진만 "원자" 블록으로 취급한다.

임계치를 넘는 공백을 만드는 사진은 남은 공간에 맞춰 비율 유지 축소한다.
단, ``min_scale`` 아래로는 줄이지 않는다 — 너무 작아진 사진은 공백보다
나쁘다. 그 경우 보고만 하고 그대로 둔다.

최상위 사진만 다룬다 (셀 안 사진은 셀 높이에 갇히므로 이 문제를 만들지
않는다). 단일 섹션 문서를 가정한다.
"""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import xml.etree.ElementTree as ET

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

#: 한글 응용 기본 줄 간격 160% — hwpxkit.boxdoc.LINE_RATIO 와 동일.
LINE_RATIO = 1.6
#: 문단 여백 등 시뮬레이션이 못 보는 소량 오차의 안전 여유 (HWPUNIT).
SAFETY = 800


@dataclass
class Block:
    kind: str            # "text" | "table" | "picture"
    height: int          # HWPUNIT
    page: int = 0        # 시뮬레이션 결과: 블록이 시작하는 쪽 (1부터)
    gap_before: int = 0  # 이 블록이 밀리며 이전 쪽에 남긴 공백 (HWPUNIT)
    pic_el: object = None      # picture 블록: <hp:pic> 요소
    preview: str = ""


@dataclass
class GapReport:
    body_width: int
    body_height: int
    pages: int
    blocks: list[Block] = field(default_factory=list)
    adjusted: int = 0   # fit_pictures 가 축소한 사진 수

    @property
    def oversized(self):
        return [b for b in self.blocks if b.kind == "picture" and b.gap_before > 0]

    def render(self, max_gap_ratio: float = 0.12) -> str:
        lines = [f"본문 {self.body_width}×{self.body_height} HWPUNIT, 추정 {self.pages}쪽"]
        worst = [b for b in self.blocks if b.gap_before > 0]
        if not worst:
            lines.append("밀림 공백 없음")
        for b in worst:
            pct = b.gap_before / self.body_height
            flag = " ← 임계치 초과" if pct > max_gap_ratio else ""
            lines.append(
                f"  {b.page-1}쪽 하단 공백 {b.gap_before} ({pct:.0%}) — "
                f"{b.kind} h={b.height} 밀림{flag}  [{b.preview[:24]}]"
            )
        return "\n".join(lines)


def _char_heights(header_root) -> dict[str, int]:
    out = {}
    for cp in header_root.iter(f"{_HH}charPr"):
        cid = cp.get("id")
        h = cp.get("height")
        if cid is not None and h is not None:
            out[cid] = int(h)
    return out


def _page_body(sec_root) -> tuple[int, int]:
    page = next(sec_root.iter(f"{_HP}pagePr"))
    margin = page.find(f"{_HP}margin")
    w = int(page.get("width")) - int(margin.get("left")) - int(margin.get("right"))
    h = (int(page.get("height")) - int(margin.get("top")) - int(margin.get("bottom"))
         - int(margin.get("header")) - int(margin.get("footer")))
    return w, h


def _para_text(p_el) -> str:
    parts = []
    for t in p_el.iter(f"{_HP}t"):
        if t.text:
            parts.append(t.text)
        for child in t:
            if child.tail:
                parts.append(child.tail)
    return "".join(parts)


def _para_font_pt(p_el, heights: dict[str, int]) -> float:
    best = 0
    for run in p_el.findall(f"{_HP}run"):
        h = heights.get(run.get("charPrIDRef", ""), 0)
        best = max(best, h)
    return (best or 1000) / 100.0


def _blocks(sec_root, header_root, body_w: int):
    from hwpx.form_fit.measure import estimate_lines

    heights = _char_heights(header_root)
    for p in sec_root.findall(f"{_HP}p"):
        tbl = p.find(f"./{_HP}run/{_HP}tbl")
        pic = p.find(f"./{_HP}run/{_HP}pic")
        if tbl is not None:
            sz = tbl.find(f"{_HP}sz")
            yield Block("table", int(sz.get("height")), preview="표")
        elif pic is not None:
            sz = pic.find(f"{_HP}sz")
            yield Block("picture", int(sz.get("height")), pic_el=pic, preview="사진")
        else:
            text = _para_text(p)
            pt = _para_font_pt(p, heights)
            pitch = int(pt * 100 * LINE_RATIO)
            n = estimate_lines(text, body_w, pt) if text.strip() else 1
            yield Block("text", n * pitch, preview=text.strip()[:30] or "(빈 문단)")


def analyze_gaps(path: str | Path) -> GapReport:
    """문서의 배치를 시뮬레이션해 사진 밀림 공백을 찾는다."""
    with zipfile.ZipFile(path) as z:
        sec_root = ET.fromstring(z.read("Contents/section0.xml"))
        header_root = ET.fromstring(z.read("Contents/header.xml"))
    body_w, body_h = _page_body(sec_root)

    report = GapReport(body_w, body_h, 1)
    y, page = 0, 1
    for b in _blocks(sec_root, header_root, body_w):
        if b.kind == "picture" and b.height <= body_h and y + b.height + SAFETY > body_h:
            b.gap_before = body_h - y          # 이전 쪽 하단에 남는 공백
            page += 1
            y = b.height
        else:
            y += b.height
            while y >= body_h:                  # 텍스트/표는 줄·셀 단위로 나뉜다
                y -= body_h
                page += 1
        b.page = page
        report.blocks.append(b)
    report.pages = page
    return report


def fit_pictures(src: str | Path, dest: str | Path | None = None, *,
                 max_gap_ratio: float = 0.12, min_scale: float = 0.55,
                 group_tolerance: float = 0.10, max_rounds: int = 4) -> GapReport:
    """임계치 초과 공백을 만드는 사진을 축소한다 — 비교 계열은 함께.

    나란히 비교하라고 넣은 사진들(원래 폭이 ``group_tolerance`` 안에서 같은
    사진들)은 한 장만 줄이면 크기가 어긋나 더 이상해 보인다. 그래서 사진을
    원래 폭 기준으로 그룹으로 묶고, 그룹의 어느 한 장이 축소가 필요하면
    **그룹 전체에 같은 배율**을 적용한다. 조정 → 재분석 피드백 루프를 돌려
    공백과 크기 일관성이 동시에 만족될 때까지 반복한다.

    비율은 유지하고, 그룹 누적 배율이 ``min_scale`` 아래로 내려가야 해결되는
    경우에는 그룹 전체를 그대로 두고 보고만 한다 — 너무 작아진 사진은
    공백보다 나쁘다. sz/curSz/imgRect 만 조정한다. orgSz/imgDim/imgClip 은
    원본 크기 공간이므로 건드리면 안 된다 (.hwp 변환에서 crop 이 틀어진다).
    """
    from hwpx.document import HwpxDocument

    src = Path(src)
    dest = Path(dest) if dest is not None else src
    doc = HwpxDocument.open(str(src))

    # 원래 폭 기준 그룹은 첫 분석에서 한 번만 정한다 (라운드마다 다시 묶으면
    # 축소된 사진이 다른 그룹으로 흘러가 일관성이 깨진다).
    first = analyze_gaps(src)
    pics0 = [b for b in first.blocks if b.kind == "picture"]
    groups = _group_series(pics0, group_tolerance)   # [ [pic_index, ...], ... ]
    cum: dict[int, float] = {}                          # pic_index -> 누적 배율
    skipped_groups: list[list[int]] = []
    changed = set()

    report = first
    for round_ in range(max_rounds):
        if round_ > 0:
            report = analyze_gaps(_snapshot(doc))
        pics = [b for b in report.blocks if b.kind == "picture"]
        offenders = {i for i, b in enumerate(pics)
                     if b.gap_before > max_gap_ratio * report.body_height}
        offenders -= {i for g in skipped_groups for i in g}
        if not offenders:
            break
        progressed = False
        for group in groups:
            hit = [i for i in group if i in offenders]
            if not hit:
                continue
            # 그룹에서 가장 크게 줄여야 하는 사진 기준의 공통 배율
            scale = min((pics[i].gap_before - SAFETY) / pics[i].height for i in hit)
            if any(cum.get(i, 1.0) * scale < min_scale for i in group):
                skipped_groups.append(group)   # 하한 미달 — 일관성 우선, 그대로 둔다
                continue
            for i in group:
                _scale_nth_picture(doc, i, scale)
                cum[i] = cum.get(i, 1.0) * scale
                changed.add(i)
            progressed = True
        if not progressed:
            break

    doc.save_to_path(str(dest))
    final = analyze_gaps(dest)
    final.adjusted = len(changed)
    return final


def _group_series(pics: list[Block], tolerance: float) -> list[list[int]]:
    """폭 **또는** 높이가 tolerance 안에서 같은 사진끼리 묶는다.

    비교 계열은 폭을 맞추기도 하지만(같은 width_mm), 가로형·세로형을 나란히
    놓을 때는 **높이**를 맞추는 것이 균형이 맞는 방법이라 폭이 서로 다르다.
    어느 한 축이라도 일치하면 같은 계열로 보고 함께 축소한다.
    """
    dims = []
    for b in pics:
        sz = b.pic_el.find(f"{_HP}sz")
        dims.append((int(sz.get("width")), int(sz.get("height"))))
    groups: list[list[int]] = []
    for i, (w, h) in enumerate(dims):
        for g in groups:
            hw, hh = dims[g[0]]
            if abs(w - hw) <= tolerance * hw or abs(h - hh) <= tolerance * hh:
                g.append(i)
                break
        else:
            groups.append([i])
    return groups


def _snapshot(doc) -> Path:
    import tempfile
    p = Path(tempfile.mktemp(suffix=".hwpx"))
    doc.save_to_path(str(p))
    return p


def _scale_nth_picture(doc, n: int, scale: float) -> None:
    """문서의 n번째(0부터, 최상위 문단 순서) 사진을 축소한다.

    크기로 찾으면 비교 계열처럼 같은 크기 사진이 여럿일 때 첫 장만 두 번
    줄어드는 사고가 난다 — 반드시 순서로 찾는다. analyze_gaps 의 블록 순서와
    동일한 규칙(최상위 hp:p 의 run 바로 아래 hp:pic)으로 센다.
    """
    idx = -1
    for sec in doc.sections:
        for p_el in sec.element.findall(f"{_HP}p"):
            pic = p_el.find(f"./{_HP}run/{_HP}pic")
            if pic is None:
                continue
            idx += 1
            if idx == n:
                _scale_pic_el(pic, scale)
                # python-hwpx 는 패치 저장이다: dirty 로 표시하지 않은 파트는
                # 원본 바이트 그대로 다시 쓰므로 직접 변형은 조용히 버려진다.
                sec.mark_dirty()
                return
    raise LookupError(f"{n}번째 사진을 문서에서 찾지 못함")


def _scale_pic_el(pic, scale: float) -> None:
    sz = pic.find(f"{_HP}sz")
    w = max(1, round(int(sz.get("width")) * scale))
    h = max(1, round(int(sz.get("height")) * scale))
    sz.set("width", str(w))
    sz.set("height", str(h))
    cur = pic.find(f"{_HP}curSz")
    if cur is not None:
        cur.set("width", str(w))
        cur.set("height", str(h))
    rect = pic.find(f"{_HP}imgRect")
    if rect is not None:
        for tag, (x, y) in {"pt0": (0, 0), "pt1": (w, 0),
                            "pt2": (w, h), "pt3": (0, h)}.items():
            el = rect.find(f"{_HC}{tag}")
            if el is not None:
                el.set("x", str(x))
                el.set("y", str(y))
