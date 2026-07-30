"""rhwp 렌더러. ``pyhwpxlib`` 를 건드리는 **유일한** 모듈이다.

``hwpxkit`` 의 나머지는 전부 ``python-hwpx`` (Apache-2.0) 에만 의존한다. 그래서
패키지 전체에는 비상업 제약이 붙지 않는다. ``pyhwpxlib`` 는 PolyForm
Noncommercial 이고, 이 라이선스의 "No Other Rights" 조항이 재실시를 금지한다.
즉 관대한 라이선스로 배포해도 그 권리를 하위 사용자에게 넘겨줄 수 없다는 뜻이다.
그 import 를 이 파일 하나에 가둬 두는 것이, ``preview`` 부가 설치를 이름뿐이
아니라 실제로 선택 사항으로 만든다.

한 코드베이스, 두 설치 프로파일:

core (부가 설치 없음)
    문서 작성, 편집, 모든 구조 검사. 끝까지 Apache-2.0 이라 호스팅·판매·오픈소스
    공개에 제약이 없다. :func:`render_pages` 와 :func:`check_render` 는
    NOT VERIFIED 를 보고한다.

``[preview]``
    ``pyhwpxlib`` + ``wasmtime`` 을 추가한다. PNG 미리보기와 렌더 검사가 켜진다.
    이 스킬을 개발할 때 쓴 프로파일이고, 로컬에 두고 쓰기 좋은 쪽이다. 개인·학술
    사용은 허용된다. 다만 호스팅 서비스로 배포하거나 상업 제품에 넣으려면
    저작권자(ratiertm@gmail.com)의 별도 라이선스가 필요하다.

렌더러 본체인 ``rhwp_bg.wasm`` 자체는 MIT (Edward Kim) 다. 제약이 걸린 것은 그
주위를 감싼 파이썬 브리지뿐이다. 그래서 상업용 빌드는 wasm 을 직접 구동할 수
있다. 단 그 브리지는 wasm 이 노출하는 인터페이스를 보고 새로 써야 한다.
``pyhwpxlib`` 의 소스를 베끼면 안 된다.
"""
from __future__ import annotations

import re
from pathlib import Path

#: 렌더러를 쓸 수 없을 때 그 이유.
UNAVAILABLE = ("rhwp renderer not installed -- this is the core (Apache-2.0) "
               "profile; `pip install hwpxkit[preview]` adds it")

FONT = "Malgun Gothic"
_FF_STYLE = re.compile(r"font-family\s*:\s*[^;\"']+", re.I)
_FF_ATTR = re.compile(r'font-family\s*=\s*"[^"]*"', re.I)


def available() -> bool:
    """선택 설치인 preview 부가 패키지가 깔려 있는지."""
    try:
        import pyhwpxlib.rhwp_bridge  # noqa: F401
    except Exception:
        return False
    return True


def _engine():
    """rhwp 엔진. 없으면 어떤 부가 설치가 필요한지 알려 주는 오류를 낸다."""
    try:
        from pyhwpxlib.rhwp_bridge import RhwpEngine
    except Exception as exc:  # ImportError, or a broken wasmtime install
        raise RendererUnavailable(f"{UNAVAILABLE} ({exc})") from exc
    return RhwpEngine()


def _rasteriser():
    """PyMuPDF. 없으면 같은 형태의 깔끔한 오류를 낸다.

    core 가 아니라 부가 설치에 둔 이유가 하나 더 있다. PyMuPDF 는 AGPL-3.0
    (또는 Artifex 상업 라이선스)이고, 그 §13 네트워크 조항이 호스팅 서비스의
    이용자에게까지 미친다. 그래서 이건 떠돌이 ImportError 가 아니라 *부가 설치*
    누락으로 실패해야 한다. 안 그러면 core 프로파일이 거절하는 대신 죽는다.
    """
    try:
        import pymupdf
    except Exception as exc:
        raise RendererUnavailable(f"{UNAVAILABLE} (pymupdf: {exc})") from exc
    return pymupdf


class RendererUnavailable(RuntimeError):
    """preview 부가 설치 없이 렌더를 요청했을 때 발생."""


def page_svgs(src: str | Path, pages=None) -> list[str]:
    """요청한 페이지들의 원본 SVG. 글꼴은 손대지 않는다."""
    engine = _engine()
    doc = engine.load(str(src))
    try:
        targets = list(pages) if pages else range(doc.page_count)
        return [doc.render_page_svg(p) for p in targets if p < doc.page_count]
    finally:
        doc.close()


def substitute_fonts(svg: str, font: str = FONT) -> str:
    """모든 ``font-family`` 를 한글이 되는 시스템 글꼴로 바꾼다.

    rhwp 가 뱉는 SVG 안의 글꼴 이름(함초롬바탕 등)은 해석되지 않는다. 이 치환이
    없으면 모든 CJK 글자가 두부 상자로 그려진다. 다만 치환하면 글자 폭이
    달라지므로, 결과물의 줄바꿈 위치는 근사치로만 볼 것.
    """
    svg = _FF_STYLE.sub(f"font-family:{font}", svg)
    return _FF_ATTR.sub(f'font-family="{font}"', svg)


def render_pages(src: str | Path, out_dir: str | Path, pages=None,
                 scale: float = 1.4) -> list[Path]:
    """rhwp WASM -> SVG -> PyMuPDF 경로로 페이지를 PNG 로 렌더한다.

    ``cairosvg`` 는 일부러 쓰지 않는다. ``libcairo-2.dll`` 이 필요한데 기본
    윈도우에는 없다. PyMuPDF 는 네이티브 의존성 없이 래스터화한다.
    """
    pymupdf = _rasteriser()

    src, out_dir = Path(src), Path(out_dir)
    engine = _engine()
    out_dir.mkdir(parents=True, exist_ok=True)
    doc = engine.load(str(src))
    written: list[Path] = []
    try:
        targets = list(pages) if pages else range(doc.page_count)
        for page in targets:
            if page >= doc.page_count:
                continue
            svg = substitute_fonts(doc.render_page_svg(page))
            pdf = pymupdf.open(stream=svg.encode("utf-8"), filetype="svg")
            pix = pdf[0].get_pixmap(matrix=pymupdf.Matrix(scale, scale))
            dst = out_dir / f"{src.stem}_p{page}.png"
            pix.save(dst)
            written.append(dst)
            print(f"{dst}  {pix.width}x{pix.height}")
    finally:
        doc.close()
    return written


def render_check(src: str | Path, *, min_pages: int = 1) -> list[tuple]:
    """구조 렌더 검사. ``(name, ok, checked, detail)`` 튜플을 돌려준다.

    ``CheckResult`` 객체가 아니라 데이터를 돌려주는 이유는, :mod:`hwpxkit.verify`
    가 — 부가 설치 없이도 깨끗하게 import 돼야 하므로 — 이 모듈에 import 시점
    의존을 갖지 않게 하기 위해서다.
    """
    if not available():
        return [("rhwp render", False, False, UNAVAILABLE)]
    try:
        engine = _engine()
        doc = engine.load(str(src))
        pages = doc.page_count
        out = [("renders", pages >= min_pages, True, f"{pages} page(s)")]
        empty = []
        for page in range(pages):
            # 마크업이 거의 없는 페이지는 사실상 빈 페이지로 렌더된 것이다.
            if len(doc.render_page_svg(page)) < 2000:
                empty.append(page)
        out.append(("no blank pages", not empty, True,
                    "" if not empty else f"blank: {empty}"))
        doc.close()
        return out
    except Exception as exc:
        return [("rhwp render", False, True, f"{type(exc).__name__}: {exc}")]
