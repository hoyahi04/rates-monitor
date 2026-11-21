"""매크로 · 인플레이션 신호와 백테스트 계산 → signals.js + signals_monthly.csv

신호 (매월 마지막 거래일에 판정, 그날까지 공개된 값만 사용)
  1) 물가 모멘텀 = Core PCE 3개월 연율 − 12개월 상승률 (%p)
       −0.3 이하 → +1(둔화, 금리 하락 쪽) / +0.3 이상 → −1(재가속) / 그 사이 0      → 수준 뷰(Duration)
  2) 장기 기대   = 5y5y 기대 인플레이션의 3개월 변화 (bp)
       +15 이상 → +1(스티프닝 쪽) / −15 이하 → −1(플래트닝 쪽) / 그 사이 0          → 기울기 뷰(Curve Slope)

백테스트 (성과월 2015-01 ~ 직전 완료월. 2015~2020은 규칙 설정, 2021~은 검증 구간)
  Q1) Core CPI 발표일: 서프라이즈 0.1%p당 2년·10년 금리 변화 (반응형)
  Q2) 물가 모멘텀 점수 → 다음 달 10년 금리 변화 (예측형)
  Q3) 장기 기대 점수   → 다음 달 5s30s 변화 (예측형)

입력: realtime_releases.csv, inflation_daily.csv, policy_rate.csv (fetch_data.py가 생성), 수익률곡선(CURVE_JS)
      cpi_consensus.csv 의 survey_mom 열을 채우면 Q1의 서프라이즈가 '실제 − 컨센서스'로 바뀐다.
실행: python3 analyze.py
"""
import csv, json, math
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parents[1] / "curve" / "data.js"   # 일별 CMT 금리(공통 데이터). 옮기면 이 줄만 고친다.

TH_MOMENTUM = 0.3    # %p   ← 백테스트 전에 정한 값. 결과를 보고 바꾸지 않는다.
TH_EXPECT = 15       # bp
BT_START = "2015-01"            # 첫 성과월
TEST_START = "2021-01"          # 검증 구간 첫 성과월
MIN_CONSENSUS = 24              # 컨센서스가 이만큼 채워져야 대용치 대신 사용
REGIME_KO = {"hike": "인상기", "cut": "인하기", "hold": "동결기"}


# ---------- 입력 ----------
def read_csv(name):
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def load_curve():
    t = CURVE_JS.read_text(encoding="utf-8")
    d = json.loads(t[t.index("{"):t.rindex("}") + 1])
    return d["dates"], d["yields"]


class Daily:
    """날짜 오름차순 시계열. at(d) = d 이하 마지막 관측값."""

    def __init__(self, dates, values):
        pairs = [(d, v) for d, v in zip(dates, values) if v is not None]
        self.dates = [p[0] for p in pairs]
        self.values = [p[1] for p in pairs]
        self.index = {d: i for i, d in enumerate(self.dates)}

    def at(self, d):
        lo, hi = 0, len(self.dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.dates[mid] <= d:
                lo = mid + 1
            else:
                hi = mid
        return self.values[lo - 1] if lo else None

    def day_change(self, d):
        """d 당일 종가 − 직전 거래일 종가. d가 거래일이 아니면 None."""
        i = self.index.get(d)
        return None if not i else self.values[i] - self.values[i - 1]


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    last = [31, 29 if (y2 % 4 == 0 and (y2 % 100 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(day, last):02d}"


def next_month(ym):
    k = int(ym[:4]) * 12 + int(ym[5:7])
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


# ---------- 국면 ----------
def build_regimes(changes, end):
    """같은 방향의 연속된 금리 변경을 한 사이클로 묶는다(첫 변경일 ~ 마지막 변경일). 그 사이는 동결기.
    사후에 붙이는 분류라서 신호 계산에는 쓰지 않고, 결과를 나눠 보는 데만 쓴다."""
    moves = [(changes[i][0], "hike" if changes[i][1] > changes[i - 1][1] else "cut") for i in range(1, len(changes))]
    cycles = []
    for d, kind in moves:
        if cycles and cycles[-1]["type"] == kind:
            cycles[-1]["end"] = d
        else:
            cycles.append({"start": d, "end": d, "type": kind})
    # 마지막 변경이 최근 6개월 안이면 그 사이클이 진행 중인 것으로 본다
    if cycles and (datetime.strptime(end, "%Y-%m-%d") - datetime.strptime(cycles[-1]["end"], "%Y-%m-%d")).days <= 183:
        cycles[-1]["end"] = end
    out, cur = [], changes[0][0]
    for c in cycles:
        if c["start"] > cur:
            out.append({"start": cur, "end": c["start"], "type": "hold"})
        out.append(c)
        cur = c["end"]
    if cur < end:
        out.append({"start": cur, "end": end, "type": "hold"})
    return out


def regime_at(regimes, d):
    for r in regimes:
        if r["type"] != "hold" and r["start"] <= d <= r["end"]:
            return r["type"]
    return "hold"


# ---------- 통계 ----------
def mean(xs):
    return sum(xs) / len(xs) if xs else None


def r1(x, n=1):
    return None if x is None else round(x, n)


def welch_t(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va = sum((x - mean(a)) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mean(b)) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (mean(a) - mean(b)) / se if se else None


def ols(xs, ys):
    """y = a + b·x → (b, R², b의 t값)"""
    n = len(xs)
    if n < 3:
        return None, None, None
    mx, my = mean(xs), mean(ys)
    sxx = sum((x - mx) ** 2 for x in xs)
    if not sxx:
        return None, None, None
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sxx
    a = my - b * mx
    sse = sum((y - a - b * x) ** 2 for x, y in zip(xs, ys))
    sst = sum((y - my) ** 2 for y in ys)
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 else None
    return b, (1 - sse / sst if sst else None), (b / se if se else None)


def score(x, th, sign=1):
    """sign=+1: x가 +th 이상이면 +1.  sign=−1: x가 −th 이하이면 +1."""
    if x is None:
        return None
    if x >= th:
        return sign
    if x <= -th:
        return -sign
    return 0


def summarize(rows, skey, tkey, expect):
    """점수별 다음 달 결과. expect: 점수 +1일 때 기대하는 변화의 부호(+1 상승 / −1 하락)."""
    rows = [r for r in rows if r[skey] is not None and r[tkey] is not None]
    out = {"n": len(rows), "by": []}
    grp = {s: [r[tkey] for r in rows if r[skey] == s] for s in (1, 0, -1)}
    for s in (1, 0, -1):
        xs = grp[s]
        hits = None if s == 0 or not xs else sum(1 for x in xs if x * expect * s > 0)
        out["by"].append({"score": s, "n": len(xs), "mean": r1(mean(xs)),
                          "hits": hits, "hit": None if hits is None else round(hits / len(xs) * 100)})
    sig = [(r[skey], r[tkey]) for r in rows if r[skey] != 0]
    h = sum(1 for s, x in sig if x * expect * s > 0)
    out["signal"] = {"n": len(sig), "hits": h, "hit": round(h / len(sig) * 100) if sig else None}
    base = sum(1 for r in rows if r[tkey] * expect > 0)
    out["base"] = round(base / len(rows) * 100) if rows else None       # +1 방향으로 움직인 달의 비율
    out["spread"] = None if not grp[1] or not grp[-1] else r1(mean(grp[1]) - mean(grp[-1]))
    out["t"] = r1(welch_t(grp[1], grp[-1]), 2)
    return out


# ---------- 본 계산 ----------
def main():
    dates, yields = load_curve()
    Y = {k: Daily(dates, yields[k]) for k in ("2Y", "5Y", "10Y", "30Y")}
    asof = dates[-1]
    daily = read_csv("inflation_daily.csv")
    F = Daily([r["date"] for r in daily], [num(r["fwd_5y5y"]) for r in daily])
    BEI = Daily([r["date"] for r in daily], [num(r["bei_10y"]) for r in daily])
    rel = read_csv("realtime_releases.csv")
    pce = [r for r in rel if r["series"] == "core_pce"]
    cpi = [r for r in rel if r["series"] == "core_cpi"]
    changes = [(r["date"], float(r["upper"])) for r in read_csv("policy_rate.csv")]
    regimes = build_regimes(changes, asof)

    def latest(rows, d):
        ok = [r for r in rows if r["release_date"] <= d]
        return ok[-1] if ok else None

    def state(d):
        """날짜 d 종가 시점에 알 수 있는 값으로 두 신호를 계산."""
        p = latest(pce, d)
        a3, yoy = (num(p["ann3"]), num(p["yoy"])) if p else (None, None)
        gap = None if a3 is None or yoy is None else round(a3 - yoy, 3)
        f, f0 = F.at(d), F.at(months_ago(d, 3))
        chg = None if f is None or f0 is None else round((f - f0) * 100, 1)
        return {"date": d, "pce_release": p and p["release_date"], "pce_ref": p and p["ref_month"],
                "ann3": a3, "ann6": p and num(p["ann6"]), "yoy": yoy, "gap": gap,
                "s1": score(gap, TH_MOMENTUM, sign=-1),
                "f5y5y": f, "f5y5y_prev": f0, "chg": chg, "s2": score(chg, TH_EXPECT, sign=1),
                "bei": BEI.at(d), "regime": regime_at(regimes, d)}

    # 월말 결정일: 수익률 데이터의 각 월 마지막 거래일 (진행 중인 달 제외)
    month_end = {}
    for d in dates:
        month_end[d[:7]] = d
    ends = [month_end[m] for m in sorted(month_end) if "2014-12" <= m < asof[:7]]

    monthly = []
    for i, d in enumerate(ends):
        row = state(d)
        row["month"] = next_month(d[:7])           # 이 판정이 적용되는 성과월
        nxt = ends[i + 1] if i + 1 < len(ends) else None
        lv = lambda k, dd: Y[k].at(dd)
        for key, fn in (("d2", lambda dd: lv("2Y", dd)), ("d5", lambda dd: lv("5Y", dd)),
                        ("d10", lambda dd: lv("10Y", dd)), ("d30", lambda dd: lv("30Y", dd)),
                        ("d2s10s", lambda dd: lv("10Y", dd) - lv("2Y", dd)),
                        ("d5s30s", lambda dd: lv("30Y", dd) - lv("5Y", dd))):
            row[key] = None if nxt is None else round((fn(nxt) - fn(d)) * 100, 1)
        monthly.append(row)

    done = [r for r in monthly if r["d10"] is not None and r["month"] >= BT_START]
    train = [r for r in done if r["month"] < TEST_START]
    test = [r for r in done if r["month"] >= TEST_START]
    samples = [("all", "전체", done), ("train", "설정 구간", train), ("test", "검증 구간", test)]

    def backtest(skey, tkey, expect):
        out = {"samples": [], "regimes": []}
        for key, label, rows in samples:
            s = summarize(rows, skey, tkey, expect)
            s.update(key=key, label=label, start=rows[0]["month"], end=rows[-1]["month"])
            out["samples"].append(s)
        for rg in ("hike", "hold", "cut"):
            s = summarize([r for r in done if r["regime"] == rg], skey, tkey, expect)
            s.update(key=rg, label=REGIME_KO[rg])
            out["regimes"].append(s)
        return out

    bt_momentum = backtest("s1", "d10", expect=-1)      # +1(둔화) → 10년 금리 하락 기대
    bt_momentum["also"] = {k: {s["key"]: [g["mean"] for g in summarize(rows, "s1", k, -1)["by"]]
                               for s, (_, _, rows) in zip(bt_momentum["samples"], samples)} for k in ("d2", "d5")}
    bt_expect = backtest("s2", "d5s30s", expect=+1)     # +1(기대 상승) → 5s30s 확대 기대
    # 같은 달 안에서의 관계(동행): 5y5y가 10bp 오른 달에 5s30s·10년 금리는 몇 bp 움직였나
    same = [(m, (F.at(b) - F.at(a)) * 100, (Y["30Y"].at(b) - Y["5Y"].at(b) - Y["30Y"].at(a) + Y["5Y"].at(a)) * 100,
             (Y["10Y"].at(b) - Y["10Y"].at(a)) * 100) for a, b, m in zip(ends, ends[1:], [next_month(e[:7]) for e in ends])
            if m >= BT_START]
    bs, r2s, ts = ols([x[1] for x in same], [x[2] for x in same])
    b10_, r210, t10_ = ols([x[1] for x in same], [x[3] for x in same])
    bt_expect["same_month"] = {"n": len(same), "slope_5s30s": r1(bs * 10), "r2_5s30s": r1(r2s, 2), "t_5s30s": r1(ts, 1),
                               "slope_10y": r1(b10_ * 10), "r2_10y": r1(r210, 2), "t_10y": r1(t10_, 1)}

    # ----- Q1: Core CPI 발표일 반응 -----
    consensus = {}
    cpath = HERE / "cpi_consensus.csv"
    if cpath.exists():
        for r in read_csv("cpi_consensus.csv"):
            if num(r.get("survey_mom")) is not None:
                consensus[r["release_date"]] = num(r["survey_mom"])
    use_cons = len(consensus) >= MIN_CONSENSUS
    firsts = [r for r in cpi if r["is_new"] == "1"]
    events, hist = [], []
    for r in firsts:
        mom = num(r["mom"])
        d = r["release_date"]
        if mom is not None and d[:7] >= BT_START:
            exp = consensus.get(d) if use_cons else (mean(hist[-12:]) if len(hist) >= 12 else None)
            d2, d10 = Y["2Y"].day_change(d), Y["10Y"].day_change(d)
            if exp is not None and d2 is not None and d10 is not None:
                act = round(mom, 1) if use_cons else mom
                events.append({"date": d, "ref": r["ref_month"], "mom": round(mom, 3), "exp": round(exp, 3),
                               "sur": round(act - exp, 3), "d2": round(d2 * 100, 1), "d10": round(d10 * 100, 1),
                               "era": "B" if d >= TEST_START else "A", "regime": regime_at(regimes, d)})
        if mom is not None:
            hist.append(mom)

    cpi_days = {r["release_date"] for r in firsts}
    moves = {k: [(d, abs(Y[k].day_change(d)) * 100) for d in Y[k].dates[1:] if d[:7] >= BT_START] for k in ("2Y", "10Y")}

    def abs_stats(k, lo, hi):
        on = [v for d, v in moves[k] if lo <= d < hi and d in cpi_days]
        off = [v for d, v in moves[k] if lo <= d < hi and d not in cpi_days]
        return r1(mean(on), 2), r1(mean(off), 2), len(on)

    eras = [("A", f"{BT_START[:4]}~{int(TEST_START[:4]) - 1}", BT_START, TEST_START),
            ("B", f"{TEST_START[:4]}~", TEST_START, "9999"), ("all", "전체", BT_START, "9999")]
    by_era = []
    for key, label, lo, hi in eras:
        ev = [e for e in events if lo <= e["date"] < hi]
        b2, r2_2, t2 = ols([e["sur"] for e in ev], [e["d2"] for e in ev])
        b10, r2_10, t10 = ols([e["sur"] for e in ev], [e["d10"] for e in ev])
        on2, off2, _ = abs_stats("2Y", lo, hi)
        on10, off10, _ = abs_stats("10Y", lo, hi)
        by_era.append({"key": key, "label": label, "n": len(ev),
                       "slope2": r1(b2 and b2 / 10), "r2_2": r1(r2_2, 2), "t2": r1(t2, 1),      # bp per 0.1%p
                       "slope10": r1(b10 and b10 / 10), "r2_10": r1(r2_10, 2), "t10": r1(t10, 1),
                       "abs_cpi2": on2, "abs_other2": off2, "abs_cpi10": on10, "abs_other10": off10})
    by_year = []
    for y in range(int(BT_START[:4]), int(asof[:4]) + 1):
        on2, off2, n = abs_stats("2Y", f"{y}-01-01", f"{y + 1}-01-01")
        if n:
            by_year.append({"year": y, "n": n, "abs_cpi2": on2, "abs_other2": off2})

    # ----- 현재 판정 -----
    cur = state(asof)
    c = latest(cpi, asof)
    cur["cpi"] = {"release": c["release_date"], "ref": c["ref_month"], "mom": num(c["mom"]),
                  "ann3": num(c["ann3"]), "yoy": num(c["yoy"])}
    cur["policy_upper"] = changes[-1][1]

    cols = ["date", "month", "pce_release", "pce_ref", "ann3", "yoy", "gap", "s1", "f5y5y", "chg", "s2",
            "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    with open(HERE / "signals_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision_date", "apply_month", "pce_release", "pce_ref_month", "core_pce_3m_ann", "core_pce_12m",
                    "momentum_gap", "score_momentum", "fwd_5y5y", "fwd_5y5y_chg_3m_bp", "score_expect", "regime",
                    "next_d2y_bp", "next_d5y_bp", "next_d10y_bp", "next_d30y_bp", "next_d2s10s_bp", "next_d5s30s_bp"])
        for r in monthly:
            w.writerow(["" if r[c_] is None else r[c_] for c_ in cols])

    # 컨센서스 입력 틀: 없으면 만들고, 있으면 새 발표일만 덧붙인다(입력한 값은 보존)
    old = {r["release_date"]: r.get("survey_mom", "") for r in read_csv("cpi_consensus.csv")} if cpath.exists() else {}
    with open(cpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["release_date", "ref_month", "actual_mom_first_print", "survey_mom"])
        for r in firsts:
            if r["release_date"][:7] >= BT_START and num(r["mom"]) is not None:
                w.writerow([r["release_date"], r["ref_month"], round(num(r["mom"]), 2), old.get(r["release_date"], "")])

    keys = ["date", "month", "pce_ref", "gap", "s1", "f5y5y", "chg", "s2", "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "asof": asof,
        "thresholds": {"momentum": TH_MOMENTUM, "expect": TH_EXPECT},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["month"]},
        "current": cur, "regimes": regimes,
        "monthly": {k: [r[k] for r in monthly] for k in keys},
        "events": events, "event_source": "consensus" if use_cons else "proxy",
        "event_stats": {"by_era": by_era, "by_year": by_year},
        "bt": {"momentum": bt_momentum, "expect": bt_expect},
    }
    (HERE / "signals.js").write_text(
        "window.INFLATION_SIGNALS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda s: {1: "+1", 0: " 0", -1: "−1", None: " ?"}[s]
    print(f"\n[현재 판정] 기준일 {asof} · 국면 {REGIME_KO[cur['regime']]}")
    print(f"  물가 모멘텀 {sc(cur['s1'])}  (Core PCE {cur['pce_ref']}: 3개월 {cur['ann3']}% − 12개월 {cur['yoy']}% = {cur['gap']:+.2f}%p)")
    print(f"  장기 기대   {sc(cur['s2'])}  (5y5y {cur['f5y5y']}% , 3개월 변화 {cur['chg']:+.0f}bp)")
    for title, bt, unit in (("Q2 물가 모멘텀 → 다음 달 10년 금리", bt_momentum, "Δ10y"), ("Q3 장기 기대 → 다음 달 5s30s", bt_expect, "Δ5s30s")):
        print(f"\n[{title}]  (평균 {unit} bp / 적중률)")
        for s in bt["samples"] + bt["regimes"]:
            by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '+.1f'):>6s}"
                           f"{'' if g['hit'] is None else ' (' + str(g['hit']) + '%)':>7s}" for g in s["by"])
            print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | 신호 적중 {s['signal']['hits']}/{s['signal']['n']}"
                  f" 기준선 {s['base']}%  (+1)−(−1)={s['spread']} t={s['t']}")
    print(f"\n[Q1 Core CPI 발표일]  서프라이즈 = {'실제 − 컨센서스' if use_cons else '실제 − 직전 12개월 평균(대용치)'}")
    for e in by_era:
        print(f"  {e['label']:10s} n={e['n']:<3d} 0.1%p당 2y {e['slope2']}bp (R² {e['r2_2']}, t {e['t2']})  10y {e['slope10']}bp (R² {e['r2_10']}, t {e['t10']})"
              f"  | |Δ2y| 발표일 {e['abs_cpi2']} vs 평소 {e['abs_other2']}bp")
    print(f"\n→ signals.js, signals_monthly.csv 저장 (월 {len(monthly)}개, 발표일 {len(events)}개)")


if __name__ == "__main__":
    main()
