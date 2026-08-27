"""HWP(구 바이너리 포맷) → HWPX 변환.

``hwpxkit.hwp_export`` 와 같은 이유로 격리된 모듈이다. 변환은 ``pyhwpxlib`` 에
의존하는데 그 패키지가 PolyForm Noncommercial 이라, import 를 이 파일 하나에
가둬 두어야 core 프로파일이 깨끗하게 유지된다.

**라이선스에 대해 오해하기 쉬운 지점이 있다.** ``pyhwpxlib`` 안에서
``hwp2hwpx.py`` / ``hwp_reader.py`` / ``value_convertor.py`` 세 파일은
Apache-2.0 이다(원본: neolord0/hwp2hwpx, neolord0/hwplib). 그래서 "변환 기능은
상업적으로 써도 된다"고 읽기 쉽다. 그렇지 않다. 실측해 보면 변환 한 번에
``pyhwpxlib`` 모듈 **59개가 로드되고 그중 56개가 PolyForm** 이다
(``.api``, ``.builder``, ``.writer.*``, ``.objects.*`` 등). Apache 라이선스는
그 세 파일의 *소스 코드*에 적용될 뿐, 동작하는 변환 기능 전체에 적용되지
않는다. 그래서 이 기능은 core 가 아니라 부가 설치다.

    pip install '<skill dir>[hwp]'

역방향(HWPX → HWP)은 **제공하지 않는다.** ``pyhwpxlib`` 에도 없다. HWP 는
OLE 복합 문서 기반 바이너리 포맷이라 쓰기가 읽기보다 훨씬 어렵다. 한글에서
직접 "다른 이름으로 저장"하는 것 말고는 방법이 없다.

상업용으로 변환이 필요하다면 원본 Apache 프로젝트(neolord0/hwp2hwpx, 자바)를
직접 쓰는 편이 낫다. ``pyhwpxlib`` 의 PolyForm 코드를 우회할 수 있다.
"""
from __future__ import annotations

import os
from pathlib import Path

_HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"

#: 변환기를 쓸 수 없을 때 그 이유.
UNAVAILABLE = ("hwp 변환기가 설치돼 있지 않다. core(Apache-2.0) 프로파일이다. "
               "`pip install '<skill dir>[hwp]'` 로 추가할 수 있다")


class ConverterUnavailable(RuntimeError):
    """``[hwp]`` 부가 설치 없이 변환을 요청했을 때 발생."""


def available() -> bool:
    """선택 설치인 hwp 변환기가 쓸 수 있는 상태인지."""
    try:
        import olefile  # noqa: F401
        from pyhwpxlib.hwp2hwpx import convert  # noqa: F401
    except Exception:
        return False
    return True


def _converter():
    """변환 함수. 없으면 어떤 부가 설치가 필요한지 알려 주는 오류를 낸다."""
    try:
        import olefile  # noqa: F401
    except Exception as exc:
        raise ConverterUnavailable(f"{UNAVAILABLE} (olefile: {exc})") from exc
    try:
        from pyhwpxlib.hwp2hwpx import convert
    except Exception as exc:
        raise ConverterUnavailable(f"{UNAVAILABLE} ({exc})") from exc
    return convert


def _jar_to_hwpx(src: Path, dest: Path, *, timeout: int = 180) -> bool:
    """vsdn/hwpConverter 로 HWP -> HWPX. 성공하면 ``True``.

    ``pyhwpxlib`` 쪽 경로보다 **먼저** 시도한다. pyhwpxlib 의 리더는 그림
    참조를 제대로 복원하지 못한다 — 실측(U300, 그림 13장): BinData 는 13개를
    다 풀어 놓고 ``<hc:img binaryItemIDRef>`` 는 전부 첫 장을 가리켜서, 문서의
    모든 그림이 같은 그림으로 보인다. jar 리더는 13개를 각각 맞게 잇는다.

    자바나 빌드본이 없으면 조용히 ``False`` — 호출부가 기존 경로로 넘어간다.
    """
    import shutil
    import subprocess
    import tempfile
    import uuid

    from .hwp_export import _JAR_MAIN, find_converter_jar

    home = find_converter_jar()
    if home is None or shutil.which("java") is None:
        return False
    cp = f"{home / 'build' / 'hwpConverter.jar'}{os.pathsep}{home / 'lib' / '*'}"
    stage = Path(tempfile.gettempdir()) / f"hwp2hwpx-{uuid.uuid4().hex}"
    stage.mkdir(parents=True)
    try:
        staged = stage / "out.hwpx"
        try:
            proc = subprocess.run(["java", "-cp", cp, _JAR_MAIN, str(src), str(staged)],
                                  capture_output=True, timeout=timeout)
        except (subprocess.TimeoutExpired, OSError):
            return False
        if proc.returncode != 0 or not staged.exists():
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(dest))
        return True
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def hwp_to_hwpx(src: str | Path, dest: str | Path | None = None, *,
                prefer_jar: bool = True) -> Path:
    """HWP 파일을 HWPX 로 변환하고 결과 경로를 돌려준다.

    *dest* 를 생략하면 *src* 옆에 같은 이름으로 ``.hwpx`` 를 만든다.

    변환 결과는 :func:`hwpxkit.verify.verify` 로 바로 검사할 수 있고,
    :mod:`hwpxkit.edit` 로 바로 편집할 수 있다. 실측한 정부 배포 양식에서는
    변환본과 한글이 직접 저장한 HWPX 가 셀 24개로 개수가 같았고, 라벨의 셀
    경로까지 일치했다. 오히려 변환본 쪽이 구조 검사를 더 잘 통과했다. 한글이
    저장한 파일은 ``mimetype`` 을 ZIP 첫 엔트리로 넣지 않아서 ODF 관례를
    어기는 반면, 변환본은 지키기 때문이다.

    다만 변환기가 원본의 모든 서식을 재현한다는 보장은 없다. 중요한 문서라면
    변환 후 한글에서 직접 열어 확인할 것. :func:`verify` 가 확인해 주는 것은
    구조이지 시각적 충실도가 아니다.
    """
    src = Path(src)
    if not src.exists():
        raise FileNotFoundError(src)
    dest = Path(dest) if dest is not None else src.with_suffix(".hwpx")
    dest.parent.mkdir(parents=True, exist_ok=True)
    # jar 이 있으면 그쪽이 정확하다 (그림 참조·표 구조). 없으면 pyhwpxlib.
    if prefer_jar and _jar_to_hwpx(src, dest):
        _restore_from_binary(src, dest)
        return dest
    convert = _converter()
    convert(str(src), str(dest))
    return dest


def _restore_from_binary(hwp: Path, hwpx: Path) -> dict[str, int]:
    """변환기가 놓친 것을 원본 ``.hwp`` 바이트에서 되살린다.

    두 가지다.

    * **표 쪽 나눔 모드** — ``hwp2hwpx`` 는 바이너리 2 를 ``TABLE`` 로 읽는데,
      한컴이 만든 파일과 그 짝 HWPX 를 대조해 보면 2 는 ``CELL`` 이다
      (:data:`hwpxkit.hwpbin.SPLIT_TO_HWPX` 의 근거 참고). 이걸 놓치면 편집본을
      다시 읽어 들일 때마다 상자가 쪽 경계에서 안 나뉘는 설정으로 바뀐다.
    * **형광펜** — HWP 는 형광펜을 문단의 ``PARA_RANGE_TAG`` 로 저장한다.
      어떤 리더도 이걸 HWPX ``markpen`` 으로 되돌리지 못해서, 한/글에서 편집한
      문서를 받아 오면 강조가 통째로 사라진다.

    문단 순서는 두 형식에서 같다(실측: PARA_HEADER 193 개 ↔ ``<hp:p>`` 193 개).
    수를 확인하고, 어긋나면 형광펜 복원만 건너뛴다 — 엉뚱한 자리에 칠하느니
    안 칠하는 편이 낫다.
    """
    from . import hwpbin
    from .richtext import apply_markpen

    from hwpx.document import HwpxDocument

    done = {"split_modes": 0, "markpen": 0}
    modes = hwpbin.table_split_modes(hwp)
    ranges = hwpbin.markpen_ranges(hwp)
    if not modes and not ranges:
        return done

    doc = HwpxDocument.open(str(hwpx))
    section = doc.sections[0].element

    tables = list(section.iter(f"{_HP}tbl"))
    for tbl, mode in zip(tables, modes):
        want = hwpbin.SPLIT_TO_HWPX.get(mode)
        if want and tbl.get("pageBreak") != want:
            tbl.set("pageBreak", want)
            done["split_modes"] += 1

    paras = list(section.iter(f"{_HP}p"))
    if ranges and len(paras) == hwpbin.counts(hwp)["paragraphs"]:
        for index, start, end, color in ranges:
            if not 0 <= index < len(paras):
                continue
            if _markpen_span(paras[index], start, end, color, apply_markpen):
                done["markpen"] += 1

    if done["split_modes"] or done["markpen"]:
        # ET 를 직접 고치면 python-hwpx 의 '변경됨' 표시가 켜지지 않아, 저장할 때
        # 손대지 않은 원본 파트가 그대로 쓰인다 — 고친 것이 조용히 사라진다.
        doc.sections[0].mark_dirty()
        doc.save_to_path(str(hwpx))
    return done


def _markpen_span(para, start: int, end: int, color: str, apply_markpen) -> bool:
    """문단 안 ``[start, end)`` 글자 구간에 형광펜을 씌운다.

    HWP 의 구간은 컨트롤 문자를 포함한 WCHAR 인덱스라 텍스트만 세면 어긋난다.
    여기서는 텍스트 run 만 걷되, 표·그림을 붙든 run 은 한 글자로 세어 맞춘다
    (HWP 도 개체를 컨트롤 문자 한 자리로 잡는다).
    """
    pos = 0
    hit = False
    for run in list(para.findall(f"{_HP}run")):
        texts = run.findall(f"{_HP}t")
        if not texts:
            pos += 1                      # 개체 run 은 컨트롤 문자 한 자리
            continue
        length = sum(len(t.text or "") for t in texts)
        if pos < end and pos + length > start:
            apply_markpen(run, color)
            hit = True
        pos += length
    return hit


def is_hwp(path: str | Path) -> bool:
    """확장자가 아니라 내용으로 구식 HWP 바이너리인지 판별한다.

    HWPX 는 ZIP 이라 ``PK`` 로 시작하고, HWP 5.x 는 OLE 복합 문서라
    ``D0 CF 11 E0`` 로 시작한다. 확장자는 믿을 게 못 된다. 실제로 이 저장소가
    다뤄 온 표본 중에도 ``.hwp.hwpx`` 처럼 두 확장자가 겹친 파일이 있었다.
    """
    try:
        with open(path, "rb") as fh:
            head = fh.read(8)
    except OSError:
        return False
    return head[:4] == b"\xd0\xcf\x11\xe0"


def open_any(src: str | Path, *, workdir: str | Path | None = None):
    """HWP 든 HWPX 든 열어서 ``HwpxDocument`` 를 돌려준다.

    HWP 면 먼저 변환한다. 변환본은 *workdir* (기본값은 임시 디렉터리)에
    만들어지므로 원본은 건드리지 않는다.
    """
    from hwpx.document import HwpxDocument

    src = Path(src)
    if not is_hwp(src):
        return HwpxDocument.open(str(src))

    if workdir is None:
        import tempfile

        workdir = tempfile.mkdtemp(prefix="hwpxkit_")
    dest = Path(workdir) / (src.stem + ".hwpx")
    return HwpxDocument.open(str(hwp_to_hwpx(src, dest)))
