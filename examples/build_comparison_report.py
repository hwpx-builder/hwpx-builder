"""강아지 vs 고양이 비교 보고서를 만든다.

    python examples/build_comparison_report.py [out.hwpx]

이 문서를 만들 때 Claude 에게 준 지시:

    개 vs 고양이 비교 보고서 만들어줘. examples/images 에 있는 사진 써서.

사진은 ``examples/images/`` 에 함께 들어 있다(CC0, 출처는 그 폴더의 README).
어느 한쪽이라도 없으면 대신 지어내지 않고 눈에 보이는 ``image_placeholder``
를 넣는다.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hwpx.document import HwpxDocument

from hwpxkit import BoxDoc, Grid, verify

IMAGES = ROOT / "examples" / "images"
DOG_IMG = IMAGES / "dog.jpg"
CAT_IMG = IMAGES / "cat.jpg"


def _figure(b: BoxDoc, path: Path, caption: str, missing: str,
            *, width_mm: float = 100) -> None:
    """Centred picture plus a caption line, or a visible gap if absent."""
    if path.exists():
        b.picture(path, width_mm=width_mm)
    else:
        b.image_placeholder(missing)
    # BoxDoc.paragraph accepts `align` but ignores it, so the caption is a
    # plain left-aligned line rather than a silently-uncentred one.
    b.paragraph(caption, size=9)


def build(out_path: str) -> str:
    doc = HwpxDocument.new()
    b = BoxDoc(doc)

    # ---------------------------------------------------------------- title --
    b.title("강아지 vs 고양이 비교 보고서")
    b.paragraph("Dogs vs Cats — A Side-by-Side Comparison", size=12, bold=True)
    b.spacer()

    # ------------------------------------------------------------ 0. 개요 --
    b.section_heading("0. 문서 개요 / Overview")
    b.label_value_box([
        ("□ 문서 목적 / Purpose",
         "반려동물 입양을 고민하는 사람이 ==생활 방식에 맞는 동물==을 고르도록, "
         "강아지와 고양이를 같은 기준으로 나란히 비교한다."),
        ("□ 비교 대상 / Subjects",
         "강아지(Canis lupus familiaris)와 고양이(Felis catus)."),
        ("□ 한 줄 결론 / Bottom line",
         "**더 나은 동물은 없다.** 강아지는 함께 움직이는 시간을, "
         "고양이는 함께 머무는 공간을 요구한다. "
         "==선택의 기준은 동물이 아니라 사람의 하루==다."),
    ])
    b.spacer()

    # ------------------------------------------------- 1. 두 후보 소개 --
    b.section_heading("1. 두 후보 / The Two Candidates")
    _figure(b, DOG_IMG,
            "[그림 1] 강아지 — 사람을 향해 열려 있는 동물",
            "강아지 사진 (examples/images/dog.jpg)")
    b.paragraph(
        "강아지는 **무리 생활**에서 온 동물이다. 사람을 무리의 일원으로 받아들이고, "
        "함께 걷고 함께 먹는 일과에서 안정감을 얻는다. "
        "감정 표현이 크고 직접적이어서 초보 보호자도 상태를 읽기 쉽다.")
    b.spacer()
    _figure(b, CAT_IMG,
            "[그림 2] 고양이 — 자기 영역 안에서 사람을 허락하는 동물",
            "고양이 사진 (examples/images/cat.jpg)")
    b.paragraph(
        "고양이는 **단독 생활**에서 온 동물이다. 관계보다 영역이 먼저이고, "
        "사람은 그 영역 안에서 허락된 존재가 된다. "
        "표현이 작고 간접적이라 ==신호를 읽는 법을 배워야== 한다.")
    b.spacer()

    # ------------------------------------------------ 2. 항목별 비교 --
    b.section_heading("2. 항목별 비교 / Comparison by Category")
    b.container_box([
        ("□ 성향 및 사회성 / Temperament and Sociability", [
            "같은 집에 살아도 두 동물이 사람에게 요구하는 것은 다르다.",
            Grid(
                headers=["구분", "강아지", "고양이"],
                rows=[
                    ["기원", "무리 사냥 (협업 전제)", "단독 사냥 (자립 전제)"],
                    ["애착 방식", "보호자를 중심으로 하루가 돌아감",
                     "영역을 중심으로 하루가 돌아감"],
                    ["혼자 두기", "장시간 단독은 분리불안 위험",
                     "단독 시간에 비교적 관대"],
                    ["감정 표현", "꼬리·짖음·전신으로 크게 표현",
                     "귀·꼬리 끝·동공으로 미세하게 표현"],
                    ["낯선 사람", "대체로 개방적, 훈련으로 조절 가능",
                     "대체로 회피, 스스로 거리 결정"],
                ],
                ratios=(0.18, 0.41, 0.41),
            ),
        ]),
        ("□ 돌봄 부담 / Daily Care Load", [
            "가장 현실적인 차이는 ==보호자의 시간을 얼마나 고정된 형태로 요구하는가==에 있다.",
            Grid(
                headers=["항목", "강아지", "고양이"],
                rows=[
                    ["산책", "하루 1~2회, 날씨와 무관하게 필수", "기본적으로 불필요"],
                    ["배변", "정해진 장소로 데리고 나가야 함",
                     "화장실을 스스로 사용, 모래 관리만 필요"],
                    ["그루밍", "목욕·빗질 등 보호자 개입 큼",
                     "스스로 관리, 장모종은 빗질 보조 필요"],
                    ["훈련", "기본 예절 훈련이 사실상 필수",
                     "화장실·스크래처 유도 위주"],
                    ["외출·여행", "동반 또는 위탁 준비 필요",
                     "1~2일은 자동 급식·급수로 대응 가능"],
                    ["소음 민원", "짖음으로 이웃 갈등 소지 있음", "상대적으로 적음"],
                ],
                ratios=(0.16, 0.42, 0.42),
            ),
        ]),
        ("□ 주거 환경 적합도 / Suitability by Housing Type", [
            # A Grid is appended at the end of the container cell regardless of
            # its position in this list, so notes must lead, never trail.
            "고양이는 바닥 면적보다 **수직 동선**이 사육 환경의 질을 결정한다.",
            Grid(
                headers=["주거 형태", "강아지", "고양이"],
                rows=[
                    ["마당 있는 단독주택", "매우 적합", "적합 (실내 사육 전제)"],
                    ["아파트·빌라", "견종·크기에 따라 조건부 적합",
                     "적합, 단 추락 방지 방충망 필수"],
                    ["원룸·오피스텔", "소형견 한정, 산책 의존도 높음",
                     "적합, 수직 공간(캣타워)으로 면적 보완"],
                    ["재택근무", "매우 유리", "유리"],
                    ["장시간 부재", "부적합", "조건부 가능"],
                ],
                ratios=(0.22, 0.39, 0.39),
            ),
        ]),
    ])
    b.spacer()

    # ------------------------------------------------ 3. 비용과 수명 --
    b.section_heading("3. 비용과 건강 / Cost and Health")
    b.container_box([
        ("□ 연간 양육비 개요 / Annual Cost Outline", [
            "아래 금액은 국내 중소형 반려동물 기준의 일반적인 범위이며, "
            "품종·건강 상태·지역에 따라 크게 달라진다.",
            Grid(
                headers=["비목", "강아지", "고양이", "비고"],
                rows=[
                    ["사료·간식", "40~90만 원", "35~70만 원", "체중에 비례"],
                    ["예방접종·정기검진", "20~40만 원", "15~35만 원", "1년 1회 기준"],
                    ["미용·그루밍", "30~80만 원", "0~15만 원", "견종 영향 큼"],
                    ["용품·소모품", "15~35만 원", "20~45만 원", "고양이는 모래 비중"],
                    ["돌봄·위탁", "10~60만 원", "0~20만 원", "외출 빈도에 비례"],
                    ["합계(대략)", "115~305만 원", "70~185만 원", "질병 발생 시 별도"],
                ],
                ratios=(0.24, 0.22, 0.22, 0.32),
            ),
        ]),
        ("□ 수명 및 흔한 건강 문제 / Lifespan and Common Conditions", [
            "고양이는 아픈 것을 드러내지 않으므로, 식욕·음수량·배뇨 횟수의 작은 변화가 "
            "==가장 신뢰할 수 있는 신호==다.",
            Grid(
                headers=["구분", "강아지", "고양이"],
                rows=[
                    ["평균 수명", "10~13년 (소형견은 더 김)", "12~18년"],
                    ["흔한 질환", "슬개골 탈구, 심장질환, 피부염",
                     "만성 신장질환, 하부요로질환, 치과질환"],
                    ["조기 발견 난이도", "증상 표현이 커서 비교적 쉬움",
                     "==통증을 숨기는 습성==으로 늦게 발견되기 쉬움"],
                    ["권장 검진 주기", "연 1회, 노령기 연 2회",
                     "연 1회, 7세 이후 연 2회 + 신장 수치 확인"],
                ],
                ratios=(0.2, 0.4, 0.4),
            ),
        ]),
    ])
    b.spacer()

    # ------------------------------------------------------- 4. 결론 --
    b.section_heading("4. 결론 / Conclusion")
    b.container_box([
        ("□ 어떤 사람에게 어떤 동물이 맞는가 / Who Should Choose What", [
            Grid(
                headers=["당신의 하루가 이렇다면", "권장", "이유"],
                rows=[
                    ["매일 30분 이상 밖에 나갈 수 있다", "강아지",
                     "산책이 부담이 아니라 일과가 된다"],
                    ["귀가 시간이 불규칙하다", "고양이",
                     "단독 시간에 대한 내성이 높다"],
                    ["아이와 함께 키우려 한다", "강아지",
                     "상호작용이 예측 가능하고 훈련으로 조절된다"],
                    ["집이 조용해야 한다", "고양이", "소음 발생이 적다"],
                    ["초기 훈련에 시간을 쓸 수 있다", "강아지",
                     "투자한 훈련이 그대로 생활 품질로 돌아온다"],
                    ["관계보다 공존이 편하다", "고양이",
                     "거리를 존중하는 방식의 애착이다"],
                ],
                ratios=(0.36, 0.14, 0.5),
            ),
        ]),
        ("□ 최종 정리 / Final Note", [
            "· 강아지는 **시간을 요구**하고, 고양이는 **공간을 요구**한다.",
            "· 비용과 손이 덜 가는 쪽은 대체로 고양이지만, "
            "고양이는 질병 신호를 숨기므로 ==관찰의 정밀도==를 요구한다.",
            "· 두 동물 모두 10년 이상의 약속이다. "
            "선택의 기준은 취향이 아니라 **지속 가능한 하루**여야 한다.",
            "※ 본 문서의 수치는 일반적인 참고 범위이며, 입양 전 수의사 상담을 권장한다.",
        ]),
    ])

    doc.save_to_path(out_path)
    return out_path


def main() -> int:
    out = sys.argv[1] if len(sys.argv) > 1 else "out/comparison_report.hwpx"
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    path = build(out)
    print(f"saved: {path}")
    print()
    report = verify(path, min_pages=1)
    print(report.render())
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
