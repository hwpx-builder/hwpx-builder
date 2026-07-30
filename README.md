# hwpx-builder

**한글(HWPX)도 이제 Claude로 예쁘게.**

중첩된 표, 형광펜, 병합 셀, 이미지 — 한국 문서가 실제로 쓰는 서식을 다룹니다~
글고 무엇을 확인했고, **무엇을 확인하지 못했는지**까지 알려주는 검증 단계를 거쳐서 최종 결과물이 나옵니다!

[Claude Code](https://claude.com/claude-code) 스킬로 만들었지만, 파이썬 라이브러리로 단독 사용도 가능하니까 많은 사랑 부탁드립니다!!!!

SB,SR 드림 

<p align="center">
  <img alt="license" src="https://img.shields.io/badge/license-Apache--2.0%20%2F%20PolyForm--NC-blue">
  <img alt="python" src="https://img.shields.io/badge/python-3.9%2B-informational">
</p>

---

## 목차

- [이런 걸 만든다](#이런-걸-만든다)
- [빠르게 시작하기](#빠르게-시작하기)
- [세 가지 사용법](#세-가지-사용법)
- [분석 틀 템플릿](#분석-틀-템플릿)
- [검증](#검증--못-한-것은-못-했다고-한다)
- [구식 .hwp 변환](#구식-hwp-변환)
- [라이선스](#라이선스)
- [이 도구의 범위](#이-도구의-범위)
- [예제](#예제)

---

## 이런 걸 만든다

아래는 전부 [`examples/`](examples/)의 스크립트가 만든 결과물이다. 한글에서
손으로 고친 부분은 없다.

| 연구 보고서 | 비교 보고서 |
|:---:|:---:|
| <img width="707" height="667" alt="image" src="https://github.com/user-attachments/assets/836713e7-3ccf-4173-9e15-741effc02819" />
| <img width="770" height="637" alt="image" src="https://github.com/user-attachments/assets/25dccef6-eba7-4b28-bebf-d5c1af548aec" />
 |
| `examples/build_research_report.py` | `examples/build_comparison_report.py` |

회색 라벨 행이 있는 박스, 중첩 표, 한/영 병기 제목, `□ · ❶ ▪ ※` 마커, 굵게와
형광펜 — 전부 정해진 몇 개의 함수로 만들며, **XML은 직접 쓰지 않는다.**

### 결과물 직접 열어보기

진짜 파일 여기서 한글로 열어볼 수 있어요. 아래 세 개는 위 예제
스크립트가 만든 결과물을 그대로 썼어요!

| 내려받기 | 내용 | 만든 스크립트 |
|---|---|---|
| [**연구 보고서**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/research_report.hwpx) | 표 6개 + 그림 2장, 5쪽 | `examples/build_research_report.py` |
| [**비교 보고서**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/comparison_report.hwpx) | 사진 2장, 중첩 표 | `examples/build_comparison_report.py` |
| [**채운 사업계획서 양식**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/startup_plan_filled.hwpx) | 배포된 `.hwp` 양식을 변환해서 채운 것 | `examples/fill_form.py` |

세 파일 모두 내용은 가상이다. 직접 다시 만들려면 [예제](#예제)를 돌리면 됩니다~

---

## 빠르게 시작하기

### 1. 설치

> **윈도우 PowerShell 사용 시:** 아래 각 줄은 한 줄로 실행해야 한다. 중간에
> 줄바꿈 문자를 넣지 말 것.

```powershell
git clone --depth 1 https://github.com/hwpx-builder/hwpx-builder.git .claude/skills/hwpx-builder
Remove-Item -Recurse -Force .claude\skills\hwpx-builder\.git

pip install ".\.claude\skills\hwpx-builder"             # 기본
pip install ".\.claude\skills\hwpx-builder[preview]"    # + PNG 미리보기
pip install ".\.claude\skills\hwpx-builder[hwp]"        # + 구식 .hwp 변환
```

**macOS / Linux / Git Bash:**

```bash
git clone --depth 1 https://github.com/hwpx-builder/hwpx-builder.git \
  .claude/skills/hwpx-builder
rm -rf .claude/skills/hwpx-builder/.git

pip install ./.claude/skills/hwpx-builder
```

모든 프로젝트에서 공용으로 쓰려면 `~/.claude/skills/hwpx-builder`
(윈도우는 `$HOME\.claude\skills\hwpx-builder`)에 내려받고 그 경로로 설치한다.

> **`.git`을 먼저 지워야 한다.** 이미 git 저장소인 프로젝트 안에 그대로 받으면
> 저장소가 중첩된다. git은 파일이 아니라 서브모듈 링크만 기록하기 때문에, 다른
> 사람이 그 프로젝트를 받으면 **빈 폴더**만 나오게 된다. `.git`을 지우면 평범한
> 파일 34개로 바뀐다. 이미 `git add`를 했다면
> `git rm --cached .claude/skills/hwpx-builder` 후 다시 추가하면 되고, 아예
> 커밋하고 싶지 않다면 `.gitignore`에 넣으면 된다.

> **`pip install hwpxkit`은 엉뚱한 패키지를 설치한다.** PyPI의 그 이름은 전혀
> 무관한 프로젝트([`Han-taz/hwpx-rust`](https://github.com/Han-taz/hwpx-rust))가
> 쓰고 있다. 반드시 위 경로로 설치할 것.

### 2. 확인

```bash
python -c "import hwpxkit; print(hwpxkit.__file__)"
python examples/build_research_report.py
```

---

## 세 가지 사용법

### ① 새로 만들기

```python
from hwpx.document import HwpxDocument
from hwpxkit import BoxDoc, Grid, verify

doc = HwpxDocument.new()
b = BoxDoc(doc)

b.title("펭귄 3종의 형태 측정값을 이용한 종 판별")
b.section_heading("0. 결론 요약 / Headline Finding")
b.container_box([
    ("□ 결론 / Conclusion", [
        "측정값 하나로는 **불가능하다.** 부리 두 값을 조합하면 ==93.0%==를 맞춘다.",
        Grid(headers=["측정값", "아델리", "턱끈", "젠투"],
             rows=[["부리 길이 (mm)", "38.8 ± 2.7", "48.8 ± 3.3", "47.5 ± 3.1"]],
             ratios=(0.28, 0.24, 0.24, 0.24)),
    ]),
])
doc.save_to_path("out.hwpx")
print(verify("out.hwpx").render())
```

글 안에서 `**굵게**`, `==형광펜==`을 바로 쓸 수 있다.

| 함수 | 만들어지는 것 |
|---|---|
| `b.title(...)` / `b.section_heading(...)` | 제목, 절 제목 |
| `b.label_value_box([(라벨, 값), ...])` | 2열. 왼쪽 라벨, 오른쪽 값 |
| `b.container_box([(라벨, [내용...]), ...])` | 회색 라벨 행 + 내용 행 (가장 많이 쓴다) |
| `Grid(headers, rows, ratios)` | 내용 안에 중첩되는 표 |
| `b.picture(경로)` / `b.image_placeholder(설명)` | 이미지 |

### ② 배포된 양식 채우기

받은 `.hwp` 양식을 변환한 뒤 칸을 채운다.

```python
from hwpxkit import open_any, clear_guidance, find_label, set_cell, fill_cell

doc = open_any("양식.hwp")               # .hwp면 변환, .hwpx면 그냥 열기
clear_guidance(doc)                      # "제출 시 삭제" 안내문(※) 제거

팀명 = find_label(doc, "팀명", direction="right")
set_cell(doc, 팀명.cell, "벳츄원", flatten=True)

전략 = find_label(doc, "사업화 전략", direction="below")
fill_cell(doc, 전략.cell, [               # 글줄과 표를 섞어서 채운다
    "개발은 3단계로 나눈다.",
    Grid(headers=["단계", "기간", "내용"], rows=[["1단계", "3개월", "..."]]),
], flatten=True)
```

**칸은 표 번호가 아니라 라벨 문구로 찾는다.** 양식이 개정되어 표 순서가 바뀌어도
라벨만 같으면 코드가 그대로 동작한다.

`flatten=True`는 양식이 갖고 있던 왼쪽 여백을 없앤다. 지정하지 않으면 넣은 글이
전부 오른쪽으로 밀려 보인다(자세한 내용은
[`references/gotchas.md`](references/gotchas.md) 참고).

전체 예제: [`examples/fill_form.py`](examples/fill_form.py)

### ③ 이미 있는 문서 고치기

```python
from hwpxkit import find_label, set_cell, replace_text, verify

doc = HwpxDocument.open("문서.hwpx")
칸 = find_label(doc, "팀명", direction="right")
set_cell(doc, 칸.cell, "새 이름")          # 원래 크기와 글꼴을 유지한다
print(replace_text(doc, "2025", "2026").render())
doc.save_to_path("수정본.hwpx")

print(verify("수정본.hwpx", baseline="문서.hwpx").render())
```

셀 360개짜리 실제 문서로 검증해 보면, `python-hwpx`의 `replace_text_in_runs`는
찾는 단어 7건 중 **0건**을 바꿨다(전부 표 안에 있었고, 그중 2건은 형광펜에
가려져 있었다). `hwpxkit`은 7건 전부를 바꾼다.

---

## 분석 틀 템플릿

사업계획서에 반복해서 나오는 틀은 그대로 가져다 쓰면 된다.

```python
from hwpxkit import tam_sam_som, swot, business_model_canvas

b.container_box([("□ 목표시장 분석", [
    "시장 규모는 아래와 같이 추정했다.",
    tam_sam_som(
        tam=("국내 4년제 대학 전체", "약 190개교", "대학알리미 공시"),
        sam=("재학생 1만 명 이상", "약 90개교", "같은 공시에서 필터"),
        som=("수도권 우선 도입", "12개교", "3년 내 목표"),
    ),
])])
```

| 함수 | 내용 |
|---|---|
| `tam_sam_som` | 시장 규모 3단계 |
| `swot` | 2×2 SWOT |
| `business_model_canvas` | BMC 9칸 |
| `milestones` | 추진 일정 |
| `budget` | 사업비 |
| `competitor_matrix` | 경쟁사 비교 |

원칙은 두 가지다. **근거 칸을 반드시 만든다** — 숫자만 있고 출처가 없는 표가
심사에서 가장 먼저 지적받는다. 그리고 **합계를 대신 계산하지 않는다** — 자동
계산은 틀렸을 때 조용히 틀리고, 제출 서류에서 그것은 가장 나쁜 실패다.

---

## 검증 — 못 한 것은 못 했다고 한다

한글 문서를 그대로 믿고 맡길 만한 렌더러가 없다. 그래서 초록불 하나만 띄우는
대신, 항목마다 확인 여부를 명확히 밝힌다.

```
  OK  zip integrity
  OK  markpen pairing: 31 begin / 31 end
  OK  binary refs: 6 ref(s)
  OK  cell overflow: no unbreakable overflow
  OK  layout cache invalidated: all edited paragraphs re-flow
  ~   highlight renders: NOT VERIFIED (렌더러가 형광펜을 아예 무시한다)
  ~   line breaking / page count: NOT VERIFIED (새 파일에는 줄 캐시가 없다)
  ~   Hancom COM oracle: NOT VERIFIED (한글 2014 이상 필요)
```

고칠 때 `baseline=원본`을 넘기면 편집에만 해당하는 검사가 추가된다: 낡은 줄
캐시를 남긴 문단, 실제로 건드린 칸의 개수, 형광펜 균형, 그리고 **넘친 칸이
원래 그랬는지 이번 편집으로 생긴 것인지** 구분까지.

> 마지막 항목이 특히 중요하다. 실제 배포 서식은 손대기 전부터 결함을 안고
> 오는 경우가 있다. 그걸 편집 탓으로 돌리면 사용자가 검사 결과 전체를
> 신뢰하지 않게 된다.

---

## 구식 `.hwp` 변환

```python
from hwpxkit import hwp_to_hwpx, open_any

hwp_to_hwpx("양식.hwp")        # -> 양식.hwpx
doc = open_any("양식.hwp")     # 변환해서 바로 열기
```

실제 정부 배포 양식으로 검증해 보면 한글이 저장한 것과 셀 24개로 개수가 같고
라벨 위치도 일치한다. 오히려 변환본이 구조 검사를 더 잘 통과한다 — 한글은
`mimetype`을 ZIP 첫 자리에 넣지 않아 ODF 관례를 어기는 반면, 변환기는 이를
지키기 때문이다.

**변환은 단방향이다.** HWPX → HWP 변환은 지원하지 않는다. HWP 5.x는 OLE
바이너리라 쓰기가 읽기보다 훨씬 까다롭다. 그 방향이 필요하면 한글의 "다른
이름으로 저장" 기능을 쓰면 된다.

---

## 라이선스

기본 설치는 **Apache-2.0**이다. 호스팅하든, 팔든, 오픈소스로 공개하든 제약이
없다.

부가 설치 두 개는 **비상업**이다. 개인·학술 용도는 괜찮지만, 서비스로
띄우거나 상업 제품에 넣어서는 안 된다.

| | 기본 | `[preview]` / `[hwp]` |
|---|:---:|:---:|
| 문서 만들기 · 편집 · 구조 검사 | ✅ | ✅ |
| PNG 미리보기, 렌더 검사 | NOT VERIFIED로 표시 | ✅ |
| 구식 `.hwp` 변환 | 안내 후 종료 | ✅ |
| 호스팅 · 상업 이용 | ✅ | ❌ |

`hwpxkit/render.py`와 `hwpxkit/convert.py`만 제한 패키지를 import한다. 기본
설치에서는 `import hwpxkit`을 해도 그 모듈들이 **아예 로드되지 않는다.** 직접
확인해 볼 수 있다:

```bash
python -c "import hwpxkit, sys; print([m for m in sys.modules if 'pyhwpx' in m])"
# 기본 설치라면 [] 가 나온다
```

> **오해하기 쉬운 지점.** `pyhwpxlib` 안에서 변환을 담당하는 파일 3개는
> Apache-2.0이라 "변환 기능은 상업적으로 써도 되겠네"로 읽기 쉽다. 아니다.
> 변환을 한 번 돌리면 그 패키지의 모듈 **59개가 로드되고, 그중 56개가
> 비상업**이다. Apache 라이선스는 그 파일 3개의 소스에만 적용될 뿐, 실제로
> 동작하는 기능 전체에는 적용되지 않는다.

자세한 내용은 [`NOTICE`](NOTICE) 참고.

---

## 이 도구의 범위

박스형 문서 어휘는 서로 무관한 정부 배포 사업계획서 **두 건을 실측**해서
뽑았다(최상위 표 5개, 내용은 한 단계 중첩, 최대 깊이 2). 다만 그 장르에 묶이지는
않는다. 같은 함수로 연구 보고서와 비교 보고서도 만들며([`examples/`](examples/)),
편집 기능은 열리는 모든 HWPX에서 동작한다.

**하지 않는 것:** 임의의 HWPX를 자유롭게 만드는 것. 연산 어휘를 일부러 작게
유지한다. 함수 하나하나가 디버깅 한 사이클씩 치르고 얻은 함정을 담고 있기
때문이다. 그 목록이 [`references/gotchas.md`](references/gotchas.md)이며, 이것이
이 프로젝트의 실질적인 자산이다.

---

## 예제

```bash
python examples/build_comparison_report.py    # 사진 2장, 한 줄 지시   (간단)
python examples/fill_form.py                  # .hwp 양식 채우기       (중간)
python examples/build_research_report.py      # 표 6개 + 그림 2장, 5쪽 (큰 문서)
python examples/edit_existing.py              # 만든 문서를 다시 편집
```

각 예제 맨 앞에는 **그 문서를 만들 때 Claude에게 준 지시**가 적혀 있다. 스킬로
쓸 때 그대로 복사해서 쓰면 된다.

## 문서

- [`SKILL.md`](SKILL.md) — 실제 작업 지침. 박스 어휘, 편집, 지켜야 할 규칙
- [`references/gotchas.md`](references/gotchas.md) — 함정 목록.
  ✅ 확인함 / 📋 소스 분석 / ⚠️ 여기서는 확인 불가

## 기반

문서 모델은 [`python-hwpx`](https://github.com/airmang/python-hwpx)
(Apache-2.0)를 사용한다. 미리보기는 [`rhwp`](https://github.com/edwardkim/rhwp)
(MIT)를 [`pyhwpxlib`](https://github.com/ratiertm/hwpx-skill)
(PolyForm Noncommercial)를 통해 쓴다. 전체 출처는 [`NOTICE`](NOTICE) 참고.
