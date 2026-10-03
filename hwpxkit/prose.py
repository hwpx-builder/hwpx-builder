"""문장 검토 — "AI 가 쓴 티"를 잡는 기계적 1차 검토와 다시 읽기용 덤프.

생성된 문장이 어색한 이유는 대개 몇 가지로 좁혀진다. 상투어("다양한",
"효과적으로", "이를 통해"), 숫자 없는 주장("크게 개선된다"), 빠져나갈 구멍을
남기는 어미("기대된다", "것으로 보인다"), 세 개씩 나열하고 "등"으로 닫는
버릇, 길이가 균일한 문장의 연속, 그리고 **강조가 없어서 어디를 읽어야 할지
모르는 본문**이다. 이 모듈은 그중 규칙으로 잡히는 것을 잡는다. 문장이 좋은지
판단하지는 못한다 — 지적이 0 이라는 건 "기계가 걸 것은 없다"는 뜻이지 "잘
썼다"는 뜻이 아니다. 최종 판단은 :func:`dump_text` 로 뽑은 글을 **읽는 사람의
자리에서 다시 읽는** 쪽이 한다. 절차는 ``references/writing.md``.

두 진입점이 있다.

* 만들기 **전**: :func:`review_text` / :func:`review_blocks` 에 마크업 문자열
  (또는 그것을 담은 list/dict)을 넘긴다. 문서를 만들기 전에 고치는 편이 싸다.
* 만든 **후**: :func:`review_document` 가 HWPX 를 열어 칸마다 같은 검토를
  한다. :func:`hwpxkit.verify` 가 이걸 "prose review" 줄로 보고한다.

강조 규칙은 일부러 후하다. 심사자는 처음부터 끝까지 읽지 않고 **굵은 글자와
형광펜만 훑고 나서** 관심이 가면 본문을 읽는다. 그래서 내용 칸마다 굵게가
없으면 지적하고, 세 문장 이상인 칸에 형광펜 한 줄이 없어도 지적한다. 반대로
절반 넘게 강조한 칸도 지적한다 — 전부 강조하면 아무것도 강조되지 않는다.
"""
from __future__ import annotations

import re
import statistics
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence
from xml.etree import ElementTree as ET

HP = "{http://www.hancom.co.kr/hwpml/2011/paragraph}"
HH = "{http://www.hancom.co.kr/hwpml/2011/head}"

#: 이 길이(마크업 제외) 미만의 글은 라벨·머리글·표 데이터로 보고 검토하지 않는다.
MIN_BLOCK_CHARS = 40
#: 이보다 긴 문장은 둘로 나누라고 지적한다 (한글 본문 문장은 60~80자가 보통).
MAX_SENTENCE_CHARS = 100
#: 마침표 없이 이어지는 개조식 줄의 상한. 한 줄이 이보다 길면 읽는 사람이 숨을 못 쉰다.
MAX_LINE_CHARS = 150
#: 강조된 글자가 이 비율을 넘으면 "강조 과다".
MAX_EMPHASIS_RATIO = 0.5
#: 한 칸에 형광펜이 이보다 많으면 지적. 한 칸의 형광펜은 "이 칸에서 기억할 한 줄"이다.
MAX_HIGHLIGHTS_PER_BLOCK = 2

# --------------------------------------------------------------- 어휘표 --

#: 상투어 → 고치는 방향. 걸리면 "fix".
CLICHES: dict[str, str] = {
    "다양한": "무엇이 몇 가지인지 쓴다 (예: '3개 대학', '두 유형')",
    "효과적으로": "어떤 효과가 얼마나 — 숫자나 비교로",
    "효과적인": "어떤 효과가 얼마나 — 숫자나 비교로",
    "효율적으로": "무엇이 얼마나 줄거나 빨라지는지",
    "효율적인": "무엇이 얼마나 줄거나 빨라지는지",
    "혁신적": "기존과 무엇이 다른지 한 문장으로",
    "획기적": "기존과 무엇이 다른지 한 문장으로",
    "차별화": "비교 대상을 적고 차이를 구체적으로",
    "최적의": "무엇을 기준으로 최적인지",
    "최적화": "무엇을 얼마나 줄이거나 늘리는지",
    "체계적": "절차를 단계로 나열한다",
    "지속 가능": "얼마나 오래, 무엇으로 유지되는지",
    "지속가능": "얼마나 오래, 무엇으로 유지되는지",
    "시너지": "누가 무엇을 주고받는지",
    "글로벌": "어느 나라·시장인지",
    "선도": "근거 없이 쓰면 주장일 뿐 — 순위나 수치로",
    "궁극적으로": "삭제하고 목표를 직접 쓴다",
    "뿐만 아니라": "문장을 둘로 나눈다",
    "이를 통해": "삭제 — 앞 문장의 결과를 주어로 이어 쓴다",
    "중요한 역할": "무슨 역할인지",
    "긍정적인 영향": "어떤 영향이 얼마나",
    "적극적으로": "삭제해도 뜻이 같다",
    "원활한": "무엇이 어떻게 되는지 구체적으로",
    "원활하게": "무엇이 어떻게 되는지 구체적으로",
    "다각적": "항목을 나열한다",
    "다각도": "항목을 나열한다",
    "종합적": "항목을 나열한다",
    "패러다임": "삭제 — 무엇이 바뀌는지 직접",
    "4차 산업혁명": "삭제 — 쓰는 기술 이름을 직접",
    "고객 만족": "무엇을 만족시키는지, 어떻게 재는지",
    "최고의": "근거나 비교 대상을 적는다",
    "최상의": "근거나 비교 대상을 적는다",
    "다양한 분야": "분야를 적는다",
    "핵심 역량": "역량을 적는다",
    "경쟁력을 확보": "무엇으로 누구를 이기는지",
    "경쟁력 있는": "무엇으로 누구를 이기는지",
    "니즈": "'필요' 또는 구체적인 요구",
    "솔루션": "제품·서비스·도구 중 실제 형태로",
    "밸류": "'가치' — 그리고 누구에게 무슨 가치인지",
}

#: 빠져나갈 구멍을 남기는 어미. 확인한 사실은 단정하고, 계획은 '~한다'로.
HEDGES: dict[str, str] = {
    "기대된다": "확인한 것은 단정, 계획은 '~한다'. 기대는 근거가 없다는 자백",
    "기대됩니다": "확인한 것은 단정, 계획은 '~한다'",
    "것으로 기대": "확인한 것은 단정, 계획은 '~한다'",
    "예상된다": "근거를 적고 '~한다'로, 또는 수치와 함께",
    "것으로 예상": "근거를 적고 '~한다'로, 또는 수치와 함께",
    "것으로 보인다": "본 것을 그대로 적는다",
    "것으로 판단된다": "'~다'로 단정하고 근거를 붙인다",
    "할 수 있을 것": "'~한다' 또는 조건을 명시",
    "할 수 있을 것으로": "'~한다' 또는 조건을 명시",
    "될 것으로": "'~된다' 와 근거",
    # 합니다체 짝. 사용자는 대개 합니다체로 받는다 — 한다체만 있으면 거의 다 샌다.
    "예상됩니다": "근거를 적고 '~합니다'로, 또는 수치와 함께",
    "것으로 보입니다": "본 것을 그대로 적는다",
    "것으로 판단됩니다": "'~입니다'로 단정하고 근거를 붙인다",
    "것 같습니다": "지원서에서는 단정하거나 조건을 적는다 (연구 검토의 의견이면 mode='research')",
}

#: 근거보다 센 말. 연구·특허 검토 문서(``mode="research"``)에서는 FIX, 지원서에서는
#: note. 외부 검토자가 실제로 지적한 표현에서 뽑았다 — "선행기술에 근거가 있다"를
#: "확인되어 있다"로 쓰면 실험 결과가 이미 있는 것처럼 읽힌다.
OVERCLAIMS: dict[str, str] = {
    "확인되어 있": "누가 어떤 조건에서 확인했는지 적거나 '근거가 있다'로 낮춘다",
    "이미 확인": "우리 조건에서 확인한 게 아니면 '선행 근거가 있다'로",
    "입증되었": "누가 무엇으로 입증했는지, 우리 제형에도 해당하는지",
    "입증된": "누가 무엇으로 입증했는지, 우리 제형에도 해당하는지",
    "증명되었": "근거의 범위를 적는다",
    "같게 볼 수": "같다고 전제하지 않는다 — '대용으로 쓴다, 다만 동일하다고 보지 않는다'",
    "동일하게 볼 수": "같다고 전제하지 않는다",
    "동일하다고 볼 수": "같다고 전제하지 않는다",
    "가장 강한": "'가장 유력한 … 중 하나' 처럼 비교 범위를 남긴다",
    "명백히": "근거 수준에 맞춰 — 삭제하거나 근거를 붙인다",
    "명백하다": "근거 수준에 맞춰 — 삭제하거나 근거를 붙인다",
    "틀림없이": "삭제",
    "확실히": "삭제하거나 근거를 붙인다",
    "완전히 대체": "'대체 모델'이 아니라 무엇을 미리 검증하는지로",
    "직접 경쟁": "용도·적용 대상이 같은지 — 다르면 '가장 가까운 비교 제품'",
}
#: 청구항 해석을 단정하는 문장. 해석은 변리사 몫이다.
_CLAIM_READING = re.compile(r"(청구항|Claim)\s*\d+[^.]{0,30}(에|에도)\s*해당(한다|합니다|할 것)")

#: 편집 흔적 — 고친 사람에게만 의미가 있는 표시. 받는 사람에게는 소음이다.
EDIT_TRACES = re.compile(
    r"※\s*(수정|변경|추가|삭제|반영)"
    r"|\((수정|추가|삭제|변경|반영)(됨|함|했음)?\)"
    r"|이번\s*(개정|수정|버전)|개정안(에서|에 따라|대로)"
    r"|(기존|이전|지난|구)\s*(버전|판)(에서|과 달리|대비)"
    r"|\bv\d+(\.\d+)?\s*(에서|대비|과 달리|와 달리)"
    r"|TODO|FIXME|\bXXX\b|\[(주석|메모|편집|확인 필요|수정)\]"
    r"|\(\s*\d{4}[-.]\s?\d{1,2}[-.]\s?\d{1,2}\.?\s*(확인|기준 확인|수정)\s*\)"
    r"|(사용자|요청자)\s*요청(에 따라|으로)|←")

#: 사람이 한글 문서에 손으로 치지 않는 문장부호. 생성된 글의 가장 흔한 표지다.
#: 받는 사람(심사자·교수)이 실제로 지적했다: 줄표 대신 '-', 가운뎃점 대신 '/'.
_TYPO_DASH = re.compile(r"[—―]")
_TYPO_EN = re.compile(r"–")
_TYPO_MIDDOT = re.compile(r"(?<=\S)[·‧・](?=\S)")

_DATE = re.compile(r"\d{4}\s?[.\-/]\s?\d{1,2}(\s?[.\-/]\s?\d{1,2})?\.?")


def is_identifier(text: str) -> bool:
    """특허·출원·논문·문서 번호처럼 보이는가 (``US20230399389A1``,
    ``WO2024220398``, ``10-2023-0012345``, ``PMC7156987``, ``10.1111/all.1``).

    굵게는 크기(숫자)와 핵심어에 쓰는 것이다. 번호를 굵게 하는 사람은 없다 —
    ``**US20230399389A1**`` 은 받는 사람이 실제로 어색하다고 지적한 모양이다.
    """
    s = text.strip().strip("()[]")
    if not s or re.search(r"[가-힣]", s) or _DATE.fullmatch(s):
        return False
    if re.fullmatch(r"10\.\d{4,}/\S+", s):                 # DOI
        return True
    if not re.fullmatch(r"[A-Za-z0-9./\-\s]+", s):
        return False
    digits = sum(ch.isdigit() for ch in s)
    if digits < 6:
        return False
    has_alpha = bool(re.search(r"[A-Za-z]", s))
    return has_alpha or digits >= 8 or s.count("-") >= 2


def humanize_punct(text: str) -> str:
    """사람이 치지 않는 문장부호를 사람이 쓰는 것으로 바꾼다. 멱등이다.

    ``A — B`` → ``A - B``, ``3–5`` → ``3-5``, ``기술·사업화`` → ``기술/사업화``.
    줄머리의 ``· `` 글머리표(개조식 기호)는 그대로 둔다 — 뒤가 빈칸이라 걸리지
    않는다. :func:`hwpxkit.richtext.parse_markup` 이 새로 쓰는 모든 글에 적용하므로
    빌더로 쓴 글에는 이 문자가 남지 않는다. 다만 기계 치환은 차선이다 — 줄표
    자리는 대개 쉼표나 문장 나눔이 더 자연스럽다. 그래서 :func:`review_text` 가
    원고 단계에서 따로 지적한다.
    """
    text = re.sub(r"[ \t]+[—―–][ \t]+", " - ", text)
    text = re.sub(r"[—―–]", "-", text)
    return _TYPO_MIDDOT.sub("/", text)


#: 문체(종결 어미). 한 문서 안에서 섞이면 가장 먼저 "말투가 이상하다"는 말을 듣는다.
REGISTERS = {"합니다": "hamnida", "합니다체": "hamnida", "입니다": "hamnida",
             "hamnida": "hamnida", "한다": "handa", "한다체": "handa", "handa": "handa",
             "개조식": "gaejo", "gaejo": "gaejo"}
_REGISTER_NAME = {"hamnida": "합니다체", "handa": "한다체", "haeyo": "해요체",
                  "gaejo": "개조식"}
_TAIL = r"[\"'”’)\]]*\s*$"
_END_HAMNIDA = re.compile(r"(니다|니까|십시오)[.!?]?" + _TAIL)
_END_HAEYO = re.compile(r"([아어여해]요|에요|예요|네요|죠|데요|군요|거든요|지요)[.!?]" + _TAIL)
_END_HANDA = re.compile(r"(?<!니)다[.!?]" + _TAIL)


def sentence_register(sentence: str) -> str | None:
    """문장의 문체. 마침표 없는 개조식 줄, 판단할 수 없는 문장은 ``None``."""
    s = _plain(sentence).strip()
    if _END_HAMNIDA.search(s):
        return "hamnida"
    if _END_HAEYO.search(s):
        return "haeyo"
    if _END_HANDA.search(s):
        return "handa"
    return None


def detect_register(texts: Iterable[str]) -> tuple[str | None, dict[str, int]]:
    """여러 글의 문장 문체를 세어 (가장 많은 문체, 개수표) 를 돌려준다."""
    counts: dict[str, int] = {}
    for t in texts:
        for sent in _sentences(_plain(t)):
            r = sentence_register(sent)
            if r:
                counts[r] = counts.get(r, 0) + 1
    if not counts:
        return None, counts
    return max(counts, key=counts.get), counts


def _resolve_register(register: str | None) -> str | None:
    if register is None:
        return None
    try:
        return REGISTERS[register]
    except KeyError:
        raise ValueError(f"register 는 {sorted(set(REGISTERS))} 중 하나: {register!r}")


#: 문서 종류. pitch = 지원서·사업계획서, research = 연구·특허 검토(교수·변리사용).
MODES = ("pitch", "research")


#: 번역투. 한 칸에 2회 이상이면 지적.
TRANSLATIONESE: dict[str, str] = {
    "에 있어서": "'~에서' 또는 삭제",
    "에 있어": "'~에서' 또는 삭제",
    "되어지": "'~되다' 로",
    "로 인해": "'~때문에' 또는 원인을 주어로",
    "함으로써": "'~해서'",
    "가지고 있": "'있다' / '갖췄다'",
    "의 경우": "'~은/는' 으로",
    "필요성이 있": "'필요하다'",
    "진행할 예정": "'~한다'",
    "을 통해": "수단을 동사로 ('설문을 통해 확인' → '설문으로 확인')",
    "를 통해": "수단을 동사로 ('설문을 통해 확인' → '설문으로 확인')",
    "에 대한": "'~의' 또는 목적어로 풀어 쓴다",
    "에 대해": "목적어로 풀어 쓴다",
}

#: 문장 첫머리의 접속 부사. 한 칸에 2회 이상이면 지적 — 논리가 아니라 접착제다.
CONNECTORS = ("또한", "더불어", "나아가", "한편", "결론적으로", "즉", "특히",
              "이에", "따라서", "그리고", "그러므로", "이처럼", "이와 같이")

#: 근거 없이 쓰면 주장만 남는 낱말. 문장에 숫자나 굵게가 없으면 지적.
CLAIM_WORDS = ("증가", "감소", "개선", "향상", "절감", "단축", "확대", "성장",
               "높다", "높은", "높아", "낮다", "낮은", "낮아", "빠르", "우수",
               "효율", "최대", "최소", "대폭", "크게", "급격", "상당")

#: 정도를 뭉개는 부사. 숫자로 바꾼다.
INTENSIFIERS = ("매우", "상당히", "크게", "대단히", "굉장히", "많은", "수많은")

_SENT_SPLIT = re.compile(r"(?<=[.!?。])\s+|\n+")
_MARKUP = re.compile(r"\*\*|==")
_TRIPLE_ETC = re.compile(r"[^,\n]{2,20},\s*[^,\n]{2,20},\s*[^,\n]{2,20}\s*등")
_DIGIT = re.compile(r"\d")


# ------------------------------------------------------------- 자료형 --

@dataclass
class Finding:
    kind: str          # cliche | hedge | translationese | connector | claim | intensifier
                       # | long | monotone | triple | no-figure | no-bold | no-highlight
                       # | over-emphasis | too-many-highlights | typography | bold-id
                       # | register | overclaim | edit-trace
    severity: str      # "fix" 는 고치고 다시 검토, "note" 는 읽고 판단
    where: str         # 칸 경로 또는 호출자가 준 이름
    text: str          # 걸린 조각
    hint: str          # 고치는 방향

    def __str__(self) -> str:
        mark = "FIX " if self.severity == "fix" else "note"
        loc = f"[{self.where}] " if self.where else ""
        return f"  {mark} {loc}{self.kind}: {self.text!r} — {self.hint}"


@dataclass
class ProseReport:
    findings: list[Finding] = field(default_factory=list)
    blocks: int = 0            # 검토한 내용 칸/문단 수

    @property
    def fixes(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "fix"]

    @property
    def notes(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "note"]

    @property
    def ok(self) -> bool:
        return not self.fixes

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for f in self.findings:
            out[f.kind] = out.get(f.kind, 0) + 1
        return out

    def summary(self) -> str:
        if not self.findings:
            return f"{self.blocks} block(s), 기계적으로 걸리는 것 없음"
        parts = ", ".join(f"{k} {n}" for k, n in sorted(self.counts().items(),
                                                      key=lambda kv: -kv[1]))
        return (f"{self.blocks} block(s): FIX {len(self.fixes)}, note {len(self.notes)}"
                f" ({parts})")

    def render(self) -> str:
        lines = [str(f) for f in self.findings]
        lines.append("")
        lines.append("PROSE: " + self.summary())
        if self.fixes:
            lines.append("       FIX 항목을 고친 뒤 다시 돌린다. 0 이 되면 dump_text() 로 "
                         "뽑아 읽는 사람의 자리에서 한 번 더 읽는다 (references/writing.md).")
        return "\n".join(lines)


# ------------------------------------------------------------ 텍스트 검토 --

def _plain(markup: str) -> str:
    return _MARKUP.sub("", markup)


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_SPLIT.split(text) if s and s.strip()]


def _emphasis_stats(markup: str) -> tuple[int, int, float]:
    """(굵게 조각 수, 형광펜 조각 수, 강조된 글자 비율)."""
    bold = re.findall(r"\*\*(.+?)\*\*", markup)
    high = re.findall(r"==(.+?)==", markup)
    plain = _plain(markup)
    emphasized = sum(len(_plain(b)) for b in bold) + sum(len(_plain(h)) for h in high)
    # 겹쳐 쓴 **==..==** 은 두 번 세어지므로 상한을 둔다.
    ratio = min(emphasized / len(plain), 1.0) if plain else 0.0
    return len(bold), len(high), ratio


#: 이런 라벨이 붙은 칸은 강조·근거 규칙을 적용하지 않는다 (출처·연락처·비고).
_NO_EMPHASIS_LABELS = re.compile(
    r"출처|참고|문헌|자료|reference|source|비고|연락|이메일|e-mail|주소|url|링크|성명|이름|소속"
    r"|인용|citation|collected|dataset|데이터셋|라이선스|licen[cs]e|저자|author|제공|파일|file",
    re.I)


def _looks_like_label(plain: str) -> bool:
    """문장부호 없는 짧은 줄들 — 양식의 라벨, 제목, 팀원 칸 같은 것."""
    lines = [l for l in plain.split("\n") if l.strip()]
    return (not re.search(r"[.!?。]", plain)
            and bool(lines) and max(len(l) for l in lines) < 35)


def review_text(markup: str, *, where: str = "", emphasis: bool = True,
                label: str = "", mode: str = "pitch", register: str | None = None,
                register_severity: str = "fix") -> list[Finding]:
    """마크업 문자열 하나(문단 여러 개면 ``\\n`` 로 구분)를 검토한다.

    *emphasis* 를 끄면 강조 밀도 규칙(굵게 없음·형광펜 없음·과다)은 건너뛴다 —
    표 칸처럼 강조가 어울리지 않는 자리용. *label* 은 이 글이 들어 있는 칸의
    라벨(있으면)이다. 출처·연락처 칸은 강조 규칙에서 뺀다.

    상투어·어미 검사는 모든 글에 하고, 문장 구조와 강조 밀도는 **본문다운
    글**에만 한다. 전부 굵은 한두 문장은 제목·라벨이고, 마침표 없는 짧은 줄의
    묶음은 양식의 라벨이나 명단이다 — 거기에 "형광펜이 없다"고 하면 소음이다.

    *mode* — ``"pitch"`` (지원서·사업계획서, 기본): 확인한 것은 단정하라는
    쪽이라 "기대된다", "것으로 보인다"가 FIX. ``"research"`` (연구·특허 검토,
    교수·변리사에게 가는 글): 위험은 반대쪽, **근거보다 센 말**이다. 의견을
    "~인 것 같습니다"로 쓰는 것은 허용하고 "확인되어 있다", "같게 볼 수 있다"
    같은 과잉 단정을 FIX 로 잡는다.

    *register* — ``"합니다"`` / ``"한다"`` / ``"개조식"``. 주면 다른 문체로 끝나는
    문장을 *register_severity* 로 지적한다. 마침표 없는 개조식 줄은 합니다체·
    한다체 문서에서도 허용한다(표 칸, 글머리표 줄).

    표기(줄표, 가운뎃점), 식별자 굵게, 편집 흔적, 문체는 길이와 상관없이 본다 —
    짧은 줄에서도 똑같이 눈에 띈다.
    """
    if mode not in MODES:
        raise ValueError(f"mode 는 {MODES} 중 하나: {mode!r}")
    reg = _resolve_register(register)
    out: list[Finding] = []
    plain = _plain(markup)

    def add(kind, sev, text, hint):
        out.append(Finding(kind, sev, where, text, hint))

    def around(m, n=8):
        return plain[max(0, m.start() - n): m.end() + n].strip()

    # 0. 길이와 무관한 검사 — 표기, 식별자 굵게, 편집 흔적, 문체.
    #    표기는 칸마다 한 줄로 묶는다 (예전 문서는 칸 하나에 열 개씩 나온다).
    for rx, mark, hint in (
            (_TYPO_DASH, "—", "줄표는 사람이 치지 않는다 — 쉼표·괄호·문장 나눔으로, "
                              "꼭 필요하면 '-'"),
            (_TYPO_EN, "–", "'-' 로"),
            (_TYPO_MIDDOT, "·", "가운뎃점 대신 '/' 또는 '와/과' "
                                "(기술/사업화, 기술과 사업화)")):
        hits = list(rx.finditer(plain))
        if hits:
            eg = ", ".join(around(m, 5) for m in hits[:2])
            add("typography", "fix", f"'{mark}' ×{len(hits)} ({eg})", hint)
    for span in re.findall(r"\*\*(.+?)\*\*", markup):
        if is_identifier(_plain(span)):
            add("bold-id", "fix", span,
                "특허·논문·문서 번호는 굵게 하지 않는다 — 굵게는 크기(숫자)와 핵심어에")
    for m in EDIT_TRACES.finditer(plain):
        add("edit-trace", "fix", around(m, 10),
            "편집 흔적 — 받는 사람에게는 소음이다. 지운다")
    if reg:
        for sent in _sentences(plain):
            got = sentence_register(sent) if len(_plain(sent).strip()) >= 6 else None
            if got and got != reg:
                add("register", register_severity,
                    sent[:40] + ("…" if len(sent) > 40 else ""),
                    f"{_REGISTER_NAME[got]} — 이 문서는 {_REGISTER_NAME[reg]}"
                    + (" (마침표 없는 명사형 종결)" if reg == "gaejo" else ""))

    if len(plain.strip()) < MIN_BLOCK_CHARS:
        return out
    sents = _sentences(plain)
    bold, high, ratio = _emphasis_stats(markup)
    heading_like = ratio >= 0.95 and len(sents) <= 2
    label_like = _looks_like_label(plain)
    prose_like = not heading_like and not label_like
    if label and _NO_EMPHASIS_LABELS.search(label):
        emphasis = False

    research = mode == "research"

    # 1. 어휘
    for phrase, hint in CLICHES.items():
        if phrase in plain:
            add("cliche", "fix", phrase, hint)
    # 연구 문서에서 의견을 낮춰 말하는 것("~인 것 같습니다")은 결함이 아니다.
    if not research:
        for phrase, hint in HEDGES.items():
            if phrase in plain:
                add("hedge", "fix", phrase, hint)
    for phrase, hint in OVERCLAIMS.items():
        if phrase in plain:
            add("overclaim", "fix" if research else "note", phrase, hint)
    for m in _CLAIM_READING.finditer(plain):
        add("overclaim", "fix" if research else "note", m.group(0)[:40],
            "청구항 해석을 단정하지 않는다 — '해당하는지는 변리사 검토가 필요합니다'")
    for phrase, hint in TRANSLATIONESE.items():
        n = plain.count(phrase)
        if n >= 2:
            add("translationese", "fix", f"{phrase} ×{n}", hint)
    heads = [s for s in sents if any(s.startswith(c) for c in CONNECTORS)]
    if len(heads) >= 2:
        add("connector", "fix", " / ".join(h[:12] for h in heads[:3]),
            "접속 부사로 시작하는 문장이 여럿 — 대부분 지워도 이어진다")
    for w in INTENSIFIERS:
        if w in plain:
            add("intensifier", "note", w, "정도를 숫자로")

    if not prose_like:
        return out

    # 2. 문장 단위
    for s in sents:
        # 마침표로 끝나는 문장은 100자, 마침표 없는 개조식 줄은 150자까지.
        limit = MAX_SENTENCE_CHARS if re.search(r"[.!?。]$", s) else MAX_LINE_CHARS
        if len(s) > limit:
            add("long", "fix", s[:40] + "…", f"{len(s)}자 — 둘로 나눈다")
        if (any(w in s for w in CLAIM_WORDS) and not _DIGIT.search(s)
                and "**" not in _slice_markup(markup, s)):
            add("claim", "fix", s[:40] + "…",
                "숫자 없는 주장 — 얼마나, 무엇에 비해, 어떻게 쟀는지")
    for m in _TRIPLE_ETC.finditer(plain):
        add("triple", "note", m.group(0)[:40],
            "'A, B, C 등' — 필요한 것만 남기거나 표로 옮긴다")
    if len(sents) >= 4:
        lens = [len(s) for s in sents]
        if statistics.pstdev(lens) / (statistics.mean(lens) or 1) < 0.2:
            add("monotone", "note", f"{len(sents)}문장 길이 {min(lens)}~{max(lens)}자",
                "문장 길이가 균일 — 짧은 문장 하나를 섞는다")
        starts = [s[:2] for s in sents]
        for i in range(len(starts) - 2):
            if starts[i] == starts[i + 1] == starts[i + 2]:
                add("monotone", "note", f"'{starts[i]}…' ×3 연속",
                    "같은 말로 시작하는 문장 연속 — 주어를 바꾸거나 합친다")
                break
    if len(sents) >= 3 and not _DIGIT.search(plain):
        add("no-figure", "fix" if len(sents) >= 4 and not research else "note",
            plain[:30] + "…",
            "숫자가 하나도 없다 — 규모·기간·비율 하나는 넣는다")

    # 3. 강조 밀도
    if emphasis:
        if bold == 0 and high == 0:
            # 형광펜이 있으면 훑어 읽을 발판은 있는 것이다. 굵게까지 강요하지 않는다.
            add("no-bold", "fix" if len(sents) >= 2 else "note", plain[:30] + "…",
                "강조 없음 — 숫자와 핵심어를 **…** 로 (심사자는 굵은 글자만 훑는다)")
        if len(sents) >= 3 and high == 0:
            add("no-highlight", "fix", plain[:30] + "…",
                "형광펜 없음 — 이 칸에서 기억해야 할 한 문장을 ==…== 로")
        if ratio > MAX_EMPHASIS_RATIO:
            add("over-emphasis", "fix", f"{ratio:.0%} 강조",
                "절반 넘게 강조 — 전부 강조하면 아무것도 강조되지 않는다")
        if high > MAX_HIGHLIGHTS_PER_BLOCK:
            add("too-many-highlights", "note", f"형광펜 {high}개",
                "한 칸에 형광펜은 한두 줄 — 나머지는 굵게로 내린다")
    return out


def _slice_markup(markup: str, plain_sentence: str) -> str:
    """*plain_sentence* 에 해당하는 마크업 조각(굵게 여부 판단용)."""
    key = plain_sentence[:12]
    i = _plain(markup).find(key)
    if i < 0:
        return markup
    # 마크업 문자를 세지 않는 대략적 대응. 굵게가 있는지만 보므로 충분하다.
    j = 0
    seen = 0
    while j < len(markup) and seen < i:
        if markup.startswith("**", j) or markup.startswith("==", j):
            j += 2
            continue
        j += 1
        seen += 1
    return markup[max(0, j - 2): j + len(plain_sentence) + 8]


def _all_strings(content) -> list[str]:
    if isinstance(content, str):
        return [content]
    if hasattr(content, "headers") and hasattr(content, "rows"):
        return [v for row in content.rows for v in row if isinstance(v, str)]
    if isinstance(content, dict):
        return [x for v in content.values() for x in _all_strings(v)]
    if isinstance(content, (list, tuple)):
        return [x for v in content for x in _all_strings(v)]
    return []


def review_blocks(content, *, where: str = "", mode: str = "pitch",
                  register: str | None = None) -> list[Finding]:
    """문자열·list·tuple·dict 가 섞인 내용 구조를 재귀적으로 검토한다.

    ``container_box`` 에 넘기는 ``[(라벨, [줄, Grid, 줄]), ...]`` 를 그대로
    넘기면 된다. ``Grid`` 의 칸은 상투어만 보고 강조 규칙은 적용하지 않는다.

    *register* 를 비우면 원고 전체에서 가장 많은 문체를 기준으로 삼아, 다른
    문체로 끝나는 문장을 FIX 로 잡는다 — 원고는 전부 작성자 글이라 섞이면 결함이다.
    """
    reg = _resolve_register(register)
    if reg is None:
        dom, counts = detect_register(_all_strings(content))
        reg = dom if dom and len(counts) > 1 else None
    return _review_blocks(content, where, mode, reg)


def _review_blocks(content, where: str, mode: str, reg: str | None) -> list[Finding]:
    out: list[Finding] = []
    if isinstance(content, str):
        out.extend(review_text(content, where=where, mode=mode, register=reg))
    elif hasattr(content, "headers") and hasattr(content, "rows"):     # Grid
        for r, row in enumerate(getattr(content, "rows")):
            for c, val in enumerate(row):
                if isinstance(val, str):
                    out.extend(review_text(val, where=f"{where}/grid r{r}c{c}",
                                           emphasis=False, mode=mode, register=reg))
    elif isinstance(content, dict):
        for k, v in content.items():
            out.extend(_review_blocks(v, f"{where}/{k}" if where else str(k), mode, reg))
    elif isinstance(content, (list, tuple)):
        # (라벨, 내용) 쌍이면 라벨을 이름으로 쓴다.
        if (len(content) == 2 and isinstance(content[0], str)
                and isinstance(content[1], (list, tuple))):
            label = content[0].strip(" □·※▪○")[:16]
            here = f"{where}/{label}" if where else label
            # 라벨 자체도 표기 검사는 받는다 ("□ 기술·사업화").
            out.extend(review_text(content[0], where=here, emphasis=False, mode=mode))
            out.extend(_review_blocks(content[1], here, mode, reg))
        else:
            # 문자열 줄들은 한 칸의 문단들이므로 묶어서 본다 (강조 밀도는 칸 단위).
            texts = [x for x in content if isinstance(x, str)]
            if texts:
                out.extend(review_text("\n".join(texts), where=where, mode=mode,
                                       register=reg))
            for i, x in enumerate(content):
                if isinstance(x, str):
                    continue
                is_pair = (isinstance(x, (list, tuple)) and len(x) == 2
                           and isinstance(x[0], str) and isinstance(x[1], (list, tuple)))
                sub = where if is_pair else (f"{where}#{i}" if where else f"#{i}")
                out.extend(_review_blocks(x, sub, mode, reg))
    return out


# ------------------------------------------------------------ 문서 검토 --

def _bold_ids(header_root) -> set[str]:
    ids = set()
    for cp in header_root.iter(f"{HH}charPr"):
        if cp.find(f"{HH}bold") is not None:
            ids.add(cp.get("id"))
    return ids


def _para_markup(p_el, bold_ids: set[str]) -> str:
    """문단을 ``**굵게**`` / ``==형광펜==`` 마크업 문자열로 되돌린다."""
    parts: list[str] = []
    mark_open = False
    for run in p_el.findall(f"{HP}run"):
        bold = run.get("charPrIDRef") in bold_ids
        for t in run.findall(f"{HP}t"):
            buf: list[str] = []
            if t.text:
                buf.append(t.text)
            for child in t:
                tag = child.tag.split("}")[1]
                if tag == "markpenBegin":
                    buf.append("==")
                    mark_open = True
                elif tag == "markpenEnd":
                    if mark_open:
                        buf.append("==")
                        mark_open = False
                elif tag == "lineBreak":
                    buf.append("\n")
                elif tag == "tab":
                    buf.append("\t")
                if child.tail:
                    buf.append(child.tail)
            s = "".join(buf)
            if s.strip() and bold:
                s = f"**{s}**"
            parts.append(s)
    if mark_open:
        parts.append("==")
    text = "".join(parts)
    # 굵은 run 이 이어지면 하나로 합친다 ("**a****b**" → "**ab**").
    return text.replace("****", "")


def _walk(sec_root, bold_ids: set[str]):
    """(경로, [문단 마크업, ...], 라벨) 을 문서 순서대로 낸다. 표는 셀 단위.

    라벨은 그 칸의 **왼쪽 칸**(2열 label-value 표) 또는 **바로 위 행**
    (1열 container 표)의 짧은 글이다. 검토 규칙이 출처·연락처 칸을 가려내는 데
    쓴다. 확실하지 않으면 빈 문자열.
    """
    tables = 0

    def cell_blocks(tbl, prefix: str):
        nonlocal tables
        tno = tables
        tables += 1
        trs = tbl.findall(f"{HP}tr")
        ncols = max((len(tr.findall(f"{HP}tc")) for tr in trs), default=0)
        cells: dict[tuple[int, int], tuple] = {}
        for r, tr in enumerate(trs):
            for c, tc in enumerate(tr.findall(f"{HP}tc")):
                cells[(r, c)] = (tc, tc.find(f"{HP}subList"))
        plain_first: dict[tuple[int, int], str] = {}
        for key, (tc, sub) in cells.items():
            if sub is None:
                continue
            for p in sub.findall(f"{HP}p"):
                if p.find(f"./{HP}run/{HP}tbl") is None:
                    t = _plain(_para_markup(p, bold_ids)).strip()
                    if t:
                        plain_first[key] = t
                        break

        def label_of(r: int, c: int) -> str:
            if c > 0 and len(plain_first.get((r, c - 1), "")) < 40:
                return plain_first.get((r, c - 1), "")
            if ncols == 1 and r > 0 and len(plain_first.get((r - 1, 0), "")) < 60:
                return plain_first.get((r - 1, 0), "")
            return ""

        for (r, c), (tc, sub) in cells.items():
            if sub is None:
                continue
            path = f"{prefix}t{tno}/r{r}c{c}"
            label = label_of(r, c)
            paras: list[str] = []
            for p in sub.findall(f"{HP}p"):
                inner = p.find(f"./{HP}run/{HP}tbl")
                if inner is not None:
                    if paras:
                        yield path, paras, label
                        paras = []
                    yield from cell_blocks(inner, path + "/")
                    continue
                m = _para_markup(p, bold_ids)
                if m.strip():
                    paras.append(m)
            if paras:
                yield path, paras, label

    body: list[str] = []
    for p in sec_root.findall(f"{HP}p"):
        tbl = p.find(f"./{HP}run/{HP}tbl")
        if tbl is not None:
            if body:
                yield "body", body, ""
                body = []
            yield from cell_blocks(tbl, "")
            continue
        m = _para_markup(p, bold_ids)
        if m.strip():
            body.append(m)
    if body:
        yield "body", body, ""


def _load(path: str | Path):
    with zipfile.ZipFile(path) as z:
        sec = ET.fromstring(z.read("Contents/section0.xml"))
        header = ET.fromstring(z.read("Contents/header.xml"))
    return sec, header


def review_document(path: str | Path, *, mode: str = "pitch",
                    register: str | None = None) -> ProseReport:
    """HWPX 의 모든 내용 칸을 검토한다. 짧은 칸(라벨·표 데이터)은 건너뛴다.

    *register* 를 주면 다른 문체 문장이 FIX 다. 비우면 문서에서 가장 많은 문체를
    기준으로 섞인 문장을 **note** 로만 알린다 — 양식의 안내문("…바랍니다")이
    본문과 문체가 다른 것은 흔하고, 그건 고칠 수 없다.
    """
    sec, header = _load(path)
    bold_ids = _bold_ids(header)
    report = ProseReport()
    blocks = list(_walk(sec, bold_ids))
    reg = _resolve_register(register)
    reg_sev = "fix"
    if reg is None:
        dom, counts = detect_register(
            "\n".join(paras) for _, paras, _ in blocks
            if len(_plain("\n".join(paras)).strip()) >= MIN_BLOCK_CHARS)
        reg, reg_sev = (dom if dom and len(counts) > 1 else None), "note"
    for where, paras, label in blocks:
        # 본문(박스 사이)은 제목·캡션이 대부분이라 문단마다 따로 본다. 캡션
        # ("[그림 1] …", "※ …")과 두 문장 이하의 본문 문단에는 강조 규칙을
        # 적용하지 않는다.
        units = [[p] for p in paras] if where == "body" else [paras]
        for unit in units:
            markup = "\n".join(unit)
            plain = _plain(markup).strip()
            if len(plain) < MIN_BLOCK_CHARS:
                continue
            caption = where == "body" and (plain.startswith(("[", "※", "<", "(", "출처"))
                                           or len(_sentences(plain)) < 3)
            report.blocks += 1
            report.findings.extend(review_text(markup, where=where,
                                               emphasis=not caption, label=label,
                                               mode=mode, register=reg,
                                               register_severity=reg_sev))
    return report


def dump_text(path: str | Path) -> str:
    """읽는 사람의 자리에서 다시 읽기 위한 평문 덤프. 강조는 마크업으로 남긴다.

    검토의 마지막 단계는 기계가 아니라 읽기다. 이 출력에서 굵은 글자와 형광펜만
    먼저 훑어 보고 — 심사자가 그렇게 읽는다 — 그것만으로 무슨 사업인지, 왜
    지금인지, 얼마나 큰지가 전달되는지 본다. 안 되면 강조 자리가 틀린 것이다.
    """
    sec, header = _load(path)
    bold_ids = _bold_ids(header)
    out: list[str] = []
    for where, paras, label in _walk(sec, bold_ids):
        out.append(f"--- {where}" + (f"  ({label[:30]})" if label else ""))
        out.extend(paras)
        out.append("")
    return "\n".join(out)


# ------------------------------------------------------------- 자동 강조 --

_UNITS = ("개월", "개소", "개교", "개체", "가지", "단계", "시간", "퍼센트", "%p", "%",
          "명", "개", "건", "원", "억", "만", "천", "배", "년", "월", "주", "일", "분",
          "초", "회", "종", "대", "곳", "점", "위", "차", "호", "쪽", "층", "층", "kg",
          "km", "mm", "cm", "m", "g", "㎡", "㎢", "㎾", "kWh", "GB", "MB", "TB", "℃")
_NUM = r"\d(?:[\d,]*\d)?(?:\.\d+)?"          # 끝의 쉼표는 문장부호다
_FIGURE = re.compile(
    r"(?<![\w./@:\-#])"                                  # URL·코드·식별자 안이면 제외
    r"(" + _NUM + r"(?:\s?[/~±–\-]\s?" + _NUM + r")*"     # 318/342, 3~5, 38.8±2.7
    r"(?:\s?(?:억\s?원|만\s?원|" + "|".join(re.escape(u) for u in _UNITS) + r"))?)"
    # 뒤에 라틴 글자·숫자가 붙으면 식별자다 (3D, 5G, U300 의 일부). 한글 조사는
    # 붙어도 된다 — "3단계로", "12억 원이다" 의 숫자는 강조 대상이다.
    r"(?![A-Za-z0-9])"
)
_SPAN_SPLIT = re.compile(r"(\*\*==.+?==\*\*|==\*\*.+?\*\*==|\*\*.+?\*\*|==.+?==)")


def bold_figures(markup: str) -> str:
    """이미 강조되지 않은 숫자(단위 포함)를 ``**…**`` 로 감싼다. 멱등이다.

    ``93.0%``, ``318/342``, ``3개월``, ``2억 원``, ``38.8 ± 2.7`` 이 대상이고,
    URL·이메일·식별자(``U300``, ``fig1``, 출원번호 ``10-2023-0012345``) 안의
    숫자는 건드리지 않는다. 심사자가
    훑어 읽을 때 눈이 멈추는 자리를 숫자로 만드는 가장 싼 방법이다. 표 칸에는
    쓰지 않는다 — 전부 숫자라 전부 굵어진다.
    """
    out: list[str] = []
    for chunk in _SPAN_SPLIT.split(markup):
        if not chunk:
            continue
        if chunk.startswith("**") or chunk.startswith("=="):
            out.append(chunk)
            continue
        out.append(_FIGURE.sub(
            lambda m: m.group(0) if is_identifier(m.group(1)) else f"**{m.group(1)}**",
            chunk))
    return "".join(out)


# --------------------------------------------------------------------- CLI --

def _main(argv: Sequence[str]) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        print("usage: python -m hwpxkit.prose <file.hwpx> [--dump] "
              "[--mode pitch|research] [--register 합니다|한다|개조식]\n"
              "  검토 보고서를 낸다. --dump 는 다시 읽기용 평문(강조 마크업 포함)을 낸다.")
        return 2
    path = argv[0]
    if "--dump" in argv:
        print(dump_text(path))
        return 0

    def opt(name):
        return argv[argv.index(name) + 1] if name in argv[:-1] else None

    rep = review_document(path, mode=opt("--mode") or "pitch",
                          register=opt("--register"))
    print(rep.render())
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
