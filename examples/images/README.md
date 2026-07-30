# 예제용 이미지

`build_comparison_report.py` 가 문서에 넣는 사진들. 둘 다 **CC0**(퍼블릭 도메인
헌정)라 출처 표시 의무 없이 어떤 용도로든 쓸 수 있지만, 이 저장소의 방침대로
어디서 왔는지 기록해 둔다.

| 파일 | 출처 | 라이선스 | 촬영자 |
|---|---|---|---|
| `dog.jpg` | [Portrait of a labrador retriever](https://commons.wikimedia.org/wiki/File:Portrait_of_a_labrador_retriever.jpg) (Wikimedia Commons) | CC0 1.0 | Dktue |
| `cat.jpg` | [Tabby cat with blue eyes](https://commons.wikimedia.org/wiki/File:Tabby_cat_with_blue_eyes-3336579.jpg) (Wikimedia Commons) | CC0 1.0 | AdinaVoicu |

원본은 각각 6240×4160, 2877×3456 이었다. 저장소에 넣기 위해 긴 변 1400 px 로
줄이고 JPEG 품질 82 로 다시 저장했다(합계 10.7 MB → 363 KB). 문서에는 폭
100 mm 로 들어가므로 이 해상도면 충분하다.

두 파일 중 하나라도 없으면 예제는 사진을 지어내지 않고 눈에 보이는
`image_placeholder` 를 넣는다. 제출 문서에서 틀린 이미지는 빈칸보다 나쁘다.

## 그림 (생성물)

`fig1_bill.png`, `fig2_flipper.png` 는 `examples/make_figures.py` 가
`examples/data/penguins.csv` 로 그린 것이다. 데이터가 CC0 이고 그림도 이
저장소에서 만든 것이므로 제약이 없다. 다시 그리려면:

```bash
pip install matplotlib
python examples/make_figures.py
```

색은 dataviz 가이드의 검증 통과 팔레트(슬롯 1~3)를 쓰고, 색맹·흑백 인쇄를
고려해 종마다 마커 모양도 다르게 했다(원/삼각형/사각형).
