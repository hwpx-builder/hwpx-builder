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
- [미리보기 · PNG · PDF](#미리보기--png--pdf)
- [사진 공백 자동 조정](#사진-공백-자동-조정)
- [검증](#검증--못-한-것은-못-했다고-한다)
- [문장 검토 — AI 티 빼기](#문장-검토--ai-티-빼기)
- [구식 .hwp 변환](#구식-hwp-변환)
- [라이선스](#라이선스)
- [이 도구의 범위](#이-도구의-범위)
- [예제](#예제)
- [다른 AI 에이전트에서 쓰기](#다른-ai-에이전트에서-쓰기)

---

## 이런 걸 만든다

아래는 전부 [`examples/`](examples/)의 스크립트가 만든 결과물이다. 한글에서
손으로 고친 부분은 없다.

| 연구 보고서 | 비교 보고서 |
|:---:|:---:|
| <img width="380" alt="image" src="https://github.com/user-attachments/assets/836713e7-3ccf-4173-9e15-741effc02819" /> | <img width="380" alt="image" src="https://github.com/user-attachments/assets/25dccef6-eba7-4b28-bebf-d5c1af548aec" /> |
| `examples/build_research_report.py` | `examples/build_comparison_report.py` |

회색 라벨 행이 있는 박스, 중첩 표, 한/영 병기 제목, `□ · ❶ ▪ ※` 마커, 굵게와
형광펜 — 전부 정해진 몇 개의 함수로 만들며, **XML은 직접 쓰지 않는다.**

### 결과물 직접 열어보기

진짜 파일 여기서 한글로 열어볼 수 있어요. 아래 세 개는 위 예제
스크립트가 만든 결과물을 그대로 썼어요!

| 내려받기 | 구버전 한글용 | 내용 | 만든 스크립트 |
|---|---|---|---|
| [**연구 보고서**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/research_report.hwpx) | [.hwp](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/research_report.hwp) | 표 6개 + 그림 2장, 5쪽 | `examples/build_research_report.py` |
| [**비교 보고서**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/comparison_report.hwpx) | [.hwp](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/comparison_report.hwp) | 사진 2장, 중첩 표 | `examples/build_comparison_report.py` |
| [**채운 사업계획서 양식**](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/startup_plan_filled.hwpx) | [.hwp](https://github.com/hwpx-builder/hwpx-builder/raw/main/docs/samples/startup_plan_filled.hwp) | 배포된 `.hwp` 양식을 변환해서 채운 것 | `examples/fill_form.py` |

세 파일 모두 내용은 가상이다. `.hwp` 열은 같은 문서를 `to_hwp` 로 변환한
것으로, HWPX 를 못 여는 구버전 한글(2010 등)에서도 열린다. 표는 쪽 경계에서
셀 단위로 나뉘고 긴 표의 머리글 행은 다음 쪽에 반복된다 — 예전 견본에서 표가
통째로 다음 쪽에 밀리며 큰 공백이 남던 문제를 고친 결과다. 직접 다시 만들려면
[예제](#예제)를 돌리면 됩니다~

---

## 빠르게 시작하기

### 1. 설치

> **윈도우 PowerShell 사용 시:** 아래 각 줄은 한 줄로 실행해야 한다. 중간에
> 줄바꿈 문자를 넣지 말 것.

```powershell
git clone --depth 1 https://github.com/hwpx-builder/hwpx-builder.git .claude/skills/hwpx-builder
Remove-Item -Recurse -Force .claude\skills\hwpx-builder\.git

pip install ".\.claude\skills\hwpx-builder"             # 기본
pip install ".\.claude\skills\hwpx-builder[hwp]"        # + 구식 .hwp 변환
```

**macOS / Linux / Git Bash:**

```bash
git clone --depth 1 https://github.com/hwpx-builder/hwpx-builder.git \
  .claude/skills/hwpx-builder
rm -rf .claude/skills/hwpx-builder/.git

pip install ./.claude/skills/hwpx-builder             # 기본
pip install "./.claude/skills/hwpx-builder[hwp]"      # + 구식 .hwp 변환
```

> 대괄호가 들어간 경로는 **따옴표로 감싸야 한다.** 셸이 `[hwp]`를 파일명
> 패턴으로 해석하기 때문이다. zsh(맥 기본 셸)는 `no matches found`로 바로
> 실패하고, bash는 대개 그냥 넘어가지만 옆에 우연히 맞는 파일명이 있으면 경로를
> 말없이 바꿔 버린다. 따옴표를 붙이면 둘 다 해결된다.

**부가 설치 두 개는 맥과 리눅스에서도 쓸 수 있다.** 미리보기와 `.hwp` 변환에
한글(HWP 프로그램)이 필요하지 않기 때문이다 — 렌더링은 WASM으로, 변환은 순수
파이썬으로 돌아간다. 네 패키지 모두 macOS(인텔·애플 실리콘)와
Linux(x86_64·aarch64·musl) 휠을 낸다.

윈도우에서만 되는 것은 검증 항목 하나뿐이다. 한글 COM으로 픽셀 단위를 대조하는
검사인데, 이건 애초에 한글 2014 이상이 깔린 윈도우에서만 켜지고 그 외에는
`NOT VERIFIED`로 표시된다. 나머지 검사는 어느 운영체제에서나 동일하게 돌아간다.

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

## 미리보기 · PNG · PDF

한글 없이 문서를 **직접 조판해서** 보여준다. 기존 rhwp 렌더러는 문서에
저장된 레이아웃 캐시를 재생할 뿐이라 갓 만든 문서(캐시 없음)는 쪽수도
줄바꿈도 엉터리였다 — 이 엔진은 반대로 캐시를 무시하고 조판한다. 표는 행
경계에서 실제로 나뉘고(제목 줄 반복 포함), 형광펜이 실제로 그려지며, 사진이
밀리면 그 공백이 그대로 보인다. 실측 대조: 쪽수가 한글과 정확히 같거나
보수적으로 +1.

```python
from hwpxkit import render_html, render_png, render_pdf, lint

render_html("보고서.hwpx", "미리보기.html")  # 자립 HTML — 더블클릭으로 열람
render_png("보고서.hwpx", "미리보기.png")    # 세로 연속 PNG
render_pdf("보고서.hwpx", "보고서.pdf")      # 벡터 PDF (실제 용지 크기)
print(lint("보고서.hwpx"))                   # 여백 침범·사진 밀림 공백·빈 쪽
```

표준 라이브러리 + Apache-2.0 재료만 쓴다. PNG/PDF 는 로컬 Chrome(headless)을
실행할 뿐 아무것도 링크하지 않는다. 문서당 0.02~0.3초라 저장할 때마다 돌려도
된다. `verify()` 의 렌더 검사도 이 엔진이 맡는다 — 예전에 NOT VERIFIED 로
남던 쪽수·형광펜 렌더가 실제 검사로 바뀌었다.

## 사진 공백 자동 조정

사진은 표와 달리 쪽 경계에서 나뉠 수 없다. 남은 공간보다 큰 사진은 통째로
다음 쪽으로 밀리고, 이전 쪽 하단에 큰 공백이 남는다 — 심사자가 가장 싫어하는
모양이다. `fit_pictures` 가 렌더러 없이 배치를 산술로 추정해서, 임계치(기본
본문 높이의 12%)를 넘는 공백을 만드는 사진만 남은 공간에 맞게 비율 유지로
축소한다.

```python
from hwpxkit import analyze_gaps, fit_pictures

print(analyze_gaps("보고서.hwpx").render())   # 공백 진단만
report = fit_pictures("보고서.hwpx")          # 조정까지 (제자리 저장)
print(f"축소한 사진 {report.adjusted}장")
```

나란히 비교하라고 넣은 사진들(원래 폭이 같은 사진들)은 **그룹으로 묶어 항상
같은 배율로 함께** 줄인다 — 한 장만 줄이면 비교 사진의 크기가 어긋나 공백보다
더 이상해 보인다. 안전장치 두 가지: 그룹이 원래 크기의 55% 아래로 내려가야
해결되는 경우에는 아무도 줄이지 않고 보고만 하고(너무 작아진 사진은 공백보다
나쁘다), 표시 크기만 바꾸고 원본 크기 정보(orgSz/imgDim/imgClip)는 건드리지
않는다. 예제 빌드 스크립트 두 개는 이 단계를 기본으로 거친다.

---

## 검증 — 못 한 것은 못 했다고 한다

한글 문서를 그대로 믿고 맡길 만한 렌더러가 없다. 그래서 초록불 하나만 띄우는
대신, 항목마다 확인 여부를 명확히 밝힌다.

```
  OK  zip integrity
  OK  markpen pairing: 31 begin / 31 end
  OK  binary refs: 6 ref(s)
  OK  cell overflow: no unbreakable overflow
  OK  korean word wrap: 어절 단위 (KEEP_WORD 20/20 paraPr)
  OK  layout cache invalidated: all edited paragraphs re-flow
  ~   highlight renders: NOT VERIFIED (렌더러가 형광펜을 아예 무시한다)
  ~   line breaking / page count: NOT VERIFIED (새 파일에는 줄 캐시가 없다)
  ~   Hancom COM oracle: NOT VERIFIED (한글 2014 이상 필요)
  FAIL prose review: 19 block(s): FIX 3, note 2 (no-highlight 2, cliche 1) — python -m hwpxkit.prose <file> 로 목록 확인
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

**반대 방향(HWPX → HWP)은 `to_hwp` 가 맡는다.** 받는 쪽이 HWPX 를 못 여는
구버전 한글(2010 등)을 쓸 때를 위한 것이다.

```python
from hwpxkit import to_hwp

print(to_hwp("사업계획서.hwpx").render())   # -> 사업계획서.hwp + 검증 리포트
```

경로는 셋을 순서대로 시도한다: ① [vsdn/hwpConverter](https://github.com/vsdn/hwpConverter)
jar (Apache-2.0, Java 8+ — 한글 불필요, 표·이미지·형광펜을 실개체로 보존.
`patches/hwpconverter-fixes.patch` 를 적용해 빌드하고 `HWPCONVERTER_HOME`
으로 알려준다) ② 한글 2014+ COM `SaveAs` ③ 한글 2010 COM + CP949 HTML
(최후 수단 — 레이아웃이 많이 깨진다). 변환마다 결과 .hwp 를 다시 읽어 텍스트
토큰 보존율을 보고하며, 100% 미만은 의심하고 열어 봐야 한다.

---

## 문장 검토 — AI 티 빼기

구조는 검사로 잡히지만 문장은 아니다. 그리고 심사자가 읽는 건 문장이다.
`hwpxkit.prose` 가 기계로 잡히는 것 — 상투어(다양한·효과적으로·이를 통해),
숫자 없는 주장, 빠져나가는 어미(기대된다), "A, B, C 등", 그리고 **강조가 없어서
어디를 읽어야 할지 모르는 칸** — 을 잡고, `verify()` 의 `prose review` 줄이
FIX 가 남아 있으면 빨간불을 낸다. 나머지는 사람이 다시 읽는다.

```python
from hwpxkit import review_blocks, BoxDoc

for f in review_blocks(content):     # 만들기 전에, 내용 구조 그대로
    print(f)                          # FIX [1. 문제/배경] cliche: '다양한' — 무엇이 몇 가지인지 쓴다
b = BoxDoc(doc, bold_figures=True)    # 본문 숫자는 자동으로 굵게
```

```bash
python -m hwpxkit.prose out.hwpx          # 칸별 지적 목록
python -m hwpxkit.prose out.hwpx --dump   # 다시 읽기용 평문 (강조 마크업 포함)
```

굵게와 형광펜은 후하게 쓴다. 심사자는 굵은 글자와 형광펜을 먼저 훑고 관심이
가는 칸만 읽는다. 숫자·고유명사·문단의 핵심은 굵게, 칸마다 기억해야 할 한 문장은
형광펜. 없어도 걸리고 절반을 넘어도 걸린다. 절차와 문체 표는
[`references/writing.md`](references/writing.md).

한글 줄 나눔도 여기서 바로잡았다. 새 문서는 한/글 기본값인 글자 단위라 좁은
칸에서 "실 / 험"처럼 갈라지고, 폴라리스 오피스처럼 글꼴이 다른 뷰어에서는 더
어색하게 갈라진다. 이제 `BoxDoc` 이 **어절 단위**(`KEEP_WORD`)로 만들고 행
높이도 같은 기준으로 잰다. 양식을 채울 때는 `keep_korean_words(doc)`.

---

## 라이선스

기본 설치는 **Apache-2.0**이다. 호스팅하든, 팔든, 오픈소스로 공개하든 제약이
없다.

부가 설치 두 개는 **비상업**이다. 개인·학술 용도는 괜찮지만, 서비스로
띄우거나 상업 제품에 넣어서는 안 된다.

| | 기본 | `[hwp]` |
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

## 다른 AI 에이전트에서 쓰기

이 저장소는 Claude Code 스킬로 시작했지만, 지침은 에이전트 중립적으로 두었다.

- **Claude Code** — 저장소를 열면 `.claude/skills/hwpx-builder/` 를 스킬로
  읽는다 (`scripts/sync_skill.sh` 로 갱신).
- **GPT(Codex) · Gemini · Grok · Laguna · Solar** — 에이전트 표준인
  [AGENTS.md](AGENTS.md) 에 준비·핵심 API·규칙 요약이 있고,
  `GEMINI.md` / `GROK.md` / `LAGUNA.md` / `SOLAR.md` 는 각 플랫폼이 자기
  이름의 파일을 찾을 때를 위한 포인터다. 내용은 전부 AGENTS.md → SKILL.md
  한 곳으로 모인다 — 사본을 두면 처음 고칠 때 바로 어긋나기 때문이다.
- **`.skill` 단일 파일** — `scripts/package_skill.sh` 가
  `dist/hwpx-builder.skill` (SKILL.md 가 루트에 오는 zip, 약 1MB)을 만든다.
  스킬 업로드를 지원하는 환경에 파일 하나로 설치할 수 있고, zip 으로 풀면
  코드·예제·패치까지 그대로 나온다.

---

## 문서

- [`SKILL.md`](SKILL.md) — 실제 작업 지침. 박스 어휘, 편집, 지켜야 할 규칙
- [`references/gotchas.md`](references/gotchas.md) — 함정 목록.
  ✅ 확인함 / 📋 소스 분석 / ⚠️ 여기서는 확인 불가

## 기반

문서 모델은 [`python-hwpx`](https://github.com/airmang/python-hwpx)
(Apache-2.0)를 사용한다. 미리보기는 [`rhwp`](https://github.com/edwardkim/rhwp)
(MIT)를 [`pyhwpxlib`](https://github.com/ratiertm/hwpx-skill)
(PolyForm Noncommercial)를 통해 쓴다. 전체 출처는 [`NOTICE`](NOTICE) 참고.
