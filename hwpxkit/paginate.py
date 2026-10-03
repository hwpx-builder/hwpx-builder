# -*- coding: utf-8 -*-
"""브라우저 실측 쪽 나눔 — 미리보기·PDF 가 **그려진 높이**로 쪽을 나눈다.

왜 따로 있나
------------
:mod:`hwpxkit.preview` 의 쪽 나눔은 파이썬에서 한/글 글자 폭으로 높이를 *추정*
하고, 그 결과를 Chrome 이 *다른* 글꼴 폭·줄 높이로 그린다. 둘이 어긋나는
만큼 PDF 가 깨졌다 — 실측한 증상:

- 본문이 쪽 아래 여백으로 흘러내림 (추정보다 한 줄 더 감긴 칸 하나로 44px)
- 컨테이너 박스를 쪽 경계에서 나눈 조각의 테두리가 추정 높이에서 끊겨,
  표와 그림이 박스 밖으로 삐져나옴
- 박스 안의 표는 통째로만 넘어가서 쪽의 40% 가 비고, 박스가 열린 채 끝남

추정을 아무리 다듬어도 두 조판기의 차이는 남는다. 그래서 **그리는 쪽이
직접 잰다**: 파이썬은 문서를 블록의 흐름으로 내보내고, 페이지 안의 스크립트가
블록을 하나씩 쪽에 넣어 보며 넘치면 나눈다.

흐름의 블록 (``#flow > .it``)
----------------------------
- ``data-kind="p"``    본문 문단 (원자)
- ``data-kind="pic"``  그림 (원자, 쪽보다 크면 줄여 넣음)
- ``data-kind="tbl"``  표. ``<tr data-u>`` 단위로 나뉘고 ``data-h`` 행(제목 줄)은
  나뉜 조각마다 다시 그린다. rowSpan 으로 묶인 행은 같은 단위라 함께 움직인다.
- ``.pc`` (piece)      **큰 셀 하나짜리 행**(컨테이너 박스의 내용 행)은 셀 내용을
  문단·표·그림마다 조각으로 편다. 조각은 좌우 테두리만 그리고, 쪽을 닫을 때
  그 쪽의 첫/끝 조각에 위/아래 테두리를 붙여 **쪽마다 닫힌 박스**가 된다(한/글과
  같은 모양). 조각 안의 표도 행 단위로 나뉜다.

제목 붙들기: 한 줄짜리 글(``가. 개발환경``, 박스 사이 절 제목, 회색 라벨 행)이
표·그림·박스 바로 앞이면 ``data-keep`` — 뒤 블록과 같은 쪽에 놓는다.

쪽 수
-----
:func:`hwpxkit.preview.render_html` 이 돌려주는 ``pages`` 는 여전히 파이썬
추정(한/글 쪽 수 흉내 — verify·lint·gapfit 이 쓴다)이다. 실제로 그려진 쪽 수는
PDF 에서 센다(:func:`hwpxkit.preview.render_pdf` 의 ``pdf_pages``).
"""
from __future__ import annotations

import html

#: 이 비율보다 큰 "셀 하나짜리 행"만 조각으로 편다. 작은 박스(제목 띠, 한 줄
#: 라벨)는 선언 높이·세로 가운데 정렬을 그대로 살려 원자 행으로 둔다.
BIG_ROW = 0.3


def _tr_units(tbl, _HP) -> list[int]:
    """행마다 단위 번호. rowSpan 이 걸친 행들은 같은 단위(함께 움직임)."""
    trs = tbl.findall(f"{_HP}tr")
    unit = list(range(len(trs)))
    for i, tr in enumerate(trs):
        for tc in tr.findall(f"{_HP}tc"):
            span = tc.find(f"{_HP}cellSpan")
            rs = int(span.get("rowSpan", "1")) if span is not None else 1
            for k in range(i + 1, min(i + rs, len(trs))):
                unit[k] = unit[i]
    # 앞 단위로 전파 (A-B, B-C 가 겹치면 A-B-C 한 단위)
    for k in range(1, len(unit)):
        if unit[k] != k:
            unit[k] = unit[unit[k]]
    return unit


def table_html(tbl, rows, theme, imgs, *, header_ids=frozenset(), unit=None,
               max_w: int | None = None) -> str:
    """*rows* (tr 요소 목록)를 나눌 수 있는 표로. 행에 ``data-u``/``data-h`` 를 단다.

    칸 폭은 % 로 쓴다 — *max_w* 로 표를 줄여도 열 비율이 유지되고, 박스 조각
    안에서 테두리 밖으로 삐져나오지 않는다."""
    from .preview import _HP, _cell_html, _px

    sz = tbl.find(f"{_HP}sz")
    width = int(sz.get("width"))
    drawn = min(width, max_w) if max_w else width
    all_trs = tbl.findall(f"{_HP}tr")
    unit = unit or _tr_units(tbl, _HP)
    out = [f'<table class="st" style="border-collapse:collapse;width:{_px(drawn)};'
           f'table-layout:fixed;margin:0 auto" border="0">']
    for tr in rows:
        i = all_trs.index(tr)
        h = ' data-h="1"' if id(tr) in header_ids else ""
        # 음영 한 칸 행 = container_box 의 회색 라벨. 조각 끝에 홀로 두지 않는다.
        cells = tr.findall(f"{_HP}tc")
        if len(cells) == 1 and theme.fill.get(cells[0].get("borderFillIDRef", ""), ""):
            h += ' data-lab="1"'
        out.append(f'<tr data-u="{unit[i]}"{h}>')
        for tc in tr.findall(f"{_HP}tc"):
            out.append(_td_html(tc, theme, imgs, _cell_html, _px, _HP, width))
        out.append("</tr>")
    out.append("</table>")
    return "".join(out)


def _td_html(tc, theme, imgs, _cell_html, _px, _HP, table_w) -> str:
    span = tc.find(f"{_HP}cellSpan")
    cs = int(span.get("colSpan", "1")) if span is not None else 1
    rs = int(span.get("rowSpan", "1")) if span is not None else 1
    csz = tc.find(f"{_HP}cellSz")
    w = int(csz.get("width", "7200")) if csz is not None else 7200
    h = int(csz.get("height", "2166")) if csz is not None else 2166
    bfid = tc.get("borderFillIDRef", "")
    sides = theme.border.get(bfid)
    style = ([f"{k}:{v}" for k, v in sides.items()] if sides
             else ["border:1px solid #666"])
    sub = tc.find(f"{_HP}subList")
    valign = {"TOP": "top", "BOTTOM": "bottom"}.get(
        sub.get("vertAlign", "CENTER") if sub is not None else "CENTER", "middle")
    style += [f"width:{w / table_w * 100:.3f}%", f"height:{_px(h)}", "padding:2px 4px",
              "box-sizing:border-box", f"vertical-align:{valign}"]
    fill = theme.fill.get(bfid, "")
    if fill:
        style.append(f"background:{fill}")
    attrs = (f' colspan="{cs}"' if cs > 1 else "") + (f' rowspan="{rs}"' if rs > 1 else "")
    return f'<td{attrs} style="{";".join(style)}">{_cell_html(tc, theme, imgs)}</td>'


def _header_ids(tbl, _HP, theme=None) -> frozenset:
    """나뉜 조각마다 다시 그릴 제목 줄.

    한/글의 ``repeatHeader`` + 셀 ``header="1"`` 이 우선이다. 그게 없으면 **첫 행만
    음영이고 둘째 행은 아닌** 3행 이상 표의 첫 행을 제목 줄로 본다 — ``Grid`` 가
    만든 표(회색 머리행)가 이 모양이고, 머리행 없이 이어진 조각은 열 뜻을 잃는다.
    """
    trs = tbl.findall(f"{_HP}tr")
    heads = []
    if tbl.get("repeatHeader") == "1":
        for tr in trs:
            if any(tc.get("header") == "1" for tc in tr.findall(f"{_HP}tc")):
                heads.append(tr)
            else:
                break
    if not heads and theme is not None and len(trs) >= 3:
        def shaded(tr):
            cells = tr.findall(f"{_HP}tc")
            return bool(cells) and all(
                theme.fill.get(tc.get("borderFillIDRef", ""), "") for tc in cells)
        if shaded(trs[0]) and not shaded(trs[1]) and len(trs[0].findall(f"{_HP}tc")) > 1:
            heads.append(trs[0])
    return frozenset(id(t) for t in heads)


def _para_item(p, theme) -> tuple[str, bool, bool, bool]:
    """문단 → (html, 한 줄짜리 글인가, 빈 문단인가, 제목인가).

    제목 = 한 줄짜리이고 글자가 **전부 굵은** 문단 ("가. 개발환경", 절 제목).
    뒤에 무엇이 오든 그것과 같은 쪽에 둔다.
    """
    from .preview import _HP, CharStyle, _para_plain, _ratio, _runs_to_html

    body, align, pt = _runs_to_html(p, theme)
    text = _para_plain(p).strip()
    div = (f'<div style="text-align:{align};font-size:{pt}pt;'
           f'line-height:{_ratio(p, theme)}">{body or "&nbsp;"}</div>')
    short = bool(text) and len(text) <= 60 and "\n" not in text
    texted = [r for r in p.findall(f"{_HP}run")
              if "".join(t.text or "" for t in r.iter(f"{_HP}t")).strip()]
    heading = short and bool(texted) and all(
        theme.char.get(r.get("charPrIDRef", ""), CharStyle()).bold for r in texted)
    return div, short, not text, heading


def flow_items(sec_root, theme, imgs, body_w: int, body_h: int) -> list[str]:
    """문서를 흐름 블록 HTML 목록으로."""
    from .preview import _HP, _pic_html, _px, _row_heights

    items: list[dict] = []          # {html, kind, short, blank, piece}

    def add(html_, kind, *, short=False, blank=False, piece=None, brk=False):
        it = dict(html=html_, kind=kind, short=short, blank=blank,
                  piece=piece, brk=brk)
        items.append(it)
        return it

    box_n = 0
    for p in sec_root.findall(f"{_HP}p"):
        brk = p.get("pageBreak") == "1"
        tbl = p.find(f"./{_HP}run/{_HP}tbl")
        pic = p.find(f"./{_HP}run/{_HP}pic")
        if tbl is not None:
            box_n += 1
            _table_items(tbl, theme, imgs, body_h, add, f"b{box_n}", brk)
        elif pic is not None:
            pics = list(p.iter(f"{_HP}pic"))
            add('<div style="text-align:center">'
                + "".join(_pic_html(x, imgs) for x in pics) + "</div>", "pic", brk=brk)
        else:
            div, short, blank, heading = _para_item(p, theme)
            add(div, "p", short=short, blank=blank, brk=brk)["heading"] = heading

    # 제목 붙들기: 한 줄짜리 글/라벨 행 + 바로 뒤가 표·그림·박스 조각
    out = []
    for i, it in enumerate(items):
        nxt = items[i + 1] if i + 1 < len(items) else None
        keep = False
        if nxt is not None and it["short"] and nxt["kind"] in ("tbl", "pic"):
            keep = True          # 한 줄 글 + 표, 캡션 없는 그림 제목
        if nxt is not None and it.get("heading"):
            keep = True          # "가. 개발환경" — 뒤가 문단이어도
        if nxt is not None and it["short"] and not it["piece"] and nxt["piece"]:
            keep = True          # 박스 사이 절 제목 + 박스 첫 조각
        if nxt is not None and it.get("label") and nxt["piece"]:
            keep = True          # 회색 라벨 행 + 내용 조각
        if (nxt is not None and it["kind"] == "pic" and nxt["kind"] == "p"
                and nxt["short"]):
            keep = True          # 그림 + 바로 아래 캡션 한 줄 — 캡션만 넘어가지 않게
        attrs = [f'data-kind="{it["kind"]}"']
        if it.get("nosplit"):
            attrs.append('data-nosplit="1"')
        if keep:
            attrs.append('data-keep="1"')
        if it["blank"]:
            attrs.append('data-blank="1"')
        if it["brk"]:
            attrs.append('data-break="1"')
        pc = it.get("piece")
        cls = "it"
        style = ""
        if pc:
            cls += " pc"
            attrs.append(f'data-box="{pc["box"]}"')
            attrs.append(f'data-bt="{html.escape(pc["bt"])}"')
            attrs.append(f'data-bb="{html.escape(pc["bb"])}"')
            if pc["first"]:
                attrs.append('data-rowfirst="1"')
            if pc["last"]:
                attrs.append('data-rowlast="1"')
            style = (f' style="width:{pc["w"]};{pc["sides"]};padding:1px 6px;'
                     f'box-sizing:border-box;margin:0 auto'
                     + (f';background:{pc["fill"]}' if pc["fill"] else "") + '"')
        out.append(f'<div class="{cls}" {" ".join(attrs)}{style}>{it["html"]}</div>')
    return out


def _table_items(tbl, theme, imgs, body_h, add, box_id, brk) -> None:
    """최상위 표 하나 → 표 블록(들) + 큰 셀 행의 조각들."""
    from .preview import _HP, _pic_html, _px, _row_heights

    trs = tbl.findall(f"{_HP}tr")
    heights = _row_heights(tbl, theme, imgs)
    unit = _tr_units(tbl, _HP)
    heads = _header_ids(tbl, _HP, theme)
    width = int(tbl.find(f"{_HP}sz").get("width"))
    nosplit = tbl.get("pageBreak") == "NONE" or tbl.get("pageBreak") == "TABLE"

    def is_big(i, tr):
        cells = tr.findall(f"{_HP}tc")
        return (len(cells) == 1 and unit[i] == i
                and (i + 1 >= len(unit) or unit[i + 1] != i)
                and heights[i] > body_h * BIG_ROW)

    seg: list = []
    first_item = True

    def flush() -> None:
        """모아 둔 보통 행들을 표 블록 하나로. 마지막 행이 회색 한 칸 라벨 행
        (container_box 의 머리)이면 뒤따르는 박스 조각과 같은 쪽에 붙든다."""
        nonlocal seg, first_item
        if not seg:
            return
        last_cells = seg[-1].findall(f"{_HP}tc")
        label = (len(last_cells) == 1 and all(
            theme.fill.get(tc.get("borderFillIDRef", ""), "") for tc in last_cells))
        it = add(table_html(tbl, seg, theme, imgs, header_ids=heads, unit=unit),
                 "tbl", brk=brk and first_item)
        it["label"] = label
        it["nosplit"] = nosplit
        seg = []
        first_item = False

    for i, tr in enumerate(trs):
        if nosplit or not is_big(i, tr):
            seg.append(tr)
            continue
        flush()
        tc = tr.find(f"{_HP}tc")
        _cell_pieces(tbl, tc, theme, imgs, add, f"{box_id}r{i}", width,
                     top_row=(i == 0), brk=brk and first_item)
        first_item = False
    flush()


def _cell_pieces(tbl, tc, theme, imgs, add, box, width, *, top_row, brk) -> None:
    """큰 셀의 내용을 문단·표·그림마다 박스 조각으로."""
    from .preview import _HP, _pic_html, _px

    bfid = tc.get("borderFillIDRef", "")
    sides = theme.border.get(bfid) or {
        "border-left": "1px solid #666", "border-right": "1px solid #666",
        "border-top": "1px solid #666", "border-bottom": "1px solid #666"}
    lr = ";".join(f"{k}:{v}" for k, v in sides.items()
                  if k in ("border-left", "border-right"))
    bt = sides.get("border-top", "none")
    bb = sides.get("border-bottom", "none")
    fill = theme.fill.get(bfid, "")
    sub = tc.find(f"{_HP}subList")
    paras = sub.findall(f"{_HP}p") if sub is not None else []
    n = len(paras)
    for j, p in enumerate(paras):
        itbl = p.find(f"./{_HP}run/{_HP}tbl")
        ipic = p.find(f"./{_HP}run/{_HP}pic")
        piece = dict(box=box, bt=bt, bb=bb, first=(j == 0), last=(j == n - 1),
                     w=_px(width), sides=lr, fill=fill)
        # 조각의 위 테두리: 표의 첫 행일 때만 정적으로 (행 사이 선은 앞 행의 아래 선)
        if j == 0 and top_row:
            piece["sides"] += f";border-top:{bt}"
        if j == n - 1:
            piece["sides"] += f";border-bottom:{bb}"
        if itbl is not None:
            heads = _header_ids(itbl, _HP, theme)
            # 조각 안쪽 폭 = 박스 폭 − 좌우 여백 6px×2 − 테두리
            add(table_html(itbl, itbl.findall(f"{_HP}tr"), theme, imgs,
                           header_ids=heads, max_w=width - 1050),
                "tbl", piece=piece, brk=brk and j == 0)
        elif ipic is not None:
            pics = list(p.iter(f"{_HP}pic"))
            add('<div style="text-align:center">'
                + "".join(_pic_html(x, imgs) for x in pics) + "</div>", "pic",
                piece=piece, brk=brk and j == 0)
        else:
            div, short, blank, heading = _para_item(p, theme)
            add(div, "p", short=short, blank=blank, piece=piece,
                brk=brk and j == 0)["heading"] = heading


#: 쪽 나누기. 동기 실행 — ``--print-to-pdf`` 는 load 뒤에 찍으므로 그 전에 끝난다.
PAGINATE_JS = r"""
(function () {
  const flow = document.getElementById('flow');
  if (!flow) return;
  const tpl = document.getElementById('page-tpl');
  const items = Array.from(flow.children);
  const pages = [];
  let body = null, H = 0;
  const SLACK = 3;   // 닫는 테두리(쪽 끝 조각의 아래 선)가 들어갈 자리

  function newPage() {
    const pg = tpl.content.firstElementChild.cloneNode(true);
    document.body.insertBefore(pg, flow);
    pages.push(pg);
    body = pg.querySelector('.body');
    H = body.getBoundingClientRect().height;   // 화면 px — 확대/축소와 무관한 기준
  }
  // scrollHeight 는 clientHeight 보다 작아지지 않는다 — 넘침 판정은 내용의 실제
  // 아래 끝으로 한다.
  const fits = () => contentBottom() <= H - SLACK + 0.5;
  function contentBottom() {
    const top = body.getBoundingClientRect().top;
    let m = 0;
    for (const c of body.children) m = Math.max(m, c.getBoundingClientRect().bottom - top);
    return m;
  }
  const isEmpty = () => body.children.length === 0;

  // 표 블록 나누기: 들어가는 단위까지 남기고 나머지를 새 블록으로 돌려준다.
  function split(it) {
    const tbl = it.querySelector(':scope > table.st');
    if (!tbl) return null;
    const rows = Array.from(tbl.rows);
    const heads = rows.filter(r => r.dataset.h);
    const bodyRows = rows.filter(r => !r.dataset.h);
    const units = [];
    for (const r of bodyRows) {
      const u = r.dataset.u;
      if (!units.length || units[units.length - 1].u !== u) units.push({u, rows: []});
      units[units.length - 1].rows.push(r);
    }
    if (units.length < 2) return null;
    const rest = it.cloneNode(false);
    const rtbl = tbl.cloneNode(false);
    rest.appendChild(rtbl);
    for (const h of heads) rtbl.appendChild(h.cloneNode(true));
    // 뒤에서부터 빼며 들어갈 때까지
    let keep = units.length;
    for (const u of units) for (const r of u.rows) r.remove();
    let k = 0;
    for (; k < units.length; k++) {
      for (const r of units[k].rows) tbl.appendChild(r);
      if (!fits()) { for (const r of units[k].rows) r.remove(); break; }
    }
    // 고아 라벨 방지: 앞 조각이 회색 라벨 행으로 끝나면 그 라벨도 다음 쪽으로.
    while (k > 0 && k < units.length
           && units[k - 1].rows[units[k - 1].rows.length - 1].dataset.lab) {
      k -= 1;
      for (const r of units[k].rows) r.remove();
    }
    // 외톨이 행 방지: 마지막 한 단위만 다음 쪽으로 넘어가게 되면 하나 더 데려간다.
    if (k === units.length - 1 && k >= 2) {
      k -= 1;
      for (const r of units[k].rows) r.remove();
    }
    if (k === 0) {                       // 한 단위도 안 들어감 — 원상 복구
      for (const u of units) for (const r of u.rows) tbl.appendChild(r);
      return null;
    }
    for (let j = k; j < units.length; j++)
      for (const r of units[j].rows) rtbl.appendChild(r);
    // 조각이면: 앞부분은 이 쪽의 끝, 뒷부분은 새 쪽의 시작
    if (it.classList.contains('pc')) { delete it.dataset.rowlast; delete rest.dataset.rowfirst; }
    delete rest.dataset.keep;
    delete rest.dataset.break;          // 쪽 나누기는 앞 조각에서 이미 했다
    return rest;
  }

  function closePage() {
    if (!body) return;
    // 쪽마다 박스를 닫는다: 박스별 첫 조각에 위 선, 끝 조각에 아래 선.
    const seen = {};
    const pcs = Array.from(body.querySelectorAll(':scope > .pc'));
    for (const pc of pcs) (seen[pc.dataset.box] = seen[pc.dataset.box] || []).push(pc);
    for (const box in seen) {
      const list = seen[box];
      const f = list[0], l = list[list.length - 1];
      if (f.dataset.bt) f.style.borderTop = f.dataset.bt;
      if (l.dataset.bb) l.style.borderBottom = l.dataset.bb;
    }
    // 그래도 넘치면(원자 블록이 한 쪽보다 큼) 그 쪽만 줄여 담는다.
    if (!fits()) {
      const h = body.clientHeight, w = body.clientWidth;
      let z = 1;
      for (let i = 0; i < 6 && !fits() && z > 0.6; i++) {
        z = Math.max(0.6, z * (H - SLACK) / contentBottom() - 0.003);
        body.style.zoom = z; body.style.width = (w / z) + 'px'; body.style.height = (h / z) + 'px';
      }
      body.dataset.fit = z.toFixed(3);
      console.warn('hwpx preview: 쪽 ' + pages.length + ' 넘침 → ' + z.toFixed(3) + ' 배');
    }
  }

  newPage();
  const queue = items.slice();
  // 안전장치: 어떤 문서에서도 무한 반복으로 PDF 내보내기가 멈추지 않게.
  let guard = items.length * 50 + 1000;
  while (queue.length) {
    if (--guard < 0) {
      console.error('hwpx preview: 쪽 나누기 반복 한도 초과 — 남은 블록 ' + queue.length
                    + '개를 이어 붙인다');
      for (const q of queue) body.appendChild(q);
      break;
    }
    let it = queue.shift();
    if (it.dataset.break && !isEmpty()) { closePage(); newPage(); }
    // 쪽 첫머리의 빈 문단은 버린다 (앞 쪽 끝의 여백이 새 쪽 위로 넘어온 것)
    if (isEmpty() && it.dataset.blank) { it.remove(); continue; }
    body.appendChild(it);
    if (fits()) continue;
    // "나누지 않음" 표는 빈 쪽에서도 안 들어갈 때만 나눈다 (한/글과 같은 양보).
    const splittable = it.dataset.kind === 'tbl'
                       && (!it.dataset.nosplit || body.children.length === 1);
    const rest = splittable ? split(it) : null;
    if (rest) { closePage(); newPage(); queue.unshift(rest); continue; }
    it.remove();
    if (isEmpty()) { body.appendChild(it); continue; }   // 한 쪽보다 큼 — closePage 가 줄인다
    // 붙들린 제목들을 데리고 다음 쪽으로
    // (떼어 내면서 세야 한다 — 안 떼면 같은 요소를 영원히 본다)
    const carry = [];
    while (body.lastElementChild && body.lastElementChild.dataset.keep
           && body.children.length > 1) {
      const c = body.lastElementChild;
      c.remove();
      carry.unshift(c);
    }
    closePage(); newPage();
    queue.unshift(...carry, it);
  }
  closePage();
  flow.remove();
  pages.forEach((pg, i) => { pg.querySelector('.pageno').textContent = '- ' + (i + 1) + ' -'; });
  document.body.dataset.pages = pages.length;
})();
"""
