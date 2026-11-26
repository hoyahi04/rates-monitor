"""2015년부터 규칙대로 운용했다고 보고 포트폴리오를 다시 계산한다 → portfolio.js

모형 (공개 자료인 재무부 CMT 금리만 사용)
  - 만기 구간 6개마다 "그달 초에 액면가로 발행된 국채" 한 종목을 든다 (대표 만기 2·4·6·8.5·15·25년).
    쿠폰 = 그날의 par 금리. 매일 그날 금리로 다시 값을 매긴다 (이자, 롤다운, 금리 변화가 모두 들어감).
  - 벤치마크 = 여섯 구간을 대용 지수 비중으로 든 것 (비중은 지금 값을 과거에도 그대로 씀).
  - 포트폴리오 = 벤치마크 + 점수표 규칙이 지시한 포지션. 매달 마지막 영업일 종가에 리밸런싱.
      Duration  ±0.25/±0.5년 : 여섯 구간 모두에서 만기를 조금씩 옮김 (벤치마크 듀레이션 기여 비율대로, 비중은 그대로)
      Slope     ±0.10년      : 1–3년 구간과 20년+ 구간 안에서 만기를 옮김
      Curvature 불릿 0.10년   : 5–7년 구간 만기를 늘리고 1–3년, 10–20년 구간 만기를 줄임
  - 거래비용 0. 실제 종목이 아니라 모형 채권이므로 종목 선택 효과는 없다.

실행:  python3 backtest.py     (표준 라이브러리만)
"""
import csv, json, math
from datetime import datetime, date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
NAV0 = 10_000_000.0
BUCKETS = [("1-3", "1–3년", 1, 3, 2.0), ("3-5", "3–5년", 3, 5, 4.0), ("5-7", "5–7년", 5, 7, 6.0),
           ("7-10", "7–10년", 7, 10, 8.5), ("10-20", "10–20년", 10, 20, 15.0), ("20+", "20년+", 20, 30, 25.0)]
BM_W_FALLBACK = [34.69, 22.39, 12.81, 9.32, 9.65, 11.13]
SLOPE_LEG, BULLET_LEG = 0.10, 0.10
TE_BUDGET = [50, 100]
SIG = [("s1_policy", "정책"), ("s2_growth", "성장"), ("s3_inflation", "물가"), ("s4_supply", "수급"), ("s5_liquidity_vol", "변동성")]
TEN_Y = {"1M": 1 / 12, "3M": .25, "6M": .5, "1Y": 1, "2Y": 2, "3Y": 3, "5Y": 5, "7Y": 7, "10Y": 10, "20Y": 20, "30Y": 30}


def load_js(p):
    s = p.read_text(encoding="utf-8")
    return json.loads(s[s.index("{"): s.rindex("}") + 1])


U = load_js(ROOT / "inputs" / "curve" / "data.js")
DATES = U["dates"]
TEN = sorted(TEN_Y.items(), key=lambda kv: kv[1])
IDX = {d: i for i, d in enumerate(DATES)}


def curve(i, m):
    """i번째 날의 만기 m년 par 금리(%). 만기 사이는 직선으로 잇는다."""
    pts = [(y, U["yields"][k][i]) for k, y in TEN if U["yields"][k][i] is not None]
    if m <= pts[0][0]:
        return pts[0][1]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        if m <= x1:
            return y0 + (y1 - y0) * (m - x0) / (x1 - x0)
    return pts[-1][1]


def price(c, y, n, f):
    """쿠폰 c%, 금리 y%, 남은 이자 횟수 n(반기), 지난 기간 비율 f → 이자 포함 가격."""
    h = y / 200
    if abs(h) < 1e-9:
        return 100 + c / 2 * n
    v = 1 / (1 + h)
    return (1 + h) ** f * (c / 2 * (1 - v ** n) / h + 100 * v ** n)


def mod_dur(m, y):
    h = y / 200
    return (1 - (1 + h) ** (-2 * m)) / (y / 100) if abs(h) > 1e-9 else m


def idx_on_or_before(d):
    if d in IDX:
        return IDX[d]
    lo = [i for i, x in enumerate(DATES) if x <= d]
    return lo[-1]


def years(a, b):
    return (date.fromisoformat(b) - date.fromisoformat(a)).days / 365.25


# ---------------------------------------------------------------- 입력
rows = list(csv.DictReader(open(ROOT / "inputs" / "macro" / "scoreboard.csv", encoding="utf-8-sig")))
try:
    bp = json.loads((ROOT / "inputs" / "curve" / "initial_portfolio_wip" / "benchmark_proxy.json").read_text(encoding="utf-8"))
    BM_W = [b["weight_pct"] for b in bp["buckets"]]
except Exception:
    BM_W = BM_W_FALLBACK
tot = sum(BM_W)
BM_W = [w / tot for w in BM_W]
NODE = [b[4] for b in BUCKETS]
NB = len(BUCKETS)

starts = [idx_on_or_before(r["decision_date"]) for r in rows]
ends = starts[1:] + [len(DATES) - 1]


def build_position(i0, dur, slope, curv):
    """리밸런싱일 i0의 벤치마크와 포트폴리오(단계별) 구성."""
    y0 = [curve(i0, m) for m in NODE]
    d0 = [mod_dur(m, y) for m, y in zip(NODE, y0)]
    dbar = sum(w * d for w, d in zip(BM_W, d0))
    w_dur = list(BM_W)

    def shift(mats, w, b, target):
        """구간 b의 듀레이션 기여를 target년만큼 바꾸도록 그 구간 안에서 만기를 옮긴다."""
        lo, hi = BUCKETS[b][2] + 0.05, BUCKETS[b][3] - 0.05
        base = mod_dur(mats[b], curve(i0, mats[b]))
        f = lambda m: w[b] * (mod_dur(m, curve(i0, m)) - base) - target
        a, c = (mats[b], hi) if target > 0 else (lo, mats[b])
        if f(a) * f(c) > 0:               # 구간 끝까지 가도 모자라면 끝에서 멈춤
            mats[b] = c if target > 0 else a
            return
        for _ in range(50):
            mid = (a + c) / 2
            if f(a) * f(mid) <= 0:
                c = mid
            else:
                a = mid
        mats[b] = (a + c) / 2

    m_dur = list(NODE)
    if dur:
        for b in range(NB):
            shift(m_dur, w_dur, b, dur * BM_W[b] * d0[b] / dbar)
    m_slope = list(m_dur)
    if slope != "none":
        s = 1 if slope == "steepener" else -1
        shift(m_slope, w_dur, 0, s * SLOPE_LEG)
        shift(m_slope, w_dur, 5, -s * SLOPE_LEG)
    m_all = list(m_slope)
    if curv == "bullet":
        shift(m_all, w_dur, 2, BULLET_LEG)
        shift(m_all, w_dur, 0, -BULLET_LEG / 2)
        shift(m_all, w_dur, 4, -BULLET_LEG / 2)
    return dict(bm=(BM_W, NODE), dur=(w_dur, m_dur), slope=(w_dur, m_slope), all=(w_dur, m_all))


def value_path(i0, i1, w, mats):
    """i0에 1을 넣었을 때 i0+1..i1의 가치."""
    cps = [curve(i0, m) for m in mats]
    out = []
    for t in range(i0 + 1, i1 + 1):
        el = years(DATES[i0], DATES[t])
        out.append(sum(wb * price(c, curve(t, m - el), 2 * m, 2 * el) / 100 for wb, c, m in zip(w, cps, mats)))
    return out


def contrib(w, mats, i0):
    ys = [curve(i0, m) for m in mats]
    return [wb * mod_dur(m, y) for wb, m, y in zip(w, mats, ys)], ys


def months_ago(i0, k):
    y, m, d = int(DATES[i0][:4]), int(DATES[i0][5:7]), DATES[i0][8:]
    m -= k
    while m <= 0:
        m += 12; y -= 1
    return idx_on_or_before(f"{y:04d}-{m:02d}-{d}")


def alt_duration(i0, r):
    """개선안: 10년 금리의 최근 6개월 추세(내렸으면 +1, 올랐으면 −1) + 물가 점수. 정책·성장 점수는 쓰지 않는다."""
    ch = U["yields"]["10Y"][i0] - U["yields"]["10Y"][months_ago(i0, 6)]
    trend = (ch < 0) - (ch > 0)
    return max(-2, min(2, trend + int(r["s3_inflation"]))) * 0.25, trend


# ---------------------------------------------------------------- 운용
nav = {k: [NAV0] for k in ("bm", "dur", "slope", "all")}
nav_alt, alt_months = [NAV0], []
ser_dates = [DATES[starts[0]]]
months, log, prev_pos, prev_w = [], [], None, None
for i, r in enumerate(rows):
    i0, i1 = starts[i], ends[i]
    dur, slope, curv = float(r["duration_active_yr"]), r["slope_position"], r["curvature_position"]
    pos = build_position(i0, dur, slope, curv)
    base = {k: nav[k][-1] for k in nav}
    paths = {k: value_path(i0, i1, *pos[k]) for k in nav}
    if i1 > i0:
        for j in range(i1 - i0):
            ser_dates.append(DATES[i0 + 1 + j])
            for k in nav:
                nav[k].append(base[k] * paths[k][j])
    ret = {k: (paths[k][-1] - 1) if paths[k] else 0.0 for k in nav}
    a_dur, a_trend = alt_duration(i0, r)
    a_path = value_path(i0, i1, *build_position(i0, a_dur, slope, curv)["all"])
    a_base = nav_alt[-1]
    nav_alt.extend(a_base * v for v in a_path)
    a_ret = (a_path[-1] - 1) if a_path else 0.0
    alt_months.append(dict(month=r["apply_month"], dur=a_dur, trend=a_trend, excess_bp=round((a_ret - ret["bm"]) * 1e4, 2),
                           cur_excess_bp=round((ret["all"] - ret["bm"]) * 1e4, 2), partial=(i == len(rows) - 1)))
    cp, yp = contrib(*pos["all"], i0)
    cb, yb = contrib(*pos["bm"], i0)
    w_p, m_p = pos["all"]
    turnover = None
    m = dict(month=r["apply_month"], date=r["decision_date"], end=DATES[i1], partial=(i == len(rows) - 1),
             dur=dur, slope=slope, curv=curv,
             ret_p=ret["all"] * 100, ret_b=ret["bm"] * 100, excess_bp=(ret["all"] - ret["bm"]) * 1e4,
             c_dur=(ret["dur"] - ret["bm"]) * 1e4, c_slope=(ret["slope"] - ret["dur"]) * 1e4, c_curv=(ret["all"] - ret["slope"]) * 1e4,
             d10y_bp=round((U["yields"]["10Y"][i1] - U["yields"]["10Y"][i0]) * 100, 1),
             active_dur=sum(cp) - sum(cb), dur_p=sum(cp), dur_b=sum(cb),
             scores={k: int(r[k]) for k, _ in SIG}, view_level=int(r["view_level"]), view_slope=int(r["view_slope"]),
             regime=r["regime"])
    months.append(m)
    cur = (dur, slope, curv)
    if prev_pos is None or cur != prev_pos:
        why = []
        if prev_pos is None:
            why.append("운용 시작. 벤치마크와 같은 구성에 그달 규칙 포지션을 얹음")
        else:
            p = rows[i - 1]
            ch = [f"{nm} {int(p[k]):+d} → {int(r[k]):+d}" for k, nm in SIG if p[k] != r[k]]
            if ch:
                why.append("점수 변화: " + ", ".join(ch))
            if int(p["view_level"]) != int(r["view_level"]):
                why.append(f"수준 뷰 {int(p['view_level']):+d} → {int(r['view_level']):+d}")
            if p["slope_position"] != slope:
                why.append(f"기울기 뷰 {int(p['view_slope']):+d} → {int(r['view_slope']):+d}")
            if p["curvature_position"] != curv:
                why.append(f"Fly z-score {float(r['fly_z_3y']):+.2f}, 곡률 조건 {'충족' if curv == 'bullet' else '해제'}")
        log.append(dict(i=i, date=r["decision_date"], month=r["apply_month"], frm=prev_pos, to=cur, why=" · ".join(why),
                        turnover=turnover, excess_bp=m["excess_bp"], partial=m["partial"]))
    prev_pos, prev_w = cur, w_p
    last_state = dict(pos=pos, i0=i0, cp=cp, cb=cb, yp=yp, yb=yb)

for k in ("turnover",):
    for e in log:
        if e[k] is not None:
            e[k] = round(e[k], 1)


# ---------------------------------------------------------------- 통계
def ann(x0, x1, yrs):
    return ((x1 / x0) ** (1 / yrs) - 1) * 100


def stdev(a):
    n = len(a); mu = sum(a) / n
    return math.sqrt(sum((x - mu) ** 2 for x in a) / (n - 1))


P, Bn = nav["all"], nav["bm"]
n = len(P)
yrs = years(ser_dates[0], ser_dates[-1])
dr_p = [P[t] / P[t - 1] - 1 for t in range(1, n)]
dr_b = [Bn[t] / Bn[t - 1] - 1 for t in range(1, n)]
dex = [a - b for a, b in zip(dr_p, dr_b)]
rel = [P[t] / Bn[t] for t in range(n)]                       # 상대 가치 (1에서 시작)
ex_cum_bp = [(x - 1) * 1e4 for x in rel]


def te(a):
    return stdev(a) * math.sqrt(252) * 1e4


def maxdd(series):
    peak, worst, w0, w1, p0 = series[0], 0.0, 0, 0, 0
    for t, x in enumerate(series):
        if x > peak:
            peak, p0 = x, t
        dd = x / peak - 1
        if dd < worst:
            worst, w0, w1 = dd, p0, t
    return worst, w0, w1


dd_p = maxdd(P); dd_b = maxdd(Bn); dd_r = maxdd(rel)
full = [m for m in months if not m["partial"]]
active = [m for m in full if (m["dur"], m["slope"], m["curv"]) != (0.0, "none", "none")]
ann_p, ann_b = ann(P[0], P[-1], yrs), ann(Bn[0], Bn[-1], yrs)
te_all = te(dex)
stats = dict(
    start=ser_dates[0], end=ser_dates[-1], years=round(yrs, 2), nav0=NAV0, nav=P[-1], nav_bm=Bn[-1],
    cum_p=(P[-1] / P[0] - 1) * 100, cum_b=(Bn[-1] / Bn[0] - 1) * 100, ann_p=ann_p, ann_b=ann_b,
    excess_cum_bp=ex_cum_bp[-1], excess_ann_bp=(ann_p - ann_b) * 100,
    vol_p=stdev(dr_p) * math.sqrt(252) * 100, vol_b=stdev(dr_b) * math.sqrt(252) * 100,
    te_all_bp=te_all, te_1y_bp=te(dex[-252:]), te_3y_bp=te(dex[-756:]),
    ir=((ann_p - ann_b) * 100) / te_all if te_all else None,
    mdd_p=dd_p[0] * 100, mdd_p_from=ser_dates[dd_p[1]], mdd_p_to=ser_dates[dd_p[2]],
    mdd_b=dd_b[0] * 100, mdd_rel_bp=dd_r[0] * 1e4, mdd_rel_from=ser_dates[dd_r[1]], mdd_rel_to=ser_dates[dd_r[2]],
    months=len(full), months_active=len(active), months_win=sum(1 for m in active if m["excess_bp"] > 0),
    best=max(full, key=lambda m: m["excess_bp"]), worst=min(full, key=lambda m: m["excess_bp"]),
    n_rebal=len(log) - 1,
    c_dur=sum(m["c_dur"] for m in months), c_slope=sum(m["c_slope"] for m in months), c_curv=sum(m["c_curv"] for m in months),
    hit=dict(dur=[sum(1 for m in full if m["dur"] and m["c_dur"] > 0), sum(1 for m in full if m["dur"])],
             slope=[sum(1 for m in full if m["slope"] != "none" and m["c_slope"] > 0), sum(1 for m in full if m["slope"] != "none")],
             curv=[sum(1 for m in full if m["curv"] == "bullet" and m["c_curv"] > 0), sum(1 for m in full if m["curv"] == "bullet")]),
)
for k in ("best", "worst"):
    stats[k] = dict(month=stats[k]["month"], excess_bp=stats[k]["excess_bp"])

# 연도별
by_year = {}
for m in months:
    y = m["month"][:4]
    e = by_year.setdefault(y, dict(year=y, p=1.0, b=1.0, n=0))
    e["p"] *= 1 + m["ret_p"] / 100; e["b"] *= 1 + m["ret_b"] / 100; e["n"] += 1
years_tbl = [dict(year=y, ret_p=(e["p"] - 1) * 100, ret_b=(e["b"] - 1) * 100, excess_bp=(e["p"] - e["b"]) * 1e4, partial=e["n"] < 12)
             for y, e in sorted(by_year.items())]

# 지금 구성
st = last_state
w_p, m_p = st["pos"]["all"]
now = []
for b in range(NB):
    yb_, yp_ = st["yb"][b], st["yp"][b]
    now.append(dict(id=BUCKETS[b][0], label=BUCKETS[b][1], w_p=w_p[b] * 100, w_b=BM_W[b] * 100, mat_p=m_p[b], mat_b=NODE[b],
                    coupon=yp_, dur_p=mod_dur(m_p[b], yp_), dur_b=mod_dur(NODE[b], yb_),
                    c_p=st["cp"][b], c_b=st["cb"][b], active=st["cp"][b] - st["cb"][b]))
i0 = st["i0"]
# 초기 구성 (2015-01)
p0 = build_position(starts[0], float(rows[0]["duration_active_yr"]), rows[0]["slope_position"], rows[0]["curvature_position"])
c0, y0 = contrib(*p0["all"], starts[0]); cb0, _ = contrib(*p0["bm"], starts[0])
init = [dict(id=BUCKETS[b][0], label=BUCKETS[b][1], w_p=p0["all"][0][b] * 100, w_b=BM_W[b] * 100, mat_p=p0["all"][1][b], coupon=y0[b],
             usd=NAV0 * p0["all"][0][b], c_p=c0[b], c_b=cb0[b], active=c0[b] - cb0[b]) for b in range(NB)]

# 사전 추적오차와 시나리오 (지금 구성)
last = len(DATES) - 1
win = range(last - 749, last + 1)
chg = [[(curve(t, m) - curve(t - 1, m)) * 100 for m in NODE] for t in win]
mu = [sum(c[b] for c in chg) / len(chg) for b in range(NB)]
cov = [[sum((c[a] - mu[a]) * (c[b] - mu[b]) for c in chg) / (len(chg) - 1) * 252 for b in range(NB)] for a in range(NB)]
act = [x["active"] for x in now]
te_ex = math.sqrt(max(0.0, sum(act[a] * cov[a][b] * act[b] for a in range(NB) for b in range(NB))))
unit = [BM_W[b] * now[b]["dur_b"] for b in range(NB)]
tot_u = sum(unit)
a_max = [0.5 * u / tot_u for u in unit]
te_max = math.sqrt(sum(a_max[a] * cov[a][b] * a_max[b] for a in range(NB) for b in range(NB)))
lin = lambda lo, hi: [lo + (hi - lo) * (m - 2) / (30 - 2) for m in NODE]
SC = [("평행 +25bp", [25] * NB), ("평행 −25bp", [-25] * NB), ("평행 +50bp", [50] * NB), ("평행 −50bp", [-50] * NB),
      ("스티프닝 (2년 −25, 30년 +25)", lin(-25, 25)), ("플래트닝 (2년 +25, 30년 −25)", lin(25, -25)),
      ("벨리만 +25bp (5–7년)", [0, 0, 25, 0, 0, 0]), ("벨리만 −25bp (5–7년)", [0, 0, -25, 0, 0, 0])]
scen = [dict(label=l, bp=-sum(a * s for a, s in zip(act, sh))) for l, sh in SC]

# 개선안 통계
A = nav_alt
dex_a = [(A[t] / A[t - 1] - 1) - dr_b[t - 1] for t in range(1, n)]
ann_a = ann(A[0], A[-1], yrs)
def split(key, lo, hi):
    x = [m[key] for m in alt_months if lo <= m["month"] < hi and not m["partial"]]
    mu = sum(x) / len(x); sd = stdev(x)
    return dict(sum_bp=round(sum(x), 1), t=round(mu / sd * math.sqrt(len(x)), 2), n=len(x), win=sum(1 for v in x if v > 0), on=sum(1 for v in x if v != 0))
alt = dict(
    name="6개월 추세 + 물가", rule="10년 금리가 6개월 전보다 내렸으면 +1, 올랐으면 −1. 여기에 물가 점수를 더합니다. 정책·성장 점수는 Duration에 쓰지 않습니다.",
    nav=A[-1], excess_cum_bp=round((A[-1] / Bn[-1] - 1) * 1e4, 1), excess_ann_bp=round((ann_a - ann_b) * 100, 2),
    te_bp=round(te(dex_a), 1), ir=round(((ann_a - ann_b) * 100) / te(dex_a), 2),
    series=[round((A[t] / Bn[t] - 1) * 1e4, 2) for t in range(n)],
    now=alt_months[-1],
    train=dict(alt=split("excess_bp", "2015-01", "2021-01"), cur=split("cur_excess_bp", "2015-01", "2021-01")),
    test=dict(alt=split("excess_bp", "2021-01", "2099-01"), cur=split("cur_excess_bp", "2021-01", "2099-01")),
)

r4 = lambda x: None if x is None else round(x, 4)
out = dict(
    generated=datetime.now().strftime("%Y-%m-%d %H:%M"), asof=DATES[last], decision_date=rows[-1]["decision_date"], apply_month=rows[-1]["apply_month"],
    model=dict(nodes=NODE, bm_weights=[round(w * 100, 2) for w in BM_W], slope_leg=SLOPE_LEG, bullet_leg=BULLET_LEG, cost_bp=0,
               note="만기 구간마다 그달 초 par 금리로 발행된 모형 국채 한 종목을 들고 재무부 CMT 금리로 매일 값을 매긴 결과입니다. 실제 종목이 아닙니다."),
    stats={k: (round(v, 4) if isinstance(v, float) else v) for k, v in stats.items()},
    series=dict(dates=ser_dates, nav_p=[round(x) for x in P], nav_b=[round(x) for x in Bn], excess_bp=[round(x, 2) for x in ex_cum_bp]),
    months=[{k: (round(v, 3) if isinstance(v, float) else v) for k, v in m.items()} for m in months],
    years=[{k: (round(v, 3) if isinstance(v, float) else v) for k, v in y.items()} for y in years_tbl],
    rebalances=[dict(date=e["date"], month=e["month"], frm=e["frm"], to=e["to"], why=e["why"], turnover=e["turnover"],
                     excess_bp=round(e["excess_bp"], 2), partial=e["partial"]) for e in log],
    now=dict(date=DATES[i0], buckets=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in x.items()} for x in now],
             dur_p=r4(sum(st["cp"])), dur_b=r4(sum(st["cb"])), active=r4(sum(act)),
             position=dict(dur=months[-1]["dur"], slope=months[-1]["slope"], curv=months[-1]["curv"])),
    initial=dict(date=rows[0]["decision_date"], buckets=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in x.items()} for x in init],
                 position=dict(dur=months[0]["dur"], slope=months[0]["slope"], curv=months[0]["curv"])),
    market=dict(date=DATES[last], decision=DATES[i0],
                y2=U["yields"]["2Y"][last], y10=U["yields"]["10Y"][last], y30=U["yields"]["30Y"][last],
                s2s10s=round((U["yields"]["10Y"][last] - U["yields"]["2Y"][last]) * 100, 1),
                d10y=round((U["yields"]["10Y"][last] - U["yields"]["10Y"][i0]) * 100, 1),
                d2s10s=round(((U["yields"]["10Y"][last] - U["yields"]["2Y"][last]) - (U["yields"]["10Y"][i0] - U["yields"]["2Y"][i0])) * 100, 1),
                curve=[dict(m=m, y=round(curve(last, m), 3)) for m in (0.25, 1, 2, 3, 5, 7, 10, 20, 30)],
                curve_prev=[dict(m=m, y=round(curve(i0, m), 3)) for m in (0.25, 1, 2, 3, 5, 7, 10, 20, 30)],
                bm_yield=round(sum(w * y for w, y in zip(BM_W, st["yb"])), 3)),
    alt=alt,
    risk=dict(te_exante_bp=round(te_ex, 2), te_max_bp=round(te_max, 2), budget=TE_BUDGET, scenarios=[dict(label=s["label"], bp=round(s["bp"], 2)) for s in scen],
              vol_bp=[round(math.sqrt(cov[b][b]), 1) for b in range(NB)]),
)
(HERE / "portfolio.js").write_text("window.PORTFOLIO = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

if __name__ == "__main__":
    s = stats
    print(f"기간 {s['start']} ~ {s['end']} ({s['years']:.1f}년), 리밸런싱 {s['n_rebal']}번")
    print(f"NAV {s['nav']:,.0f} (벤치마크 {s['nav_bm']:,.0f})  연 {s['ann_p']:.2f}% 대 {s['ann_b']:.2f}%  초과 누적 {s['excess_cum_bp']:+.1f}bp, 연 {s['excess_ann_bp']:+.2f}bp")
    print(f"추적오차 사후 {s['te_all_bp']:.1f}bp (1년 {s['te_1y_bp']:.1f}, 3년 {s['te_3y_bp']:.1f}) · 사전 {te_ex:.1f}bp · 최대 {te_max:.1f}bp · IR {s['ir']:.2f}")
    print(f"최대 낙폭 포트 {s['mdd_p']:.1f}% 벤치 {s['mdd_b']:.1f}% · 상대 {s['mdd_rel_bp']:.0f}bp ({s['mdd_rel_from']} → {s['mdd_rel_to']})")
    print(f"전략별 누적 bp: Duration {s['c_dur']:+.1f} Slope {s['c_slope']:+.1f} Curvature {s['c_curv']:+.1f} · 적중 {s['hit']}")
    print(f"지금 듀레이션 {out['now']['dur_p']:.2f} 대 {out['now']['dur_b']:.2f} (액티브 {out['now']['active']:+.3f})")
    print(f"개선안 누적 {alt['excess_cum_bp']:+.1f}bp IR {alt['ir']:.2f} · 수립 {alt['train']} · 검증 {alt['test']} · 지금 {alt['now']}")
    print("portfolio.js", (HERE / 'portfolio.js').stat().st_size // 1024, "KB")
