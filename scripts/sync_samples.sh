#!/usr/bin/env bash
# README 에서 내려받는 견본을 예제 결과물로 갱신한다.
#
# out/ 은 예제가 매번 덮어쓰는 작업 공간이라 커밋하지 않는다. 대신 세 개만
# docs/samples/ 로 복사해서 커밋한다. 예제나 출력이 달라졌으면 이 스크립트를
# 돌리고 결과를 한글에서 한 번 열어 본 뒤 커밋할 것.
set -euo pipefail
cd "$(dirname "$0")/.."

python examples/build_research_report.py
python examples/build_comparison_report.py
python examples/fill_form.py

mkdir -p docs/samples
for f in research_report comparison_report startup_plan_filled; do
    cp "out/$f.hwpx" "docs/samples/$f.hwpx"
    echo "  갱신: docs/samples/$f.hwpx"
done

echo
echo "한글에서 세 파일을 열어 확인한 뒤 커밋할 것."
