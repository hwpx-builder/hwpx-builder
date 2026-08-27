"""구식 ``.hwp`` 바이너리를 **읽기 전용**으로 훑는다.

왜 따로 있나. ``.hwp`` 를 다시 HWPX 로 바꿔서 확인하는 방식은 두 번 배신했다.

* ``pyhwpxlib`` 리더는 그림 참조를 전부 첫 장으로 뭉갠다 (실측: U300 그림 13장이
  모두 같은 그림으로 보인다).
* ``hwp2hwpx`` 리더는 형광펜을 아예 잃고, 표 쪽나눔 모드를 뒤집어 읽는다.

그래서 "왕복해서 세어 보니 0 개더라"가 **파일에 없다는 뜻이 아니다.** 실제로
형광펜 8개가 멀쩡히 들어 있는 파일을 두고 "다 날아갔다"고 볼 뻔했다. 검증은
리더를 믿지 말고 바이트를 직접 봐야 한다.

레코드 구조(HWP 5.x): 32비트 헤더 = tagID(10) | level(10) | size(12).
size 가 ``0xFFF`` 면 이어지는 4바이트가 진짜 크기다. 본문 스트림은 보통
raw-deflate 로 압축돼 있고, 압축 여부는 ``FileHeader`` 의 37번째 바이트 bit0 이다.

``olefile`` 만 있으면 되고 PolyForm 패키지는 건드리지 않는다.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path
from typing import Iterator

_BEGIN = 0x010
TAG_PARA_HEADER = _BEGIN + 50
TAG_PARA_TEXT = _BEGIN + 51
TAG_PARA_RANGE_TAG = _BEGIN + 54
TAG_TABLE = _BEGIN + 61
TAG_SHAPE_COMPONENT_PICTURE = _BEGIN + 69

#: ``PARA_RANGE_TAG`` 의 sort 값 중 형광펜. data 는 24비트 BGR.
RANGE_SORT_MARKPEN = 2

#: 표 속성 bits 0~1. 한컴이 만든 파일과 그 짝 HWPX 를 대조해 확인한 매핑이다 —
#: 양식.hwp 표 5개 / 온리브.hwp 표 26개 모두 바이너리 **2** 였고, 같은 문서의
#: 한컴 산출 HWPX 는 그 표들을 ``pageBreak="CELL"`` 로 적었다. 공식 스펙 표 76 은
#: 값 2 를 "나누지 않음"으로 중복 표기한 오류가 있어 믿을 수 없다.
SPLIT_TO_HWPX = {0: "NONE", 1: "TABLE", 2: "CELL", 3: "CELL"}


def _sections(path: Path):
    import olefile

    ole = olefile.OleFileIO(str(path))
    try:
        compressed = bool(ole.openstream("FileHeader").read()[36] & 0x01)
        names = sorted("/".join(s) for s in ole.listdir()
                       if s and s[0] == "BodyText")
        for name in names:
            raw = ole.openstream(name).read()
            yield name, (zlib.decompress(raw, -15) if compressed else raw)
    finally:
        ole.close()


def records(path: str | Path) -> Iterator[tuple[str, int, int, bytes]]:
    """``(스트림 이름, tagID, level, payload)`` 를 문서 순서대로."""
    for name, data in _sections(Path(path)):
        i = 0
        while i + 4 <= len(data):
            (head,) = struct.unpack_from("<I", data, i)
            tag = head & 0x3FF
            level = (head >> 10) & 0x3FF
            size = (head >> 20) & 0xFFF
            i += 4
            if size == 0xFFF:
                (size,) = struct.unpack_from("<I", data, i)
                i += 4
            yield name, tag, level, data[i:i + size]
            i += size


def table_split_modes(path: str | Path) -> list[int]:
    """표마다 '쪽 나눔' 모드(bits 0~1)를 문서 순서대로."""
    out = []
    for _, tag, _, body in records(path):
        if tag == TAG_TABLE and len(body) >= 4:
            out.append(struct.unpack_from("<I", body, 0)[0] & 0x3)
    return out


def markpen_ranges(path: str | Path) -> list[tuple[int, int, int, str]]:
    """형광펜 구간을 ``(문단 번호, 시작, 끝, "#RRGGBB")`` 로.

    문단 번호는 ``PARA_HEADER`` 를 문서 순서대로 0 부터 센 값이다. 구간은
    컨트롤 문자를 포함한 WCHAR 인덱스이고 끝은 제외(exclusive)다.
    """
    out: list[tuple[int, int, int, str]] = []
    para = -1
    for _, tag, _, body in records(path):
        if tag == TAG_PARA_HEADER:
            para += 1
        elif tag == TAG_PARA_RANGE_TAG:
            for j in range(0, len(body) - 11, 12):
                start, end, raw = struct.unpack_from("<III", body, j)
                if (raw >> 24) & 0xFF != RANGE_SORT_MARKPEN:
                    continue
                bgr = raw & 0xFFFFFF
                rgb = f"#{bgr & 0xFF:02X}{(bgr >> 8) & 0xFF:02X}{(bgr >> 16) & 0xFF:02X}"
                out.append((para, start, end, rgb))
    return out


def counts(path: str | Path) -> dict[str, int]:
    """빠른 요약. ``to_hwp`` 검증이 리더를 거치지 않고 쓰는 값이다."""
    tally = {"paragraphs": 0, "tables": 0, "pictures": 0, "markpen": 0}
    for _, tag, _, body in records(path):
        if tag == TAG_PARA_HEADER:
            tally["paragraphs"] += 1
        elif tag == TAG_TABLE:
            tally["tables"] += 1
        elif tag == TAG_SHAPE_COMPONENT_PICTURE:
            tally["pictures"] += 1
        elif tag == TAG_PARA_RANGE_TAG:
            tally["markpen"] += sum(
                1 for j in range(0, len(body) - 11, 12)
                if (struct.unpack_from("<III", body, j)[2] >> 24) & 0xFF
                == RANGE_SORT_MARKPEN)
    return tally


def bindata_names(path: str | Path) -> list[str]:
    """``BinData`` 스트림 이름 목록."""
    import olefile

    ole = olefile.OleFileIO(str(path))
    try:
        return sorted("/".join(s) for s in ole.listdir() if s and s[0] == "BinData")
    finally:
        ole.close()
