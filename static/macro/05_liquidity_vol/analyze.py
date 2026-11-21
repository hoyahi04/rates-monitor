"""매크로 · 유동성·변동성 신호와 백테스트 계산 → signals.js + signals_monthly.csv

신호 (매월 마지막 거래일 종가에 판정, 그날까지 공개된 값만 사용. 판정은 다음 달에 적용)
  세 축을 같은 자로 잰다: "직전 3년 분포에서 몇 번째 백분위인가"
    V 금리 변동성 = 그 달 MOVE 최고값의 3년 백분위
    R 리스크 심리 = (그 달 VIX 최고값의 3년 백분위 + Baa−10년 스프레드의 3년 백분위) ÷ 2
    L 유동성      = SOFR − 준비금 금리의 20영업일 평균이 +5bp 초과면 자금 경보
  통합 점수
    −1 스트레스 : V > 90                          → 벨리 불릿 청산, 모든 액티브 포지션 절반
    +1 안정     : V < 50 그리고 R < 50 그리고 자금 경보 꺼짐 → Fly z-score ≥ +1이면 벨리 불릿 허용
     0 중립     : 그 외                            → 기존 포지션 유지, 신규 불릿 없음

백테스트 (성과월 2015-01 ~ 직전 완료월. 2015~2020은 규칙 설정, 2021~은 검증 구간)
  Q1) 점수 → 다음 달 10년 금리의 실현변동성 (크기 예측)
  Q2) 점수 → 다음 달 2s5s10s Fly 방향 (방향 예측)
  Q3) 세 축 가운데 무엇이 다음 달 변동 크기를 설명하나
  Q4) 스트레스가 시작된 달에 커브는 어떻게 움직였나 (반응형)

입력: liquidity_daily.csv, liquidity_weekly.csv, policy_rate.csv (fetch_data.py가 생성), 수익률곡선(CURVE_JS)
실행: python3 analyze.py
"""
import bisect, csv, json, math
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parents[1] / "curve" / "data.js"   # 일별 CMT 금리(공통 데이터). 옮기면 이 줄만 고친다.

TH_STRESS = 90       # 백분위  ← 결과를 보기 전에 정한 값. 바꾸지 않는다.
TH_CALM = 50         # 백분위
TH_FUND = 5          # bp
LOOKBACK_M = 36      # 비교 대상 분포: 직전 36개월
FUND_DAYS = 20       # 자금 스프레드 평균 기간(영업일)
BT_START = "2015-01"            # 첫 성과월
TEST_START = "2021-01"          # 검증 구간 첫 성과월
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


class Series:
    """날짜 오름차순 시계열(빈 값 제외)."""

    def __init__(self, dates, values):
        pairs = [(d, v) for d, v in zip(dates, values) if v is not None]
        self.d = [p[0] for p in pairs]
        self.v = [p[1] for p in pairs]

    def at(self, d):
        """d 이하 마지막 관측값"""
        i = bisect.bisect_right(self.d, d)
        return self.v[i - 1] if i else None

    def window(self, lo, hi):
        """lo < 날짜 ≤ hi 의 (날짜, 값) 목록"""
        a, b = bisect.bisect_right(self.d, lo), bisect.bisect_right(self.d, hi)
        return list(zip(self.d[a:b], self.v[a:b]))

    def before(self, d, n=1):
        """d 보다 앞선 마지막 n개 (날짜, 값). 다음 날 아침에 공개되는 지표용."""
        i = bisect.bisect_left(self.d, d)
        return list(zip(self.d[max(0, i - n):i], self.v[max(0, i - n):i]))


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    last = [31, 29 if (y2 % 4 == 0 and (y2 % 100 or y2 % 400 == 0)) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m2 - 1]
    return f"{y2:04d}-{m2:02d}-{min(day, last):02d}"


def days_ago(d, n):
    return (datetime.strptime(d, "%Y-%m-%d") - timedelta(days=n)).strftime("%Y-%m-%d")


def next_month(ym):
    k = int(ym[:4]) * 12 + int(ym[5:7])
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


# ---------- 국면 (03_inflation과 같은 규칙) ----------
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


def median(xs):
    s = sorted(xs)
    n = len(s)
    return None if not n else (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2)


def r1(x, n=1):
    return None if x is None else round(x, n)


def pct(x, hist):
    """hist 가운데 x 이하인 값의 비율(%)"""
    return None if x is None or not hist else sum(1 for h in hist if h <= x) / len(hist) * 100


def quantile(xs, q):
    s = sorted(xs)
    if not s:
        return None
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def welch_t(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    va = sum((x - mean(a)) ** 2 for x in a) / (len(a) - 1)
    vb = sum((x - mean(b)) ** 2 for x in b) / (len(b) - 1)
    se = math.sqrt(va / len(a) + vb / len(b))
    return (mean(a) - mean(b)) / se if se else None


def corr(xs, ys):
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None]
    n = len(pairs)
    if n < 3:
        return None, n
    mx, my = mean([p[0] for p in pairs]), mean([p[1] for p in pairs])
    sxx = sum((p[0] - mx) ** 2 for p in pairs)
    syy = sum((p[1] - my) ** 2 for p in pairs)
    if not sxx or not syy:
        return None, n
    return sum((p[0] - mx) * (p[1] - my) for p in pairs) / math.sqrt(sxx * syy), n


def summarize_dir(rows, skey, tkey, expect):
    """점수별 다음 달 결과(방향). expect: 점수 +1일 때 기대하는 변화의 부호. (03_inflation과 같은 틀)"""
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
    out["base"] = round(base / len(rows) * 100) if rows else None
    out["spread"] = None if not grp[1] or not grp[-1] else r1(mean(grp[1]) - mean(grp[-1]))
    out["t"] = r1(welch_t(grp[1], grp[-1]), 2)
    return out


def summarize_mag(rows):
    """점수별 다음 달 10년 금리 실현변동성(크기)."""
    rows = [r for r in rows if r["score"] is not None and r["rv"] is not None]
    grp = {s: [r["rv"] for r in rows if r["score"] == s] for s in (-1, 0, 1)}
    grp_abs = {s: [r["absd"] for r in rows if r["score"] == s] for s in (-1, 0, 1)}
    out = {"n": len(rows), "by": [{"score": s, "n": len(grp[s]), "mean": r1(mean(grp[s])), "median": r1(median(grp[s])),
                                   "absd": r1(mean(grp_abs[s]), 2)} for s in (-1, 0, 1)]}
    m = {s: mean(grp[s]) for s in grp}
    out["ratio"] = None if not m[-1] or not m[1] else r1(m[-1] / m[1], 2)
    out["diff"] = None if m[-1] is None or m[1] is None else r1(m[-1] - m[1])
    out["t"] = r1(welch_t(grp[-1], grp[1]), 2)
    out["ordered"] = None if None in m.values() else bool(m[-1] > m[0] > m[1])
    c, _ = corr([r["V"] for r in rows], [r["rv"] for r in rows])
    c2, _ = corr([r["move_end"] for r in rows], [r["rv"] for r in rows])
    out["corr_v"], out["corr_level"] = r1(c, 2), r1(c2, 2)
    return out


def axes_table(rows):
    """세 축과 비교 지표가 다음 달 실현변동성을 얼마나 설명하나(상관계수)."""
    rows = [r for r in rows if r["rv"] is not None]
    rv = [r["rv"] for r in rows]
    items = [("V", "금리 변동성 (MOVE 백분위)", [r["V"] for r in rows]),
             ("R", "리스크 심리 (VIX·신용 백분위)", [r["R"] for r in rows]),
             ("VR", "두 축 평균", [None if r["R"] is None else (r["V"] + r["R"]) / 2 for r in rows]),
             ("L", "유동성 (SOFR − 준비금 금리 20일 평균)", [r["fund"] for r in rows]),
             ("NFCI", "시카고 연은 금융여건지수", [r["nfci"] for r in rows]),
             ("STLFSI", "세인트루이스 연은 금융스트레스지수", [r["stlfsi"] for r in rows])]
    out = {"rows": []}
    for key, label, xs in items:
        c, n = corr(xs, rv)
        out["rows"].append({"key": key, "label": label, "corr": r1(c, 2), "n": n})
    ok = [r for r in rows if r["R"] is not None]
    yv, _ = corr([r["V"] for r in ok], [r["rv"] for r in ok])
    yr, _ = corr([r["R"] for r in ok], [r["rv"] for r in ok])
    vr, _ = corr([r["V"] for r in ok], [r["R"] for r in ok])
    if None not in (yv, yr, vr) and abs(vr) < 1:
        out["r2_v"] = r1(yv ** 2 * 100)
        out["r2_vr"] = r1((yv ** 2 + yr ** 2 - 2 * yv * yr * vr) / (1 - vr ** 2) * 100)   # V와 R을 함께 넣은 회귀의 R²
        out["corr_vr"] = r1(vr, 2)
    r_only = [r["rv"] for r in ok if r["R"] > TH_STRESS and r["V"] <= TH_STRESS]
    neither = [r["rv"] for r in ok if r["R"] <= TH_STRESS and r["V"] <= TH_STRESS]
    v_st = [r["rv"] for r in ok if r["V"] > TH_STRESS]
    out["r_only"] = {"n": len(r_only), "mean": r1(mean(r_only))}
    out["neither"] = {"n": len(neither), "mean": r1(mean(neither))}
    out["v_stress"] = {"n": len(v_st), "mean": r1(mean(v_st))}
    al = [r["rv"] for r in rows if r["alarm"]]
    no = [r["rv"] for r in rows if r["alarm"] is False]
    out["alarm"] = {"n": len(al), "mean": r1(mean(al)), "n_off": len(no), "mean_off": r1(mean(no))}
    return out


def curve_type(d10, dsl):
    if d10 is None or dsl is None or d10 == 0 or dsl == 0:
        return "혼조"
    return ("불 " if d10 < 0 else "베어 ") + ("스티프닝" if dsl > 0 else "플래트닝")


# ---------- 본 계산 ----------
def main():
    dates, yields = load_curve()
    Y = {k: Series(dates, yields[k]) for k in ("2Y", "5Y", "10Y", "30Y")}
    asof = dates[-1]
    day = read_csv("liquidity_daily.csv")
    dd = [r["date"] for r in day]
    S = {k: Series(dd, [num(r[k]) for r in day]) for k in
         ("move", "vix", "baa_spread", "sofr_minus_rr_bp", "effr_minus_rr_bp", "rrp_bn", "sofr", "reserve_rate", "hy_oas")}
    wk = read_csv("liquidity_weekly.csv")
    wd = [r["date"] for r in wk]
    W = {k: Series(wd, [num(r[k]) for r in wk]) for k in ("reserves_bn", "tga_bn", "nfci", "stlfsi")}
    changes = [(r["date"], float(r["upper"])) for r in read_csv("policy_rate.csv")]
    regimes = build_regimes(changes, asof)
    move_src = {r["date"]: r["move_src"] for r in day if r["move_src"]}

    def lv(k, d):
        return Y[k].at(d)

    def fly(d):
        return (2 * lv("5Y", d) - lv("2Y", d) - lv("10Y", d)) * 100

    def slope(d):
        return (lv("10Y", d) - lv("2Y", d)) * 100

    def state(d, prev):
        """prev(직전 월말) 다음 날부터 d까지를 '그 달'로 보고, d 종가 시점에 알 수 있는 값으로 판정."""
        lo = months_ago(d, LOOKBACK_M)
        mw, vw = S["move"].window(prev, d), S["vix"].window(prev, d)
        if not mw:
            return None
        peak_d, peak = max(mw, key=lambda p: p[1])
        hist = [v for _, v in S["move"].window(lo, d)]
        V = pct(peak, hist)
        vpk = max(v for _, v in vw) if vw else None
        Rv = pct(vpk, [v for _, v in S["vix"].window(lo, d)])
        b = S["baa_spread"].before(d)                       # 신용 스프레드는 다음 날 공개 → 전일 값까지
        baa = b[-1][1] if b else None
        Rc = pct(baa, [v for _, v in S["baa_spread"].window(lo, b[-1][0])]) if b else None
        R = None if Rv is None or Rc is None else (Rv + Rc) / 2
        f = S["sofr_minus_rr_bp"].before(d, FUND_DAYS)      # SOFR도 다음 날 아침 공개 → 전일 값까지
        fund = mean([v for _, v in f]) if len(f) == FUND_DAYS and f[0][0] >= days_ago(d, 45) else None
        e = S["effr_minus_rr_bp"].before(d, FUND_DAYS)
        alarm = None if fund is None else fund > TH_FUND
        if V > TH_STRESS:
            score = -1
        elif V < TH_CALM and R is not None and R < TH_CALM and not alarm:
            score = 1
        else:
            score = 0
        lag = days_ago(d, 7)                                # 주간 지수는 발표 시차를 두고 사용
        return {"date": d, "move_end": mw[-1][1], "move_peak": peak, "move_peak_date": peak_d,
                "p90": r1(quantile(hist, .9)), "p50": r1(quantile(hist, .5)), "V": r1(V),
                "vix_peak": vpk, "Rv": r1(Rv), "baa": baa, "Rc": r1(Rc), "R": r1(R),
                "fund": r1(fund), "effr20": r1(mean([v for _, v in e])) if e else None, "alarm": alarm, "score": score,
                "reserves": W["reserves_bn"].at(lag), "rrp": S["rrp_bn"].at(d), "nfci": W["nfci"].at(lag),
                "stlfsi": W["stlfsi"].at(lag), "regime": regime_at(regimes, d),
                "src": move_src.get(peak_d, "")}

    # 월말 결정일: 수익률 데이터의 각 월 마지막 거래일 (진행 중인 달 제외)
    month_end = {}
    for d in dates:
        month_end[d[:7]] = d
    ends = [month_end[m] for m in sorted(month_end) if "2014-11" <= m < asof[:7]]

    monthly = []
    for i in range(1, len(ends)):
        d, prev = ends[i], ends[i - 1]
        row = state(d, prev)
        row["month"] = next_month(d[:7])           # 이 판정이 적용되는 성과월
        row["c2"] = r1((lv("2Y", d) - lv("2Y", prev)) * 100)          # 같은 달(판정에 쓰인 달)의 커브 변화
        row["c10"] = r1((lv("10Y", d) - lv("10Y", prev)) * 100)
        row["c2s10s"] = r1(slope(d) - slope(prev))
        row["cfly"] = r1(fly(d) - fly(prev))
        nxt = ends[i + 1] if i + 1 < len(ends) else None
        if nxt:
            path = [v for _, v in Y["10Y"].window(days_ago(d, 1), nxt)]
            chg = [(b - a) * 100 for a, b in zip(path, path[1:])]
            row["rv"] = r1(math.sqrt(sum(x * x for x in chg) / len(chg)) * math.sqrt(252))
            row["absd"] = r1(mean([abs(x) for x in chg]), 2)
            row["d2"] = r1((lv("2Y", nxt) - lv("2Y", d)) * 100)
            row["d10"] = r1((lv("10Y", nxt) - lv("10Y", d)) * 100)
            row["d2s10s"] = r1(slope(nxt) - slope(d))
            row["dfly"] = r1(fly(nxt) - fly(d))
        else:
            row.update(rv=None, absd=None, d2=None, d10=None, d2s10s=None, dfly=None)
        monthly.append(row)

    done = [r for r in monthly if r["rv"] is not None and r["month"] >= BT_START]
    train = [r for r in done if r["month"] < TEST_START]
    test = [r for r in done if r["month"] >= TEST_START]
    samples = [("all", "전체", done), ("train", "설정 구간", train), ("test", "검증 구간", test)]

    def by_sample(fn):
        out = {"samples": [], "regimes": []}
        for key, label, rows in samples:
            s = fn(rows)
            s.update(key=key, label=label, start=rows[0]["month"], end=rows[-1]["month"])
            out["samples"].append(s)
        for rg in ("hike", "hold", "cut"):
            s = fn([r for r in done if r["regime"] == rg])
            s.update(key=rg, label=REGIME_KO[rg])
            out["regimes"].append(s)
        return out

    bt_mag = by_sample(summarize_mag)
    bt_dir = by_sample(lambda rows: summarize_dir(rows, "score", "dfly", expect=-1))   # +1(안정) → Fly 하락(벨리 강세) 기대
    bt_axes = {key: axes_table(rows) for key, _, rows in samples}

    # 점수 빈도
    freq = {key: {str(s): sum(1 for r in rows if r["score"] == s) for s in (-1, 0, 1)} for key, _, rows in samples}

    # ----- Q4: 스트레스가 시작된 달 -----
    episodes = []
    in_bt = [r for r in monthly if r["month"] >= BT_START]
    for i, r in enumerate(monthly):
        if r["month"] < BT_START or r["score"] != -1:
            continue
        if i and monthly[i - 1]["score"] == -1:
            continue
        run = 1
        while i + run < len(monthly) and monthly[i + run]["score"] == -1:
            run += 1
        span = monthly[i:i + run]
        episodes.append({"month": r["date"][:7], "date": r["date"], "months": run, "move_peak": r1(r["move_peak"]),
                         "epi_peak": r1(max(x["move_peak"] for x in span)),
                         "epi_peak_date": max(span, key=lambda x: x["move_peak"])["move_peak_date"],
                         "peak_date": r["move_peak_date"], "vix_peak": r1(r["vix_peak"]), "V": r["V"], "R": r["R"],
                         "c2": r["c2"], "c10": r["c10"], "c2s10s": r["c2s10s"], "cfly": r["cfly"],
                         "type": curve_type(r["c10"], r["c2s10s"]), "rv": r["rv"], "d10": r["d10"],
                         "era": "B" if r["month"] >= TEST_START else "A", "src": r["src"]})
    types = ["불 플래트닝", "불 스티프닝", "베어 플래트닝", "베어 스티프닝", "혼조"]
    stress_rows = [r for r in in_bt if r["score"] == -1]
    type_count = {"onset": {t: sum(1 for e in episodes if e["type"] == t) for t in types},
                  "all": {t: sum(1 for r in stress_rows if curve_type(r["c10"], r["c2s10s"]) == t) for t in types},
                  "n_onset": len(episodes), "n_all": len(stress_rows)}
    c_same, n_same = corr([r["V"] for r in in_bt], [r["c10"] for r in in_bt])
    same = {"corr_v_c10": r1(c_same, 2), "n": n_same,
            "stress_c10": r1(mean([r["c10"] for r in stress_rows])), "stress_c2s10s": r1(mean([r["c2s10s"] for r in stress_rows])),
            "stress_cfly": r1(mean([r["cfly"] for r in stress_rows])),
            "stress_down": sum(1 for r in stress_rows if r["c10"] < 0)}

    # ----- 현재 -----
    official = monthly[-1]                      # 직전 월말 판정 = 이번 달에 적용 중인 점수
    mtd = state(asof, ends[-1])                 # 이번 달 들어 기준일까지(참고)
    mtd["month"] = next_month(asof[:7])
    cur = {"official": official, "mtd": mtd, "policy_upper": changes[-1][1],
           "move_last": S["move"].at(asof), "vix_last": S["vix"].at(asof), "baa_last": S["baa_spread"].at(asof),
           "hy_last": S["hy_oas"].at(asof), "sofr_last": S["sofr"].at(asof), "rr_last": S["reserve_rate"].at(asof)}

    cols = ["date", "month", "move_end", "move_peak", "move_peak_date", "p50", "p90", "V", "vix_peak", "Rv", "baa", "Rc", "R",
            "fund", "alarm", "score", "regime", "rv", "d2", "d10", "d2s10s", "dfly"]
    with open(HERE / "signals_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision_date", "apply_month", "move_month_end", "move_month_peak", "move_peak_date", "move_3y_median",
                    "move_3y_p90", "vol_pct", "vix_month_peak", "vix_pct", "baa_spread", "baa_pct", "risk_pct",
                    "funding_20d_bp", "funding_alarm", "score_liquidity_vol", "regime", "next_rv10y_bp_ann",
                    "next_d2y_bp", "next_d10y_bp", "next_d2s10s_bp", "next_dfly_bp"])
        for r in monthly:
            w.writerow(["" if r[c] is None else (int(r[c]) if isinstance(r[c], bool) else r[c]) for c in cols])

    keys = ["date", "month", "move_end", "move_peak", "p50", "p90", "V", "vix_peak", "Rv", "baa", "Rc", "R", "fund", "alarm",
            "score", "regime", "rv", "d10", "d2s10s", "dfly", "c10", "c2s10s", "cfly"]
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "asof": asof,
        "thresholds": {"stress": TH_STRESS, "calm": TH_CALM, "fund": TH_FUND, "lookback_m": LOOKBACK_M, "fund_days": FUND_DAYS},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["month"]},
        "current": cur, "regimes": regimes,
        "monthly": {k: [r[k] for r in monthly] for k in keys},
        "freq": freq, "episodes": episodes, "type_count": type_count, "same_month": same,
        "bt": {"mag": bt_mag, "dir": bt_dir, "axes": bt_axes},
    }
    (HERE / "signals.js").write_text(
        "window.LIQUIDITY_SIGNALS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda s: {1: "+1", 0: " 0", -1: "−1", None: " ?"}[s]
    al = lambda a: "자료 없음" if a is None else ("켜짐" if a else "꺼짐")
    o = official
    print(f"\n[적용 중인 판정] {o['date']} 판정 → {o['month']} 적용 · 점수 {sc(o['score'])}")
    print(f"  V 금리 변동성 {o['V']:.0f} (MOVE 월중 최고 {o['move_peak']:.1f}, 3년 상위 10% 경계 {o['p90']}, 중앙값 {o['p50']})")
    print(f"  R 리스크 심리 {o['R']:.0f} (VIX 최고 {o['vix_peak']:.1f} → {o['Rv']:.0f}, Baa 스프레드 {o['baa']:.2f}% → {o['Rc']:.0f})")
    print(f"  L 자금 경보 {al(o['alarm'])} (SOFR − 준비금 금리 20일 평균 {o['fund']}bp)")
    print(f"[이번 달 진행 중] 기준일 {asof} · 점수 {sc(mtd['score'])}  V {mtd['V']:.0f}  R {mtd['R']:.0f}  자금 {mtd['fund']}bp")
    print("\n[점수 빈도] " + "  ".join(f"{lab} " + "/".join(f"{sc(s)}:{freq[k][str(s)]}" for s in (-1, 0, 1)) for k, lab, _ in samples))
    print("\n[Q1 점수 → 다음 달 10년 금리 실현변동성 (연 bp)]")
    for s in bt_mag["samples"] + bt_mag["regimes"]:
        by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '.1f'):>6s}" for g in s["by"])
        print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | (−1)÷(+1)={s['ratio']} 차이 {s['diff']} t={s['t']} 순서 유지 {s['ordered']}"
              f"  corr V {s['corr_v']} / MOVE 수준 {s['corr_level']}")
    print("\n[Q2 점수 → 다음 달 Fly (bp, 음수 = 벨리 강세)]")
    for s in bt_dir["samples"] + bt_dir["regimes"]:
        by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '+.1f'):>6s}"
                       f"{'' if g['hit'] is None else ' (' + str(g['hit']) + '%)':>7s}" for g in s["by"])
        print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | 신호 적중 {s['signal']['hits']}/{s['signal']['n']} 기준선 {s['base']}%  t={s['t']}")
    print("\n[Q3 축별 상관계수: 다음 달 실현변동성]")
    for key, lab, _ in samples:
        a = bt_axes[key]
        print(f"  {lab:6s} " + "  ".join(f"{r['key']} {r['corr']}(n={r['n']})" for r in a["rows"])
              + f"  | R² V만 {a.get('r2_v')}% → V+R {a.get('r2_vr')}%  | 심리만 스트레스 n={a['r_only']['n']} {a['r_only']['mean']} vs 평소 {a['neither']['mean']}"
              + f"  | 경보 켜짐 n={a['alarm']['n']} {a['alarm']['mean']} vs 꺼짐 {a['alarm']['mean_off']}")
    print(f"\n[Q4 스트레스 시작 달 {len(episodes)}번]  유형: {type_count['onset']}")
    for e in episodes:
        print(f"  {e['month']} ({e['months']}개월) MOVE {e['move_peak']:6.1f} VIX {e['vix_peak']:5.1f} | 그 달 2y {e['c2']:+6.1f} 10y {e['c10']:+6.1f} 2s10s {e['c2s10s']:+6.1f} fly {e['cfly']:+5.1f}  {e['type']}")
    print(f"  스트레스 {type_count['n_all']}개월 전체: {type_count['all']}  평균 10y {same['stress_c10']} 2s10s {same['stress_c2s10s']} fly {same['stress_cfly']}")
    print(f"\n→ signals.js, signals_monthly.csv 저장 (월 {len(monthly)}개)")


if __name__ == "__main__":
    main()
