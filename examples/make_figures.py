"""보고서용 그림 2장을 그린다 (examples/build_research_report.py 가 쓴다).

    python examples/make_figures.py

- 범주형 색: 검증 통과한 슬롯 1~3 (#2a78d6 파랑, #eb6834 주황, #1baf7a 아쿠아)
- 색만으로 식별하지 않는다: 마커 모양도 종마다 다르게 (원/삼각형/사각형)
- 마커 >= 8px, 겹치는 점에 표면색 링 2px
- 축/격자는 뒤로 물러나게, 텍스트는 색이 아니라 잉크색
"""
import csv, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager

# 한글 라벨용 폰트
for cand in ("Malgun Gothic", "NanumGothic", "AppleGothic"):
    if any(cand in f.name for f in font_manager.fontManager.ttflist):
        plt.rcParams["font.family"] = cand
        break
plt.rcParams["axes.unicode_minus"] = False

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK2 = "#52514e"
GRID = "#e3e2df"
COLORS = {"Adelie": "#2a78d6", "Chinstrap": "#eb6834", "Gentoo": "#1baf7a"}
MARKERS = {"Adelie": "o", "Chinstrap": "^", "Gentoo": "s"}
KO = {"Adelie": "아델리", "Chinstrap": "턱끈", "Gentoo": "젠투"}

NUM = ("bill_length_mm", "bill_depth_mm", "flipper_length_mm", "body_mass_g")
rows = []
with open(r"C:\hwpx-builder\examples\data\penguins.csv", encoding="utf-8") as fh:
    for r in csv.DictReader(fh):
        if all(r[c] and r[c] != "NA" for c in NUM):
            rows.append({**{c: float(r[c]) for c in NUM}, "species": r["species"]})

OUT = r"C:\hwpx-builder\examples\images"
os.makedirs(OUT, exist_ok=True)


def style(ax, xlabel, ylabel):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    ax.set_xlabel(xlabel, color=INK2, fontsize=10)
    ax.set_ylabel(ylabel, color=INK2, fontsize=10)
    ax.tick_params(colors=INK2, labelsize=9)
    ax.grid(True, color=GRID, linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)


def scatter(ax, xcol, ycol):
    for sp in ("Adelie", "Chinstrap", "Gentoo"):
        pts = [r for r in rows if r["species"] == sp]
        ax.scatter([p[xcol] for p in pts], [p[ycol] for p in pts],
                   s=46, c=COLORS[sp], marker=MARKERS[sp],
                   edgecolors=SURFACE, linewidths=1.4,   # 겹치는 점 분리용 링
                   label=f"{KO[sp]} (n={len(pts)})", zorder=3, alpha=0.92)


# --- 그림 1: 부리 2변수 + 분류 경계 -------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
scatter(ax, "bill_length_mm", "bill_depth_mm")
ax.set_ylim(12.6, 22.4)          # 라벨 자리를 확보하고 경계선 좌표를 고정
ax.set_xlim(31, 61)
lo, hi = ax.get_ylim()
# 가로선: 젠투를 나머지에서 분리. 세로선: 그 *위쪽*에서만 아델리/턱끈을 가른다.
ax.axhline(16.5, color=INK2, linestyle="--", linewidth=1.6, zorder=2)
ax.axvline(44.9, color=INK2, linestyle="--", linewidth=1.6, zorder=2,
           ymin=(16.5 - lo) / (hi - lo), ymax=1.0)
ax.text(31.4, 14.6, "부리 깊이 16.5 mm 아래 → 젠투", ha="left", va="top",
        color=INK2, fontsize=8.5)
ax.text(45.5, 22.1, "부리 길이 44.9 mm", ha="left", va="top",
        color=INK2, fontsize=8.5)
style(ax, "부리 길이 (mm)", "부리 깊이 (mm)")
ax.legend(loc="lower right", frameon=False, fontsize=9, labelcolor=INK)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig1_bill.png"), facecolor=SURFACE)
print("fig1_bill.png")

# --- 그림 2: 날개 길이 x 체중 -------------------------------------------
fig, ax = plt.subplots(figsize=(7.2, 4.6), dpi=200)
scatter(ax, "flipper_length_mm", "body_mass_g")
style(ax, "날개 길이 (mm)", "체중 (g)")
ax.legend(loc="upper left", frameon=False, fontsize=9, labelcolor=INK)
fig.tight_layout()
fig.savefig(os.path.join(OUT, "fig2_flipper.png"), facecolor=SURFACE)
print("fig2_flipper.png")

for n in ("fig1_bill.png", "fig2_flipper.png"):
    print(f"  {n}: {os.path.getsize(os.path.join(OUT, n))//1024} KB")
