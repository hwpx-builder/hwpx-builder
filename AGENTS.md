# hwpx-builder — AI 에이전트 지침

이 저장소는 한글(HWPX) 문서를 만들고·고치고·검증하는 파이썬 도구 `hwpxkit` 이다.
**정본 지침은 [SKILL.md](SKILL.md)** 이고, 이 파일은 어느 에이전트에서든 같은
내용을 찾아가게 하는 어댑터다. 문서 작업을 시작하기 전에 SKILL.md 를 먼저 읽고,
디버깅 중에는 [references/gotchas.md](references/gotchas.md) 를 참조하라 — 항목
하나하나가 실제 디버깅 사이클을 소모하고 얻은 실측 지식이다.

## 준비

```bash
pip install .            # core: 작성·편집·구조 검증 (Apache-2.0, 제약 없음)
pip install ".[hwp]"     # + 구식 .hwp 변환 (NONCOMMERCIAL — NOTICE 참조)
pip install ".[preview]" # + PNG 미리보기 (NONCOMMERCIAL + AGPL — 호스팅 금지)
pip install ".[images]"  # + Pillow. 사진을 넣는다면 사실상 필수 —
                         #   없으면 모든 사진이 조용히 4:3 으로 왜곡된다
```

## 핵심 API 한 장

```python
from hwpx.document import HwpxDocument
from hwpxkit import BoxDoc, Grid, fit_pictures, to_hwp, verify

doc = HwpxDocument.new()
b = BoxDoc(doc)
b.title("제목")
b.section_heading("1. 절 제목")
b.container_box([("라벨", ["내용 줄", Grid(headers=[...], rows=[...])])])
b.content_table(["열1", "열2"], rows, repeat_header=True)  # 긴 표: 제목 줄 반복
b.picture("사진.jpg", width_mm=100)
doc.save_to_path("문서.hwpx")

fit_pictures("문서.hwpx")            # 사진 밀림 공백 검사·축소 (비교 계열은 함께)
print(verify("문서.hwpx").render())  # 저장 후 반드시. NOT VERIFIED 는 통과가 아니다
to_hwp("문서.hwpx")                  # 구버전 한글용 .hwp 내보내기 (SKILL.md 참조)
```

기존 문서 편집은 `hwpxkit.edit` 의 `find_label / set_cell / replace_text /
highlight_cell` 을 쓴다 — 원 라이브러리의 문단 단위 API 는 표 셀에 닿지 않는다.

## 어기면 안 되는 규칙 (요약 — 전문은 SKILL.md)

1. `<hp:...>` XML 을 손으로 쓰지 마라. 빌더가 함정을 하나씩 안고 있다.
2. 형광펜은 markpen 이다. `shadeColor` 는 음영이라 다른 것이다 (`==텍스트==` 사용).
3. 다른 문서의 `charPrIDRef` 등 ID 를 하드코딩하지 마라 — 문서마다 재번호된다.
4. 없는 이미지를 지어내지 마라. `image_placeholder()` 로 자리를 비워 둬라.
5. 저장 후 `verify()` 를 돌리고, NOT VERIFIED 항목을 통과로 읽지 마라.
6. 편집 시: 손댄 문단의 레이아웃 캐시만 지워라 (`hwpxkit.edit` 가 해 준다).
7. 직접 만들지 않은 표에 `autofit()` 을 돌리지 마라 (병합 셀에서 깨진다).
8. python-hwpx 요소를 직접 변형했다면 `section.mark_dirty()` — 패치 저장이라
   표시 없는 변경은 조용히 버려진다.

## 자주 하는 작업 → 진입점

| 작업 | 위치 |
|---|---|
| 새 보고서/사업계획서 작성 | `examples/build_research_report.py`, `build_comparison_report.py` |
| 배포 양식(.hwp) 채우기 | `examples/fill_form.py` |
| 견본 재생성 (hwpx+hwp) | `scripts/sync_samples.sh` |
| HWPX→HWP 변환기(jar) 패치 | `patches/hwpconverter-fixes.patch` (SKILL.md 내보내기 절) |
