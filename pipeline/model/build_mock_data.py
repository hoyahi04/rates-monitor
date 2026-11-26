#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""운용 페이지 화면 시안용 자료 만들기  →  mock_portfolio.js  (window.PORTFOLIO_MOCK)

쓰는 법:  python3 build_mock_data.py
표준 라이브러리만 쓴다. 읽는 파일은 모두 읽기 전용이고, 읽은 값은 mock_portfolio.js 안에 그대로 고정된다.

값의 성격 (자료 안의 kind):
  real      공개 자료에서 그대로 읽었거나 그것만으로 계산한 값
  estimate  포지션 × 금리 변화로 추정한 값
  example   초기 포트폴리오가 정해지기 전이라 견본 포트폴리오로 계산한 값
  pending   종목 가격으로 과거를 다시 만든 뒤에야 나오는 값 (비워 둔다. 지어낸 숫자를 넣지 않는다)

화면에 소수 한 자리로 찍는 값은 넷째 자리까지 담는다 (화면에서 한 번만 반올림하게).

Bloomberg 자료는 읽지 않는다. benchmark_proxy.json 의 validation 항목(공식 값과의 대조)은 읽자마자 버린다.
"""
import bisect
import csv
import json
import math
import sys
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent                                        # .../rates monitor
OUT = HERE / "mock_portfolio.js"

CURVE_JS = ROOT / "inputs" / "curve" / "data.js"
SB_CSV = ROOT / "inputs" / "macro" / "scoreboard.csv"
SB_CSV_BACKUP = ROOT / "inputs" / "macro" / "page_build_wip" / "backup_before_build" / "scoreboard.csv"
SB_JS = ROOT / "inputs" / "macro" / "scoreboard.js"
BENCH_JSON = ROOT / "inputs" / "curve" / "initial_portfolio_wip" / "benchmark_proxy.json"
UNIVERSE_CSV = ROOT / "inputs" / "curve" / "initial_portfolio_wip" / "universe.csv"

# ----------------------------------------------------------------- 기본값 (design_spec.md 5절)
NAV_BASE = 10_000_000          # 가상 운용 규모 (USD)
CASH_USD = 100_000             # 예시 포트폴리오의 현금 1%
PER_BUCKET = 3                 # 예시 포트폴리오: 버킷당 종목 수
WEIGHT_GRID_PCT = 0.25         # 예시 포트폴리오: 종목 비중을 이 단위로 맞춘다
PAR_STEP = 1_000               # 액면 단위
BUCKET_LIMIT_PP = 5.0          # 버킷 한도선 (팀 미확정: ±5 / ±10)
TE_BUDGET_BP = [50, 100]
TE_SCALE_MAX = 120
N_RANGE = [12, 20]
CASH_RANGE_PCT = [0, 2]
DUR_STEP, DUR_CAP = 0.25, 0.5
SLOPE_LEG_YR = 0.10            # 시안 가정: Slope 다리당 0.10년
CURV_BELLY_YR, CURV_WING_YR = 0.10, 0.05
FLY_Z_TH = 1.0
LOOKBACK_M, LOOKBACK_SHORT_M = 36, 12
COV_WINDOW_M = 36
TRAIN_END, TEST_START, DAILY_START = "2020-12", "2021-01", "2026-12"
MIN_MATURITY_Y = 1.0           # 잔존 1년 이상만 담는다
CASH_YIELD_PCT = 0.0           # 현금 이자 (초기 포트폴리오 엔진과 같게 0 으로 둔다)

TENORS = ["1M", "3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]
BUCKETS = [   # id, 화면 이름, 대표 금리(평균), 대표 만기(년)
    {"id": "1-3", "label": "1–3", "rep_tenors": ["2Y"], "rep_maturity": 2.0},
    {"id": "3-5", "label": "3–5", "rep_tenors": ["3Y", "5Y"], "rep_maturity": 4.0},
    {"id": "5-7", "label": "5–7", "rep_tenors": ["5Y", "7Y"], "rep_maturity": 6.0},
    {"id": "7-10", "label": "7–10", "rep_tenors": ["7Y", "10Y"], "rep_maturity": 8.5},
    {"id": "10-20", "label": "10–20", "rep_tenors": ["10Y", "20Y"], "rep_maturity": 15.0},
    {"id": "20+", "label": "20y+", "rep_tenors": ["30Y"], "rep_maturity": 30.0},
]
BIDS = [b["id"] for b in BUCKETS]
NB = len(BUCKETS)
SIGNALS = [("s1_policy", "정책", 1), ("s2_growth", "성장", 2), ("s3_inflation", "물가", 3),
           ("s4_supply", "수급", 4), ("s5_liquidity_vol", "유동성·변동성", 5)]
SKEYS = [s[0] for s in SIGNALS]
STRATS = ["duration", "slope", "curvature", "carry", "other"]

checks = []


def check(name, expected, got, ok):
    checks.append({"name": name, "expected": expected, "got": got, "ok": bool(ok)})
    print(f"  [{'맞음' if ok else '어긋남'}] {name}: 기준 {expected} / 계산 {got}")


def rnd(x, d=2):
    return None if x is None else round(float(x), d) + 0.0      # + 0.0: −0.0 을 0.0 으로


def rel(p):
    return str(p.relative_to(ROOT))


def mtime(p):
    return datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M")


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    last = [31, 29 if (y2 % 4 == 0 and (y2 % 100 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(day, last):02d}"


def next_month(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return f"{y + (m == 12):04d}-{m % 12 + 1:02d}"


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def solve(a, b):
    """가우스 소거 (작은 연립방정식용)"""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[p] = m[p], m[c]
        for r in range(c + 1, n):
            f = m[r][c] / m[c][c]
            for k in range(c, n + 1):
                m[r][k] -= f * m[c][k]
    x = [0.0] * n
    for r in range(n - 1, -1, -1):
        x[r] = (m[r][n] - sum(m[r][k] * x[k] for k in range(r + 1, n))) / m[r][r]
    return x


# ================================================================= 1. 읽기
def read_curve():
    t = CURVE_JS.read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    return d["dates"], d["yields"]


def read_scoreboard():
    """scoreboard.csv. 다른 세션이 고치는 중이라 깨져 있으면 백업본을 쓴다."""
    need = {"decision_date", "apply_month", "view_level", "view_slope", "fly_z_3y", "duration_active_yr",
            "slope_position", "curvature_position", "next_d10y_bp"} | set(SKEYS)
    for path in (SB_CSV, SB_CSV_BACKUP):
        try:
            with open(path, encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            if len(rows) >= 100 and need <= set(rows[0]):
                return path, rows
        except (OSError, ValueError, csv.Error):
            pass
    sys.exit("scoreboard.csv 를 읽을 수 없습니다 (본 파일과 백업본 모두).")


def read_live():
    """scoreboard.js 의 오늘 기준 잠정 값(live). 없으면 None."""
    try:
        t = SB_JS.read_text(encoding="utf-8")
        d = json.loads(t[t.index("{"):t.rindex("}") + 1])
        live = d.get("live")
        if isinstance(live, dict) and all(k in live for k in SKEYS + ["apply_month", "duration_active_yr", "slope_position"]):
            return live
    except (OSError, ValueError):
        pass
    return None


def read_benchmark():
    with open(BENCH_JSON, encoding="utf-8") as f:
        d = json.load(f)
    d.pop("validation", None)                 # 공식 값과의 대조 항목은 쓰지 않는다
    return d


def read_universe():
    with open(UNIVERSE_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


print("자료를 읽습니다.")
DATES, Y = read_curve()
sb_path, SB = read_scoreboard()
LIVE = read_live()
BENCH = read_benchmark()
UNIV = read_universe()

RATES_DATE = DATES[-1]
CUR = SB[-1]
DECISION_DATE, APPLY_MONTH = CUR["decision_date"], CUR["apply_month"]
PRICE_DATE, SETTLE_DATE = BENCH["meta"]["price_date"], BENCH["meta"]["settle_date"]


def at(d):
    """d 이하 마지막 거래일의 위치"""
    return bisect.bisect_right(DATES, d) - 1


def rep_yield(b, i):
    """버킷 대표 금리(%)"""
    v = [Y[t][i] for t in BUCKETS[b]["rep_tenors"]]
    return None if None in v else sum(v) / len(v)


def spread_bp(kind, i):
    y2, y5, y10, y30 = Y["2Y"][i], Y["5Y"][i], Y["10Y"][i], Y["30Y"][i]
    if kind == "s2s10s":
        return None if None in (y2, y10) else (y10 - y2) * 100
    if kind == "s5s30s":
        return None if None in (y5, y30) else (y30 - y5) * 100
    return None if None in (y2, y5, y10) else (2 * y5 - y2 - y10) * 100


SERIES = {}
for kind in ("s2s10s", "s5s30s", "fly"):
    ds, vs = [], []
    for i, day in enumerate(DATES):
        v = spread_bp(kind, i)
        if v is not None:
            ds.append(day)
            vs.append(v)
    SERIES[kind] = (ds, vs)


def zscore(kind, d, months):
    """d 이하 마지막 값이 직전 months 개월(그 값 포함) 분포에서 몇 표준편차인가. 표본 표준편차(n−1).
    pipeline/inputs/macro/scoreboard.py 의 zscore 와 같은 식."""
    ds, vs = SERIES[kind]
    b = bisect.bisect_right(ds, d)
    a = bisect.bisect_right(ds, months_ago(d, months))
    w = vs[a:b]
    if len(w) < 60:
        return None, None
    mu = sum(w) / len(w)
    sd = math.sqrt(sum((x - mu) ** 2 for x in w) / (len(w) - 1))
    return w[-1], ((w[-1] - mu) / sd if sd else None)


# ================================================================= 2. 점수표
def view_state(parts):
    pos, neg = any(v > 0 for v in parts), any(v < 0 for v in parts)
    return "conflict" if pos and neg else "aligned" if pos or neg else "no_signal"


def sb_row(r, live=False):
    s = {k: int(float(r[k])) for k in SKEYS}
    z3, z1 = num(r.get("fly_z_3y")), num(r.get("fly_z_1y"))
    return {
        "decision_date": r.get("date", r["decision_date"]) if live else r["decision_date"],
        "apply_month": r["apply_month"],
        "scores": s,
        "view_level": int(float(r["view_level"])), "view_slope": int(float(r["view_slope"])),
        "view_curvature": int(float(r["view_curvature"])),
        "level_state": view_state([s["s1_policy"], s["s2_growth"], s["s3_inflation"]]),
        "slope_state": view_state([s["s1_policy"], s["s4_supply"]]),
        "fly_bp": num(r.get("fly_2s5s10s_bp")), "fly_z_3y": z3, "fly_z_1y": z1,
        "gate_met": s["s5_liquidity_vol"] == 1, "z_met": z3 is not None and z3 >= FLY_Z_TH,
        "duration_active_yr": float(r["duration_active_yr"]),
        "slope_position": r["slope_position"], "curvature_position": r["curvature_position"],
        "carry_rolldown": r.get("carry_rolldown", "on"),
        "next_d10y_bp": num(r.get("next_d10y_bp")), "next_d2s10s_bp": num(r.get("next_d2s10s_bp")),
        "next_dfly_bp": num(r.get("next_dfly_bp")),
    }


ROWS = [sb_row(r) for r in SB]
current = ROWS[-1]

if LIVE:
    nxt = sb_row(LIVE, live=True)
    nxt_source = f"{rel(SB_JS)} 의 live (기준일 {LIVE.get('date')})"
else:
    fv, z3 = zscore("fly", RATES_DATE, LOOKBACK_M)
    _, z1 = zscore("fly", RATES_DATE, LOOKBACK_SHORT_M)
    nxt = sb_row({"decision_date": RATES_DATE, "apply_month": next_month(APPLY_MONTH),
                  "s1_policy": 1, "s2_growth": -1, "s3_inflation": 0, "s4_supply": -1, "s5_liquidity_vol": 0,
                  "view_level": 0, "view_slope": 0, "view_curvature": 0,
                  "fly_2s5s10s_bp": round(fv, 1), "fly_z_3y": round(z3, 2), "fly_z_1y": round(z1, 2),
                  "duration_active_yr": 0.0, "slope_position": "none", "curvature_position": "none"})
    nxt_source = "scoreboard.js 에 live 값이 없어 초기 포트폴리오 세션의 11-20 종가 기준 예비 판정을 씀"
for k in ("next_d10y_bp", "next_d2s10s_bp", "next_dfly_bp"):
    nxt.pop(k, None)
nxt["month_end"] = LIVE.get("month_end") if LIVE else None
nxt["changes"] = [{"key": k, "name": n, "from": current["scores"][k], "to": nxt["scores"][k]}
                  for k, n, _ in SIGNALS if current["scores"][k] != nxt["scores"][k]]

dur_counts = {}
for r in ROWS:
    k = f"{r['duration_active_yr']:+.2f}" if r["duration_active_yr"] else "0"
    dur_counts[k] = dur_counts.get(k, 0) + 1
freq = {
    "months": len(ROWS), "from": ROWS[0]["apply_month"], "to": ROWS[-1]["apply_month"],
    "duration": dur_counts, "duration_on": sum(1 for r in ROWS if r["duration_active_yr"]),
    "slope": {k: sum(1 for r in ROWS if r["slope_position"] == k) for k in ("steepener", "flattener", "none")},
    "slope_on": sum(1 for r in ROWS if r["slope_position"] != "none"),
    "curvature_on": sum(1 for r in ROWS if r["curvature_position"] == "bullet"),
    "carry_on": len(ROWS),
}

scoreboard = {
    "kind": "real", "source": rel(sb_path),
    "signals": [{"key": k, "name": n, "no": no} for k, n, no in SIGNALS],
    "rules": {"dur_step_yr": DUR_STEP, "dur_cap_yr": DUR_CAP, "slope_trigger": 2, "fly_z_th": FLY_Z_TH,
              "fly_lookback_y": LOOKBACK_M // 12, "fly_lookback_alt_y": LOOKBACK_SHORT_M // 12,
              "level_view": ["s1_policy", "s2_growth", "s3_inflation"], "slope_view": ["s1_policy", "s4_supply"],
              "curvature_gate": {"key": "s5_liquidity_vol", "score": 1},
              "brake": {"adopted": False, "label": "제안(미채택)",
                        "text": "유동성·변동성 점수가 −1이면 포지션을 절반으로 줄이자는 제안입니다. 팀이 정하기 전이라 포지션 계산에는 넣지 않았습니다."}},
    "current": current,
    "next": {**nxt, "provisional": True, "source": nxt_source},
    "last12": ROWS[-12:],
    "freq": freq,
}

# ================================================================= 3. 금리
print("금리와 스프레드를 계산합니다.")


def snapshot(d):
    i = at(d)
    out = {"date": DATES[i], "y2": Y["2Y"][i], "y5": Y["5Y"][i], "y10": Y["10Y"][i], "y30": Y["30Y"][i]}
    for kind in ("s2s10s", "s5s30s", "fly"):
        v, z3 = zscore(kind, DATES[i], LOOKBACK_M)
        _, z1 = zscore(kind, DATES[i], LOOKBACK_SHORT_M)
        out[kind + "_bp"] = rnd(v, 1)
        out[kind + "_z_3y"] = rnd(z3, 2)
        out[kind + "_z_1y"] = rnd(z1, 2)
    return out


latest, at_dec = snapshot(RATES_DATE), snapshot(DECISION_DATE)
i_now, i_dec, i_yr = at(RATES_DATE), at(DECISION_DATE), at(months_ago(RATES_DATE, 12))
i_px = at(PRICE_DATE)

win_start = months_ago(RATES_DATE, LOOKBACK_M)
i0 = bisect.bisect_right(DATES, win_start)
ser = {"dates": [], "s2s10s_bp": [], "s5s30s_bp": [], "fly_bp": [], "fly_z_3y": [], "fly_z_1y": []}
for i in range(i0, len(DATES)):
    vals = [spread_bp(k, i) for k in ("s2s10s", "s5s30s", "fly")]
    if None in vals:
        continue
    _, z3 = zscore("fly", DATES[i], LOOKBACK_M)
    _, z1 = zscore("fly", DATES[i], LOOKBACK_SHORT_M)
    ser["dates"].append(DATES[i])
    ser["s2s10s_bp"].append(rnd(vals[0], 1))
    ser["s5s30s_bp"].append(rnd(vals[1], 1))
    ser["fly_bp"].append(rnd(vals[2], 1))
    ser["fly_z_3y"].append(rnd(z3, 3))
    ser["fly_z_1y"].append(rnd(z1, 3))

decision_points = []
for r in ROWS:
    if r["decision_date"] > win_start:
        decision_points.append({"date": DATES[at(r["decision_date"])], "apply_month": r["apply_month"],
                                "fly_bp": r["fly_bp"], "fly_z_3y": r["fly_z_3y"], "fly_z_1y": r["fly_z_1y"],
                                "gate_met": r["gate_met"], "bullet": r["curvature_position"] == "bullet"})

rates = {
    "kind": "real", "source": rel(CURVE_JS), "note": "재무부 CMT par 금리 (보간된 금리이고 개별 종목의 수익률이 아님)",
    "tenors": TENORS,
    "curves": [
        {"key": "latest", "label": "금리 기준일", "date": DATES[i_now], "yields": [Y[t][i_now] for t in TENORS]},
        {"key": "decision", "label": "판정일", "date": DATES[i_dec], "yields": [Y[t][i_dec] for t in TENORS]},
        {"key": "year_ago", "label": "1년 전", "date": DATES[i_yr], "yields": [Y[t][i_yr] for t in TENORS]},
    ],
    "latest": latest, "at_decision": at_dec,
    "change_since_decision_bp": {
        **{t: rnd((Y[t][i_now] - Y[t][i_dec]) * 100, 1) for t in ("2Y", "5Y", "10Y", "30Y")},
        **{k: rnd(latest[k + "_bp"] - at_dec[k + "_bp"], 1) for k in ("s2s10s", "s5s30s", "fly")}},
    "window": {"start": ser["dates"][0], "end": ser["dates"][-1], "n": len(ser["dates"]), "lookback_y": LOOKBACK_M // 12},
    "series": ser,
    "decision_points": decision_points,
}

check("판정일 Fly (bp)", current["fly_bp"], at_dec["fly_bp"], abs(at_dec["fly_bp"] - current["fly_bp"]) < 0.06)
check("판정일 Fly z 3년", current["fly_z_3y"], at_dec["fly_z_3y"], abs(at_dec["fly_z_3y"] - current["fly_z_3y"]) < 0.006)
check("판정일 Fly z 1년", current["fly_z_1y"], at_dec["fly_z_1y"], abs(at_dec["fly_z_1y"] - current["fly_z_1y"]) < 0.006)
if DECISION_DATE == "2026-10-30":
    got = [at_dec["fly_bp"], at_dec["fly_z_3y"], at_dec["fly_z_1y"]]
    check("2026-10-30 검산 (Fly, z 3년, z 1년)", [-8.0, 1.48, 1.16], got, got == [-8.0, 1.48, 1.16])
if RATES_DATE == "2026-11-20":
    got = [round(latest["s2s10s_bp"]), round(latest["s5s30s_bp"]), round(latest["fly_bp"]), latest["fly_z_3y"], latest["fly_z_1y"]]
    check("2026-11-20 검산 (2s10s, 5s30s, Fly, z 3년, z 1년)", [29, 60, -13, 1.03, 0.47], got,
          got[:3] == [29, 60, -13] and abs(got[3] - 1.03) < 0.011 and abs(got[4] - 0.47) < 0.011)
bad = [(p["date"], p["fly_z_3y"], ser["fly_z_3y"][ser["dates"].index(p["date"])]) for p in decision_points
       if p["fly_z_3y"] is not None and abs(p["fly_z_3y"] - ser["fly_z_3y"][ser["dates"].index(p["date"])]) > 0.006]
check("최근 3년 월말 판정의 z 3년이 일별 계산과 같은가", "어긋난 달 0개", f"어긋난 달 {len(bad)}개", not bad)

# ================================================================= 4. 벤치마크(대용 지수)
print("벤치마크(대용 지수)를 정리합니다.")
bt = BENCH["totals"]
BENCH_DUR = bt["mod_duration"]
by_bucket = {b: [] for b in BIDS}
for u in UNIV:
    by_bucket[u["bucket"]].append(u)

bench_buckets = []
for b in BENCH["buckets"]:
    us = by_bucket[b["bucket"]]
    w = sum(float(u["index_weight_pct"]) for u in us)
    carry = sum(float(u["index_weight_pct"]) * float(u["carry_1m_bp"]) for u in us) / w
    roll = sum(float(u["index_weight_pct"]) * float(u["roll_1m_bp"]) for u in us) / w
    bench_buckets.append({
        "id": b["bucket"], "n_issues": b["n_issues"], "weight_pct": rnd(b["weight_pct"], 4),
        "mod_duration": rnd(b["mod_duration"], 4), "contrib_duration": rnd(b["contrib_duration"], 6),
        "contrib_share": b["contrib_duration"] / BENCH_DUR,
        "yield_pct": rnd(b["yield_pct"], 3),
        "carry_1m_bp": rnd(carry, 4), "roll_1m_bp": rnd(roll, 4), "carry_roll_1m_bp": rnd(b["carry_roll_1m_bp"], 4),
        "carry_roll_per_dur_bp": rnd(b["carry_roll_1m_bp"] / b["mod_duration"], 4),
    })
    check(f"버킷 {b['bucket']} carry+roll (종목 가중합 = 대용 지수 값)", rnd(b["carry_roll_1m_bp"], 2), rnd(carry + roll, 2),
          abs(carry + roll - b["carry_roll_1m_bp"]) < 0.02)
assert [b["id"] for b in bench_buckets] == BIDS
SHARE = [b["contrib_share"] for b in bench_buckets]          # 듀레이션 기여 비율 (합 1)
BENCH_CONTRIB = [b["contrib_duration"] for b in BENCH["buckets"]]   # 반올림 전 값
BENCH_W = [b["weight_pct"] for b in BENCH["buckets"]]
BENCH_BDUR = [b["mod_duration"] for b in BENCH["buckets"]]
for b in bench_buckets:
    b["contrib_share"] = rnd(b["contrib_share"], 4)

n_fed = sum(1 for u in UNIV if u["price_source"].startswith("FedInvest"))
n_wi = sum(1 for u in UNIV if u["price_source"].startswith("WI"))
n_interp = len(UNIV) - n_fed - n_wi
w_not_fed = sum(float(u["index_weight_pct"]) for u in UNIV if not u["price_source"].startswith("FedInvest"))
COMP_DATE = BENCH["meta"].get("composition_date")
benchmark = {
    "kind": "real", "name": "벤치마크(대용 지수)",
    "method": "재무부 발행 잔액에서 연준 보유분을 뺀 금액으로 종목 비중을 정한 지수입니다. "
              f"{len(UNIV)}종목 중 {n_fed}개는 재무부 FedInvest 종가로, 발행 전인 {n_wi}개와 종가가 없는 {n_interp}개는 CMT 금리로 값을 매겼습니다.",
    "source": [rel(BENCH_JSON), rel(UNIVERSE_CSV)],
    "price_date": PRICE_DATE, "settle_date": SETTLE_DATE, "composition_date": COMP_DATE,
    "composition_month": (BENCH["meta"].get("index_settle_date") or COMP_DATE or "")[:7],   # 이 구성이 쓰이는 달
    "pricing": {"fedinvest": n_fed, "when_issued": n_wi, "cmt_interp": n_interp, "not_fedinvest_weight_pct": rnd(w_not_fed, 2)},
    "status": "확정 전",
    "totals": {"n_issues": bt["n_issues"], "mod_duration": rnd(BENCH_DUR, 4), "yield_pct": rnd(bt["yield_pct"], 4),
               "carry_1m_bp": rnd(bt["carry_1m_bp"], 4), "roll_1m_bp": rnd(bt["roll_1m_bp"], 4),
               "carry_roll_1m_bp": rnd(bt["carry_roll_1m_bp"], 4),
               "carry_roll_per_dur_bp": rnd(bt["carry_roll_1m_bp"] / BENCH_DUR, 4)},
    "buckets": bench_buckets,
}
check("대용 지수 버킷 비중 합 (%)", 100.0, rnd(sum(BENCH_W), 2), abs(sum(BENCH_W) - 100) < 0.01)
check("대용 지수 종목 수 = universe.csv 줄 수", bt["n_issues"], len(UNIV), bt["n_issues"] == len(UNIV))
check("대용 지수 듀레이션 = 버킷 기여 합", rnd(BENCH_DUR, 3), rnd(sum(BENCH_CONTRIB), 3), abs(sum(BENCH_CONTRIB) - BENCH_DUR) < 0.002)

# ================================================================= 5. 예시 포트폴리오
print("예시 포트폴리오를 만듭니다.")
RULE_DUR = current["duration_active_yr"]                   # 이번 달 점수표 포지션
picks = []
for bi, bid in enumerate(BIDS):
    cand = [u for u in by_bucket[bid]
            if u["price_source"].startswith("FedInvest") and u["is_when_issued"] == "0" and u["settle_date"] == SETTLE_DATE]
    cand.sort(key=lambda u: (u["maturity_date"], u["cusip"]))
    for k in range(PER_BUCKET):                            # 만기 순서로 세운 뒤 1/6, 3/6, 5/6 지점
        picks.append((bi, cand[min(len(cand) - 1, int((2 * k + 1) / (2 * PER_BUCKET) * len(cand)))]))
assert len({u["cusip"] for _, u in picks}) == len(picks)

n = len(picks)
dur = [float(u["mod_duration"]) for _, u in picks]
invest = 1 - CASH_USD / NAV_BASE
x0 = [invest * BENCH_W[bi] / 100 / PER_BUCKET for bi, _ in picks]         # 출발점: 버킷 비중을 3등분
target = [c * (BENCH_DUR + RULE_DUR) / BENCH_DUR for c in BENCH_CONTRIB]  # 버킷별 듀레이션 기여 목표
A = [[dur[j] if picks[j][0] == bi else 0.0 for j in range(n)] for bi in range(NB)] + [[1.0] * n]
t = target + [invest]
resid = [t[i] - sum(A[i][j] * x0[j] for j in range(n)) for i in range(NB + 1)]
lam = solve([[sum(A[i][k] * A[j][k] for k in range(n)) for j in range(NB + 1)] for i in range(NB + 1)], resid)
x = [x0[j] + sum(A[i][j] * lam[i] for i in range(NB + 1)) for j in range(n)]   # 목표를 채우면서 출발점에서 가장 덜 움직인 비중

g = WEIGHT_GRID_PCT / 100                                   # 사람이 정하듯 0.25% 단위로 맞춘다
xr = [round(v / g) * g for v in x]
gap = round((invest - sum(xr)) / g)
order = sorted(range(n), key=lambda j: (x[j] - xr[j]) * (1 if gap > 0 else -1), reverse=True)
for j in order[:abs(gap)]:
    xr[j] += g if gap > 0 else -g
assert min(xr) > 0.01, "예시 포트폴리오 비중이 너무 작은 종목이 있습니다."

holdings = []
for (bi, u), w in zip(picks, xr):
    dirty = float(u["dirty_price"])
    par = round(w * NAV_BASE / (dirty / 100) / PAR_STEP) * PAR_STEP
    holdings.append({
        "cusip": u["cusip"], "bucket": BIDS[bi], "type": u["type"],
        "coupon_pct": float(u["coupon_pct"]), "maturity_date": u["maturity_date"],
        "years_to_maturity": rnd(u["years_to_maturity"], 2), "is_on_the_run": u["is_on_the_run"] == "1",
        "par_usd": par, "clean_price": float(u["clean_price"]), "accrued": rnd(u["accrued"], 4),
        "dirty_price": rnd(dirty, 4), "mv_usd": round(par * dirty / 100, 2),
        "yield_pct": rnd(u["yield_pct"], 4), "mod_duration": rnd(u["mod_duration"], 4),
        "carry_1m_bp": rnd(u["carry_1m_bp"], 4), "roll_1m_bp": rnd(u["roll_1m_bp"], 4),
        "carry_roll_1m_bp": rnd(u["carry_roll_1m_bp"], 4),
        "price_source": "재무부 FedInvest 종가 " + PRICE_DATE,
    })
NAV = round(sum(h["mv_usd"] for h in holdings) + CASH_USD, 2)
USD_PER_BP = NAV / 10_000
for h in holdings:
    h["weight"] = h["mv_usd"] / NAV                         # 계산용 (끝에서 지운다)
    h["weight_pct"] = rnd(h["weight"] * 100, 4)
    h["contrib_duration"] = rnd(h["weight"] * h["mod_duration"], 6)
    h["dv01_usd"] = rnd(h["mv_usd"] * h["mod_duration"] * 0.0001, 2)

port_buckets, PORT_CONTRIB, PORT_W = [], [], []
for bi, bid in enumerate(BIDS):
    hs = [h for h in holdings if h["bucket"] == bid]
    w = sum(h["weight"] for h in hs)
    c = sum(h["weight"] * h["mod_duration"] for h in hs)
    PORT_W.append(w * 100)
    PORT_CONTRIB.append(c)
    port_buckets.append({
        "id": bid, "n": len(hs), "mv_usd": round(sum(h["mv_usd"] for h in hs), 2),
        "weight_pct": rnd(w * 100, 4), "bench_weight_pct": rnd(BENCH_W[bi], 4), "active_weight_pp": rnd(w * 100 - BENCH_W[bi], 4),
        "mod_duration": rnd(c / w, 4), "bench_mod_duration": rnd(BENCH_BDUR[bi], 4),
        "contrib_duration": rnd(c, 6), "bench_contrib_duration": rnd(BENCH_CONTRIB[bi], 6),
        "active_duration": rnd(c - BENCH_CONTRIB[bi], 6),
        "yield_pct": rnd(sum(h["weight"] * h["yield_pct"] for h in hs) / w, 4),
        "dv01_usd": rnd(sum(h["dv01_usd"] for h in hs), 2),
        "carry_roll_1m_bp": rnd(sum(h["weight"] * h["carry_roll_1m_bp"] for h in hs) / w, 4),
        "carry_roll_contrib_bp": rnd(sum(h["weight"] * h["carry_roll_1m_bp"] for h in hs), 4),
    })
PORT_DUR = sum(PORT_CONTRIB)
ACTIVE = [PORT_CONTRIB[i] - BENCH_CONTRIB[i] for i in range(NB)]
ACTIVE_TOTAL = PORT_DUR - BENCH_DUR
cash_pct = CASH_USD / NAV * 100
port_cr = sum(h["weight"] * h["carry_roll_1m_bp"] for h in holdings)       # NAV 대비, 현금 이자 0 (CASH_YIELD_PCT)
CASH_1M_RATE = Y["1M"][i_px]                                                # 현금이 1개월 금리를 받는다고 볼 때의 참고값
port_carry = sum(h["weight"] * h["carry_1m_bp"] for h in holdings)
port_roll = sum(h["weight"] * h["roll_1m_bp"] for h in holdings)
port_yield = sum(h["weight"] * h["yield_pct"] for h in holdings)
port_dv01 = sum(h["dv01_usd"] for h in holdings)
max_w = max(range(NB), key=lambda i: abs(PORT_W[i] - BENCH_W[i]))

short_n = sum(1 for h in holdings if h["years_to_maturity"] < MIN_MATURITY_Y)
min_ytm_h = min(holdings, key=lambda h: h["years_to_maturity"])
max_w_h = max(holdings, key=lambda h: h["weight_pct"])
limits_items = [
    {"key": "n_holdings", "label": "종목 수", "value": len(holdings), "unit": "개", "lo": N_RANGE[0], "hi": N_RANGE[1],
     "ok": N_RANGE[0] <= len(holdings) <= N_RANGE[1]},
    {"key": "cash", "label": "현금", "value": rnd(cash_pct, 2), "unit": "%", "lo": CASH_RANGE_PCT[0], "hi": CASH_RANGE_PCT[1],
     "ok": CASH_RANGE_PCT[0] <= cash_pct <= CASH_RANGE_PCT[1]},
    {"key": "bucket", "label": "버킷 비중 차이 (최대)", "value": rnd(PORT_W[max_w] - BENCH_W[max_w], 2), "unit": "%p",
     "lo": -BUCKET_LIMIT_PP, "hi": BUCKET_LIMIT_PP, "worst_bucket": BIDS[max_w],
     "ok": abs(PORT_W[max_w] - BENCH_W[max_w]) <= BUCKET_LIMIT_PP, "status": "한도는 팀 확정 전 (±5%p 기본값)"},
    {"key": "min_maturity", "label": "잔존 1년 미만", "value": short_n, "unit": "개", "lo": 0, "hi": 0,
     "shortest_years": min_ytm_h["years_to_maturity"], "ok": short_n == 0},
]

# 오늘 치 추정: 종목 종가는 하루 늦게 나오므로, 가격일 뒤의 변화는 금리 변화로만 계산한다
d_px = [(rep_yield(b, i_now) - rep_yield(b, i_px)) * 100 for b in range(NB)]
est_port = -sum(PORT_CONTRIB[b] * d_px[b] for b in range(NB))
est_bench = -sum(BENCH_CONTRIB[b] * d_px[b] for b in range(NB))
today_estimate = {
    "kind": "estimate", "from": DATES[i_px], "to": DATES[i_now],
    "method": "버킷별 듀레이션 기여에 버킷 대표 금리 변화를 곱했습니다. 이자와 볼록성은 넣지 않았습니다.",
    "rep_change_bp": [rnd(v, 1) for v in d_px],
    "port_return_bp": rnd(est_port, 1), "bench_return_bp": rnd(est_bench, 1), "excess_bp": rnd(est_port - est_bench, 1),
    "nav_usd": round(NAV * (1 + est_port / 10_000)), "nav_change_usd": round(NAV * est_port / 10_000),
}

cr_gap = [port_buckets[b]["carry_roll_1m_bp"] - bench_buckets[b]["carry_roll_1m_bp"] for b in range(NB)]
cash_if_paid = cash_pct / 100 * CASH_1M_RATE * 100 / 12                     # 현금이 1개월 금리를 받으면 더해지는 bp
carry_summary = {
    "port_bp": rnd(port_cr, 4), "bench_bp": rnd(bt["carry_roll_1m_bp"], 4), "active_bp": rnd(port_cr - bt["carry_roll_1m_bp"], 4),
    "bucket_gap_bp": [rnd(v, 4) for v in cr_gap], "buckets_above": sum(1 for v in cr_gap if v > 0),
    "cash_drag_bp": rnd(-cash_pct / 100 * bt["carry_roll_1m_bp"], 4),
    "cash_yield_pct": CASH_YIELD_PCT, "cash_1m_rate_pct": CASH_1M_RATE,
    "active_bp_if_cash_paid": rnd(port_cr + cash_if_paid - bt["carry_roll_1m_bp"], 4),
    "picked_by_carry": False,
    "note": "예시 포트폴리오는 carry 기준으로 고르지 않았습니다 (버킷마다 만기 순서의 1/6·3/6·5/6 지점). 실제 포트폴리오는 버킷 안에서 carry+roll 이 높은 종목을 담습니다.",
}
for h in holdings:
    del h["weight"]
portfolio = {
    "kind": "example",
    "note": "초기 포트폴리오가 아직 정해지지 않아 견본으로 만든 구성입니다. 종목과 가격은 실제 것이고, 어떤 종목을 얼마나 담을지만 예시입니다.",
    "how": f"대용 지수 편입 종목 중 재무부 공시 종가가 있는 것에서 버킷마다 만기 순서의 1/6·3/6·5/6 지점 {PER_BUCKET}종목을 골랐습니다. "
           f"버킷별 듀레이션 기여가 벤치마크의 (1 + {RULE_DUR:+.2f}/{BENCH_DUR:.2f})배가 되게 비중을 풀고 {WEIGHT_GRID_PCT}% 단위로 맞췄습니다.",
    "price_date": PRICE_DATE, "settle_date": SETTLE_DATE,
    "nav_usd": NAV, "usd_per_bp": rnd(USD_PER_BP, 2), "cash_usd": CASH_USD, "cash_pct": rnd(cash_pct, 4),
    "max_holding_weight_pct": rnd(max_w_h["weight_pct"], 2),
    "n_holdings": len(holdings),
    "totals": {"par_usd": sum(h["par_usd"] for h in holdings), "mv_usd": round(NAV - CASH_USD, 2), "weight_pct": 100.0,
               "mod_duration": rnd(PORT_DUR, 4), "bench_mod_duration": rnd(BENCH_DUR, 4), "active_duration": rnd(ACTIVE_TOTAL, 4),
               "yield_pct": rnd(port_yield, 4), "yield_invested_pct": rnd(port_yield / (1 - cash_pct / 100), 4),
               "dv01_usd": rnd(port_dv01, 2), "active_dv01_usd": rnd(ACTIVE_TOTAL * USD_PER_BP, 0),
               "carry_1m_bp": rnd(port_carry, 4), "roll_1m_bp": rnd(port_roll, 4), "carry_roll_1m_bp": rnd(port_cr, 4),
               "bench_carry_roll_1m_bp": rnd(bt["carry_roll_1m_bp"], 4), "active_carry_roll_1m_bp": rnd(port_cr - bt["carry_roll_1m_bp"], 4)},
    "buckets": port_buckets,
    "holdings": holdings,
    "carry": carry_summary,
    "limits": {"violations": sum(1 for it in limits_items if not it["ok"]), "items": limits_items},
    "today_estimate": today_estimate,
}

check("잔존 1년 미만 종목", 0, short_n, short_n == 0)
wsum = sum(h["weight_pct"] for h in holdings) + portfolio["cash_pct"]
check("예시 포트폴리오 비중 합 (%)", 100.0, rnd(wsum, 2), abs(wsum - 100) < 0.01)
check("예시 포트폴리오 NAV (USD 10,000,000 근처)", "±0.05% 안", NAV, abs(NAV / NAV_BASE - 1) < 0.0005)
check("듀레이션 = 종목 기여 합 = 버킷 기여 합", rnd(PORT_DUR, 3),
      [rnd(sum(h["contrib_duration"] for h in holdings), 3), rnd(sum(b["contrib_duration"] for b in port_buckets), 3)],
      abs(sum(h["contrib_duration"] for h in holdings) - PORT_DUR) < 0.002)
check("DV01 합 = NAV × 듀레이션 × 0.0001", rnd(NAV * PORT_DUR * 0.0001, 0), rnd(port_dv01, 0), abs(port_dv01 - NAV * PORT_DUR * 0.0001) < 2)
check("예시 포트폴리오의 액티브 듀레이션이 점수표 포지션에 가까운가", f"{RULE_DUR:+.2f} ± 0.05", rnd(ACTIVE_TOTAL, 3), abs(ACTIVE_TOTAL - RULE_DUR) <= 0.05)
check("버킷 비중 차이가 한도 안인가", f"±{BUCKET_LIMIT_PP}%p", rnd(PORT_W[max_w] - BENCH_W[max_w], 2), limits_items[2]["ok"])
check("종목 수", f"{PER_BUCKET * NB}", len(holdings), len(holdings) == PER_BUCKET * NB)

# ================================================================= 6. 위험
print("추적오차와 시나리오를 계산합니다.")
ia = bisect.bisect_right(DATES, months_ago(RATES_DATE, COV_WINDOW_M))
chg, prev, cov_start = [], None, None
for i in range(ia, len(DATES)):
    row = [rep_yield(b, i) for b in range(NB)]
    if None in row:
        continue
    if prev is not None:
        chg.append([(row[b] - prev[b]) * 100 for b in range(NB)])
    else:
        cov_start = DATES[i]                                   # 창 안의 첫 관측일
    prev = row
nobs = len(chg)
mean = [sum(c[b] for c in chg) / nobs for b in range(NB)]
COV = [[sum((c[i] - mean[i]) * (c[j] - mean[j]) for c in chg) / (nobs - 1) * 252 for j in range(NB)] for i in range(NB)]


def quad(a, b=None):
    b = a if b is None else b
    return sum(a[i] * COV[i][j] * b[j] for i in range(NB) for j in range(NB))


def te(a):
    return math.sqrt(max(quad(a), 0.0))


OVERLAY = {
    "duration": [RULE_DUR * SHARE[b] for b in range(NB)],     # 점수표 포지션을 벤치마크(대용 지수) 듀레이션 기여 비율대로
    "slope": [0.0] * NB, "curvature": [0.0] * NB, "carry": [0.0] * NB,
}
OVERLAY["other"] = [ACTIVE[b] - OVERLAY["duration"][b] for b in range(NB)]   # 예시 포트폴리오가 중립 바탕에서 벗어난 나머지
TE_NOW = te(ACTIVE)
te_by = {k: (quad(OVERLAY[k], ACTIVE) / TE_NOW if TE_NOW else 0.0) for k in STRATS}
TE_RULE = te(OVERLAY["duration"])
TE_Q = te([DUR_STEP * s for s in SHARE])
TE_MAX = te([DUR_CAP * s for s in SHARE])

REP_M = [b["rep_maturity"] for b in BUCKETS]


def twist(sign):
    return [sign * (-25 + 50 * (m - REP_M[0]) / (REP_M[-1] - REP_M[0])) for m in REP_M]


SCEN = [
    ("par_p25", "평행 +25bp", "모든 만기 금리가 25bp 오름", [25.0] * NB),
    ("par_p50", "평행 +50bp", "모든 만기 금리가 50bp 오름", [50.0] * NB),
    ("par_m25", "평행 −25bp", "모든 만기 금리가 25bp 내림", [-25.0] * NB),
    ("par_m50", "평행 −50bp", "모든 만기 금리가 50bp 내림", [-50.0] * NB),
    ("steep", "스티프닝", "2년 −25bp, 30년 +25bp, 사이는 만기에 따라 직선", twist(1)),
    ("flat", "플래트닝", "2년 +25bp, 30년 −25bp, 사이는 만기에 따라 직선", twist(-1)),
    ("belly_p25", "벨리만 +25bp", "가운데 구간(5–7 버킷) 금리만 25bp 오름", [25.0 if b == 2 else 0.0 for b in range(NB)]),
    ("belly_m25", "벨리만 −25bp", "가운데 구간(5–7 버킷) 금리만 25bp 내림", [-25.0 if b == 2 else 0.0 for b in range(NB)]),
]
scenarios = []
for key, label, desc, shock in SCEN:
    pnl = {k: -sum(OVERLAY[k][b] * shock[b] for b in range(NB)) for k in STRATS}
    pnl["total"] = -sum(ACTIVE[b] * shock[b] for b in range(NB))
    scenarios.append({"key": key, "label": label, "desc": desc, "shocks_bp": [rnd(s, 1) for s in shock],
                      "pnl_bp": {k: rnd(v, 4) for k, v in pnl.items()}})
carry_active = port_cr - bt["carry_roll_1m_bp"]
scenarios.append({"key": "unchanged", "label": "변화 없음", "desc": "수익률곡선이 그대로일 때 한 달 carry+roll 차이 (현금 이자는 0으로 봄)",
                  "shocks_bp": [0.0] * NB,
                  "pnl_bp": {"duration": 0.0, "slope": 0.0, "curvature": 0.0, "carry": rnd(carry_active, 4), "other": 0.0,
                             "total": rnd(carry_active, 4)}})

risk = {
    "kind": "example",
    "note": "예시 포트폴리오의 버킷별 액티브 듀레이션에 실제 금리 공분산을 곱한 값입니다. 포트폴리오가 정해지면 바뀝니다.",
    "usd_per_bp": rnd(USD_PER_BP, 2),
    "active_by_bucket": [{"id": BIDS[b], **{k: rnd(OVERLAY[k][b], 6) for k in STRATS}, "total": rnd(ACTIVE[b], 6)} for b in range(NB)],
    "active_total": {**{k: rnd(sum(OVERLAY[k]), 6) for k in STRATS}, "total": rnd(ACTIVE_TOTAL, 6)},
    "te": {
        "bp": rnd(TE_NOW, 3), "budget_bp": TE_BUDGET_BP, "scale_max": TE_SCALE_MAX,
        "by_strategy_bp": {k: rnd(v, 4) for k, v in te_by.items()},
        "rule_only_bp": rnd(TE_RULE, 3),
        "reference": {"kind": "real", "duration_025_bp": rnd(TE_Q, 3), "duration_050_bp": rnd(TE_MAX, 3),
                      "note": "Duration 포지션만 있을 때의 값입니다 (±0.25년, ±0.5년). ±0.5년이 규칙이 낼 수 있는 가장 큰 포지션입니다."},
        "method": "추적오차 = √(a′Sa)입니다. a는 버킷별 액티브 듀레이션, S는 버킷 대표 금리 일별 변화의 연율 공분산(bp², 252일 기준)입니다. 금리 움직임에서 오는 위험만 봅니다.",
        "cov": {"kind": "real", "start": cov_start, "end": RATES_DATE, "n_obs": nobs,
                "rep_vol_bp_annual": [rnd(math.sqrt(COV[b][b]), 1) for b in range(NB)],
                "cov_bp2_annual": [[rnd(v, 1) for v in row] for row in COV]},
    },
    "scenarios": scenarios,
}
check("추적오차: 액티브 +0.25년 (약 20bp)", "15~25bp", rnd(TE_Q, 1), 15 <= TE_Q <= 25)
check("추적오차: Duration ±0.5년 = ±0.25년의 2배", rnd(2 * TE_Q, 1), rnd(TE_MAX, 1), abs(TE_MAX - 2 * TE_Q) < 0.05)
check("추적오차 전략별 몫의 합 = 전체", rnd(TE_NOW, 2), rnd(sum(te_by.values()), 2), abs(sum(te_by.values()) - TE_NOW) < 0.01)
check("평행 +25bp 손익 = −액티브 듀레이션 × 25", rnd(-ACTIVE_TOTAL * 25, 4), scenarios[0]["pnl_bp"]["total"],
      abs(scenarios[0]["pnl_bp"]["total"] + ACTIVE_TOTAL * 25) < 0.01)
for s in scenarios:
    tot = sum(s["pnl_bp"][k] for k in STRATS)
    if abs(tot - s["pnl_bp"]["total"]) > 0.03:
        check(f"시나리오 {s['label']}: 전략 합 = 합계", s["pnl_bp"]["total"], rnd(tot, 2), False)
check("시나리오 표: 전략별 손익의 합 = 합계 (9줄)", "모두 일치",
      "모두 일치" if all(abs(sum(s["pnl_bp"][k] for k in STRATS) - s["pnl_bp"]["total"]) <= 0.03 for s in scenarios) else "어긋남",
      all(abs(sum(s["pnl_bp"][k] for k in STRATS) - s["pnl_bp"]["total"]) <= 0.03 for s in scenarios))

# ================================================================= 7. 성과 분해 이력
# Duration·Slope·Curvature 는 포지션 × 금리 변화로 추정한다.
# Carry·기타·초과수익 합계는 종목 가격으로 과거를 다시 만든 뒤에야 나오므로 비워 둔다 (지어낸 숫자를 넣지 않는다).
print("성과 분해 이력을 만듭니다.")
M = len(ROWS)
EST = ["duration", "slope", "curvature"]
SLOPE_LEGS = {"steepener": [("1-3", SLOPE_LEG_YR), ("20+", -SLOPE_LEG_YR)],       # 스티프너: 1–3 +0.10년, 20y+ −0.10년
              "flattener": [("1-3", -SLOPE_LEG_YR), ("20+", SLOPE_LEG_YR)], "none": []}
BULLET_LEGS = [("5-7", CURV_BELLY_YR), ("1-3", -CURV_WING_YR), ("10-20", -CURV_WING_YR)]   # 불릿: 5–7 +0.10, 1–3·10–20 −0.05씩


def overlay_vec(r):
    """그달 포지션을 전략별 · 버킷별 액티브 듀레이션(년)으로"""
    v = {k: [0.0] * NB for k in EST}
    v["duration"] = [r["duration_active_yr"] * SHARE[k] for k in range(NB)]
    for bid, yr in SLOPE_LEGS[r["slope_position"]]:
        v["slope"][BIDS.index(bid)] += yr
    if r["curvature_position"] == "bullet":
        for bid, yr in BULLET_LEGS:
            v["curvature"][BIDS.index(bid)] += yr
    return v


def contrib(v, dy):
    return {k: -sum(v[k][b] * dy[b] for b in range(NB)) for k in EST}


att = {"months": [], "start_date": [], "end_date": [], "partial": [],
       "market": {"d10y_bp": [], "d2s10s_bp": [], "dfly_bp": []},
       "position": {"duration_yr": [], "slope": [], "curvature": []},
       "contrib_bp": {k: [] for k in EST + ["est"]}}
diff = {"d10y": 0.0, "d2s10s": 0.0, "dfly": 0.0}
RAW = []                                                       # 반올림 전 값 (적중 횟수와 통계용)
cur_detail = None
for m, r in enumerate(ROWS):
    a = at(r["decision_date"])
    last = m == M - 1
    b = at(RATES_DATE) if last else at(ROWS[m + 1]["decision_date"])
    dy = [(rep_yield(k, b) - rep_yield(k, a)) * 100 for k in range(NB)]
    d10 = (Y["10Y"][b] - Y["10Y"][a]) * 100
    d2s10s = spread_bp("s2s10s", b) - spread_bp("s2s10s", a)
    dfly = spread_bp("fly", b) - spread_bp("fly", a)
    if r["next_d10y_bp"] is not None:
        diff["d10y"] = max(diff["d10y"], abs(d10 - r["next_d10y_bp"]))
        diff["d2s10s"] = max(diff["d2s10s"], abs(d2s10s - r["next_d2s10s_bp"]))
        diff["dfly"] = max(diff["dfly"], abs(dfly - r["next_dfly_bp"]))
    v = overlay_vec(r)
    vals = contrib(v, dy)
    vals["est"] = sum(vals.values())
    RAW.append(vals)
    att["months"].append(r["apply_month"])
    att["start_date"].append(DATES[a])
    att["end_date"].append(DATES[b])
    att["partial"].append(bool(last and DATES[b][:7] == r["apply_month"] and next_month(r["apply_month"]) > DATES[b][:7]))
    att["market"]["d10y_bp"].append(rnd(d10, 1))
    att["market"]["d2s10s_bp"].append(rnd(d2s10s, 1))
    att["market"]["dfly_bp"].append(rnd(dfly, 1))
    att["position"]["duration_yr"].append(r["duration_active_yr"])
    att["position"]["slope"].append(r["slope_position"])
    att["position"]["curvature"].append(r["curvature_position"])
    for k, x in vals.items():
        att["contrib_bp"][k].append(rnd(x, 4))
    if last:                                                    # 이번 달 Duration 기여를 버킷별로 (카드의 이유 한 줄에 쓴다)
        cur_detail = {"rep_change_bp": [rnd(x, 1) for x in dy],
                      "duration_by_bucket_bp": [rnd(-v["duration"][k] * dy[k], 4) for k in range(NB)]}

cum = {}
for k in EST + ["est"]:
    run, out = 0.0, []
    for x in RAW:
        run += x[k]
        out.append(rnd(run, 4))
    cum[k] = out
att["cum_bp"] = cum
for k in ("carry", "other", "excess"):                          # 아직 없는 값
    att["contrib_bp"][k] = None
    att["cum_bp"][k] = None

check("월별 시장 움직임이 scoreboard 의 next_* 와 같은가 (최대 차이 bp)", "0.5 이하",
      {k: rnd(x, 2) for k, x in diff.items()}, max(diff.values()) <= 0.5)

# 이번 달 일별 (이번 달 선): 판정일 뒤 날마다의 금리로 계산
a, b = at(DECISION_DATE), at(RATES_DATE)
v_cur = overlay_vec(current)
mtd = {"dates": [], "contrib_cum_bp": {k: [] for k in EST + ["est"]}}
for i in range(a, b + 1):
    dy = [(rep_yield(k, i) - rep_yield(k, a)) * 100 for k in range(NB)]
    row = contrib(v_cur, dy)
    row["est"] = sum(row.values())
    mtd["dates"].append(DATES[i])
    for k, x in row.items():
        mtd["contrib_cum_bp"][k].append(rnd(x, 4))
check("이번 달 일별 선의 끝값 = 이번 달 기여 (세 전략 합)", att["contrib_bp"]["est"][-1], mtd["contrib_cum_bp"]["est"][-1],
      abs(att["contrib_bp"]["est"][-1] - mtd["contrib_cum_bp"]["est"][-1]) < 0.0002)

PARTIAL = att["partial"][-1]


def stats(idx):
    """끝난 달만으로 평균이 0 과 구분되는지(t), 그리고 가장 크게 밀린 폭"""
    done_i = [i for i in idx if not (i == M - 1 and PARTIAL)]
    xs = [RAW[i]["est"] for i in done_i]
    out = {"n_done": len(xs), "per_year_bp": rnd(sum(xs) / len(xs) * 12, 2) if xs else None, "t": None}
    if len(xs) >= 24:
        mu = sum(xs) / len(xs)
        sd = math.sqrt(sum((x - mu) ** 2 for x in xs) / (len(xs) - 1))
        out["t"] = rnd(mu / (sd / math.sqrt(len(xs))), 2) if sd else None
    run = peak = dd = 0.0
    peak_m = trough_m = dd_peak_m = None
    for i in idx:
        run += RAW[i]["est"]
        if run > peak:
            peak, peak_m = run, att["months"][i]
        if run - peak < dd:
            dd, trough_m, dd_peak_m = run - peak, att["months"][i], peak_m
    out["max_drawdown_bp"] = rnd(dd, 1)
    out["drawdown_from"], out["drawdown_to"] = dd_peak_m, trough_m
    return out


def period(key, label, first):
    idx = [i for i, mth in enumerate(att["months"]) if mth >= first]
    sm = {k: rnd(sum(RAW[i][k] for i in idx), 4) for k in EST + ["est"]}
    sm.update({"carry": None, "other": None, "excess": None})
    return {"key": key, "label": label, "i0": idx[0], "n_months": len(idx),
            "from": att["start_date"][idx[0]], "to": att["end_date"][-1], "sum_bp": sm, "stats": stats(idx)}


cur_m = att["months"][-1]
periods = [
    period("mtd", "이번 달", cur_m),
    period("ytd", "연초 이후", cur_m[:4] + "-01"),
    period("1y", "최근 1년", att["months"][-12]),
    period("2021", "2021년 이후", TEST_START),
    period("2015", "2015년 이후", att["months"][0]),
]
ok_sum = all(abs(sum(p["sum_bp"][k] for k in EST) - p["sum_bp"]["est"]) <= 0.0005 for p in periods)
check("기간별 워터폴: 세 전략의 합 = 합계 (5개 기간)", "모두 일치", "모두 일치" if ok_sum else "어긋남", ok_sum)
check("2015년 이후 합계 = 누적 계열의 끝값", periods[-1]["sum_bp"]["est"], cum["est"][-1],
      abs(periods[-1]["sum_bp"]["est"] - cum["est"][-1]) < 0.0005)

# 적중 횟수: 끝난 달만 센다 (이번 달은 진행 중). 기여를 0.01bp 단위로 반올림해 0 보다 큰 달만 적중이다 (0 은 적중이 아님).
done = [i for i in range(M) if ROWS[i]["next_d10y_bp"] is not None]
SGN = {"steepener": 1, "flattener": -1, "none": 0}


def hit_count(key, on, market_ok=None):
    idx = [i for i in done if on(ROWS[i])]
    hit = lambda i: round(RAW[i][key], 2) > 0
    out = {"on": len(idx), "hits": sum(1 for i in idx if hit(i))}
    if market_ok:
        out["market"] = {"hits": sum(1 for i in idx if market_ok(ROWS[i])),
                         "differs": sum(1 for i in idx if hit(i) != market_ok(ROWS[i]))}
    return out


h_dur = hit_count("duration", lambda r: r["duration_active_yr"] != 0, lambda r: r["duration_active_yr"] * r["next_d10y_bp"] < 0)
h_dur["market"]["note"] = "scoreboard 방식: 다음 달 10년 금리가 포지션에 유리한 쪽으로 움직인 달"
h_slope = hit_count("slope", lambda r: r["slope_position"] != "none", lambda r: SGN[r["slope_position"]] * r["next_d2s10s_bp"] > 0)
h_slope["market"]["note"] = "scoreboard 방식: 다음 달 2s10s 방향. 기여는 2년과 30년 금리로 계산하므로 달이 다를 수 있음"
h_curv = hit_count("curvature", lambda r: r["curvature_position"] == "bullet")
hits = {"through": ROWS[done[-1]]["apply_month"], "months": len(done), "min_n_for_ratio": 20,
        "rule": "포지션이 있던 달 중 그 전략의 기여가 0보다 큰 달을 셉니다 (0.01bp 단위로 반올림). 끝난 달만 셉니다.",
        "duration": {**h_dur, "kind": "estimate"}, "slope": {**h_slope, "kind": "estimate"},
        "curvature": {**h_curv, "kind": "estimate"},
        "carry": {"on": len(done), "hits": None, "kind": "pending"}}
if hits["through"] == "2026-10":
    check("Duration 적중 (scoreboard 방식, 2026-10 까지)", "55/109", f"{h_dur['market']['hits']}/{h_dur['on']}",
          (h_dur["market"]["hits"], h_dur["on"]) == (55, 109))

# 가정한 포지션 크기를 버킷 비중으로 바꾸면 얼마인가 (한도와 견주어 보려고)
leg_pp = {bid: rnd(SLOPE_LEG_YR / BENCH_BDUR[BIDS.index(bid)] * 100, 2) for bid in ("1-3", "20+")}
bullet_vec = [0.0] * NB
for bid, yr in BULLET_LEGS:
    bullet_vec[BIDS.index(bid)] += yr
bullet_in_steep = -sum(bullet_vec[k] * twist(1)[k] for k in range(NB))

attribution = {
    "kinds": {"market": "real", "position": "real", "duration": "estimate", "slope": "estimate", "curvature": "estimate",
              "est": "estimate", "carry": "pending", "other": "pending", "excess": "pending"},
    "method": {
        "duration": "기여 = −Σ(그달 액티브 듀레이션 × 벤치마크(대용 지수) 듀레이션 기여 비율 × 버킷 대표 금리의 그달 변화)입니다. 버킷 비율은 지금의 대용 지수 값을 과거에도 그대로 썼습니다.",
        "slope": f"다리 하나에 {SLOPE_LEG_YR:.2f}년이라고 가정했습니다. 스티프너는 1–3 버킷 +{SLOPE_LEG_YR:.2f}년, 20y+ 버킷 −{SLOPE_LEG_YR:.2f}년이고 플래트너는 반대입니다. 그래서 기여는 2년과 30년 금리의 차이로 정해집니다.",
        "curvature": f"불릿은 5–7 버킷 +{CURV_BELLY_YR:.2f}년, 1–3과 10–20 버킷 −{CURV_WING_YR:.2f}년씩이라고 가정했습니다.",
        "est": "Duration + Slope + Curvature 입니다. 화면의 누적 선과 맨 위 초과수익 타일이 이 값입니다.",
        "carry": "아직 없습니다. 기본값은 포트폴리오 carry+roll − 벤치마크(대용 지수) carry+roll 이고 팀 확정 전입니다.",
        "other": "아직 없습니다. 초과수익에서 네 전략을 뺀 나머지이고, 종목 가격으로 과거를 다시 만든 뒤에 나옵니다.",
        "excess": "아직 없습니다. 종목 가격으로 과거를 다시 만든 뒤에 나옵니다.",
    },
    "assumed_size": {
        "slope_legs": {k: [{"bucket": bid, "yr": yr} for bid, yr in legs] for k, legs in SLOPE_LEGS.items() if legs},
        "bullet_legs": [{"bucket": bid, "yr": yr} for bid, yr in BULLET_LEGS],
        "slope_leg_weight_pp": leg_pp, "bucket_limit_pp": BUCKET_LIMIT_PP,
        "slope_leg_over_limit": leg_pp["1-3"] > BUCKET_LIMIT_PP,
        "bullet_pnl_in_steepening_bp": rnd(bullet_in_steep, 2),
    },
    "split": {"train_end": TRAIN_END, "test_start": TEST_START, "daily_start": DAILY_START},
    "current": {"month": cur_m, "partial": PARTIAL, "from": att["start_date"][-1], "to": att["end_date"][-1], **cur_detail},
    **att,
    "mtd_daily": mtd,
    "periods": periods,
    "hits": hits,
}

# ================================================================= 8. 쓰기
sources = [
    {"id": "curve", "path": rel(CURVE_JS), "modified": mtime(CURVE_JS), "kind": "real",
     "use": "수익률곡선, 스프레드, Fly z-score, 금리 공분산, 월별 금리 변화"},
    {"id": "scoreboard", "path": rel(sb_path), "modified": mtime(sb_path), "kind": "real",
     "use": "점수 5개, 뷰 3개, 포지션, 판단 기록"},
    {"id": "benchmark", "path": rel(BENCH_JSON), "modified": mtime(BENCH_JSON), "kind": "real",
     "use": "대용 지수의 버킷 비중·듀레이션·수익률·carry+roll (공식 값과의 대조 항목은 쓰지 않음)"},
    {"id": "universe", "path": rel(UNIVERSE_CSV), "modified": mtime(UNIVERSE_CSV), "kind": "real",
     "use": "예시 포트폴리오에 담은 종목의 가격·경과이자·듀레이션·carry+roll"},
]
if LIVE:
    sources.insert(2, {"id": "scoreboard_live", "path": rel(SB_JS), "modified": mtime(SB_JS), "kind": "real",
                       "use": "다음 달 잠정 판정 (live)"})

out = {
    "schema": 1, "mock": True,
    "title": "운용 페이지 화면 시안 자료",
    "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
    "kinds": {"real": "공개 자료에서 그대로 읽었거나 그것만으로 계산한 값",
              "estimate": "포지션 × 금리 변화로 추정한 값",
              "example": "초기 포트폴리오가 정해지기 전이라 견본 포트폴리오로 계산한 값",
              "pending": "종목 가격으로 과거를 다시 만든 뒤에야 나오는 값 (지금은 비어 있음)"},
    "asof": {"price_date": PRICE_DATE, "settle_date": SETTLE_DATE, "rates_date": RATES_DATE,
             "decision_date": DECISION_DATE, "apply_month": APPLY_MONTH,
             "next_date": nxt["decision_date"], "next_apply_month": nxt["apply_month"],
             "note": "종목 종가는 하루 늦게 나옵니다. 그래서 평가 기준일이 금리 기준일보다 하루 이릅니다."},
    "sources": sources,
    "params": {"nav_base_usd": NAV_BASE, "bucket_limit_pp": BUCKET_LIMIT_PP, "te_budget_bp": TE_BUDGET_BP,
               "n_holdings_range": N_RANGE, "cash_range_pct": CASH_RANGE_PCT,
               "slope_leg_yr": SLOPE_LEG_YR, "curvature_belly_yr": CURV_BELLY_YR, "curvature_wing_yr": CURV_WING_YR,
               "cov_window_m": COV_WINDOW_M,
               "cash_yield_pct": CASH_YIELD_PCT, "min_maturity_y": MIN_MATURITY_Y,
               "undecided": ["버킷 한도 (±5%p / ±10%p)",
                             "성과를 네 전략으로 나누는 방법, 특히 Carry & Rolldown 기여를 어떻게 셀지",
                             "Slope·Curvature 포지션의 크기와 버킷 위치 (지금은 다리당 0.10년, 2년과 30년 쪽)",
                             "현금 이자 (지금은 0)", "종목 하나의 비중 한도 (지금은 없음)", "거래비용 (지금은 0)"]},
    "buckets": BUCKETS,
    "strategies": [{"key": "duration", "name": "Duration"}, {"key": "slope", "name": "Curve Slope"},
                   {"key": "curvature", "name": "Curve Curvature"}, {"key": "carry", "name": "Carry & Rolldown"},
                   {"key": "other", "name": "기타"}],
    "scoreboard": scoreboard,
    "rates": rates,
    "benchmark": benchmark,
    "portfolio": portfolio,
    "risk": risk,
    "attribution": attribution,
    "checks": checks,
}

bad_checks = [c for c in checks if not c["ok"]]
if bad_checks:                                                  # 검산이 어긋나면 자료 파일을 쓰지 않는다
    print(f"\n검산 {len(checks)}개 중 {len(bad_checks)}개가 어긋나 {OUT.name} 를 쓰지 않았습니다.")
    for c in bad_checks:
        print(f"  - {c['name']}: 기준 {c['expected']} / 계산 {c['got']}")
    sys.exit(1)

text = json.dumps(out, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
for banned in ("LUATTRUU", "Bloomberg", "validation"):
    assert banned not in text, f"자료 파일에 들어가면 안 되는 말: {banned}"
OUT.write_text("window.PORTFOLIO_MOCK = " + text + ";\n", encoding="utf-8")

p15 = periods[-1]
print(f"\n{OUT.name} 를 썼습니다 ({OUT.stat().st_size / 1024:.0f} KB). 검산 {len(checks)}개가 모두 맞습니다.")
print(f"  기준일: 종목 평가 {PRICE_DATE} · 금리 {RATES_DATE} · 판정 {DECISION_DATE} → {APPLY_MONTH} 적용")
print(f"  금리: 2s10s {latest['s2s10s_bp']:.0f}bp · 5s30s {latest['s5s30s_bp']:.0f}bp · Fly {latest['fly_bp']:.0f}bp · z {latest['fly_z_3y']:+.2f} (3년) / {latest['fly_z_1y']:+.2f} (1년)")
print(f"  벤치마크(대용 지수): 듀레이션 {BENCH_DUR:.2f}년 · 수익률 {bt['yield_pct']:.2f}% · 월 carry+roll {bt['carry_roll_1m_bp']:.1f}bp · 가격 출처 FedInvest {n_fed} / 발행 전 {n_wi} / CMT 보간 {n_interp}")
print(f"  예시 포트폴리오: NAV USD {NAV:,.2f} · {len(holdings)}종목 · 현금 {cash_pct:.2f}% · 듀레이션 {PORT_DUR:.3f}년 (액티브 {ACTIVE_TOTAL:+.3f}년)")
print(f"  추적오차: {TE_NOW:.1f}bp (Duration 포지션만 {TE_RULE:.1f}bp · ±0.5년이면 {TE_MAX:.1f}bp) · 공분산 표본 {nobs}일 ({cov_start} ~)")
print(f"  세 전략 기여(추정): 이번 달 {periods[0]['sum_bp']['est']:+.2f}bp · 연초 이후 {periods[1]['sum_bp']['est']:+.1f}bp · 2015년 이후 {p15['sum_bp']['est']:+.1f}bp "
      f"(1년에 {p15['stats']['per_year_bp']:+.1f}bp, t {p15['stats']['t']:+.2f}, 가장 크게 밀린 폭 {p15['stats']['max_drawdown_bp']:.1f}bp)")
print(f"  적중: Duration {h_dur['hits']}/{h_dur['on']} (10년 금리 방향으로는 {h_dur['market']['hits']}, 다른 달 {h_dur['market']['differs']}개) · "
      f"Slope {h_slope['hits']}/{h_slope['on']} (2s10s 방향으로는 {h_slope['market']['hits']}, 다른 달 {h_slope['market']['differs']}개) · Curvature {h_curv['hits']}/{h_curv['on']}")
print("  Carry · 기타 · 초과수익 합계는 비워 두었습니다 (종목 가격으로 과거를 다시 만든 뒤에 채움).")
