"""사업계획서에 반복해서 나오는 분석 틀들.

TAM-SAM-SOM, SWOT, 비즈니스 모델 캔버스처럼 이름과 칸이 정해져 있는 틀은
매번 표를 새로 짜는 대신 여기서 가져다 쓴다. 전부 :class:`hwpxkit.boxdoc.Grid`
를 돌려주므로, 새로 만드는 문서(:meth:`BoxDoc.container_box`)에도, 기존 양식을
채울 때(:func:`hwpxkit.edit.fill_cell`)에도 똑같이 들어간다::

    from hwpxkit.templates import tam_sam_som

    b.container_box([("□ 목표시장 분석", [
        "시장 규모는 아래와 같이 추정했다.",
        tam_sam_som(
            tam=("국내 4년제 대학 전체", "약 190개교", "대학알리미 공시"),
            sam=("재학생 1만 명 이상", "약 90개교", "같은 공시에서 필터"),
            som=("수도권 우선 도입", "12개교", "3년 내 목표"),
        ),
    ])])

**숫자는 넣어 주는 사람이 책임진다.** 이 모듈은 칸의 이름과 배치만 안다.
근거 없는 수치를 채워 넣지 않도록, 모든 함수가 근거/출처 칸을 함께 만든다.
"""
from __future__ import annotations

from typing import Sequence

from .boxdoc import Grid

#: 근거 칸을 비워 둘 때 쓰는 표시. 빈칸으로 두면 채운 것처럼 보인다.
TBD = "(근거 미기재)"


def tam_sam_som(*, tam: Sequence[str], sam: Sequence[str], som: Sequence[str],
                headers: Sequence[str] = ("구분", "정의", "규모", "산출 근거"),
                ratios: Sequence[float] = (0.12, 0.30, 0.20, 0.38)) -> Grid:
    """TAM-SAM-SOM 시장 규모 추정표.

    각 인자는 ``(정의, 규모, 산출 근거)`` 3요소다. 근거 칸이 따로 있는 이유는,
    이 표에서 가장 자주 지적받는 것이 "그 숫자 어디서 나왔나" 이기 때문이다.

    - **TAM** (Total Addressable Market) — 제품이 이론상 닿을 수 있는 전체 시장
    - **SAM** (Serviceable Available Market) — 그중 실제로 공략 가능한 부분
    - **SOM** (Serviceable Obtainable Market) — 그중 기간 내 확보를 목표하는 몫
    """
    def row(label: str, full: str, item: Sequence[str]) -> list[str]:
        vals = list(item) + [TBD] * (3 - len(item))
        return [f"**{label}**", vals[0], vals[1], vals[2] or TBD]

    return Grid(
        headers=list(headers),
        rows=[
            row("TAM", "Total Addressable Market", tam),
            row("SAM", "Serviceable Available Market", sam),
            row("SOM", "Serviceable Obtainable Market", som),
        ],
        ratios=tuple(ratios),
    )


def swot(*, strengths: Sequence[str], weaknesses: Sequence[str],
         opportunities: Sequence[str], threats: Sequence[str],
         bullet: str = "· ") -> Grid:
    """SWOT 2×2 표.

    네 칸에 각각 여러 항목을 넣을 수 있다. 한 칸 안에서는 줄바꿈으로 나뉜다.
    2×2 배치라 내부 요인(S/W)이 위, 외부 요인(O/T)이 아래로 온다.
    """
    def cell(items: Sequence[str]) -> str:
        return "\n".join(f"{bullet}{x}" for x in items) if items else TBD

    return Grid(
        headers=["내부 요인 / Internal", "외부 요인 / External"],
        rows=[
            [f"**강점 (Strengths)**\n{cell(strengths)}",
             f"**기회 (Opportunities)**\n{cell(opportunities)}"],
            [f"**약점 (Weaknesses)**\n{cell(weaknesses)}",
             f"**위협 (Threats)**\n{cell(threats)}"],
        ],
        ratios=(0.5, 0.5),
    )


#: 비즈니스 모델 캔버스의 아홉 칸. 원문 순서를 따른다.
BMC_BLOCKS = (
    ("key_partners", "핵심 파트너 / Key Partners"),
    ("key_activities", "핵심 활동 / Key Activities"),
    ("key_resources", "핵심 자원 / Key Resources"),
    ("value_propositions", "가치 제안 / Value Propositions"),
    ("customer_relationships", "고객 관계 / Customer Relationships"),
    ("channels", "채널 / Channels"),
    ("customer_segments", "고객 세그먼트 / Customer Segments"),
    ("cost_structure", "비용 구조 / Cost Structure"),
    ("revenue_streams", "수익원 / Revenue Streams"),
)


def business_model_canvas(*, bullet: str = "· ", **blocks) -> Grid:
    """비즈니스 모델 캔버스 아홉 칸.

    키워드 인자로 채운다. 이름은 :data:`BMC_BLOCKS` 의 첫 항목들이다::

        business_model_canvas(
            customer_segments=["재학생 1만 명 이상 대학"],
            value_propositions=["분실물 회수율을 높인다"],
            revenue_streams=["대학 단위 연간 이용료"],
        )

    원래 캔버스는 9칸이 특유의 격자로 배치되지만, 한글 표에서 그 배치를
    재현하면 병합 셀이 잔뜩 생기고 **병합 표는 높이 재계산을 할 수 없다**
    (:func:`hwpxkit.edit.refit_cell` 참고). 그래서 여기서는 병합 없는 2열
    목록으로 편다. 정보는 같고, 편집·검증이 가능한 형태다.

    알 수 없는 칸 이름을 주면 조용히 무시하지 않고 :class:`ValueError` 를 낸다.
    오타 때문에 빈 캔버스가 나가는 것을 막기 위해서다.
    """
    known = {k for k, _ in BMC_BLOCKS}
    unknown = set(blocks) - known
    if unknown:
        raise ValueError(
            f"모르는 칸: {sorted(unknown)}. 쓸 수 있는 이름: {sorted(known)}")

    def cell(value) -> str:
        if value is None:
            return TBD
        if isinstance(value, str):
            return value
        return "\n".join(f"{bullet}{x}" for x in value) if value else TBD

    return Grid(
        headers=["구분", "내용"],
        rows=[[f"**{label}**", cell(blocks.get(key))] for key, label in BMC_BLOCKS],
        ratios=(0.28, 0.72),
    )


def milestones(rows: Sequence[Sequence[str]], *,
               headers: Sequence[str] = ("단계", "기간", "내용", "완료 기준"),
               ratios: Sequence[float] = (0.12, 0.14, 0.42, 0.32)) -> Grid:
    """추진 일정표.

    마지막 열이 "완료 기준" 인 것이 핵심이다. 일정만 적힌 표는 검증할 수 없고,
    심사에서도 그 점을 묻는다.
    """
    return Grid(headers=list(headers), rows=[list(r) for r in rows],
                ratios=tuple(ratios))


def budget(rows: Sequence[Sequence[str]], *,
           headers: Sequence[str] = ("비목", "금액", "산출 근거"),
           ratios: Sequence[float] = (0.24, 0.20, 0.56),
           total_label: str = "합계") -> Grid:
    """사업비 표.

    *rows* 의 마지막 행 라벨이 *total_label* 로 시작하면 굵게 처리한다.
    금액을 합산해 주지는 **않는다.** 계산을 대신하면 틀렸을 때 조용히 틀리고,
    제출 서류에서 그건 가장 나쁜 실패다.
    """
    out = []
    for r in rows:
        r = list(r)
        if r and str(r[0]).startswith(total_label):
            r = [f"**{c}**" for c in r]
        out.append(r)
    return Grid(headers=list(headers), rows=out, ratios=tuple(ratios))


def competitor_matrix(*, criteria: Sequence[str], us: Sequence[str],
                      competitors: Sequence[tuple[str, Sequence[str]]],
                      our_label: str = "본 서비스") -> Grid:
    """경쟁사 비교표.

    *criteria* 가 행, 우리와 경쟁사가 열이 된다. 각 열의 값 개수는 *criteria*
    개수와 같아야 한다. 다르면 :class:`ValueError` — 열이 밀린 비교표는
    읽는 사람이 알아채기 어렵기 때문이다.
    """
    n = len(criteria)
    if len(us) != n:
        raise ValueError(f"{our_label} 값이 {len(us)}개, 기준은 {n}개다")
    for name, vals in competitors:
        if len(vals) != n:
            raise ValueError(f"{name} 값이 {len(vals)}개, 기준은 {n}개다")

    cols = 2 + len(competitors)
    width = round(1.0 / cols, 3)
    return Grid(
        headers=["구분", f"**{our_label}**"] + [n for n, _ in competitors],
        rows=[[criteria[i], us[i]] + [v[i] for _, v in competitors]
              for i in range(n)],
        ratios=tuple([width] * cols),
    )
