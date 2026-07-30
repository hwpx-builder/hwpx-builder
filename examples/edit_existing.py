"""기존 HWPX 편집: 라벨 칸 채우기, 문구 치환, 형광펜 추가.

    python examples/build_comparison_report.py   # out/comparison_report.hwpx 생성
    python examples/edit_existing.py             # 그 문서를 편집 -> out/..._edited.hwpx

자기 파일을 지정할 수도 있다:

    python examples/edit_existing.py path/to/in.hwpx path/to/out.hwpx

이 문서를 편집할 때 Claude 에게 준 지시:

    이 보고서에서 비교 대상을 햄스터로 바꿔줘. 강아지 나오는 데 다 바꾸고,
    수직 동선 부분은 형광펜 쳐줘.

개별 호출보다 루프의 모양이 더 중요하다:

1. 파일을 열고 *내용으로 위치를 찾는다*. 절대 인덱스로 찾지 않는다.
   ``charPrIDRef`` 와 표 순서는 문서마다 다르고, 두 번 편집한 서식은 첫 번째와
   같은 파일이 아니다.
2. :mod:`hwpxkit.edit` 를 통해 편집한다. 건드린 문단의 레이아웃 캐시를 정확히
   그만큼만 무효화해 준다.
3. **원본과 대조해서** 검증한다. 낡은 캐시나 의도보다 멀리 간 편집이 한글에서
   놀라는 대신 실패한 검사로 드러난다.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hwpx.document import HwpxDocument

from hwpxkit import (find_cells, find_label, has_merged_cells, highlight_cell,
                     refit_cell, replace_text, set_cell, verify)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SRC = ROOT / "out" / "comparison_report.hwpx"
DEFAULT_DEST = ROOT / "out" / "comparison_report_edited.hwpx"


def main(src: str, dest: str) -> int:
    if not Path(src).exists():
        print(f"missing source: {src}\n"
              f"run `python examples/build_comparison_report.py` first, "
              f"or pass your own file as an argument.")
        return 2

    doc = HwpxDocument.open(src)

    # 1. Fill a labelled field. find_label walks nested cells, which is why it
    #    finds labels where the library's own find_cell_by_label returns none.
    field = find_label(doc, "비교 대상", direction="right")
    if field is None:
        print("no 비교 대상 field -- not filling one rather than guessing at a cell")
    else:
        print(f"비교 대상 at {field.path}: {field.text.strip()[:40]!r}")
        warnings = refit_cell(field)         # check fit *before* the cache goes
        set_cell(doc, field.cell, "햄스터(Mesocricetus auratus)와 고양이(Felis catus).")
        for w in warnings:
            print(w)

    # 2. Replace a phrase everywhere -- cells and markpen tails included.
    print(replace_text(doc, "강아지", "햄스터").render())

    # 3. Highlight an existing phrase with a real markpen (not cell shading).
    for ref in find_cells(doc, "수직 동선")[:1]:
        n = highlight_cell(doc, ref.cell, "수직 동선")
        print(f"highlighted {n} occurrence(s) in {ref.path}"
              f" (merged table: {has_merged_cells(ref.table)})")

    Path(dest).parent.mkdir(parents=True, exist_ok=True)
    doc.save_to_path(dest)
    print(f"saved: {dest}")

    # 4. Verify against the file we started from. Without `baseline` the stale
    #    layout cache check cannot run -- it needs the before-and-after pair.
    report = verify(dest, baseline=src, render=False)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    args = sys.argv[1:]
    if len(args) not in (0, 2):
        print(__doc__)
        raise SystemExit(2)
    raise SystemExit(main(*(args or (str(DEFAULT_SRC), str(DEFAULT_DEST)))))
