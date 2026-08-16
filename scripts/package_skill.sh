#!/usr/bin/env bash
# 스킬을 단일 배포 파일 dist/hwpx-builder.skill 로 패키징한다.
#
# .skill 파일은 SKILL.md 가 아카이브 루트에 오는 zip 이다. 스킬을 지원하는
# 에이전트 환경에 파일 하나로 설치할 수 있다 (zip 으로 풀어도 동일).
# 포함: 스킬 본문 + 코드 + 실측 지식 + 예제 + 변환기 패치.
# 제외: 견본 산출물(docs/), 작업 폴더(out/), 가상환경, git, 캐시.
#
#   PYTHON=.venv/Scripts/python.exe scripts/package_skill.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
    for c in python python3 py; do
        command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }
    done
fi
[ -n "$PY" ] || { echo "파이썬을 찾지 못했다. PYTHON=... 으로 지정할 것." >&2; exit 1; }

"$PY" - <<'PYEOF'
import zipfile
from pathlib import Path

ROOT = Path(".")
OUT = ROOT / "dist" / "hwpx-builder.skill"
OUT.parent.mkdir(exist_ok=True)

FILES = ["SKILL.md", "AGENTS.md", "LICENSE", "NOTICE", "LICENSING.md",
         "pyproject.toml", "README.md", "CONTRIBUTING.md"]
DIRS = ["hwpxkit", "references", "scripts", "examples", "patches"]
SKIP_PARTS = {"__pycache__", ".venv", ".git", "out", "dist"}

with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
    for f in FILES:
        p = ROOT / f
        if p.exists():
            z.write(p, f)
    for d in DIRS:
        base = ROOT / d
        if not base.is_dir():
            continue
        for p in sorted(base.rglob("*")):
            if p.is_dir() or SKIP_PARTS & set(p.parts):
                continue
            z.write(p, p.as_posix())

size = OUT.stat().st_size
print(f"packaged: {OUT} ({size/1024/1024:.1f} MB, {len(z.namelist())} files)")
PYEOF
