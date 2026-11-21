"""매크로 · 수급·기간 프리미엄 신호와 백테스트 계산 → signals.js + signals_monthly.csv

신호 (매월 마지막 거래일에 판정, 그날까지 공개된 값만 사용)
  1) 공급 압력 = 민간이 받아야 하는 장기물 순공급의 가속 (%)
       장기물 순공급 = Bonds(발행 만기 20·30년) 잔액 증감 − 연준의 Bonds 보유 증감
       가속 = [최근 3개월 합 − 직전 12개월의 3개월 평균] ÷ 민간 보유 Bonds 잔액 × 100
       설정 구간(2015~2020) 신호 분포의 상위 1/3 → +1(공급 부담 증가, 스티프닝 쪽)
       하위 1/3 → −1(공급 부담 감소, 플래트닝 쪽) / 그 사이 0                      → 기울기 뷰(Curve Slope)
       ※ 문턱값은 신호 분포만 보고 정한다. 금리 결과는 보지 않는다.
  2) 기간 프리미엄 = ACM 10년 기간 프리미엄의 3개월 변화 (bp)
       +15 이상 → +1(스티프닝 쪽) / −15 이하 → −1(플래트닝 쪽) / 그 사이 0          → 참고 지표

백테스트 (성과월 2015-01 ~ 직전 완료월. 2015~2020은 규칙 설정, 2021~은 검증 구간)
  Q1) 10·20·30년 입찰일: 입찰 약세(직전 6회 평균 응찰률 − 응찰률) 0.1당 10년·30년·5s30s 변화 (반응형)
      분기 환매(QRA) 발표일의 변동폭도 함께 본다.
  Q2) 공급 압력 점수   → 다음 달 5s30s 변화 (예측형)
  Q3) 기간 프리미엄 점수 → 다음 달 5s30s 변화 (예측형) + 같은 달 안에서의 관계

입력: auctions.csv, supply_monthly.csv, tp_daily.csv, refunding_dates.csv, policy_rate.csv
      (fetch_data.py가 생성), 수익률곡선(CURVE_JS), FOMC 날짜(FOMC_CSV, 없으면 생략)
      auction_wi.csv 의 wi_yield 열을 채우면 Q1의 입찰 약세가 tail(낙찰금리 − WI 금리)로 바뀐다.
실행: python3 analyze.py
"""
import csv, json, math
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parents[1] / "curve" / "data.js"   # 일별 CMT 금리(공통 데이터). 옮기면 이 줄만 고친다.
FOMC_CSV = HERE.parent / "01_policy_path" / "fomc_dates.csv"   # QRA 발표일과 FOMC가 겹치는 날을 가려낼 때만 쓴다

TH_TP = 15                      # bp   ← 백테스트 전에 정한 값. 결과를 보고 바꾸지 않는다.
TERCILE = (1 / 3, 2 / 3)        # 공급 압력 문턱값: 설정 구간 신호 분포의 분위
MSPD_LAG_DAY = 8                # 전월 말 잔액 통계(MSPD)는 매월 4영업일쯤 발표 → 8일부터 쓸 수 있다고 본다
LOOKBACK = 6                    # 입찰 약세의 기준: 같은 만기 직전 6회 평균
LONG = ("10Y", "20Y", "30Y")    # Q1에서 보는 입찰
BT_START = "2015-01"            # 첫 성과월
TEST_START = "2021-01"          # 검증 구간 첫 성과월
MIN_WI = 24                     # WI 금리가 이만큼 채워져야 응찰률 대신 tail을 쓴다
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


def stdev(xs):
    return math.sqrt(sum((x - mean(xs)) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else None


def r1(x, n=1):
    return None if x is None else round(x, n)


def quantile(xs, q):
    """선형 보간 분위수."""
    s = sorted(xs)
    pos = (len(s) - 1) * q
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


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


def score_band(x, lo, hi):
    """x가 hi 이상이면 +1, lo 이하이면 −1, 그 사이 0."""
    if x is None:
        return None
    return 1 if x >= hi else -1 if x <= lo else 0


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
    SL = Daily(dates, [None if a is None or b is None else round(b - a, 4)
                       for a, b in zip(yields["5Y"], yields["30Y"])])          # 5s30s (%p)
    asof = dates[-1]
    tp = read_csv("tp_daily.csv")
    TP = Daily([r["date"] for r in tp], [num(r["acm_tp10"]) for r in tp])
    use_acm = bool(TP.dates)
    if not use_acm:   # xlrd가 없어 ACM을 못 받은 경우: Kim-Wright로 대신한다
        TP = Daily([r["date"] for r in tp], [num(r["kw_tp10"]) for r in tp])
    sup = read_csv("supply_monthly.csv")
    S_ym = [r["date"][:7] for r in sup]
    S_net = [num(r["long_net_bn"]) for r in sup]
    S_priv = [None if num(r["bonds_bn"]) is None or num(r["soma_bonds_bn"]) is None
              else num(r["bonds_bn"]) - num(r["soma_bonds_bn"]) for r in sup]
    S_idx = {m: i for i, m in enumerate(S_ym)}
    changes = [(r["date"], float(r["upper"])) for r in read_csv("policy_rate.csv")]
    regimes = build_regimes(changes, asof)

    def supply_state(d):
        """날짜 d에 공개돼 있던 잔액 통계로 공급 압력을 계산. 월말에는 전월 말 값까지만 쓴다."""
        ref = months_ago(d[:8] + "01", 1 if int(d[8:10]) >= MSPD_LAG_DAY else 2)[:7]
        while ref not in S_idx and ref > S_ym[0]:      # 최신 달이 아직 수집되지 않았으면 한 달 앞으로
            ref = months_ago(ref + "-01", 1)[:7]
        i = S_idx.get(ref)
        if i is None or i < 14 or any(v is None for v in S_net[i - 14:i + 1]) or not S_priv[i - 3]:
            return {"ref": ref, "sum3": None, "prev3": None, "accel": None, "priv": None, "pct": None}
        sum3, prev3 = sum(S_net[i - 2:i + 1]), sum(S_net[i - 14:i - 2]) / 4
        return {"ref": ref, "sum3": round(sum3, 1), "prev3": round(prev3, 1), "accel": round(sum3 - prev3, 1),
                "priv": round(S_priv[i - 3], 1), "pct": round((sum3 - prev3) / S_priv[i - 3] * 100, 3)}

    def state(d):
        """날짜 d 종가 시점에 알 수 있는 값으로 두 신호의 원자료를 계산 (점수는 문턱값을 정한 뒤 붙인다)."""
        t, t0 = TP.at(d), TP.at(months_ago(d, 3))
        chg = None if t is None or t0 is None else round((t - t0) * 100, 1)
        return {"date": d, **supply_state(d), "tp10": t, "tp10_prev": t0, "chg": chg,
                "s5s30": SL.at(d), "y10": Y["10Y"].at(d), "y30": Y["30Y"].at(d), "regime": regime_at(regimes, d)}

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

    # 공급 압력 문턱값: 설정 구간의 신호 분포만 본다 (금리 결과는 보지 않는다)
    train_pct = [r["pct"] for r in monthly if BT_START <= r["month"] < TEST_START and r["pct"] is not None]
    th_lo, th_hi = (round(quantile(train_pct, q), 2) for q in TERCILE)
    cur = state(asof)
    for r in monthly + [cur]:
        r["s1"] = score_band(r["pct"], th_lo, th_hi)
        r["s2"] = score_band(r["chg"], -TH_TP, TH_TP)

    done = [r for r in monthly if r["d5s30s"] is not None and r["month"] >= BT_START]
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
        out["also"] = {k: {key: [g["mean"] for g in summarize(rows, skey, k, expect)["by"]]
                           for key, _, rows in samples} for k in ("d10", "d30", "d2s10s")}
        return out

    bt_supply = backtest("s1", "d5s30s", expect=+1)     # +1(공급 부담 증가) → 5s30s 확대 기대
    bt_tp = backtest("s2", "d5s30s", expect=+1)         # +1(기간 프리미엄 상승) → 5s30s 확대 기대
    # 검증 구간의 +1이 어느 해에 나왔나 (한 사건에 몰려 있는지 확인용)
    plus = [r["month"][:4] for r in test if r["s1"] == 1]
    bt_supply["test_plus_years"] = sorted(({"year": y, "n": plus.count(y)} for y in set(plus)), key=lambda x: -x["n"])
    # 같은 달 안에서의 관계(동행): 기간 프리미엄이 10bp 오른 달에 5s30s·10년 금리는 몇 bp 움직였나
    same = [((TP.at(b) - TP.at(a)) * 100, (SL.at(b) - SL.at(a)) * 100, (Y["10Y"].at(b) - Y["10Y"].at(a)) * 100)
            for a, b in zip(ends, ends[1:]) if next_month(a[:7]) >= BT_START]
    bs, r2s, ts = ols([x[0] for x in same], [x[1] for x in same])
    b10_, r210, t10_ = ols([x[0] for x in same], [x[2] for x in same])
    bt_tp["same_month"] = {"n": len(same), "slope_5s30s": r1(bs * 10), "r2_5s30s": r1(r2s, 2), "t_5s30s": r1(ts, 1),
                           "slope_10y": r1(b10_ * 10), "r2_10y": r1(r210, 2), "t_10y": r1(t10_, 1)}

    # ----- Q1: 장기물 입찰일 반응 -----
    auctions = read_csv("auctions.csv")
    wi = {}
    wpath = HERE / "auction_wi.csv"
    if wpath.exists():
        for r in read_csv("auction_wi.csv"):
            if num(r.get("wi_yield")) is not None:
                wi[(r["auction_date"], r["cusip"])] = num(r["wi_yield"])
    use_tail = len(wi) >= MIN_WI
    unit = 1.0 if use_tail else 0.1        # 기울기를 읽는 단위: tail 1bp / 응찰률 0.1
    events, hist = [], {}
    for a in auctions:
        t, d, btc = a["tenor"], a["auction_date"], num(a["bid_to_cover"])
        prev = hist.setdefault(t, [])
        if t in LONG and d[:7] >= BT_START and len(prev) >= LOOKBACK:
            avg = mean([p[0] for p in prev[-LOOKBACK:]])
            avg_dl = mean([p[1] for p in prev[-LOOKBACK:]])
            w = wi.get((d, a["cusip"]))
            tail = None if w is None else round((num(a["high_yield"]) - w) * 100, 1)
            weak = tail if use_tail else round(avg - btc, 3)
            d10, d30, dsl = Y["10Y"].day_change(d), Y["30Y"].day_change(d), SL.day_change(d)
            if weak is not None and None not in (d10, d30, dsl):
                events.append({"date": d, "tenor": t, "reopen": a["reopening"] == "Yes", "hy": num(a["high_yield"]),
                               "btc": btc, "avg": round(avg, 3), "tail": tail, "weak": weak,
                               "dealer": num(a["dealer_pct"]), "dealer_dev": round(num(a["dealer_pct"]) - avg_dl, 2),
                               "d10": round(d10 * 100, 1), "d30": round(d30 * 100, 1), "dsl": round(dsl * 100, 1),
                               "era": "B" if d >= TEST_START else "A", "regime": regime_at(regimes, d)})
        prev.append((btc, num(a["dealer_pct"])))

    def reg(ev, xkey="weak", k=unit):
        out = {"n": len(ev)}
        for name, ykey in (("10", "d10"), ("30", "d30"), ("sl", "dsl")):
            b, r2, t = ols([e[xkey] for e in ev], [e[ykey] for e in ev])
            out[f"slope{name}"], out[f"r2_{name}"], out[f"t{name}"] = r1(b and b * k, 2), r1(r2, 2), r1(t, 1)
        out["sd"] = r1(stdev([e[xkey] for e in ev]), 3)
        return out

    auction_days = {a["auction_date"] for a in auctions if a["tenor"] in LONG}
    refund_days = {r["date"] for r in read_csv("refunding_dates.csv")}
    fomc_days = {r["date"] for r in csv.DictReader(open(FOMC_CSV, encoding="utf-8"))} if FOMC_CSV.exists() else set()
    moves = {"30Y": [(d, abs(Y["30Y"].day_change(d)) * 100) for d in Y["30Y"].dates[1:] if d[:7] >= BT_START],
             "SL": [(d, abs(SL.day_change(d)) * 100) for d in SL.dates[1:] if d[:7] >= BT_START]}

    def abs_stats(k, lo, hi, days, skip=frozenset()):
        on = [v for d, v in moves[k] if lo <= d < hi and d in days and d not in skip]
        off = [v for d, v in moves[k] if lo <= d < hi and d not in days and d not in skip]
        return r1(mean(on), 2), r1(mean(off), 2), len(on)

    eras = [("A", f"{BT_START[:4]}~{int(TEST_START[:4]) - 1}", BT_START, TEST_START),
            ("B", f"{TEST_START[:4]}~", TEST_START, "9999"), ("all", "전체", BT_START, "9999")]
    by_era, qra = [], []
    for key, label, lo, hi in eras:
        ev = [e for e in events if lo <= e["date"] < hi]
        on, off, _ = abs_stats("30Y", lo, hi, auction_days)
        by_era.append({"key": key, "label": label, **reg(ev), "abs_on": on, "abs_off": off,
                       "dealer": reg(ev, "dealer_dev", 1.0)})          # 딜러 배정 비중 1%p당 (교차 확인)
        q = {"key": key, "label": label}
        for name, skip in (("all", frozenset()), ("nofomc", fomc_days)):
            on30, off30, n = abs_stats("30Y", lo, hi, refund_days, skip)
            onsl, offsl, _ = abs_stats("SL", lo, hi, refund_days, skip)
            q[name] = {"n": n, "on30": on30, "off30": off30, "onsl": onsl, "offsl": offsl}
        qra.append(q)
    by_tenor = [{"key": t, "label": t.replace("Y", "년"), **reg([e for e in events if e["tenor"] == t])} for t in LONG]
    by_year = []
    for y in range(int(BT_START[:4]), int(asof[:4]) + 1):
        on, off, n = abs_stats("30Y", f"{y}-01-01", f"{y + 1}-01-01", auction_days)
        if n:
            by_year.append({"year": y, "n": n, "abs_on": on, "abs_off": off})

    # ----- 현재 판정에 붙일 것 -----
    cur["policy_upper"] = changes[-1][1]
    cur["last_auctions"] = [e for t in LONG for e in [next((x for x in reversed(events) if x["tenor"] == t), None)] if e]

    cols = ["date", "month", "ref", "sum3", "prev3", "accel", "priv", "pct", "s1", "tp10", "chg", "s2",
            "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    with open(HERE / "signals_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision_date", "apply_month", "mspd_ref_month", "long_net_3m_bn", "long_net_prev12m_per3m_bn",
                    "accel_bn", "private_bonds_bn", "supply_accel_pct", "score_supply", "tp10", "tp10_chg_3m_bp",
                    "score_tp", "regime", "next_d2y_bp", "next_d5y_bp", "next_d10y_bp", "next_d30y_bp",
                    "next_d2s10s_bp", "next_d5s30s_bp"])
        for r in monthly:
            w.writerow(["" if r[c_] is None else r[c_] for c_ in cols])

    # WI 금리 입력 틀: 없으면 만들고, 있으면 새 입찰만 덧붙인다(입력한 값은 보존)
    old = {(r["auction_date"], r["cusip"]): r.get("wi_yield", "") for r in read_csv("auction_wi.csv")} if wpath.exists() else {}
    with open(wpath, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["auction_date", "tenor", "cusip", "high_yield", "wi_yield"])
        for a in auctions:
            if a["tenor"] in LONG and a["auction_date"][:7] >= BT_START:
                w.writerow([a["auction_date"], a["tenor"], a["cusip"], a["high_yield"],
                            old.get((a["auction_date"], a["cusip"]), "")])

    # 차트용 일별 5s30s: data.js의 기간 프리미엄 날짜와 같은 순서로 맞춘다
    keys = ["date", "month", "ref", "sum3", "prev3", "pct", "s1", "tp10", "chg", "s2", "regime", "d10", "d30", "d2s10s", "d5s30s"]
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "asof": asof,
        "thresholds": {"supply_lo": th_lo, "supply_hi": th_hi, "tp": TH_TP},
        "tp_source": "ACM" if use_acm else "Kim-Wright",
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["month"]},
        "current": cur, "regimes": regimes,
        "monthly": {k: [r[k] for r in monthly] for k in keys},
        "slope_daily": [r1(SL.at(r["date"]), 3) for r in tp],
        "events": events, "event_source": "tail" if use_tail else "btc", "event_unit": unit,
        "event_stats": {"by_era": by_era, "by_tenor": by_tenor, "by_year": by_year, "qra": qra,
                        "fomc_known": bool(fomc_days)},
        "bt": {"supply": bt_supply, "tp": bt_tp},
    }
    (HERE / "signals.js").write_text(
        "window.SUPPLY_SIGNALS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda s: {1: "+1", 0: " 0", -1: "−1", None: " ?"}[s]
    print(f"\n[현재 판정] 기준일 {asof} · 국면 {REGIME_KO[cur['regime']]}")
    print(f"  공급 압력     {sc(cur['s1'])}  ({cur['ref']}까지 3개월 순공급 {cur['sum3']}bn − 직전 12개월의 3개월 평균 {cur['prev3']}bn"
          f" = {cur['accel']:+.1f}bn, 민간 보유 Bonds {cur['priv']}bn 대비 {cur['pct']:+.2f}% · 문턱값 {th_lo:+.2f} / {th_hi:+.2f}%)")
    print(f"  기간 프리미엄 {sc(cur['s2'])}  ({out['tp_source']} 10년 {cur['tp10']}%, 3개월 변화 {cur['chg']:+.0f}bp)")
    for title, bt in (("Q2 공급 압력 → 다음 달 5s30s", bt_supply), ("Q3 기간 프리미엄 → 다음 달 5s30s", bt_tp)):
        print(f"\n[{title}]  (평균 Δ5s30s bp / 적중률)")
        for s in bt["samples"] + bt["regimes"]:
            by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '+.1f'):>6s}"
                           f"{'' if g['hit'] is None else ' (' + str(g['hit']) + '%)':>7s}" for g in s["by"])
            print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | 신호 적중 {s['signal']['hits']}/{s['signal']['n']}"
                  f" 기준선 {s['base']}%  (+1)−(−1)={s['spread']} t={s['t']}")
        print(f"  다른 구간(전체, +1/0/−1 뒤 평균 bp): " + "  ".join(f"{k} {v['all']}" for k, v in bt["also"].items()))
    sm = bt_tp["same_month"]
    print(f"  같은 달: 기간 프리미엄 +10bp → 5s30s {sm['slope_5s30s']:+.1f}bp (t {sm['t_5s30s']}), 10년 {sm['slope_10y']:+.1f}bp (t {sm['t_10y']})")
    what = "tail 1bp" if use_tail else "응찰률 0.1 부족"
    print(f"\n[Q1 장기물 입찰일]  입찰 약세 = {'낙찰금리 − WI 금리(tail)' if use_tail else '직전 6회 평균 응찰률 − 응찰률(대용치)'}")
    for e in by_era + by_tenor:
        print(f"  {e['label']:10s} n={e['n']:<3d} {what}당 10y {e['slope10']}bp (t {e['t10']})  30y {e['slope30']}bp (t {e['t30']})"
              f"  5s30s {e['slopesl']}bp (t {e['tsl']})  1σ={e['sd']}"
              + (f"  | |Δ30y| 입찰일 {e['abs_on']} vs 평소 {e['abs_off']}bp" if "abs_on" in e else ""))
    for e in by_era:
        dl = e["dealer"]
        print(f"  {e['label']:10s} 딜러 비중 +1%p당 10y {dl['slope10']}bp (t {dl['t10']})  30y {dl['slope30']}bp (t {dl['t30']})  5s30s {dl['slopesl']}bp (t {dl['tsl']})")
    for q in qra:
        a, b = q["all"], q["nofomc"]
        print(f"  QRA {q['label']:8s} n={a['n']:<2d} |Δ30y| {a['on30']} vs {a['off30']}  |Δ5s30s| {a['onsl']} vs {a['offsl']}"
              f"  · FOMC 제외 n={b['n']:<2d} |Δ30y| {b['on30']} vs {b['off30']}  |Δ5s30s| {b['onsl']} vs {b['offsl']}")
    print(f"\n→ signals.js, signals_monthly.csv, auction_wi.csv 저장 (월 {len(monthly)}개, 입찰 {len(events)}건)")


if __name__ == "__main__":
    main()
