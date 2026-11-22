"""매크로 · 성장·고용 신호와 백테스트 계산 → signals.js + signals_monthly.csv

신호 (매월 마지막 거래일에 판정, 그날까지 발표된 고용보고서의 '발표 당시 값'만 사용)
  투표 1) NFP 모멘텀 = 3개월 평균 증감 − 12개월 평균 증감 (천 명)
            −50 이하 → +1(둔화) / +50 이상 → −1(가속) / 그 사이 0
  투표 2) 실업률 추세 = 실업률 3개월 평균의 3개월 변화 (%p)
            +0.2 이상 → +1(둔화) / −0.2 이하 → −1(개선) / 그 사이 0
  성장·고용 점수 = 두 투표 합의 부호 (+1 = 경기 둔화, 금리 하락 쪽)                → 수준 뷰(Duration)

백테스트 (성과월 2015-01 ~ 직전 완료월. 2015~2020은 규칙 설정, 2021~은 검증 구간)
  Q1) 고용보고서 발표일: NFP 서프라이즈 10만 명당 2년·5년·10년·30년 금리와 2s10s 변화 (반응형)
  Q2) 성장·고용 점수 → 다음 달 10년 금리 변화 (예측형)

Q1의 서프라이즈
  nfp_consensus.csv의 survey 열이 24개 이상 채워지면 '첫 발표치 − 컨센서스', 아니면 대용치
  '첫 발표치 − 직전 12회 첫 발표치 평균'.
  코로나 구간은 결과를 보기 전에 정한 규칙으로 뺀다(전체 포함 결과도 참고로 함께 낸다).
    · 컨센서스 사용 시: 기준월 2020-03 ~ 2020-06 (4월 −2,050만 명이 회귀를 혼자 좌우)
    · 대용치 사용 시:   기준월 2020-03 ~ 2021-06 (직전 12회 평균에 위 넉 달이 섞이는 동안은 대용치가 무의미)
  발표일에 금리 데이터가 없으면(휴장) 다음 거래일의 변화를 쓴다.

입력: realtime_releases.csv, claims_weekly.csv, ism_manufacturing.csv, nfp_consensus.csv, policy_rate.csv
      (fetch_data.py가 생성), 수익률곡선(CURVE_JS)
실행: python3 analyze.py
"""
import csv, json, math
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parents[1] / "curve" / "data.js"   # 일별 CMT 금리(공통 데이터). 옮기면 이 줄만 고친다.

TH_NFP = 50          # 천 명  ← 백테스트 전에 정한 값. 결과를 보고 바꾸지 않는다.
TH_UR = 0.2          # %p
BT_START = "2015-01"            # 첫 성과월
TEST_START = "2021-01"          # 검증 구간 첫 성과월
MIN_CONSENSUS = 24              # 컨센서스가 이만큼 채워져야 대용치 대신 사용
COVID_FROM = "2020-03"          # Q1 제외 구간 시작(기준월)
COVID_TO_CONS, COVID_TO_PROXY = "2020-06", "2021-06"
CLAIMS_LAG_DAYS = 5             # 주 마감(토) → 발표(목)
TENORS = [("d2", "2Y"), ("d5", "5Y"), ("d10", "10Y"), ("d30", "30Y")]
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

    def _pos(self, d):
        """d 이하 관측 개수."""
        lo, hi = 0, len(self.dates)
        while lo < hi:
            mid = (lo + hi) // 2
            if self.dates[mid] <= d:
                lo = mid + 1
            else:
                hi = mid
        return lo

    def at(self, d):
        i = self._pos(d)
        return self.values[i - 1] if i else None

    def react(self, d, max_gap=5):
        """d(또는 d가 휴장이면 다음 거래일) 종가 − 직전 거래일 종가 → (반응일, 변화). 없으면 (None, None)."""
        i = self._pos(d)
        if i and self.dates[i - 1] == d:
            i -= 1
        if i == 0 or i >= len(self.dates):
            return None, None
        if (datetime.strptime(self.dates[i], "%Y-%m-%d") - datetime.strptime(d, "%Y-%m-%d")).days > max_gap:
            return None, None
        return self.dates[i], self.values[i] - self.values[i - 1]


def next_month(ym):
    k = int(ym[:4]) * 12 + int(ym[5:7])
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def shift_days(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


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


def sd(xs):
    return math.sqrt(sum((x - mean(xs)) ** 2 for x in xs) / (len(xs) - 1)) if len(xs) > 1 else None


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
    se = math.sqrt(sse / (n - 2) / sxx) if n > 2 and sse else None
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


def combine(a, b):
    """두 투표 합의 부호. 하나라도 없으면 None."""
    if a is None or b is None:
        return None
    return (a + b > 0) - (a + b < 0)


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
    rel = read_csv("realtime_releases.csv")
    pay = [r for r in rel if r["series"] == "payems"]
    une = [r for r in rel if r["series"] == "unrate"]
    changes = [(r["date"], float(r["upper"])) for r in read_csv("policy_rate.csv")]
    regimes = build_regimes(changes, asof)
    claims = [(shift_days(r["week_ending"], CLAIMS_LAG_DAYS), num(r["ic4wsa_k"])) for r in read_csv("claims_weekly.csv")]
    C = Daily([c[0] for c in claims], [c[1] for c in claims])     # 날짜 = 발표(추정)일
    ism = {r["ref_month"]: num(r["pmi"]) for r in read_csv("ism_manufacturing.csv") if num(r.get("pmi")) is not None}

    def latest(rows, d):
        ok = [r for r in rows if r["release_date"] <= d]
        return ok[-1] if ok else None

    def state(d):
        """날짜 d 종가 시점에 알 수 있는 값으로 두 투표와 점수를 계산."""
        p, u = latest(pay, d), latest(une, d)
        gap = p and num(p["mom_gap"])
        uchg = u and num(u["lvl_3m_avg_chg3"])
        v1, v2 = score(gap, TH_NFP, sign=-1), score(uchg, TH_UR, sign=+1)
        return {"date": d, "release": p and p["release_date"], "ref": p and p["ref_month"],
                "nfp": p and num(p["chg_1m"]), "nfp3": p and num(p["chg_3m_avg"]), "nfp12": p and num(p["chg_12m_avg"]),
                "gap": gap, "v_nfp": v1,
                "ur": u and num(u["level"]), "ur3": u and num(u["lvl_3m_avg"]), "ur_chg": uchg, "v_ur": v2,
                "s": combine(v1, v2), "regime": regime_at(regimes, d)}

    # 월말 결정일: 수익률 데이터의 각 월 마지막 거래일 (진행 중인 달 제외)
    month_end = {}
    for d in dates:
        month_end[d[:7]] = d
    ends = [month_end[m] for m in sorted(month_end) if "2014-12" <= m < asof[:7]]

    lv = lambda k, dd: Y[k].at(dd)
    targets = [("d2", lambda dd: lv("2Y", dd)), ("d5", lambda dd: lv("5Y", dd)),
               ("d10", lambda dd: lv("10Y", dd)), ("d30", lambda dd: lv("30Y", dd)),
               ("d2s10s", lambda dd: lv("10Y", dd) - lv("2Y", dd)),
               ("d5s30s", lambda dd: lv("30Y", dd) - lv("5Y", dd))]
    monthly = []
    for i, d in enumerate(ends):
        row = state(d)
        row["month"] = next_month(d[:7])           # 이 판정이 적용되는 성과월
        nxt = ends[i + 1] if i + 1 < len(ends) else None
        for key, fn in targets:
            row[key] = None if nxt is None else round((fn(nxt) - fn(d)) * 100, 1)
        monthly.append(row)

    done = [r for r in monthly if r["d10"] is not None and r["month"] >= BT_START]
    train = [r for r in done if r["month"] < TEST_START]
    test = [r for r in done if r["month"] >= TEST_START]
    samples = [("all", "전체", done), ("train", "설정 구간", train), ("test", "검증 구간", test)]

    def backtest(skey, tkey, expect, with_regimes=True):
        out = {"samples": [], "regimes": []}
        for key, label, rows in samples:
            s = summarize(rows, skey, tkey, expect)
            s.update(key=key, label=label, start=rows[0]["month"], end=rows[-1]["month"])
            out["samples"].append(s)
        for rg in ("hike", "hold", "cut") if with_regimes else ():
            s = summarize([r for r in done if r["regime"] == rg], skey, tkey, expect)
            s.update(key=rg, label=REGIME_KO[rg])
            out["regimes"].append(s)
        return out

    bt_growth = backtest("s", "d10", expect=-1)         # +1(둔화) → 10년 금리 하락 기대
    bt_growth["also"] = {k: {s["key"]: [g["mean"] for g in summarize(rows, "s", k, -1)["by"]]
                             for s, (_, _, rows) in zip(bt_growth["samples"], samples)} for k in ("d2", "d5", "d2s10s")}
    # 참고: 투표를 따로 봤을 때 (고르기 위한 것이 아니라 점수가 어디서 나오는지 보기 위한 것)
    bt_votes = {"nfp": backtest("v_nfp", "d10", -1, with_regimes=False),
                "ur": backtest("v_ur", "d10", -1, with_regimes=False)}

    # ----- Q1: 고용보고서 발표일 반응 -----
    cons_rows = read_csv("nfp_consensus.csv") if (HERE / "nfp_consensus.csv").exists() else []
    consensus = {r["release_date"]: num(r["survey"]) for r in cons_rows if num(r.get("survey")) is not None}
    use_cons = len(consensus) >= MIN_CONSENSUS
    covid_to = COVID_TO_CONS if use_cons else COVID_TO_PROXY
    ur_first = {r["release_date"]: num(r["chg_1m"]) for r in une if r["is_new"] == "1"}
    firsts = [r for r in pay if r["is_new"] == "1"]
    events, hist = [], []
    for r in firsts:
        act, d = num(r["chg_1m"]), r["release_date"]
        if act is not None and d[:7] >= BT_START:
            exp = consensus.get(d) if use_cons else (mean(hist[-12:]) if len(hist) >= 12 else None)
            rd, d2 = Y["2Y"].react(d)
            if exp is not None and rd is not None:
                e = {"date": d, "react": rd, "ref": r["ref_month"], "nfp": act, "exp": round(exp, 1),
                     "sur": round(act - exp, 1), "ur_chg": ur_first.get(d), "rev": num(r["rev_prev"]),
                     "era": "B" if d >= TEST_START else "A", "regime": regime_at(regimes, d),
                     "ex": int(COVID_FROM <= r["ref_month"] <= covid_to)}
                for key, k in TENORS:
                    e[key] = round(Y[k].react(d)[1] * 100, 1)
                e["d2s10s"] = round(e["d10"] - e["d2"], 1)
                events.append(e)
        if act is not None:
            hist.append(act)

    nfp_days = {Y["2Y"].react(r["release_date"])[0] for r in firsts}
    moves = {k: [(Y[k].dates[i], abs(Y[k].values[i] - Y[k].values[i - 1]) * 100)
                 for i in range(1, len(Y[k].dates)) if Y[k].dates[i][:7] >= BT_START] for k in ("2Y", "10Y")}

    def abs_stats(k, lo, hi):
        on = [v for d, v in moves[k] if lo <= d < hi and d in nfp_days]
        off = [v for d, v in moves[k] if lo <= d < hi and d not in nfp_days]
        return r1(mean(on), 2), r1(mean(off), 2), len(on)

    def reaction(ev):
        """서프라이즈 10만 명(=100천 명)당 bp."""
        out = {"n": len(ev), "sd_sur": r1(sd([e["sur"] for e in ev]), 0)}
        for key in ("d2", "d5", "d10", "d30", "d2s10s"):
            b, r2, t = ols([e["sur"] for e in ev], [e[key] for e in ev])
            out[key] = {"slope": r1(b and b * 100, 2), "r2": r1(r2, 2), "t": r1(t, 1)}
        u = [e for e in ev if e["ur_chg"] is not None]
        b, r2, t = ols([e["ur_chg"] for e in u], [e["d2"] for e in u])      # 실업률 0.1%p 상승당 2년 금리
        out["ur_d2"] = {"slope": r1(b and b / 10, 2), "r2": r1(r2, 2), "t": r1(t, 1), "n": len(u)}
        return out

    eras = [("A", f"{BT_START[:4]}~{int(TEST_START[:4]) - 1}", BT_START, TEST_START),
            ("B", f"{TEST_START[:4]}~", TEST_START, "9999"), ("all", "전체", BT_START, "9999")]
    by_era = []
    for key, label, lo, hi in eras:
        s = reaction([e for e in events if lo <= e["date"] < hi and not e["ex"]])
        on2, off2, _ = abs_stats("2Y", lo, hi)
        on10, off10, _ = abs_stats("10Y", lo, hi)
        s.update(key=key, label=label, abs_nfp2=on2, abs_other2=off2, abs_nfp10=on10, abs_other10=off10)
        by_era.append(s)
    incl = reaction(events)                                   # 참고: 코로나 구간 포함
    by_regime = []
    for rg in ("hike", "hold", "cut"):
        s = reaction([e for e in events if e["regime"] == rg and not e["ex"]])
        s.update(key=rg, label=REGIME_KO[rg])
        by_regime.append(s)
    by_year = []
    for y in range(int(BT_START[:4]), int(asof[:4]) + 1):
        on2, off2, n = abs_stats("2Y", f"{y}-01-01", f"{y + 1}-01-01")
        if n:
            by_year.append({"year": y, "n": n, "abs_nfp2": on2, "abs_other2": off2})

    # ----- 현재 판정 -----
    cur = state(asof)
    cur["claims_4w"] = C.at(asof)
    cur["claims_4w_13w_ago"] = C.at(shift_days(asof, -91))
    ism_ok = sorted(m for m in ism if m < asof[:7])           # 기준월 다음 달 첫 영업일 발표
    cur["ism"] = {"ref": ism_ok[-1], "pmi": ism[ism_ok[-1]]} if ism_ok else None
    cur["policy_upper"] = changes[-1][1]

    cols = ["date", "month", "release", "ref", "nfp", "nfp3", "nfp12", "gap", "v_nfp", "ur", "ur3", "ur_chg", "v_ur", "s",
            "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    with open(HERE / "signals_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision_date", "apply_month", "jobs_release", "jobs_ref_month", "nfp_chg_k", "nfp_3m_avg_k",
                    "nfp_12m_avg_k", "nfp_gap_k", "vote_nfp", "unrate", "unrate_3m_avg", "unrate_3m_avg_chg3", "vote_unrate",
                    "score_growth", "regime", "next_d2y_bp", "next_d5y_bp", "next_d10y_bp", "next_d30y_bp",
                    "next_d2s10s_bp", "next_d5s30s_bp"])
        for r in monthly:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    keys = ["date", "month", "ref", "nfp", "nfp3", "nfp12", "gap", "v_nfp", "ur", "ur3", "ur_chg", "v_ur", "s", "regime",
            "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    n_ex = sum(e["ex"] for e in events)
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "asof": asof,
        "thresholds": {"nfp_gap": TH_NFP, "ur_chg": TH_UR},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["month"]},
        "current": cur, "regimes": regimes,
        "monthly": {k: [r[k] for r in monthly] for k in keys},
        "events": events, "event_source": "consensus" if use_cons else "proxy",
        "event_excluded": {"from": COVID_FROM, "to": covid_to, "n": n_ex},
        "event_stats": {"by_era": by_era, "by_regime": by_regime, "by_year": by_year, "incl_covid": incl},
        "bt": {"growth": bt_growth, "votes": bt_votes},
    }
    (HERE / "signals.js").write_text(
        "window.GROWTH_SIGNALS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda s: {1: "+1", 0: " 0", -1: "−1", None: " ?"}[s]
    print(f"\n[현재 판정] 기준일 {asof} · 국면 {REGIME_KO[cur['regime']]}")
    print(f"  성장·고용 점수 {sc(cur['s'])}   (고용보고서 {cur['ref']}, {cur['release']} 발표)")
    print(f"    NFP 투표    {sc(cur['v_nfp'])}  3개월 평균 {cur['nfp3']:+.0f}천 − 12개월 평균 {cur['nfp12']:+.0f}천 = {cur['gap']:+.0f}천")
    print(f"    실업률 투표 {sc(cur['v_ur'])}  실업률 {cur['ur']}%, 3개월 평균의 3개월 변화 {cur['ur_chg']:+.2f}%p")
    print(f"    참고: 청구건수 4주 평균 {cur['claims_4w']}천 (13주 전 {cur['claims_4w_13w_ago']}천)"
          + (f", ISM {cur['ism']['pmi']} ({cur['ism']['ref']})" if cur["ism"] else ", ISM 미입력"))

    def show(title, bt):
        print(f"\n[{title}]  (평균 Δ10y bp / 적중률)")
        for s in bt["samples"] + bt["regimes"]:
            by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '+.1f'):>6s}"
                           f"{'' if g['hit'] is None else ' (' + str(g['hit']) + '%)':>7s}" for g in s["by"])
            print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | 신호 적중 {s['signal']['hits']}/{s['signal']['n']}"
                  f" 기준선 {s['base']}%  (+1)−(−1)={s['spread']} t={s['t']}")

    show("Q2 성장·고용 점수 → 다음 달 10년 금리", bt_growth)
    show("참고: NFP 투표만", bt_votes["nfp"])
    show("참고: 실업률 투표만", bt_votes["ur"])
    print(f"\n[Q1 고용보고서 발표일]  서프라이즈 = {'첫 발표치 − 컨센서스' if use_cons else '첫 발표치 − 직전 12회 평균(대용치)'}"
          f"  · 제외 {COVID_FROM}~{covid_to} ({n_ex}회)")
    fmt = lambda s, k: f"{s[k]['slope']:+.2f}bp (t {s[k]['t']})"
    for e in by_era + by_regime + [dict(incl, label="코로나 포함")]:
        print(f"  {e['label']:10s} n={e['n']:<3d} σ={e['sd_sur']}천 | 10만 명당 2y {fmt(e, 'd2')}  5y {fmt(e, 'd5')}  10y {fmt(e, 'd10')}"
              f"  30y {fmt(e, 'd30')}  2s10s {fmt(e, 'd2s10s')} | 2y R² {e['d2']['r2']}"
              + (f" | |Δ2y| 발표일 {e['abs_nfp2']} vs 평소 {e['abs_other2']}bp" if "abs_nfp2" in e else ""))
    print("  실업률 0.1%p 상승당 2y: " + "  ".join(f"{e['label']} {e['ur_d2']['slope']}bp (t {e['ur_d2']['t']})" for e in by_era))
    print("  연도별 |Δ2y| 발표일/평소: " + "  ".join(f"{y['year']} {y['abs_nfp2']}/{y['abs_other2']}" for y in by_year))
    print(f"\n→ signals.js, signals_monthly.csv 저장 (월 {len(monthly)}개, 발표일 {len(events)}개)")


if __name__ == "__main__":
    main()
