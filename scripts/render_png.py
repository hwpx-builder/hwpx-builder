"""Render HWPX pages to PNG for visual inspection.

    python scripts/render_png.py <file.hwpx> [out_dir] [--pages 0,1] [--scale 1.4]

Requires the optional preview extra (``pip install 'hwpxkit[preview]'``), which
pulls in the PolyForm-Noncommercial ``pyhwpxlib``. The rendering itself lives in
:mod:`hwpxkit.render`; this script is only a command line around it.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hwpxkit.render import RendererUnavailable, render_pages


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    src = argv[0]
    out_dir = argv[1] if len(argv) > 1 and not argv[1].startswith("--") else "render"
    pages = None
    scale = 1.4
    for arg in argv:
        if arg.startswith("--pages"):
            pages = [int(x) for x in arg.split("=", 1)[1].split(",")]
        elif arg.startswith("--scale"):
            scale = float(arg.split("=", 1)[1])
    try:
        render_pages(src, out_dir, pages, scale)
    except RendererUnavailable as exc:
        print(exc)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
