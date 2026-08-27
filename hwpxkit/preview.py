# -*- coding: utf-8 -*-
"""HWPX 자체 미리보기 렌더러 (프로토타입, Apache-2.0 재료만 사용).

rhwp 기반 미리보기의 근본 한계를 대체한다: rhwp 는 문서에 저장된
``<hp:linesegarray>`` 캐시를 재생할 뿐 스스로 조판하지 못해서, 캐시가 없는
새 문서(우리가 만드는 모든 문서)는 줄바꿈도 쪽수도 엉터리로 나온다.

이 렌더러는 반대로 간다 — 캐시를 무시하고 **직접 조판한다**:

- 줄 수: ``hwpx.form_fit.measure`` (실제 한글 줄 캐시로 보정된 글자 폭)
- 쪽 나눔: gapfit 과 같은 산술. 표는 행 경계에서 실제로 나뉘고(제목 줄
  반복 지원), 사진은 원자 블록이라 밀리면 **공백이 그대로 보인다** —
  미리보기가 문제를 숨기지 않고 드러낸다.
- 출력: 페이지 크기 div 가 이어지는 자립 HTML 한 파일 (이미지 base64 내장)

의존성: 표준 라이브러리 + python-hwpx 의 form_fit (둘 다 Apache-2.0).
PNG/PDF 내보내기만 로컬 Chrome(headless)을 실행한다 — 링크되는 것은 없다.

gapfit(사진 공백 조정)도 이 조판을 공유한다: 배치를 아는 코드는 이 모듈
하나여야 하고, 두 곳에 있으면 처음 고칠 때 바로 어긋난다.
"""
from __future__ import annotations

import base64
import html
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import xml.etree.ElementTree as ET

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
_HH = "{http://www.hancom.co.kr/hwpml/2011/head}"
_HC = "{http://www.hancom.co.kr/hwpml/2011/core}"

PX = 1 / 75          # 96dpi: 1px = 75 HWPUNIT
LINE_RATIO = 1.6     # 한글 응용 기본 줄 간격 160%
SAFETY = 800         # 시뮬레이션이 못 보는 소량 오차 (HWPUNIT)


def _px(v: float) -> str:
    return f"{v * PX:.1f}px"


# ---------------------------------------------------------------- 스타일 --

@dataclass
class CharStyle:
    height: int = 1000          # 1/100 pt
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = "#000000"

    @property
    def pt(self) -> float:
        return self.height / 100.0


@dataclass
class Theme:
    char: dict[str, CharStyle] = field(default_factory=dict)
    align: dict[str, str] = field(default_factory=dict)       # paraPr id -> css
    spacing: dict[str, float] = field(default_factory=dict)   # paraPr id -> 줄간격 배수
    fill: dict[str, str] = field(default_factory=dict)        # borderFill id -> css color
    border: dict[str, dict[str, str]] = field(default_factory=dict)  # id -> side -> css


def _parse_theme(header_root) -> Theme:
    t = Theme()
    for cp in header_root.iter(f"{_HH}charPr"):
        cid = cp.get("id")
        if cid is None:
            continue
        st = CharStyle(height=int(cp.get("height", "1000")))
        if cp.find(f"{_HH}bold") is not None:
            st.bold = True
        if cp.find(f"{_HH}italic") is not None:
            st.italic = True
        ul = cp.find(f"{_HH}underline")
        if ul is not None and ul.get("type", "NONE") not in ("NONE", "none"):
            st.underline = True
        col = cp.get("textColor")
        if col and col.lower() not in ("none", "#none"):
            st.color = col
        t.char[cid] = st
    for pp in header_root.iter(f"{_HH}paraPr"):
        pid = pp.get("id")
        if pid is None:
            continue
        al = pp.find(f"{_HH}align")
        if al is not None:
            t.align[pid] = {
                "CENTER": "center", "RIGHT": "right", "JUSTIFY": "justify",
                "DISTRIBUTE": "justify",
            }.get(al.get("horizontal", ""), "left")
        # 줄간격. 문단마다 다를 수 있는데 예전에는 문서 전체를 160% 로 박아
        # 두었다 — 줄간격을 바꿔도 미리보기 쪽 수가 꿈쩍하지 않았다.
        #
        # ``<hh:lineSpacing>`` 은 paraPr 의 **직접 자식이 아니다** — find() 로는
        # 못 찾는다. 게다가 같은 값이 두 번 들어 있는 경우가 있어 첫 개만 쓴다.
        for ls in pp.iter(f"{_HH}lineSpacing"):
            if ls.get("type") == "PERCENT":
                try:
                    t.spacing[pid] = int(ls.get("value", "160")) / 100
                except ValueError:
                    pass
            break
    for bf in header_root.iter(f"{_HH}borderFill"):
        bid = bf.get("id")
        if bid is None:
            continue
        wb = bf.find(f".//{_HC}winBrush")
        if wb is not None:
            face = wb.get("faceColor")
            if face and face.lower() not in ("none", "#none"):
                t.fill[bid] = face
        sides = {}
        for side, css in (("leftBorder", "border-left"), ("rightBorder", "border-right"),
                          ("topBorder", "border-top"), ("bottomBorder", "border-bottom")):
            el = bf.find(f"{_HH}{side}")
            if el is None:
                continue
            sides[css] = _border_css(el.get("type", "SOLID"),
                                     el.get("width", "0.12 mm"),
                                     el.get("color", "#000000"))
        t.border[bid] = sides
    return t


def _border_css(kind: str, width: str, color: str) -> str:
    if kind == "NONE":
        return "none"
    mm = 0.12
    m = re.match(r"([\d.]+)", width or "")
    if m:
        mm = float(m.group(1))
    px = max(1, round(mm * 96 / 25.4))
    style = {"DASH": "dashed", "DOT": "dotted", "DOUBLE_SLIM": "double",
             "SLIM_THICK": "double", "THICK_SLIM": "double"}.get(kind, "solid")
    return f"{px}px {style} {color}"


# -------------------------------------------------------------- 리치 텍스트 --

def _runs_to_html(p_el, theme: Theme) -> tuple[str, str, float]:
    """문단 → (본문 HTML, 정렬 css, 지배 글자 pt)."""
    parts: list[str] = []
    max_pt = 0.0
    mark_open = False
    for run in p_el.findall(f"{_HP}run"):
        st = theme.char.get(run.get("charPrIDRef", ""), CharStyle())
        max_pt = max(max_pt, st.pt)
        css = [f"font-size:{st.pt}pt"]
        if st.bold:
            css.append("font-weight:bold")
        if st.italic:
            css.append("font-style:italic")
        if st.underline:
            css.append("text-decoration:underline")
        if st.color != "#000000":
            css.append(f"color:{st.color}")
        span_open = f'<span style="{";".join(css)}">'
        for t in run.findall(f"{_HP}t"):
            buf: list[str] = [span_open]
            if mark_open:
                buf.append('<mark>')
            if t.text:
                buf.append(html.escape(t.text))
            for child in t:
                tag = child.tag.split("}")[1]
                if tag == "markpenBegin":
                    color = child.get("color", "#FFFF00")
                    buf.append(f'<mark style="background:{color}">')
                    mark_open = True
                elif tag == "markpenEnd":
                    if mark_open:
                        buf.append("</mark>")
                        mark_open = False
                elif tag == "lineBreak":
                    buf.append("<br>")
                elif tag == "tab":
                    buf.append('<span style="display:inline-block;width:2em"></span>')
                if child.tail:
                    buf.append(html.escape(child.tail))
            if mark_open:
                buf.append("</mark>")   # span 경계에서 닫고 다음 t 에서 다시 연다
            buf.append("</span>")
            parts.append("".join(buf))
    align = theme.align.get(p_el.get("paraPrIDRef", ""), "left")
    return "".join(parts), align, (max_pt or 10.0)


def _para_plain(p_el) -> str:
    out = []
    for t in p_el.iter(f"{_HP}t"):
        if t.text:
            out.append(t.text)
        for c in t:
            if c.tail:
                out.append(c.tail)
    return "".join(out)


# ----------------------------------------------------------------- 이미지 --

def _bin_data(z: zipfile.ZipFile) -> dict[str, str]:
    """manifest id·파일명 → data URI."""
    out: dict[str, str] = {}
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "gif": "image/gif", "bmp": "image/bmp"}
    try:
        hpf = z.read("Contents/content.hpf").decode("utf-8")
        items = re.findall(r'<opf:item id="([^"]+)" href="([^"]+)"', hpf)
    except KeyError:
        items = []
    hrefs = dict(items)
    for name in z.namelist():
        if "/BinData/" not in name and not name.startswith("BinData/"):
            continue
        ext = name.rsplit(".", 1)[-1].lower()
        if ext not in mime:
            continue
        uri = f"data:{mime[ext]};base64,{base64.b64encode(z.read(name)).decode()}"
        stem = name.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        out[stem] = uri
        for iid, href in hrefs.items():
            if href.endswith(name.rsplit("/", 1)[-1]):
                out[iid] = uri
    return out


# ------------------------------------------------------------------- 블록 --

@dataclass
class Block:
    kind: str                    # text | table | picture
    height: int
    el: object = None
    #: 같은 문단에 나란히 놓인 그림들 (glyph 처럼 이어 붙는다). el 이 그 첫 장.
    siblings: list = None


def _page_body(sec_root) -> tuple[int, int, dict[str, int]]:
    page = next(sec_root.iter(f"{_HP}pagePr"))
    m = page.find(f"{_HP}margin")
    mg = {k: int(m.get(k)) for k in ("left", "right", "top", "bottom", "header", "footer")}
    w = int(page.get("width")) - mg["left"] - mg["right"]
    h = int(page.get("height")) - mg["top"] - mg["bottom"] - mg["header"] - mg["footer"]
    return w, h, mg


def _blocks(sec_root, theme: Theme, body_w: int, imgs: dict[str, str]):
    from hwpx.form_fit.measure import estimate_lines

    for p in sec_root.findall(f"{_HP}p"):
        tbl = p.find(f"./{_HP}run/{_HP}tbl")
        pic = p.find(f"./{_HP}run/{_HP}pic")
        if tbl is not None:
            sz = tbl.find(f"{_HP}sz")
            yield Block("table", sum(_row_heights(tbl, theme, imgs)), tbl)
        elif pic is not None:
            pics = list(p.iter(f"{_HP}pic"))
            height = max(int(x.find(f"{_HP}sz").get("height")) for x in pics)
            yield Block("picture", height, pic, pics)
        else:
            text = _para_plain(p)
            _, _, pt = _runs_to_html(p, theme)
            pitch = int(pt * 100 * _ratio(p, theme))
            n = estimate_lines(text, body_w, pt) if text.strip() else 1
            yield Block("text", n * pitch, p)


# -------------------------------------------------------------- 표 렌더링 --

def _cell_html(tc, theme: Theme, imgs: dict[str, str]) -> str:
    parts = []
    sub = tc.find(f"{_HP}subList")
    if sub is None:
        return ""
    for p in sub.findall(f"{_HP}p"):
        inner_tbl = p.find(f"./{_HP}run/{_HP}tbl")
        inner_pic = p.find(f"./{_HP}run/{_HP}pic")
        if inner_tbl is not None:
            parts.append(_table_html(inner_tbl, theme, imgs, rows_slice=None))
        elif inner_pic is not None:
            # 한 문단에 여러 장이면 글자처럼 나란히 놓인 것이다. 예전에는
            # 첫 장만 그려서, 나란히 배치가 미리보기로 검증되지 않았다.
            parts.append("".join(_pic_html(x, imgs) for x in p.iter(f"{_HP}pic")))
        else:
            body, align, _ = _runs_to_html(p, theme)
            parts.append(f'<div style="text-align:{align}">{body or "&nbsp;"}</div>')
    return "".join(parts)


def _table_html(tbl, theme: Theme, imgs: dict[str, str],
                rows_slice: tuple[int, int] | None,
                repeat_header_rows: list | None = None) -> str:
    trs = tbl.findall(f"{_HP}tr")
    lo, hi = rows_slice if rows_slice else (0, len(trs))
    render_rows = ([r for r in repeat_header_rows] if repeat_header_rows else []) \
        + trs[lo:hi]

    # 이 조각에 걸치는 rowSpan 병합은 조각 안으로 잘라 그린다 (근사)
    sz = tbl.find(f"{_HP}sz")
    width = int(sz.get("width"))
    out = [f'<table style="border-collapse:collapse;width:{_px(width)};'
           f'table-layout:fixed" border="0">']
    for tr in render_rows:
        out.append("<tr>")
        for tc in tr.findall(f"{_HP}tc"):
            span = tc.find(f"{_HP}cellSpan")
            cs = int(span.get("colSpan", "1")) if span is not None else 1
            rs = int(span.get("rowSpan", "1")) if span is not None else 1
            csz = tc.find(f"{_HP}cellSz")
            w = int(csz.get("width", "7200")) if csz is not None else 7200
            h = int(csz.get("height", "2166")) if csz is not None else 2166
            bfid = tc.get("borderFillIDRef", "")
            fill = theme.fill.get(bfid, "")
            sides = theme.border.get(bfid)
            if sides:
                border_css = [f"{k}:{v}" for k, v in sides.items()]
            else:
                border_css = ["border:1px solid #666"]
            style = border_css + [f"width:{_px(w)}",
                     f"min-height:{_px(h)}", "padding:2px 4px",
                     "box-sizing:border-box",
                     "vertical-align:middle", "overflow:hidden"]
            if fill:
                style.append(f"background:{fill}")
            attrs = ""
            if cs > 1:
                attrs += f' colspan="{cs}"'
            if rs > 1:
                attrs += f' rowspan="{rs}"'
            out.append(f'<td{attrs} style="{";".join(style)}">'
                       f'{_cell_html(tc, theme, imgs)}</td>')
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _ratio(p_el, theme: Theme) -> float:
    """이 문단의 줄간격 배수. 선언이 없으면 한/글 기본값."""
    return theme.spacing.get(p_el.get("paraPrIDRef", ""), LINE_RATIO)


def _is_cached(p_el) -> bool:
    """한/글이 이 문단을 실제로 조판한 적이 있는가.

    ``<hp:linesegarray>`` 는 한/글이 배치하면서 남기는 줄 캐시다. 있으면 그
    문단이 속한 행의 **선언 높이는 한/글이 계산한 값**이라 믿을 수 있고,
    없으면 우리가 써 넣은 추정치라 믿으면 안 된다. 배포 양식을 채운 문서는
    이 둘이 한 표 안에 섞여 있으므로 문서 단위가 아니라 문단 단위로 본다.
    """
    return p_el.find(f"{_HP}linesegarray") is not None


def _row_heights(tbl, theme: Theme, imgs: dict[str, str]) -> list[int]:
    """행 높이 = max(선언 높이, 셀 내용 추정 높이).

    실측 근거: 병합·사진이 많은 실문서는 선언 셀 높이가 내용과 무관하다 —
    [2차] U300 문서는 그림 13장(두 쪽 분량)이 전부 셀 안에 있는데 선언
    높이엔 반영돼 있지 않아, 선언값만 믿으면 6쪽짜리가 3쪽으로 나온다.
    rowSpan 셀의 내용은 걸친 행들에 균등 분배한다 (근사).
    """
    from hwpx.form_fit.measure import estimate_lines

    trs = tbl.findall(f"{_HP}tr")
    n = len(trs)
    heights = [2166] * n
    need = [0.0] * n
    for i, tr in enumerate(trs):
        for tc in tr.findall(f"{_HP}tc"):
            csz = tc.find(f"{_HP}cellSz")
            span = tc.find(f"{_HP}cellSpan")
            rs = int(span.get("rowSpan", "1")) if span is not None else 1
            if csz is not None and rs == 1:
                heights[i] = max(heights[i], int(csz.get("height", "2166")))
            inner_w = max(int(csz.get("width", "7200")) - 566, 1000) if csz is not None else 7200
            # 한/글이 조판한 텍스트 행의 선언 높이는 그대로 믿는다 — 텍스트까지
            # 다시 재면 실문서가 크게 부푼다(온리브 6쪽이 8쪽, U300 이 10쪽).
            # 선언에 반영되지 않는 것은 (a) 셀 안의 이미지·중첩표, 그리고
            # (b) **우리가 방금 써 넣어 아직 조판된 적 없는 문단**이다.
            # (b) 를 빼먹으면 양식을 채운 문서의 쪽 수가 통째로 거짓이 된다.
            sub = tc.find(f"{_HP}subList")
            content = 0
            if sub is not None:
                for p_ in sub.findall(f"{_HP}p"):
                    itbl = p_.find(f"./{_HP}run/{_HP}tbl")
                    ipic = p_.find(f"./{_HP}run/{_HP}pic")
                    if itbl is not None:
                        content += int(itbl.find(f"{_HP}sz").get("height"))
                    elif ipic is not None:
                        # 한 문단의 그림들은 글자처럼 나란히 놓이므로 높이는 최댓값.
                        content += max(int(x.find(f"{_HP}sz").get("height"))
                                       for x in p_.iter(f"{_HP}pic"))
                    elif not _is_cached(p_):
                        text = _para_plain(p_)
                        pt = max((theme.char.get(r.get("charPrIDRef", ""),
                                                 CharStyle()).pt)
                                 for r in p_.findall(f"{_HP}run")) \
                            if p_.findall(f"{_HP}run") else 10.0
                        lines = estimate_lines(text, inner_w, pt) if text.strip() else 1
                        content += int(lines * pt * 100 * _ratio(p_, theme))
            if content:
                per = (content + 566) / rs
                for k in range(i, min(i + rs, n)):
                    need[k] = max(need[k], per)
    return [max(h, int(nd)) for h, nd in zip(heights, need)]


def _header_rows(tbl) -> list:
    """repeatHeader=1 이면 header="1" 셀을 가진 선두 행들."""
    if tbl.get("repeatHeader") != "1":
        return []
    out = []
    for tr in tbl.findall(f"{_HP}tr"):
        if any(tc.get("header") == "1" for tc in tr.findall(f"{_HP}tc")):
            out.append(tr)
        else:
            break
    return out


def _pic_html(pic, imgs: dict[str, str]) -> str:
    sz = pic.find(f"{_HP}sz")
    w, h = int(sz.get("width")), int(sz.get("height"))
    img = pic.find(f"{_HC}img")
    if img is None:
        img = pic.find(f"{_HP}img")
    ref = img.get("binaryItemIDRef", "") if img is not None else ""
    uri = imgs.get(ref) or imgs.get(ref.replace("BIN", "BIN"))
    if uri is None:
        for k, v in imgs.items():
            if k in ref or ref in k:
                uri = v
                break
    if uri is None:
        return (f'<div style="width:{_px(w)};height:{_px(h)};border:1px dashed #999;'
                f'display:flex;align-items:center;justify-content:center;color:#999">'
                f'이미지 {html.escape(ref)}</div>')
    return (f'<img src="{uri}" style="width:{_px(w)};height:{_px(h)};display:block"'
            f' alt="{html.escape(ref)}">')


def _cell_blocks(tc, theme: Theme, imgs: dict[str, str], inner_w: int):
    """셀 내용을 (높이, html) 블록 목록으로 — 초대형 행의 쪽 나눔용."""
    from hwpx.form_fit.measure import estimate_lines

    out: list[tuple[int, str]] = []
    sub = tc.find(f"{_HP}subList")
    if sub is None:
        return out
    for p in sub.findall(f"{_HP}p"):
        inner_tbl = p.find(f"./{_HP}run/{_HP}tbl")
        inner_pic = p.find(f"./{_HP}run/{_HP}pic")
        if inner_tbl is not None:
            sz = inner_tbl.find(f"{_HP}sz")
            out.append((int(sz.get("height")),
                        _table_html(inner_tbl, theme, imgs, rows_slice=None)))
        elif inner_pic is not None:
            pics = list(p.iter(f"{_HP}pic"))
            h = max(int(x.find(f"{_HP}sz").get("height")) for x in pics)
            out.append((h, "".join(_pic_html(x, imgs) for x in pics)))
        else:
            body, align, pt = _runs_to_html(p, theme)
            pitch = int(pt * 100 * _ratio(p, theme))
            text = _para_plain(p)
            n = estimate_lines(text, inner_w, pt) if text.strip() else 1
            out.append((n * pitch,
                        f'<div style="text-align:{align}">{body or "&nbsp;"}</div>'))
    return out


def _row_fragment_html(width: int, fill: str, inner: str, pos: str) -> str:
    """초대형 행의 한 조각을 셀 하나짜리 표로 그린다.

    한글은 셀 단위 나눔에서 셀 *내용*도 쪽 경계에서 이어 나눈다. 나뉜 자리는
    테두리를 열어 두어(위/아래 선 없음) 이어짐이 보이게 한다.
    """
    border = {
        "first": "border-bottom:none",
        "mid": "border-top:none;border-bottom:none",
        "last": "border-top:none",
        "only": "",
    }[pos]
    style = [f"border:1px solid #666", border, "padding:2px 4px",
             "box-sizing:border-box", "vertical-align:top", "overflow:hidden"]
    if fill:
        style.append(f"background:{fill}")
    return (f'<table style="border-collapse:collapse;width:{_px(width)};'
            f'table-layout:fixed" border="0"><tr>'
            f'<td style="{";".join(style)}">{inner}</td></tr></table>')


# ------------------------------------------------------------------ 조판 --

def _korean_word_break(header_root) -> str:
    """문서의 한글 줄 나눔 기준을 CSS ``word-break`` 값으로.

    ``<hh:breakSetting breakNonLatinWord="...">`` 가 한글의 "줄 나눔 기준"이다.
    ``BREAK_WORD`` (한글 기본값)는 글자 단위로 끊고, ``KEEP_WORD`` 는 어절을
    통째로 넘긴다. 브라우저의 CJK 기본 동작은 전자라, 이걸 읽지 않으면
    어절 단위로 설정한 문서도 미리보기에서는 "실 / 험"처럼 갈라져 보인다 —
    파일은 멀쩡한데 미리보기만 틀리는, 가장 헷갈리는 종류의 불일치다.

    문단마다 다를 수 있지만 CSS 한 줄로 처리하므로 **다수결**을 쓴다. 실제
    문서에서 이 값이 문단별로 갈리는 경우는 보지 못했다.
    """
    counts: dict[str, int] = {}
    for node in header_root.iter(f"{_HH}breakSetting"):
        counts[node.get("breakNonLatinWord", "BREAK_WORD")] = (
            counts.get(node.get("breakNonLatinWord", "BREAK_WORD"), 0) + 1)
    if not counts:
        return "normal"
    dominant = max(counts, key=lambda k: counts[k])
    return "keep-all" if dominant == "KEEP_WORD" else "normal"


def render_html(src: str | Path, out: str | Path | None = None) -> dict:
    """조판해서 자립 HTML 로. *out* 이 None 이면 결과 dict 의 "html" 로 반환.

    반환 dict: pages, warnings, body_width, body_height,
    pictures(사진별 배치: page/gap_before/height/el — gapfit 이 소비),
    out 또는 html.
    """
    src = Path(src)
    with zipfile.ZipFile(src) as z:
        sec_root = ET.fromstring(z.read("Contents/section0.xml"))
        header_root = ET.fromstring(z.read("Contents/header.xml"))
        imgs = _bin_data(z)
    theme = _parse_theme(header_root)
    body_w, body_h, mg = _page_body(sec_root)
    word_break = _korean_word_break(header_root)
    warnings: list[str] = []
    over = sorted({int(t.find(f"{_HP}sz").get("width"))
                   for t in sec_root.iter(f"{_HP}tbl")
                   if int(t.find(f"{_HP}sz").get("width")) > body_w * 1.01})
    if over:
        warnings.append(
            f"표 폭 {', '.join(map(str, over))} 이 본문 폭 {body_w} 을 초과 — "
            f"한글에서도 오른쪽 여백을 침범한다 (문서 결함)")
    page = next(sec_root.iter(f"{_HP}pagePr"))
    page_w, page_h = int(page.get("width")), int(page.get("height"))

    pages: list[list[str]] = [[]]
    y = 0
    pics_info: list[dict] = []

    def new_page():
        nonlocal y
        pages.append([])
        y = 0

    for b in _blocks(sec_root, theme, body_w, imgs):
        if b.kind == "text":
            body, align, pt = _runs_to_html(b.el, theme)
            frag = (f'<div style="text-align:{align};line-height:{LINE_RATIO}">'
                    f'{body or "&nbsp;"}</div>')
            if y + b.height + SAFETY > body_h and b.height <= body_h and pages[-1]:
                new_page()
            pages[-1].append(frag)
            y += b.height

        elif b.kind == "picture":
            gap = 0
            if y + b.height + SAFETY > body_h and b.height <= body_h and pages[-1]:
                gap = body_h - y
                new_page()
            pics_info.append({"page": len(pages), "gap_before": int(gap),
                              "height": b.height, "el": b.el})
            drawn = "".join(_pic_html(x, imgs) for x in (b.siblings or [b.el]))
            pages[-1].append(f'<div style="text-align:center">{drawn}</div>')
            y += b.height

        elif b.kind == "table":
            trs = b.el.findall(f"{_HP}tr")
            heights = _row_heights(b.el, theme, imgs)
            head_rows = _header_rows(b.el)
            head_h = sum(heights[:len(head_rows)]) if head_rows else 0
            split = b.el.get("pageBreak", "CELL")
            i = 0
            first = True
            while i < len(trs):
                remain = body_h - y - (SAFETY if first else 0)
                if split == "TABLE" and first and sum(heights) > remain \
                        and sum(heights) <= body_h and pages[-1]:
                    new_page()
                    remain = body_h - SAFETY
                take, used = 0, (0 if first else head_h)
                while i + take < len(trs) and used + heights[i + take] <= remain:
                    used += heights[i + take]
                    take += 1
                # 고아 라벨 방지: 조각이 중간에서 끊길 때 마지막 행이 음영
                # 라벨 행(전 셀에 채움)이면 다음 내용 행과 함께 다음 쪽으로
                # 넘긴다 — 회색 라벨만 페이지 끝에 남는 모양은 어색하다.
                while take > 1 and i + take < len(trs):
                    last_tr = trs[i + take - 1]
                    cells = last_tr.findall(f"{_HP}tc")
                    if cells and all(
                            theme.fill.get(c.get("borderFillIDRef", ""), "")
                            for c in cells):
                        take -= 1
                        used -= heights[i + take]
                    else:
                        break
                if take == 0:
                    tr_cells = trs[i].findall(f"{_HP}tc")
                    if len(tr_cells) == 1:
                        # 행 하나가 남은 공간보다 큼 + 셀 하나(컨테이너 박스의
                        # 내용 행) — 셀 내용을 블록 단위로 이어 나눈다.
                        tc = tr_cells[0]
                        sz_ = b.el.find(f"{_HP}sz")
                        t_w = int(sz_.get("width"))
                        fill = theme.fill.get(tc.get("borderFillIDRef", ""), "")
                        blocks_ = _cell_blocks(tc, theme, imgs, t_w - 566)
                        j, frag_i = 0, 0
                        while j < len(blocks_):
                            remain2 = body_h - y
                            chunk, ch = [], 0
                            while j < len(blocks_) and                                     (ch + blocks_[j][0] <= remain2 or not chunk):
                                ch += blocks_[j][0]
                                chunk.append(blocks_[j][1])
                                j += 1
                            pos_ = ("only" if frag_i == 0 and j >= len(blocks_) else
                                    "first" if frag_i == 0 else
                                    "last" if j >= len(blocks_) else "mid")
                            pages[-1].append(_row_fragment_html(
                                t_w, fill, "".join(chunk), pos_))
                            y += min(ch, remain2)
                            frag_i += 1
                            if j < len(blocks_):
                                new_page()
                        i += 1
                        first = False
                        if i < len(trs) and body_h - y < heights[i]:
                            new_page()
                        continue
                    if pages[-1]:
                        new_page()
                        continue
                    take = 1                     # 다열 초대형 행 — 그대로 배치 (근사)
                    used = heights[i]
                frag = _table_html(b.el, theme, imgs, (i, i + take),
                                   repeat_header_rows=None if first else head_rows)
                pages[-1].append(frag)
                y += used
                i += take
                first = False
                if i < len(trs):
                    new_page()

    # ------------------------------------------------------------- HTML --
    doc_pages = []
    for n, frags in enumerate(pages, 1):
        doc_pages.append(
            f'<div class="page"><div class="body">{"".join(frags)}</div>'
            f'<div class="pageno">- {n} -</div></div>')

    warn_html = "".join(
        f'<div class="warnbar" style="max-width:840px;margin:0 auto 12px;padding:8px 14px;'
        f'background:#7a1f1f;color:#ffdddd;font-size:13px;border-radius:4px">'
        f'⚠ {html.escape(w)}</div>' for w in warnings)
    html_doc = f"""<!doctype html>
<meta charset="utf-8">
<title>{html.escape(src.stem)} — hwpx preview</title>
<style>
  body {{ background:#525659; margin:0; padding:24px 0;
         font-family:'함초롬바탕','Hancom Gothic','Malgun Gothic',Batang,serif;
         word-break:{word_break}; }}
  .page {{ position:relative; width:{_px(page_w)}; height:{_px(page_h)};
           background:#fff; margin:0 auto 16px; box-shadow:0 2px 8px rgba(0,0,0,.4);
           box-sizing:border-box;
           padding:{_px(mg["top"] + mg["header"])} {_px(mg["right"])}
                   {_px(mg["bottom"] + mg["footer"])} {_px(mg["left"])};
           overflow:hidden; }}
  .body {{ width:{_px(page_w - mg["left"] - mg["right"])}; height:100%; overflow:visible; }}
  .pageno {{ position:absolute; bottom:{_px(mg["footer"])}; left:0; right:0;
             text-align:center; font-size:9pt; color:#888; }}
  mark {{ padding:0; }}
  td > div {{ line-height:{LINE_RATIO}; }}
  table {{ margin:0 auto; }}
  @media print {{
    body {{ background:#fff; padding:0; }}
    .page {{ box-shadow:none; margin:0; page-break-after:always; }}
    .warnbar {{ display:none; }}
  }}
  @page {{ size:{_px(page_w)} {_px(page_h)}; margin:0; }}
</style>
{warn_html}{"".join(doc_pages)}
"""
    # 한/글이 아직 조판한 적 없는 문단 수. 0 이면 쪽 수는 한/글이 계산한
    # 선언 높이만 쓴 것이고, 0 보다 크면 그만큼은 우리가 직접 잰 값이다.
    measured = sum(1 for p_ in sec_root.iter(f"{_HP}p") if not _is_cached(p_))
    result = {"pages": len(pages), "warnings": warnings,
              "body_width": body_w, "body_height": body_h,
              "empty_pages": sum(1 for fr in pages if not fr),
              "measured": measured,
              "pictures": pics_info}
    if out is None:
        result["html"] = html_doc
    else:
        Path(out).write_text(html_doc, encoding="utf-8")
        result["out"] = str(out)
    return result


# ------------------------------------------------------------ PNG 내보내기 --

def render_png(src: str | Path, out_png: str | Path, *, scale: float = 1.0) -> dict:
    """HTML 미리보기를 headless Chrome 으로 찍어 PNG 한 장(세로 연속)으로.

    rhwp 기반 PNG 의 대체다. Chrome 이 없으면 명확히 실패한다.
    """
    import subprocess, tempfile, shutil

    chrome = None
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              shutil.which("chrome"), shutil.which("chromium")):
        if c and Path(c).exists():
            chrome = c
            break
    if chrome is None:
        raise RuntimeError("Chrome 을 찾지 못함 — PNG 내보내기는 Chrome headless 필요")

    tmp = Path(tempfile.mkdtemp(prefix="hwpxprev-"))
    try:
        html_path = tmp / "preview.html"
        info = render_html(src, html_path)
        # 페이지 수로 전체 높이 계산 (페이지 px + 아래 간격 16 + 상하 24)
        with zipfile.ZipFile(src) as z:
            sec_root = ET.fromstring(z.read("Contents/section0.xml"))
        page = next(sec_root.iter(f"{_HP}pagePr"))
        page_h_px = int(int(page.get("height")) * PX) + 16
        page_w_px = int(int(page.get("width")) * PX)
        total_h = 48 + info["pages"] * page_h_px + (60 if info["warnings"] else 0)
        width = max(page_w_px + 80, 900)
        out_png = Path(out_png).resolve()
        out_png.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
             f"--screenshot={out_png}",
             f"--window-size={int(width * scale)},{int(total_h * scale)}",
             f"--force-device-scale-factor={scale}",
             html_path.as_uri()],
            capture_output=True, timeout=120)
        if not out_png.exists():
            raise RuntimeError("Chrome 스크린샷 실패: "
                               + r.stderr.decode("utf-8", "replace")[:200])
        info["png"] = str(out_png)
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- 린트 --

def lint(src: str | Path, *, max_gap_ratio: float = 0.12) -> list[str]:
    """조판 결과에서 "보기 안 좋은 것"을 사람 문장으로 나열한다.

    검사 항목: 본문 폭 초과(여백 침범), 임계치를 넘는 사진 밀림 공백,
    내용 없는 빈 쪽. 렌더러가 보는 것과 같은 조판에서 재므로, 미리보기에
    보이는 문제와 린트가 잡는 문제가 항상 같다.
    """
    info = render_html(src, out=None)
    findings = list(info["warnings"])
    for pic in info["pictures"]:
        gap = pic["gap_before"]
        if gap > max_gap_ratio * info["body_height"]:
            findings.append(
                f"{pic['page']-1}쪽 하단에 공백 {gap} HWPUNIT "
                f"({gap/info['body_height']:.0%}) — 사진이 통째로 밀림. "
                f"fit_pictures() 로 조정 가능")
    if info["empty_pages"]:
        findings.append(f"내용 없는 쪽 {info['empty_pages']}개")
    return findings


def render_pdf(src: str | Path, out_pdf: str | Path) -> dict:
    """미리보기 조판을 headless Chrome 인쇄로 벡터 PDF 한 파일로.

    한글 없이 .hwpx → PDF. 페이지 크기는 문서의 실제 용지 크기를 따른다.
    """
    import subprocess, tempfile, shutil

    chrome = None
    for c in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
              shutil.which("chrome"), shutil.which("chromium"),
              shutil.which("google-chrome")):
        if c and Path(c).exists():
            chrome = c
            break
    if chrome is None:
        raise RuntimeError("Chrome 을 찾지 못함 — PDF 내보내기는 Chrome headless 필요")

    tmp = Path(tempfile.mkdtemp(prefix="hwpxpdf-"))
    try:
        html_path = tmp / "preview.html"
        info = render_html(src, html_path)
        out_pdf = Path(out_pdf).resolve()
        out_pdf.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            [chrome, "--headless=new", "--disable-gpu",
             f"--print-to-pdf={out_pdf}", "--no-pdf-header-footer",
             html_path.as_uri()],
            capture_output=True, timeout=120)
        if not out_pdf.exists():
            raise RuntimeError("Chrome PDF 인쇄 실패: "
                               + r.stderr.decode("utf-8", "replace")[:200])
        info["pdf"] = str(out_pdf)
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
