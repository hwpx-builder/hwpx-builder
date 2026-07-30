"""검증. 구조 검사를 먼저 하고, 그 다음 렌더 검사를 한다.

일부러 싼 것부터 층을 쌓았다:

1. **패키지 + 기하** — 렌더러 불필요, 밀리초 단위. 깨진 ZIP, 끊어진
   ``binaryItemIDRef``, 표 너비와 안 맞는 열 너비 합계를 잡는다.
2. **rhwp 렌더** — 페이지당 약 0.1초. 무너진 표, 빈 페이지, 사라진 이미지를
   잡는다.
3. **한글 COM** — 픽셀 단위 결과에 대한 유일한 권위. 다만 한글 **2014 이상**이
   필요하다. 한글 2010 은 HWPX 를 아예 파싱하지 못하면서도 ``Open()`` 이
   ``True`` 를 돌려주므로 *가짜* 오라클이다. 쓰지 않는다.

정직성 규칙: 어떤 층이 실행되지 못했으면 결과는 ``checked=False`` —
"아무것도 검증하지 않았다" — 이지, 조용한 통과가 아니다.
"""
from __future__ import annotations

import zipfile
from dataclasses import dataclass, field
from pathlib import Path

#: 예전에 이 이름을 import 하던 코드를 위해 남겨 둔다. 실제 메시지는 이제
#: hwpxkit.render 에 있다.
RHWP_UNAVAILABLE = "rhwp renderer unavailable (pip install 'hwpxkit[preview]')"


@dataclass
class CheckResult:
    name: str
    ok: bool
    checked: bool = True
    detail: str = ""

    def __str__(self) -> str:
        if not self.checked:
            return f"  ~  {self.name}: NOT VERIFIED ({self.detail})"
        mark = "OK " if self.ok else "FAIL"
        return f"  {mark} {self.name}{': ' + self.detail if self.detail else ''}"


@dataclass
class Report:
    results: list[CheckResult] = field(default_factory=list)

    def add(self, *results: CheckResult) -> None:
        self.results.extend(results)

    @property
    def failed(self) -> list[CheckResult]:
        return [r for r in self.results if r.checked and not r.ok]

    @property
    def unverified(self) -> list[CheckResult]:
        return [r for r in self.results if not r.checked]

    @property
    def ok(self) -> bool:
        return not self.failed

    def render(self) -> str:
        lines = [str(r) for r in self.results]
        lines.append("")
        if self.failed:
            lines.append(f"RESULT: {len(self.failed)} check(s) FAILED")
        elif self.unverified:
            lines.append(
                f"RESULT: structural checks passed; "
                f"{len(self.unverified)} check(s) NOT VERIFIED"
            )
        else:
            lines.append("RESULT: all checks passed")
        return "\n".join(lines)


def check_package(path: str | Path) -> list[CheckResult]:
    """ZIP 무결성과 모든 HWPX 가 반드시 가져야 하는 파트."""
    path = Path(path)
    out: list[CheckResult] = []
    try:
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            bad = z.testzip()
            out.append(CheckResult("zip integrity", bad is None,
                                   detail="" if bad is None else f"corrupt: {bad}"))
            required = ["mimetype", "version.xml", "Contents/content.hpf",
                        "Contents/header.xml", "META-INF/manifest.xml"]
            missing = [n for n in required if n not in names]
            out.append(CheckResult("required parts", not missing,
                                   detail="" if not missing else f"missing {missing}"))
            sections = [n for n in names if n.startswith("Contents/section")]
            out.append(CheckResult("section parts", bool(sections),
                                   detail=f"{len(sections)} section(s)"))
            # mimetype 은 ZIP 의 첫 엔트리이면서 무압축이어야 한다 (ODF 관례).
            info = z.infolist()
            first_ok = bool(info) and info[0].filename == "mimetype"
            stored_ok = bool(info) and info[0].compress_type == zipfile.ZIP_STORED
            out.append(CheckResult(
                "mimetype first+stored", first_ok and stored_ok,
                detail="" if first_ok and stored_ok
                else f"first={info[0].filename if info else None} "
                     f"stored={stored_ok}"))
    except zipfile.BadZipFile as exc:
        out.append(CheckResult("zip integrity", False, detail=str(exc)))
    return out


def check_markpen_pairs(path: str | Path) -> CheckResult:
    """``markpenBegin`` 과 ``markpenEnd`` 는 모든 섹션에서 짝이 맞아야 한다.

    짝 잃은 ``markpenBegin`` 하나가 문서 나머지 전체에 형광색을 번지게 한다.
    추출한 텍스트만 봐서는 보이지 않는 결함이다.
    """
    begins = ends = 0
    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if name.startswith("Contents/section") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "replace")
                begins += xml.count("<hp:markpenBegin")
                ends += xml.count("<hp:markpenEnd")
    return CheckResult(
        "markpen pairing", begins == ends,
        detail=f"{begins} begin / {ends} end",
    )


def check_binary_refs(path: str | Path) -> CheckResult:
    """모든 ``binaryItemIDRef`` 가 실제 ``BinData/`` 항목으로 이어져야 한다."""
    import re

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        bindata = {n.split("/")[-1].split(".")[0].lower()
                   for n in names if n.startswith("BinData/")}
        manifest = ""
        if "META-INF/manifest.xml" in names:
            manifest = z.read("META-INF/manifest.xml").decode("utf-8", "replace")
        refs: set[str] = set()
        for name in names:
            if name.startswith("Contents/section") and name.endswith(".xml"):
                xml = z.read(name).decode("utf-8", "replace")
                refs.update(re.findall(r'binaryItemIDRef="([^"]+)"', xml))

    if not refs:
        return CheckResult("binary refs", True, detail="no images")

    unresolved = [r for r in refs
                  if r.lower() not in bindata and r not in manifest]
    return CheckResult(
        "binary refs", not unresolved,
        detail=f"{len(refs)} ref(s)" if not unresolved
        else f"unresolved: {unresolved}",
    )


def check_cell_overflow(path: str | Path, *, font_pt: float = 10.0) -> CheckResult:
    """렌더러 없이 셀의 가로 넘침을 예측한다.

    ``hwpx.form_fit.measure`` 를 쓴다. 이 모듈의 글자 폭은 실제 한글이 남긴 줄
    캐시에 맞춰 보정돼 있다(한글/전각은 정확, 라틴은 근사). 여기서 쓸 수 있는
    넘침 신호 중 신뢰할 수 있는 것은 이것뿐이다. rhwp 는 문서에 캐시된
    ``linesegarray`` 를 재생하는 쪽에 가까워서, 새로 만든 파일은 판단하지
    못한다.

    한 셀에서 끊을 수 없는 단어가 하나라도 있으면 실패로 본다. 한글이 줄을
    나눌 수 없어 셀 경계를 밀고 나가는 텍스트이기 때문이다.
    """
    try:
        offenders = _overflow_offenders(path, font_pt=font_pt)
    except Exception as exc:
        return CheckResult("cell overflow", False, checked=False, detail=str(exc))

    words = [w for _, w in offenders]
    return CheckResult(
        "cell overflow", not offenders,
        detail="no unbreakable overflow" if not offenders
        else f"{len(offenders)} cell(s) overflow, e.g. {words[:3]}",
    )


def _overflow_offenders(path: str | Path, *, font_pt: float = 10.0
                        ) -> list[tuple[str, str]]:
    """텍스트가 안 들어가는 셀마다 ``(셀 경로, 문제 단어)``."""
    from hwpx.document import HwpxDocument
    from hwpx.form_fit.measure import estimate_text_width

    from .boxdoc import CELL_PAD
    from .edit import iter_cells

    doc = HwpxDocument.open(str(path))
    offenders: list[tuple[str, str]] = []
    for ref in iter_cells(doc):
        inner = (ref.cell.width or 0) - 2 * CELL_PAD
        if inner <= 0:
            continue
        for para in ref.cell.paragraphs:
            hit = None
            for word in _longest_words(para):
                if estimate_text_width(word, font_pt) > inner:
                    hit = word[:28]
                    break
            if hit:
                offenders.append((ref.path, hit))
                break
    return offenders


def _iter_tables(section):
    """섹션 안의 모든 표(중첩 포함).

    별칭으로 남겨 둔다. 이 순회 함수는 :mod:`hwpxkit.edit` 로 옮겨갔다.
    편집 쪽에서 같은 순회를 안정적인 주소와 함께 쓰기 때문이다.
    """
    from .edit import iter_tables

    return iter_tables(section)


def _longest_words(paragraph) -> list[str]:
    from .richtext import paragraph_text

    text = paragraph_text(paragraph)
    # 한글은 음절 사이에서 줄이 바뀌므로, 공백으로 구분된 라틴/숫자 덩어리만
    # 진짜로 끊을 수 없는 단어다.
    return [w for w in text.split() if w and not any("가" <= c <= "힣" for c in w)]


def check_against_baseline(path: str | Path, baseline: str | Path) -> list[CheckResult]:
    """편집한 파일을 그 원본과 비교한다.

    편집에는 새로 만들 때는 있을 수 없는 실패 방식이 하나 있다. 텍스트는
    바뀌었는데 ``<hp:linesegarray>`` 가 그대로 남은 문단이다. 그러면 한글이 새
    텍스트를 옛 줄 자리에 그려서 글자가 겹친다. 파일 하나만 봐서는 이걸 알 수
    없고 편집 전후 쌍이 필요하다. 그래서 이 검사만 baseline 을 받는다.

    얼마나 바뀌었는지도 함께 보고한다. 의도보다 많은 셀을 건드린 편집이
    묻히지 않고 눈에 보이도록.
    """
    try:
        from hwpx.document import HwpxDocument

        from .edit import cached_line_count, iter_cells
        from .richtext import paragraph_text
    except Exception as exc:
        return [CheckResult("baseline diff", False, checked=False, detail=str(exc))]

    def snapshot(p):
        doc = HwpxDocument.open(str(p))
        out: dict[str, list[tuple[str, bool]]] = {}
        for ref in iter_cells(doc):
            out[ref.path] = [
                (paragraph_text(par), cached_line_count(par) is not None)
                for par in ref.cell.paragraphs
            ]
        body = [paragraph_text(par)
                for sec in doc.sections for par in (sec.paragraphs or [])]
        return out, body

    try:
        before, before_body = snapshot(baseline)
        after, after_body = snapshot(path)
    except Exception as exc:
        return [CheckResult("baseline diff", False, checked=False,
                            detail=f"{type(exc).__name__}: {exc}")]

    stale: list[str] = []
    changed = 0
    for path_key, paras in after.items():
        old = before.get(path_key)
        if old is None:
            continue
        for i, (text, has_cache) in enumerate(paras):
            if i >= len(old):
                continue
            if text != old[i][0]:
                changed += 1
                # 원래 캐시를 *가지고 있던* 문단만 낡은 캐시를 남길 수 있다.
                if has_cache and old[i][1]:
                    stale.append(f"{path_key}#{i}")

    body_changed = sum(1 for a, b in zip(after_body, before_body) if a != b)
    out = [CheckResult(
        "edit scope", True,
        detail=f"{changed} cell paragraph(s), {body_changed} body paragraph(s) changed")]
    out.append(CheckResult(
        "layout cache invalidated", not stale,
        detail="all edited paragraphs re-flow"
        if not stale else f"{len(stale)} stale: {stale[:3]}"))

    # 편집이 형광펜 균형을 어느 방향으로도 바꾸면 안 된다.
    b_pairs = check_markpen_pairs(baseline)
    a_pairs = check_markpen_pairs(path)
    out.append(CheckResult(
        "markpen preserved", a_pairs.ok,
        detail=f"baseline {b_pairs.detail} -> edited {a_pairs.detail}"))

    # 실제 제출 서식은 결함을 이미 안고 온다. 실측한 두 문서 모두 손대기 전부터
    # 셀 하나가 넘쳐 있었다. 그걸 편집 탓으로 돌리면 사용자가 이 검사를 무시하게
    # 되므로, 원래 있던 것인지 새로 생긴 것인지 구분해서 알려 준다.
    try:
        was = {p for p, _ in _overflow_offenders(baseline)}
        now = _overflow_offenders(path)
        introduced = [(p, w) for p, w in now if p not in was]
        inherited = len(now) - len(introduced)
        out.append(CheckResult(
            "overflow introduced", not introduced,
            detail=f"{inherited} pre-existing, none added" if not introduced
            else f"{len(introduced)} new: {introduced[:3]}"))
    except Exception as exc:
        out.append(CheckResult("overflow introduced", False, checked=False,
                               detail=str(exc)))
    return out


def check_render(path: str | Path, *, min_pages: int = 1) -> list[CheckResult]:
    """rhwp 로 모든 페이지를 렌더해서 구조가 무너졌는지 본다.

    :mod:`hwpxkit.render` 에 위임한다. 비상업 라이선스인 ``pyhwpxlib`` 를
    import 해도 되는 유일한 모듈이다. 지연 import 라서 core 프로파일에서도
    이 모듈이 — 따라서 모든 구조 검사가 — 문제없이 로드된다.
    """
    from .render import render_check

    return [CheckResult(name, ok, checked=checked, detail=detail)
            for name, ok, checked, detail in render_check(path, min_pages=min_pages)]


def verify(path: str | Path, *, render: bool = True, min_pages: int = 1,
           baseline: str | Path | None = None) -> Report:
    """가능한 모든 층을 돌려서 보고서 하나로 돌려준다.

    편집을 시작한 원본 파일을 *baseline* 으로 넘기면, 편집에만 존재하는
    검사들이 추가된다. 바뀐 문단의 낡은 레이아웃 캐시, 편집 범위, 원본 대비
    형광펜 균형이다.
    """
    report = Report()
    report.add(*check_package(path))
    report.add(check_markpen_pairs(path))
    report.add(check_binary_refs(path))
    report.add(check_cell_overflow(path))
    if baseline is not None:
        report.add(*check_against_baseline(path, baseline))
    if render:
        report.add(*check_render(path, min_pages=min_pages))
    # 아래 항목들은 여기서 쓸 수 있는 어떤 수단으로도 확인할 수 없다. 하나씩
    # 이름을 붙여 두면 "안 봤다"가 "보니 괜찮더라"로 읽히지 않는다.
    report.add(CheckResult(
        "highlight renders", False, checked=False,
        detail="rhwp ignores markpen entirely (A/B confirmed); XML pairing only"))
    report.add(CheckResult(
        "line breaking / page count", False, checked=False,
        detail="rhwp replays cached linesegarray; a generated file has none"))
    report.add(CheckResult(
        "Hancom COM oracle", False, checked=False,
        detail="requires Hangul 2014+; Hangul 2010 cannot parse HWPX"))
    return report
