"""줄 나눔 기준을 아는 줄 수 추정.

``hwpx.form_fit.measure.estimate_lines`` 는 한글 글자 사이 어디서든 줄을
끊는다고 가정한다 — 한/글 기본값(``breakNonLatinWord="BREAK_WORD"``, 글자
단위)에는 맞지만, 한컴이 만든 배포 양식의 본문 문단과 이 도구가 새로 만드는
문서는 **어절 단위**(``KEEP_WORD``)다. 어절 단위 조판은 줄 끝에서 어절을
통째로 넘기므로 같은 글이 더 많은 줄을 차지한다. 글자 단위로 재서 행 높이를
쓰면 한/글은 열 때 행을 다시 키워 주지만, 선언된 높이를 그대로 믿는 뷰어
(폴라리스 오피스 등)에서는 마지막 줄이 잘려 보인다. 그래서 행 높이를 잴 때는
문서의 실제 줄 나눔 기준으로 재야 한다.

글자 폭은 python-hwpx 의 보정된 표(``char_advance``)를 그대로 쓴다. 이 모듈이
더하는 것은 **끊을 수 있는 자리**의 판단뿐이다.
"""
from __future__ import annotations

from hwpx.form_fit.measure import char_advance, classify_char

HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

#: 라틴 낱말 안에서 그 *뒤*에서 끊을 수 있는 문장부호 (한/글 · UAX #14).
_LATIN_BREAK_AFTER = frozenset("/\\-.@:_?=&,;")

#: 어절 단위에서도 그 *앞*에서는 끊지 않는 닫는 부호 (줄 첫머리 금칙).
_NO_BREAK_BEFORE = frozenset(").,;:!?%]}」』〉》”’·…")


def _break_opportunities(text: str, *, keep_words: bool) -> set[int]:
    """*text* 의 인덱스 중 그 **앞**에서 줄을 바꿔도 되는 자리."""
    out: set[int] = set()
    for i in range(1, len(text)):
        prev, cur = text[i - 1], text[i]
        if cur in _NO_BREAK_BEFORE:
            continue
        if prev in " \t　":
            out.add(i)
            continue
        wide_prev = classify_char(prev) in ("hangul", "wide")
        wide_cur = classify_char(cur) in ("hangul", "wide")
        if wide_prev or wide_cur:
            # 글자 단위면 한글/전각 글자 사이 어디서든 끊는다. 어절 단위면
            # 공백에서만 끊는다 — "약3억" 같은 붙여쓰기도 한 어절로 본다.
            # 어절 단위에서 자리를 덜 잡으면 줄 수가 **늘어나는** 쪽으로
            # 틀리므로 행 높이는 안전하다.
            if not keep_words:
                out.add(i)
            continue
        if prev in _LATIN_BREAK_AFTER and cur not in " \t":
            out.add(i)
    return out


def _wrap_line(line: str, width: float, pt: float, *, keep_words: bool) -> int:
    if not line:
        return 1
    breaks = _break_opportunities(line, keep_words=keep_words)
    used = 0.0
    count = 1
    last_break: int | None = None
    used_at_break = 0.0
    for i, ch in enumerate(line):
        adv = char_advance(ch, pt)
        if i in breaks:
            last_break = i
            used_at_break = used
        if used + adv > width and used > 0:
            count += 1
            if last_break is not None and last_break > 0:
                # 마지막 끊을 자리 뒤의 글자들이 다음 줄로 내려간다.
                used = (used - used_at_break) + adv
                last_break = None
            else:
                # 끊을 자리가 없는 긴 어절은 한/글도 글자에서 강제로 끊는다.
                used = adv
        else:
            used += adv
    return count


def estimate_lines(text: str, width: float, pt: float, *,
                   keep_words: bool = False) -> int:
    """*text* 가 폭 *width* (HWPUNIT) 안에서 차지하는 줄 수 (탐욕 조판).

    *keep_words* 가 참이면 어절 단위(``KEEP_WORD``)로, 거짓이면 글자 단위
    (``BREAK_WORD``)로 끊는다. 어절 단위 결과는 글자 단위보다 작아지지 않는다.
    """
    if width <= 0:
        return 1_000_000
    total = 0
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        total += _wrap_line(line, width, pt, keep_words=keep_words)
    return max(total, 1)


def keeps_words(header_root) -> bool:
    """헤더의 ``breakSetting`` 다수결이 어절 단위인가.

    :func:`hwpxkit.preview._korean_word_break` 와 같은 규칙이다 — 문단별로
    다를 수 있지만 실문서에서 갈리는 경우는 보지 못했고, 갈리면 한 표 안에서
    칸마다 규칙이 달라지므로 어차피 고쳐야 한다(:func:`hwpxkit.edit.keep_korean_words`).
    """
    counts: dict[str, int] = {}
    for node in header_root.iter(f"{HH}breakSetting"):
        v = node.get("breakNonLatinWord", "BREAK_WORD")
        counts[v] = counts.get(v, 0) + 1
    if not counts:
        return False
    return max(counts, key=lambda k: counts[k]) == "KEEP_WORD"


def doc_keeps_words(doc) -> bool:
    """python-hwpx 문서 객체판 :func:`keeps_words`."""
    headers = getattr(doc, "headers", None) or []
    return bool(headers) and keeps_words(headers[0].element)
