# -*- coding: utf-8 -*-
"""사진 밀림 공백 검사 + 크기 자동 조정.

사진은 표와 달리 쪽 경계에서 나뉠 수 없다. 남은 공간보다 큰 사진은 통째로
다음 쪽으로 밀리고, 이전 쪽 하단에 큰 공백이 남는다 — 제출 문서에서
심사자가 가장 싫어하는 모양이다.

조판은 :mod:`hwpxkit.preview` 를 그대로 쓴다. 배치를 아는 코드는 한 곳이어야
하고, 미리보기에 보이는 것과 여기서 재는 것이 같은 계산이어야 하기 때문이다.

비교 계열(원래 폭 **또는** 높이가 같은 사진들)은 그룹으로 묶어 항상 같은
배율로 함께 축소한다 — 한 장만 줄이면 크기가 어긋나 공백보다 더 이상해
보인다. 그룹이 ``min_scale`` 아래로 내려가야 해결되는 경우에는 아무도 줄이지
않고 보고만 한다.

표시 크기(sz/curSz/imgRect)만 조정한다. orgSz/imgDim/imgClip 은 원본 크기
공간이므로 건드리면 안 된다 (.hwp 변환에서 crop 이 틀어진다).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .preview import _HC, _HP, SAFETY, render_html


@dataclass
class Block:
    kind: str            # "picture"
    height: int          # HWPUNIT
    page: int = 0
    gap_before: int = 0  # 밀리며 이전 쪽에 남긴 공백 (HWPUNIT)
    pic_el: object = None
    preview: str = "사진"


@dataclass
class GapReport:
    body_width: int
    body_height: int
    pages: int
    blocks: list[Block] = field(default_factory=list)
    adjusted: int = 0    # fit_pictures 가 축소한 사진 수

    @property
    def oversized(self):
        return [b for b in self.blocks if b.gap_before > 0]

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
                f"사진 h={b.height} 밀림{flag}")
        return "\n".join(lines)


def analyze_gaps(path: str | Path) -> GapReport:
    """preview 조판으로 문서를 배치해 사진 밀림 공백을 찾는다."""
    info = render_html(path, out=None)
    blocks = [Block("picture", p["height"], page=p["page"],
                    gap_before=p["gap_before"], pic_el=p["el"])
              for p in info["pictures"]]
    return GapReport(info["body_width"], info["body_height"],
                     info["pages"], blocks)


def fit_pictures(src: str | Path, dest: str | Path | None = None, *,
                 max_gap_ratio: float = 0.12, min_scale: float = 0.55,
                 group_tolerance: float = 0.10, max_rounds: int = 4) -> GapReport:
    """임계치 초과 공백을 만드는 사진을 비교 계열 단위로 함께 축소한다."""
    from hwpx.document import HwpxDocument

    src = Path(src)
    dest = Path(dest) if dest is not None else src
    doc = HwpxDocument.open(str(src))

    first = analyze_gaps(src)
    pics0 = first.blocks
    groups = _group_series(pics0, group_tolerance)
    cum: dict[int, float] = {}
    skipped_groups: list[list[int]] = []
    changed = set()

    report = first
    for round_ in range(max_rounds):
        if round_ > 0:
            report = analyze_gaps(_snapshot(doc))
        pics = report.blocks
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
            scale = min((pics[i].gap_before - SAFETY) / pics[i].height for i in hit)
            if any(cum.get(i, 1.0) * scale < min_scale for i in group):
                skipped_groups.append(group)   # 하한 미달 — 일관성 우선
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
    놓을 때는 높이를 맞추는 것이 균형이라 폭이 서로 다르다. 어느 한 축이라도
    일치하면 같은 계열로 보고 함께 축소한다.
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
    """문서의 n번째(최상위 문단 순서) 사진을 축소한다.

    크기로 찾으면 같은 크기의 비교 계열에서 첫 장만 두 번 줄어드는 사고가
    난다 — 반드시 순서로 찾는다. preview 의 블록 순서와 같은 규칙
    (최상위 hp:p 의 run 바로 아래 hp:pic)으로 센다.
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
                # python-hwpx 는 패치 저장 — dirty 표시 없는 직접 변형은
                # 조용히 버려진다.
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
