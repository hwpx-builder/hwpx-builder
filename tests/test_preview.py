# -*- coding: utf-8 -*-
"""preview 조판 엔진 회귀 테스트.

기준값은 최초 검수 시점의 조판 결과다. 쪽수는 ±1 허용 — 산술 조판이라
한글의 정밀 조판과 항상 같을 수는 없고, 보수적 +1은 결함이 아니다.
그 이상 벗어나거나 경고 수가 달라지면 회귀다.

실행:  PYTHON=.venv/Scripts/python.exe python tests/test_preview.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hwpxkit import analyze_gaps, render_html  # noqa: E402

#: (파일, 기대 쪽수, 기대 경고 수, 기대 임계초과 공백 수)
CASES = [
    ("docs/samples/research_report.hwpx", 5, 0, 0),
    ("docs/samples/comparison_report.hwpx", 4, 0, 0),
    ("docs/samples/startup_plan_filled.hwpx", 4, 0, 0),
]


def main() -> int:
    failed = 0
    for rel, pages, warns, gaps in CASES:
        f = ROOT / rel
        try:
            r = render_html(f, out=None)
            g = analyze_gaps(f)
        except Exception as e:
            print(f"FAIL {rel}: {type(e).__name__}: {e}")
            failed += 1
            continue
        over = [b for b in g.blocks if b.gap_before > 0.12 * g.body_height]
        ok = (abs(r["pages"] - pages) <= 1
              and len(r["warnings"]) == warns and len(over) == gaps)
        print(f"{'OK  ' if ok else 'FAIL'} {rel}: {r['pages']}쪽(기준 {pages}) "
              f"경고 {len(r['warnings'])}(기대 {warns}) 임계공백 {len(over)}(기대 {gaps})")
        if not ok:
            failed += 1
    print("\n" + ("전부 통과" if not failed else f"{failed}건 실패"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
