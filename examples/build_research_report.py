"""연구 결과 보고서를 만든다 — 정보량이 많고 그림이 들어가는 예제.

    python examples/build_research_report.py [out.hwpx]

이 문서를 만들 때 Claude 에게 준 지시:

    examples/data/penguins.csv 로 종 판별 분석 보고서 만들어줘.
    Palmer Archipelago 펭귄 3종(아델리/턱끈/젠투) 형태 측정 데이터야.

    먼저 분석부터 해줘. 종별 기술통계 내고, 단일 측정값 하나로 3종을
    가를 수 있는지 확인하고, 안 되면 2변수 조합을 격자 탐색으로 찾아서
    정확도랑 혼동행렬까지 뽑아줘.

    그 결과로 보고서를 써줘. 맨 앞에 결론 요약 박스, 그 다음 데이터 개요,
    종별 기술통계 표, 단일 변수 검토, 2변수 규칙과 혼동행렬, 산점도 두 장,
    한계, 데이터 출처 순서로. 수치는 분석 결과 그대로 쓰고 과장하지 마.
    한계 절에는 섬 정보가 종과 교란되는 문제도 꼭 넣어줘.

숫자는 전부 `penguins.csv` 를 실제로 분석해서 나온 값이다. 그림 2장은
`examples/make_figures.py` 가 같은 데이터로 그린 것이다.

세 예제 중 정보량이 가장 많은 쪽이다. 표 6개, 그림 2장, 본문 문단이 섞여
있어도 박스 구조가 무너지지 않는지 보는 용도이기도 하다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hwpx.document import HwpxDocument

from hwpxkit import BoxDoc, Grid, verify

IMAGES = ROOT / "examples" / "images"
FIG1 = IMAGES / "fig1_bill.png"
FIG2 = IMAGES / "fig2_flipper.png"


def _figure(b: BoxDoc, path: Path, caption: str, missing: str,
            *, width_mm: float = 150) -> None:
    """가운데 정렬 그림 + 캡션 한 줄. 파일이 없으면 눈에 보이는 빈칸."""
    if path.exists():
        b.picture(path, width_mm=width_mm)
    else:
        b.image_placeholder(missing)
    b.paragraph(caption, size=9)


def build(out_path: str) -> str:
    doc = HwpxDocument.new()
    b = BoxDoc(doc)

    # ------------------------------------------------------------- 제목 --
    b.title("펭귄 3종의 형태 측정값을 이용한 종 판별")
    b.paragraph("Species Discrimination of Palmer Archipelago Penguins "
                "from Morphometric Measurements", size=12, bold=True)
    b.paragraph("분석 대상 344개체 · 완전 관측 342개체", size=9)
    b.spacer()

    # -------------------------------------------------------- 0. 결론 --
    b.section_heading("0. 결론 요약 / Headline Finding")
    b.label_value_box([
        ("□ 연구 질문 / Question",
         "부리·날개·체중 같은 형태 측정값만으로 아델리·턱끈·젠투 3종을 "
         "가를 수 있는가?"),
        ("□ 결론 / Conclusion",
         "**측정값 하나로는 불가능하다.** 네 측정값 모두 세 종의 범위가 서로 "
         "겹친다. 반면 ==부리 길이와 부리 깊이 두 값을 조합==하면 임계값 두 "
         "개만으로 **93.0%**(318/342)를 맞춘다."),
        ("□ 규칙 / Rule",
         "부리 깊이 < 16.5 mm 이면 젠투. 그렇지 않으면 부리 길이 < 44.9 mm "
         "일 때 아델리, 아니면 턱끈."),
        ("□ 부리의 우월성 / Why the bill",
         "같은 구조에서 두 번째 변수를 날개 길이로 바꾸면 79.2%, 체중으로 "
         "바꾸면 76.3% 로 떨어진다. **부리 형태가 종 구분 정보를 가장 많이 "
         "담고 있다**(격차 약 14%p)."),
        ("□ 한계 / Caveat",
         "섬 분포가 종과 교란되어 있어(4절), 이 정확도를 다른 지역에 그대로 "
         "적용할 수 없다."),
    ])
    b.spacer()

    # ---------------------------------------------------- 1. 데이터 --
    b.section_heading("1. 데이터 / The Dataset")
    b.container_box([
        ("□ 구성 / Composition", [
            "남극 Palmer Archipelago 3개 섬에서 관측된 펭귄 344개체. "
            "측정값 4종(부리 길이·부리 깊이·날개 길이·체중)과 성별·관측 연도가 "
            "함께 기록되어 있다.",
            "※ 측정값에 결측이 있는 2개체는 분석에서 제외했다(342개체 사용). "
            "성별 결측 11건은 성별을 쓰지 않는 분석이므로 그대로 두었다.",
            Grid(
                headers=["종", "개체 수", "관측된 섬", "비율"],
                rows=[
                    ["아델리 (Adelie)", "151", "Biscoe, Dream, Torgersen", "44.2%"],
                    ["턱끈 (Chinstrap)", "68", "Dream", "19.9%"],
                    ["젠투 (Gentoo)", "123", "Biscoe", "36.0%"],
                    ["합계", "342", "3개 섬", "100%"],
                ],
                ratios=(0.28, 0.14, 0.40, 0.18),
            ),
        ]),
        ("□ 관측 연도 / Sampling Years", [
            "3년에 걸쳐 고르게 수집되어 특정 연도에 치우치지 않았다.",
            Grid(
                headers=["연도", "2007", "2008", "2009"],
                rows=[["개체 수", "109", "114", "119"]],
                ratios=(0.25, 0.25, 0.25, 0.25),
            ),
        ]),
    ])
    b.spacer()

    # ------------------------------------------------ 2. 기술통계 --
    b.section_heading("2. 종별 기술통계 / Descriptive Statistics")
    b.container_box([
        ("□ 측정값 요약 (평균 ± 표준편차) / Summary by Species", [
            "젠투는 부리가 얕고(15.0 mm) 날개가 길며(217.2 mm) 무겁다(5076 g). "
            "아델리와 턱끈은 부리 깊이·체중이 거의 같아서, ==둘을 가르는 것은 "
            "부리 길이==뿐이다(38.8 vs 48.8 mm).",
            Grid(
                headers=["측정값", "아델리", "턱끈", "젠투"],
                rows=[
                    ["부리 길이 (mm)", "38.8 ± 2.7", "48.8 ± 3.3", "47.5 ± 3.1"],
                    ["부리 깊이 (mm)", "18.3 ± 1.2", "18.4 ± 1.1", "15.0 ± 1.0"],
                    ["날개 길이 (mm)", "190.0 ± 6.5", "195.8 ± 7.1", "217.2 ± 6.5"],
                    ["체중 (g)", "3701 ± 459", "3733 ± 384", "5076 ± 504"],
                ],
                ratios=(0.28, 0.24, 0.24, 0.24),
            ),
        ]),
        ("□ 성별 이형성 / Sexual Dimorphism", [
            "세 종 모두 수컷이 무겁고, 젠투에서 그 차이가 가장 크다(805 g). "
            "성별을 모르는 개체가 11건 있으므로 아래 표의 합은 342보다 작다.",
            Grid(
                headers=["종", "수컷 평균 (g)", "암컷 평균 (g)", "차이"],
                rows=[
                    ["아델리", "4043 (n=73)", "3369 (n=73)", "674 g"],
                    ["턱끈", "3939 (n=34)", "3527 (n=34)", "412 g"],
                    ["젠투", "5485 (n=61)", "4680 (n=58)", "805 g"],
                ],
                ratios=(0.22, 0.28, 0.28, 0.22),
            ),
        ]),
    ])
    b.spacer()

    # --------------------------------------------- 3. 판별 분석 --
    b.section_heading("3. 종 판별 / Discriminating the Species")
    b.container_box([
        ("□ 단일 측정값으로는 갈리지 않는다 / No Single Measurement Suffices", [
            "네 측정값 각각에 대해 세 종의 관측 범위를 겹쳐 보았다. "
            "**어느 것도 세 종을 분리하지 못한다.**",
            Grid(
                headers=["측정값", "겹치는 종 쌍", "판정"],
                rows=[
                    ["부리 길이", "아델리~턱끈, 턱끈~젠투", "분리 불가"],
                    ["부리 깊이", "젠투~아델리, 아델리~턱끈", "분리 불가"],
                    ["날개 길이", "아델리~턱끈, 턱끈~젠투", "분리 불가"],
                    ["체중", "턱끈~아델리, 아델리~젠투", "분리 불가"],
                ],
                ratios=(0.24, 0.46, 0.30),
            ),
        ]),
        ("□ 2변수 규칙 / A Two-Variable Rule", [
            "네 측정값에서 두 개를 고르고 임계값을 각각 60구간으로 나누어 전수 "
            "탐색했다. 최적 조합은 **부리 깊이 + 부리 길이**였다.",
            "· 1단계 — 부리 깊이 < 16.5 mm 이면 **젠투**",
            "· 2단계 — 그 외에서 부리 길이 < 44.9 mm 이면 **아델리**, 아니면 **턱끈**",
            Grid(
                headers=["두 번째 변수", "정확도", "최적 대비"],
                rows=[
                    ["부리 길이", "93.0%", "—"],
                    ["날개 길이", "79.2%", "-13.8%p"],
                    ["체중", "76.3%", "-16.7%p"],
                ],
                ratios=(0.36, 0.32, 0.32),
            ),
        ]),
        ("□ 혼동행렬 / Confusion Matrix", [
            "행이 실제 종, 열이 규칙의 예측이다. 세 종 모두 재현율이 90% 안팎으로 "
            "고르다. 특정 종만 잘 맞히는 식의 편향은 없다.",
            Grid(
                headers=["실제 \\ 예측", "아델리", "턱끈", "젠투", "재현율"],
                rows=[
                    ["아델리", "142", "3", "6", "94.0%"],
                    ["턱끈", "6", "61", "1", "89.7%"],
                    ["젠투", "1", "7", "115", "93.5%"],
                ],
                ratios=(0.24, 0.19, 0.19, 0.19, 0.19),
            ),
        ]),
    ])
    b.spacer()

    # ------------------------------------------------------ 그림 --
    b.section_heading("4. 그림 / Figures")
    _figure(b, FIG1,
            "[그림 1] 부리 길이 × 부리 깊이. 점선은 3절의 두 임계값이다. "
            "가로선 아래가 젠투, 위쪽에서 세로선을 기준으로 아델리와 턱끈이 갈린다.",
            "그림 1 (examples/images/fig1_bill.png) — "
            "examples/make_figures.py 로 생성")
    b.spacer()
    _figure(b, FIG2,
            "[그림 2] 날개 길이 × 체중. 젠투는 잘 떨어지지만 아델리와 턱끈이 "
            "거의 완전히 겹친다. 이 조합의 정확도가 79.2% 에 그치는 이유다.",
            "그림 2 (examples/images/fig2_flipper.png) — "
            "examples/make_figures.py 로 생성")
    b.spacer()

    # ------------------------------------------------------ 한계 --
    b.section_heading("5. 한계 / Caveats — Do Not Over-claim")
    b.container_box([
        ("□ 섬 정보와의 교란 / Geographic Confounding", [
            "==이것이 가장 중요한 한계다.== 턱끈은 Dream 섬에서만, 젠투는 Biscoe "
            "섬에서만 관측되었다. 즉 섬을 아는 것만으로도 상당한 판별이 가능하다. "
            "본 분석은 형태만 사용했으므로 이 교란의 영향을 받지는 않지만, "
            "**여기서 얻은 93.0% 를 다른 지역에 그대로 적용할 수는 없다.** "
            "세 종이 함께 서식하는 지역에서는 낮아질 가능성이 크다.",
            Grid(
                headers=["섬", "아델리", "턱끈", "젠투"],
                rows=[
                    ["Biscoe", "있음", "없음", "있음"],
                    ["Dream", "있음", "있음", "없음"],
                    ["Torgersen", "있음", "없음", "없음"],
                ],
                ratios=(0.28, 0.24, 0.24, 0.24),
            ),
        ]),
        ("□ 그 밖의 유보 사항 / Other Limitations", [
            "· **검증 세트가 없다.** 임계값을 342개체 전체에서 찾고 같은 342개체로 "
            "정확도를 쟀다. 즉 93.0% 는 낙관적인 추정치다. 학습/검증을 나누면 "
            "낮아진다.",
            "· **표본이 불균형하다.** 턱끈이 68개체로 아델리(151)의 절반 미만이다.",
            "· **성별을 쓰지 않았다.** 성별 이형성이 뚜렷하므로(2절), 성별을 "
            "알 수 있다면 정확도가 오를 여지가 있다.",
            "· **3년치 관측이다.** 연도별로 고르지만 장기 추세를 말할 수는 없다.",
        ]),
    ])
    b.spacer()

    # ------------------------------------------------- 데이터 출처 --
    b.section_heading("6. 데이터 출처 / Data Provenance")
    b.label_value_box([
        ("□ 데이터셋 / Dataset",
         "palmerpenguins — Palmer Archipelago (Antarctica) penguin data"),
        ("□ 수집 / Collected by",
         "Dr. Kristen Gorman, Palmer Station Long Term Ecological Research "
         "(LTER) Network"),
        ("□ 인용 / Citation",
         "Horst AM, Hill AP, Gorman KB (2020). palmerpenguins: Palmer "
         "Archipelago (Antarctica) penguin data. R package version 0.1.0. "
         "doi:10.5281/zenodo.3960218"),
        ("□ 라이선스 / Licence",
         "**CC0** (퍼블릭 도메인 헌정). Palmer Station LTER Data Policy 의 "
         "Type I 데이터."),
        ("□ 분석 재현 / Reproducing",
         "원본 CSV 는 examples/data/penguins.csv, 그림은 "
         "examples/make_figures.py 로 생성한다."),
    ])

    doc.save_to_path(out_path)
    return out_path


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "out/research_report.hwpx"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    path = build(out)
    print(f"saved: {path}")
    print()
    print(verify(path, min_pages=1).render())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
