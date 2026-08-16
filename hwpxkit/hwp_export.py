"""HWPX -> HWP 5.x binary export.

Some recipients still run Hangul versions that cannot open HWPX (Hangul 2010
opens the ZIP as a text file and ``Open()`` still returns ``True`` -- see
gotchas). This module produces a binary ``.hwp`` they can open, trying routes
in fidelity/stability order:

``jar``      vsdn/hwpConverter (Apache-2.0, Java): a real HWPX->HWP writer
             built on hwplib/hwpxlib. No Hancom involved, works headless and
             cross-platform. Preferred whenever Java and the built jar are
             found (env ``HWPCONVERTER_HOME`` or ``ref/hwpConverter``).
``direct``   Hangul 2014+ (COM major version >= 9): open the HWPX itself,
             ``SaveAs(..., "HWP")``.
``html``     Hangul 2010 (major version 8): the HWPX is flattened to CP949
             HTML and imported. Last resort -- layout degrades badly; text
             and table structure survive but little else.

COM route choice reads the ``Version`` property -- it never opens a document
to find out, because opening an HWPX on Hangul 2010 chews the ZIP as text for
minutes. Every export is verified afterwards by reading the produced .hwp
back with ``pyhwpxlib.hwp_reader`` (needs ``olefile``) and reporting how many
source text tokens survived; on route="auto" a garbage result falls through
to the next route automatically.

The jar route needs only Java 8+. The COM routes need Windows with Hancom
Office and are driven through ``scripts/hancom_saveas.ps1`` (no pywin32
dependency). If a COM call exceeds its timeout, any hwp.exe the call spawned
is killed so a stuck instance cannot poison later runs with recovery dialogs
-- though on this project's Hangul 2010 machine COM has proven fragile even
so, which is exactly why the jar route exists and comes first.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

_PS_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "hancom_saveas.ps1"
_MAX_TOKENS = 400
_JAR_MAIN = "kr.n.nframe.newfeature.HwpConverterCli"

#: Per-process cache of the COM version tuple (None = not asked yet).
_hancom_version: tuple[int, ...] | None = None


class HwpExportError(RuntimeError):
    """The COM conversion could not produce a .hwp at all."""


class DestLockedError(HwpExportError):
    """The destination .hwp is open in another program (e.g. Hangul).

    Retrying another conversion route cannot help -- to_hwp re-raises this
    immediately instead of falling through the route ladder.
    """


def _replace_dest(produced: Path, dest: Path) -> None:
    """Atomically put *produced* at *dest*, with a clear error when locked."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # 임시 temp 가 다른 드라이브일 수 있으므로 대상 폴더로 복사한 뒤
    # 같은 볼륨 안에서 원자적으로 교체한다.
    tmp = dest.with_name(dest.name + ".new")
    shutil.copyfile(produced, tmp)
    try:
        os.replace(str(tmp), str(dest))
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise DestLockedError(
            f"대상 파일을 덮어쓸 수 없음 — 한글 등 다른 프로그램에서 "
            f"{dest.name} 이(가) 열려 있으면 닫고 다시 시도: {exc}"
        )


@dataclass
class ExportReport:
    dest: Path
    route: str                       # "direct" | "html"
    coverage: float                  # fraction of source tokens found in the .hwp
    tokens_total: int
    missing: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.coverage >= 0.9

    def render(self) -> str:
        labels = {
            "jar": " (hwpConverter — 한글 불필요, 구조 보존)",
            "direct": " (한글 COM — 원본 그대로)",
            "html": " (HTML 경유 — 서식 손실 있음)",
        }
        lines = [
            f"저장: {self.dest}",
            f"경로: {self.route}" + labels.get(self.route, ""),
            f"텍스트 보존율: {self.coverage:.0%} ({self.tokens_total}개 표본 기준)",
        ]
        if self.missing:
            lines.append(f"누락 예시: {self.missing[:5]}")
        for w in self.warnings:
            lines.append(f"주의: {w}")
        lines.append("최종 확인은 한컴오피스에서 열어서 할 것.")
        return "\n".join(lines)


# --------------------------------------------------------------------- COM --

def _hwp_pids() -> set[int]:
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq hwp.exe", "/FO", "CSV", "/NH"],
            capture_output=True, timeout=30,
        ).stdout.decode("utf-8", "replace")
    except Exception:
        return set()
    pids = set()
    for line in out.splitlines():
        parts = line.split('","')
        if len(parts) >= 2 and parts[0].strip('"').lower() == "hwp.exe":
            try:
                pids.add(int(parts[1].strip('"')))
            except ValueError:
                pass
    return pids


def _run_com(source: Path | None, dest: Path | None, *, timeout: int,
             staged: bool = False) -> dict:
    """Run the COM helper: version query, or Open *source* / SaveAs *dest*.

    Paths are staged inside a fresh temp directory: the copy sidesteps
    Hancom's file-path security prompt and keeps Korean/space paths out of
    the COM arguments. Pass ``staged=True`` when *source* already sits in a
    safe ASCII temp location and must be opened in place (e.g. an HTML file
    whose relative image references would break if copied alone). On
    timeout, any hwp.exe spawned during this call is killed -- a stuck
    instance holding an open document makes every later launch block on the
    recovery dialog.
    """
    if not _PS_SCRIPT.exists():
        raise HwpExportError(f"COM helper missing: {_PS_SCRIPT}")

    stage = Path(tempfile.gettempdir()) / f"hwpx2hwp-{uuid.uuid4().hex}"
    stage.mkdir(parents=True)
    before = _hwp_pids()
    try:
        out_json = stage / "result.json"
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(_PS_SCRIPT), "-OutJson", str(out_json),
        ]
        staged_dest = None
        if source is not None:
            if staged:
                staged_src = source
            else:
                staged_src = stage / f"in{source.suffix.lower()}"
                shutil.copyfile(source, staged_src)
            cmd += ["-Source", str(staged_src)]
            if dest is not None:
                staged_dest = stage / "out.hwp"
                cmd += ["-Dest", str(staged_dest), "-Format", "HWP"]

        try:
            proc = subprocess.run(cmd, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            for pid in _hwp_pids() - before:
                subprocess.run(["taskkill", "/PID", str(pid), "/F"],
                               capture_output=True, timeout=30)
            raise HwpExportError(f"한글 COM 호출이 {timeout}초 안에 끝나지 않아 중단함")
        if not out_json.exists():
            detail = (proc.stderr or b"").decode("utf-8", "replace").strip()
            raise HwpExportError(f"COM 헬퍼가 결과를 남기지 않음: {detail[:300]}")

        result = json.loads(out_json.read_text(encoding="utf-8-sig"))
        if staged_dest is not None and result.get("saved"):
            _replace_dest(staged_dest, dest)
        return result
    finally:
        shutil.rmtree(stage, ignore_errors=True)


def hancom_version(*, timeout: int = 120) -> tuple[int, ...]:
    """Version of the installed Hancom Office, e.g. ``(8, 0, 0, 466)`` (cached).

    Raises HwpExportError when Hancom/COM is unavailable.
    """
    global _hancom_version
    if _hancom_version is None:
        result = _run_com(None, None, timeout=timeout)
        raw = result.get("version") or ""
        parts = tuple(int(p) for p in re.findall(r"\d+", raw))
        if not parts:
            raise HwpExportError(
                f"한글 COM 버전을 확인할 수 없음 (설치 안 됨?): {result.get('error')}"
            )
        _hancom_version = parts
    return _hancom_version


def hancom_opens_hwpx() -> bool:
    """Whether the installed Hancom can genuinely parse HWPX.

    Hangul 2010 is COM major version 8 and cannot (``Open()`` lies -- it
    reads the ZIP as text); HWPX support arrived with Hangul 2014+ (major 9).
    """
    return hancom_version()[0] >= 9


# ------------------------------------------------------------ verification --

def _hwpx_tokens(path: Path) -> list[str]:
    """Distinctive text tokens from every ``<hp:t>`` in the HWPX sections."""
    tokens: list[str] = []
    seen: set[str] = set()
    with zipfile.ZipFile(path) as z:
        names = sorted(n for n in z.namelist()
                       if re.match(r"Contents/section\d+\.xml$", n))
        for name in names:
            root = ET.fromstring(z.read(name))
            for elem in root.iter():
                if elem.tag.endswith("}t") and elem.text:
                    for tok in elem.text.split():
                        if len(tok) >= 2 and tok not in seen:
                            seen.add(tok)
                            tokens.append(tok)
    return tokens[:_MAX_TOKENS]


def _hwp_text(path: Path) -> str:
    from pyhwpxlib.hwp_reader import read_hwp

    doc = read_hwp(str(path))
    return "\n".join(doc.texts)


def _coverage(tokens: list[str], text: str) -> tuple[float, list[str]]:
    if not tokens:
        return 1.0, []
    missing = [t for t in tokens if t not in text]
    return 1.0 - len(missing) / len(tokens), missing


# ---------------------------------------------------------------- jar route --

def find_converter_jar() -> Path | None:
    """Locate a built vsdn/hwpConverter checkout, or None.

    Looks at ``HWPCONVERTER_HOME``, then ``ref/hwpConverter`` under the
    current directory and its parents. A hit must contain
    ``build/hwpConverter.jar`` and the ``lib`` directory.
    """
    candidates: list[Path] = []
    env = os.environ.get("HWPCONVERTER_HOME")
    if env:
        candidates.append(Path(env))
    for base in [Path.cwd(), *Path.cwd().parents]:
        candidates.append(base / "ref" / "hwpConverter")
    for home in candidates:
        if (home / "build" / "hwpConverter.jar").exists() and (home / "lib").is_dir():
            return home
    return None


def _java_available() -> bool:
    return shutil.which("java") is not None


def _export_jar_route(src: Path, dest: Path, *, timeout: int) -> None:
    """HWPX -> HWP with hwpConverter (Java, no Hancom). Raises on failure.

    The CLI never overwrites: an existing output path is silently renamed to
    "name(1).hwp" (OutputNaming.unique), which once left a stale dest that
    passed verification. Converting into a fresh empty temp dir and moving
    the result over dest makes overwrites explicit and atomic.
    """
    home = find_converter_jar()
    if home is None:
        raise HwpExportError("hwpConverter jar를 찾을 수 없음 (HWPCONVERTER_HOME)")
    cp = f"{home / 'build' / 'hwpConverter.jar'}{os.pathsep}{home / 'lib'}{os.sep}*"
    stage = Path(tempfile.gettempdir()) / f"hwpxjar-{uuid.uuid4().hex}"
    stage.mkdir(parents=True)
    try:
        staged_out = stage / "out.hwp"
        try:
            proc = subprocess.run(
                ["java", "-cp", cp, _JAR_MAIN, str(src), str(staged_out)],
                capture_output=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise HwpExportError(f"hwpConverter가 {timeout}초 안에 끝나지 않음")
        if proc.returncode != 0 or not staged_out.exists():
            detail = (proc.stderr or proc.stdout or b"").decode("utf-8", "replace")
            raise HwpExportError(f"hwpConverter 변환 실패: {detail.strip()[:300]}")
        _replace_dest(staged_out, dest)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ------------------------------------------------------------------- export --

def _export_html_route(src: Path, dest: Path, *, timeout: int) -> dict:
    from pyhwpxlib.html_converter import convert_hwpx_to_html

    stage = Path(tempfile.gettempdir()) / f"hwpx2html-{uuid.uuid4().hex}"
    stage.mkdir(parents=True)
    try:
        html = stage / "in.html"
        # embed_images=False: Hangul 2010's HTML filter drops base64 data
        # URIs, but follows relative <img src="BinData/...">, so unpack the
        # HWPX's images next to the HTML under their zip entry names.
        content = convert_hwpx_to_html(str(src), None, embed_images=False,
                                       title=src.stem)
        with zipfile.ZipFile(src) as z:
            for name in z.namelist():
                if name.startswith("BinData/") and not name.endswith("/"):
                    target = stage / name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(z.read(name))
        # Hangul 2010's HTML import filter also ignores the charset meta and
        # assumes EUC-KR; UTF-8 input arrives as mojibake and multibyte lead
        # bytes even swallow the "<" of closing tags. Encode CP949, escaping
        # anything outside it as numeric character references.
        content = content.replace(
            '<meta charset="UTF-8">',
            '<meta http-equiv="Content-Type"'
            ' content="text/html; charset=euc-kr">',
        )
        html.write_bytes(content.encode("cp949", errors="xmlcharrefreplace"))
        return _run_com(html, dest, timeout=timeout, staged=True)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


_HTML_LOSS_WARNING = (
    "HTML 경유 변환 — 형광펜, 표의 제목 줄 반복/여러 쪽 속성, "
    "정밀한 서식은 손실됨. 텍스트와 표 구조 위주로 보존."
)


def to_hwp(src: str | Path, dest: str | Path | None = None, *,
           route: str = "auto", timeout: int = 300) -> ExportReport:
    """Convert *src* (.hwpx) to a binary .hwp next to it (or at *dest*).

    route="auto" tries jar (hwpConverter, no Hancom) first, then the Hancom
    COM routes, falling through whenever a route is unavailable or its
    result verifies as garbage. Pass "jar", "direct", or "html" to force one.
    """
    src = Path(src)
    dest = Path(dest) if dest is not None else src.with_suffix(".hwp")
    if route not in ("auto", "jar", "direct", "html"):
        raise ValueError(f"route must be auto|jar|direct|html, got {route!r}")

    tokens = _hwpx_tokens(src)
    warnings: list[str] = []

    def _verify() -> tuple[float, list[str]]:
        try:
            return _coverage(tokens, _hwp_text(dest))
        except Exception as exc:
            warnings.append(f"결과 .hwp 검증 실패(파일은 생성됨): {exc}")
            return 0.0, []

    def _convert(chosen: str) -> None:
        if chosen == "jar":
            _export_jar_route(src, dest, timeout=timeout)
            return
        if chosen == "direct":
            result = _run_com(src, dest, timeout=timeout)
        else:
            warnings.append(_HTML_LOSS_WARNING)
            result = _export_html_route(src, dest, timeout=timeout)
        if not result.get("opened"):
            raise HwpExportError(f"한글이 원본을 열지 못함: {result.get('error')}")
        if not (result.get("saved") and dest.exists()):
            raise HwpExportError(f"SaveAs(HWP) 실패: {result.get('error')}")

    if route != "auto":
        _convert(route)
        coverage, missing = _verify()
    else:
        ladder: list[str] = []
        if _java_available() and find_converter_jar() is not None:
            ladder.append("jar")
        try:
            ladder.append("direct" if hancom_opens_hwpx() else "html")
        except HwpExportError:
            pass  # no Hancom at all -- jar may still carry it
        if not ladder:
            raise HwpExportError(
                "사용할 수 있는 변환 경로가 없음: hwpConverter jar(Java)도, "
                "한글 COM도 찾지 못함"
            )
        coverage, missing, route = 0.0, [], ladder[-1]
        for i, chosen in enumerate(ladder):
            try:
                _convert(chosen)
            except DestLockedError:
                raise  # 대상 파일 잠김 — 어떤 경로로도 못 쓰므로 즉시 중단
            except HwpExportError as exc:
                if i == len(ladder) - 1:
                    raise
                warnings.append(f"{chosen} 경로 실패({exc}) — 다음 경로로 재시도.")
                continue
            coverage, missing = _verify()
            route = chosen
            if coverage >= 0.5:
                break
            if i < len(ladder) - 1:
                warnings.append(
                    f"{chosen} 변환 결과가 깨져서(보존율 {coverage:.0%}) "
                    "다음 경로로 재시도함."
                )

    if coverage < 0.9:
        warnings.append("텍스트 보존율이 90% 미만 — 결과물을 반드시 눈으로 대조할 것.")
    return ExportReport(dest=dest, route=route, coverage=coverage,
                        tokens_total=len(tokens), missing=missing,
                        warnings=warnings)
