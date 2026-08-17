"""HWPX 미리보기 내보내기 CLI — 자체 조판 엔진(hwpxkit.preview) 사용.

    python scripts/render_png.py <file.hwpx> [out.png|out.pdf|out.html]

부가 설치가 필요 없다 (PNG/PDF 는 로컬 Chrome headless 실행).
출력 경로를 생략하면 <file>_preview.png 를 만든다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hwpxkit import lint, render_html, render_pdf, render_png


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 1
    src = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else src.with_name(src.stem + "_preview.png")
    if out.suffix == ".html":
        info = render_html(src, out)
    elif out.suffix == ".pdf":
        info = render_pdf(src, out)
    else:
        info = render_png(src, out)
    print(f"{info['pages']}쪽 -> {out}")
    for w in lint(src):
        print(f"  린트: {w}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
