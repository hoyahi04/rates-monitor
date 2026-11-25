"""매크로 · 정책 경로 신호와 백테스트 계산 → signals.js + signals_monthly.csv

신호 (매월 마지막 거래일에 판정, 그날까지 공개된 값만 사용)
  1) 경로 괴리 = 시장이 가격한 앞으로 2년 평균 정책금리 − 점도표가 뜻하는 2년 평균 정책금리 (bp)
       +25 이상 → +1(시장이 점도표보다 높게 가격 = 인하를 덜·인상을 더 가격, 금리 하락 쪽)
       −25 이하 → −1(시장이 점도표보다 낮게 가격, 금리 상승 쪽) / 그 사이 0          → 수준 뷰(Duration), 기울기 뷰(Curve Slope)
       · 시장 쪽: 2년 국채 금리(CMT)를 익일물 금리 단위로 환산한 값. 선물 과거 자료가 없어서 쓰는 대용치다.
       · 연준 쪽: 직전 SEP 점도표 중간값을 현재 정책금리에서 각 연말까지 직선으로 이은 경로의 2년 평균.
  2) 정책 기조 = 시장이 가격한 1년 뒤 1년 금리(1y1y) − 장기 점도표(중립금리) (bp)
       +50 이상 → +1(긴축으로 가격, 스티프닝 쪽) / −50 이하 → −1(완화로 가격, 플래트닝 쪽)   → 기울기 뷰(참고)

백테스트 (성과월 2015-01 ~ 직전 완료월. 2015~2020은 규칙 설정, 2021~은 검증 구간)
  Q1) FOMC 결정일: 2년 금리가 10bp 움직일 때 10년·30년 금리 변화 (반응형)
  Q2) 경로 괴리 점수 → 다음 달 2년 금리 변화 (예측형, 수준)
  Q3) 경로 괴리 점수 → 다음 달 2s10s 변화 (예측형, 기울기)
  Q4) 정책 기조 점수 → 다음 달 2s10s 변화 (예측형, 기울기)

현재 시점 교차 확인: 연방기금금리 선물(ff_futures.csv)로 회의별 내재 금리와 '선물 기준 1년 괴리'를 따로 계산한다.

입력: policy_daily.csv, dots.csv, fomc_dates.csv, ff_futures.csv (fetch_data.py가 생성), 수익률곡선(CURVE_JS)
실행: python3 analyze.py
"""
import bisect, calendar, csv, json, math
from datetime import date, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
CURVE_JS = HERE.parents[1] / "curve" / "data.js"   # 일별 CMT 금리(공통 데이터). 옮기면 이 줄만 고친다.

TH_GAP = 25          # bp (25bp = 금리 변경 한 번)  ← 백테스트 전에 정한 값. 결과를 보고 바꾸지 않는다.
TH_STANCE = 50       # bp
BT_START = "2015-01"            # 첫 성과월
TEST_START = "2021-01"          # 검증 구간 첫 성과월
BASIS_DAYS = 20                 # EFFR − 목표 범위 중간값을 평균하는 거래일 수
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
        i = bisect.bisect_right(self.dates, d)
        return self.values[i - 1] if i else None

    def before(self, d, n):
        """d보다 앞선 마지막 n개 값 (d 당일 제외)."""
        i = bisect.bisect_left(self.dates, d)
        return self.values[max(0, i - n):i]

    def day_change(self, d):
        """d 당일 종가 − 직전 거래일 종가. d가 거래일이 아니면 None."""
        i = self.index.get(d)
        return None if not i else self.values[i] - self.values[i - 1]


def months_ago(d, n):
    y, m, day = int(d[:4]), int(d[5:7]), int(d[8:10])
    k = y * 12 + (m - 1) - n
    y2, m2 = k // 12, k % 12 + 1
    return f"{y2:04d}-{m2:02d}-{min(day, calendar.monthrange(y2, m2)[1]):02d}"


def next_month(ym):
    k = int(ym[:4]) * 12 + int(ym[5:7])
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def ordinal(d):
    return date(int(d[:4]), int(d[5:7]), int(d[8:10])).toordinal()


def shift_day(d, n):
    return date.fromordinal(ordinal(d) + n).isoformat()


# ---------- 단위 맞추기 ----------
def to_overnight(y):
    """국채 금리(%, 연 2회 복리·365일 기준) → 익일물 금리 단위(%, 일복리·360일 기준).
    점도표와 연방기금금리는 익일물 단위라서 그대로 빼면 금리 4%에서 약 10bp 어긋난다."""
    return None if y is None else math.log(1 + y / 200) * 200 * 360 / 365


# ---------- 점도표 경로 ----------
def dot_knots(d, mid, years, shift=0.0):
    """현재 정책금리(목표 범위 중간값)에서 각 연말 점도표 중간값까지 직선으로 이은 경로의 꺾이는 점.
    shift = EFFR − 목표 범위 중간값. 경로 전체를 실효 금리 기준으로 옮긴다."""
    t0 = ordinal(d)
    knots = [(t0, mid + shift)]
    for y in sorted(years):
        t = date(y, 12, 31).toordinal()
        if t > t0:
            knots.append((t, years[y] + shift))
    return knots


def path_value(knots, t):
    if t <= knots[0][0]:
        return knots[0][1]
    for (ta, va), (tb, vb) in zip(knots, knots[1:]):
        if t <= tb:
            return va + (vb - va) * (t - ta) / (tb - ta)
    return knots[-1][1]          # 마지막 점 이후는 그대로


def path_avg(knots, a, b):
    """[a, b] 구간 평균. 꺾이는 점에서 나눠 사다리꼴로 더하므로 직선 경로에서는 정확하다."""
    pts = sorted({a, b} | {t for t, _ in knots if a < t < b})
    area = sum((path_value(knots, p) + path_value(knots, q)) / 2 * (q - p) for p, q in zip(pts, pts[1:]))
    return area / (b - a)


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


def score(x, th):
    """x가 +th 이상이면 +1, −th 이하이면 −1."""
    if x is None:
        return None
    return 1 if x >= th else -1 if x <= -th else 0


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


# ---------- 선물: 회의별 내재 금리 ----------
def meeting_path(strip, meetings, start_rate):
    """월물별 내재 금리(월평균) → 회의 직후 금리. CME FedWatch와 같은 방식이다.
    회의가 없는 달의 월평균은 그 달 내내 적용되는 금리로 본다.
    회의가 있는 달은 다음 달에 회의가 없으면 다음 달 월평균을 회의 직후 금리로 쓰고,
    다음 달에도 회의가 있으면 그 달 월평균을 회의 전·후 날짜 수로 풀어서 구한다."""
    by_month = {}
    for d in meetings:
        by_month.setdefault(d[:7], d)
    months = sorted(strip)
    out, rate = [], start_rate
    for i, m in enumerate(months):
        if m not in by_month:
            rate = strip[m]
            continue
        d = by_month[m]
        n, day = calendar.monthrange(int(m[:4]), int(m[5:7]))[1], int(d[8:10])
        nxt = months[i + 1] if i + 1 < len(months) else None
        if nxt and nxt == next_month(m) and nxt not in by_month:
            post = strip[nxt]
        elif n - day >= 3:
            post = (strip[m] * n - rate * day) / (n - day)      # 새 금리는 결정 다음 날부터 적용
        else:
            continue
        out.append({"date": d, "pre": round(rate, 3), "post": round(post, 3), "move": round((post - rate) * 100, 1)})
        rate = post
    return out


def strip_avg(strip, a, b):
    """월물별 내재 금리를 [a, b) 구간의 날짜 수로 가중 평균. 구간을 다 덮지 못하면 None."""
    total, days = 0.0, 0
    for m, v in strip.items():
        y, mo = int(m[:4]), int(m[5:7])
        lo = date(y, mo, 1).toordinal()
        hi = lo + calendar.monthrange(y, mo)[1]
        k = min(hi, b) - max(lo, a)
        if k > 0:
            total, days = total + v * k, days + k
    return total / days if days == b - a else None


# ---------- 본 계산 ----------
def main():
    dates, yields = load_curve()
    Y = {k: Daily(dates, yields[k]) for k in ("1Y", "2Y", "5Y", "10Y", "30Y")}
    asof = dates[-1]
    pol = read_csv("policy_daily.csv")
    pdates = [r["date"] for r in pol]
    MID = Daily(pdates, [num(r["mid"]) for r in pol])
    UP = Daily(pdates, [num(r["upper"]) for r in pol])
    LO = Daily(pdates, [num(r["lower"]) for r in pol])
    EFFR = Daily(pdates, [num(r["effr"]) for r in pol])
    BASIS = Daily(pdates, [None if num(r["effr"]) is None or num(r["mid"]) is None else num(r["effr"]) - num(r["mid"])
                           for r in pol])
    changes, prev = [], None
    for d, v in zip(UP.dates, UP.values):
        if v != prev:
            changes.append((d, v))
            prev = v
    regimes = build_regimes(changes, asof)

    seps = {}
    for r in read_csv("dots.csv"):
        s = seps.setdefault(r["sep_date"], {"date": r["sep_date"], "years": {}, "lr": None})
        if r["target"] == "LR":
            s["lr"] = float(r["median"])
        else:
            s["years"][int(r["target"])] = float(r["median"])
    sep_list = [seps[d] for d in sorted(seps)]
    sep_dates = [s["date"] for s in sep_list]
    fomc = read_csv("fomc_dates.csv")

    def state(d):
        """날짜 d 종가 시점에 알 수 있는 값으로 두 신호를 계산."""
        i = bisect.bisect_right(sep_dates, d)
        sep = sep_list[i - 1] if i else None
        mid = MID.at(shift_day(d, 1))       # FRED는 새 목표 범위를 결정 다음 날부터 싣는다. 결정일 종가는 이미 새 금리를 안다.
        y1, y2 = Y["1Y"].at(d), Y["2Y"].at(d)
        if sep is None or mid is None or y1 is None or y2 is None:
            return None
        basis = mean(BASIS.before(d, BASIS_DAYS)) or 0.0        # EFFR은 다음 날 아침에 나오므로 전날까지만
        knots = dot_knots(d, mid, sep["years"], basis)
        t0 = ordinal(d)
        m1, m2 = to_overnight(y1), to_overnight(y2)
        dot1, dot2 = path_avg(knots, t0, t0 + 365), path_avg(knots, t0, t0 + 730)
        fwd = 2 * m2 - m1                                       # 1년 뒤 1년 금리(근사)
        neutral = sep["lr"] + basis
        gap, stance = (m2 - dot2) * 100, (fwd - neutral) * 100
        y2_1m = Y["2Y"].at(months_ago(d, 1))
        return {"date": d, "sep": sep["date"], "mid": mid, "basis": round(basis * 100, 1),
                "y1": y1, "y2": y2, "m1": round(m1, 3), "m2": round(m2, 3),
                "dot1": round(dot1, 3), "dot2": round(dot2, 3),
                "gap": round(gap, 1), "gap1": round((m1 - dot1) * 100, 1), "s1": score(gap, TH_GAP),
                "fwd": round(fwd, 3), "lr": sep["lr"], "neutral": round(neutral, 3),
                "stance": round(stance, 1), "s2": score(stance, TH_STANCE),
                "chg1m": None if y2_1m is None else round((y2 - y2_1m) * 100, 1),
                "regime": regime_at(regimes, d)}

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

    bt_level = backtest("s1", "d2", expect=-1)          # +1(시장 > 점도표) → 2년 금리 하락 기대
    bt_level["also"] = {k: {s["key"]: [g["mean"] for g in summarize(rows, "s1", k, -1)["by"]]
                            for s, (_, _, rows) in zip(bt_level["samples"], samples)} for k in ("d5", "d10")}
    bt_slope = backtest("s1", "d2s10s", expect=+1)      # +1 → 단기 금리가 더 내려 2s10s 확대 기대
    bt_stance = backtest("s2", "d2s10s", expect=+1)     # +1(긴축으로 가격) → 2s10s 확대 기대

    # ----- Q1: FOMC 결정일 반응 -----
    events = []
    for r in fomc:
        d = r["date"]
        if r["kind"] != "scheduled" or d[:7] < BT_START or d > asof:
            continue
        ch = {k: Y[k].day_change(d) for k in ("2Y", "10Y", "30Y")}
        if any(v is None for v in ch.values()):
            continue
        events.append({"date": d, "sep": int(r["sep"]), "d2": round(ch["2Y"] * 100, 1), "d10": round(ch["10Y"] * 100, 1),
                       "d30": round(ch["30Y"] * 100, 1), "era": "B" if d >= TEST_START else "A",
                       "regime": regime_at(regimes, d),
                       "move": round((MID.at(shift_day(d, 1)) - MID.at(shift_day(d, -1))) * 100)})   # 그 회의의 금리 변경폭
    fomc_days = {e["date"] for e in events}
    day = {k: [(d, Y[k].day_change(d) * 100) for d in Y[k].dates[1:] if d[:7] >= BT_START] for k in ("2Y", "10Y")}
    other = [(d, a, b) for (d, a), (_, b) in zip(day["2Y"], day["10Y"]) if d not in fomc_days]

    def abs_stats(lo, hi):
        on = [abs(e["d2"]) for e in events if lo <= e["date"] < hi]
        off = [abs(a) for d, a, _ in other if lo <= d < hi]
        return r1(mean(on), 2), r1(mean(off), 2), len(on)

    eras = [("A", f"{BT_START[:4]}~{int(TEST_START[:4]) - 1}", BT_START, TEST_START),
            ("B", f"{TEST_START[:4]}~", TEST_START, "9999"), ("all", "전체", BT_START, "9999")]
    by_era = []
    for key, label, lo, hi in eras:
        ev = [e for e in events if lo <= e["date"] < hi]
        b10, r2_10, t10 = ols([e["d2"] for e in ev], [e["d10"] for e in ev])
        b30, r2_30, t30 = ols([e["d2"] for e in ev], [e["d30"] for e in ev])
        ot = [(a, b) for d, a, b in other if lo <= d < hi]
        bo, _, _ = ols([a for a, _ in ot], [b for _, b in ot])
        on2, off2, _ = abs_stats(lo, hi)
        sep_abs = [abs(e["d2"]) for e in ev if e["sep"]]
        non_abs = [abs(e["d2"]) for e in ev if not e["sep"]]
        by_era.append({"key": key, "label": label, "n": len(ev), "sd2": r1(stdev([e["d2"] for e in ev])),
                       "slope10": r1(b10 and b10 * 10), "r2_10": r1(r2_10, 2), "t10": r1(t10, 1),     # bp per 10bp of 2y
                       "slope30": r1(b30 and b30 * 10), "r2_30": r1(r2_30, 2), "t30": r1(t30, 1),
                       "slope10_other": r1(bo and bo * 10),
                       "abs_fomc2": on2, "abs_other2": off2,
                       "abs_sep2": r1(mean(sep_abs), 2), "abs_nosep2": r1(mean(non_abs), 2)})
    by_year = []
    for y in range(int(BT_START[:4]), int(asof[:4]) + 1):
        on2, off2, n = abs_stats(f"{y}-01-01", f"{y + 1}-01-01")
        if n:
            by_year.append({"year": y, "n": n, "abs_fomc2": on2, "abs_other2": off2})

    # ----- 현재 판정 + 선물 교차 확인 -----
    cur = state(asof)
    cur.update(upper=UP.at(asof), lower=LO.at(asof), effr=EFFR.at(asof), dots=seps[cur["sep"]]["years"])
    prev_sep = sep_list[sep_dates.index(cur["sep"]) - 1]
    cur["prev_sep"] = {"date": prev_sep["date"], "years": prev_sep["years"], "lr": prev_sep["lr"]}
    t0 = ordinal(asof)
    knots = dot_knots(asof, cur["mid"], seps[cur["sep"]]["years"], cur["basis"] / 100)
    fut = None
    if (HERE / "ff_futures.csv").exists():
        by_date = {}
        for r in read_csv("ff_futures.csv"):
            by_date.setdefault(r["date"], {})[r["contract"]] = round(100 - float(r["price"]), 4)
        fdates = sorted(d for d in by_date if len(by_date[d]) >= 6)

        def snap(target):
            i = bisect.bisect_right(fdates, target)
            return fdates[i - 1] if i else None

        d_now = snap(asof)
        if d_now and (t0 - ordinal(d_now)) <= 7:
            strip = {m: v for m, v in by_date[d_now].items() if m >= d_now[:7]}
            upcoming = [r["date"] for r in fomc if r["kind"] == "scheduled" and r["date"] > d_now]
            meets = meeting_path(strip, upcoming, cur["effr"])
            for m in meets:
                m["cum"] = round((m["post"] - cur["effr"]) * 100, 1)
                m["dot"] = round(path_value(knots, ordinal(m["date"])), 3)
            fut1 = strip_avg(strip, t0, t0 + 365)
            snaps = [{"key": "now", "label": "현재", "date": d_now}]
            for key, label, target in (("m1", "1개월 전", months_ago(asof, 1)), ("sep", "직전 SEP 발표일", cur["sep"])):
                ds = snap(target)
                if ds and ds < d_now and (key != "sep" or ds == target):
                    snaps.append({"key": key, "label": label, "date": ds})
            for s in snaps:
                st = by_date[s["date"]]
                s["months"] = sorted(m for m in st if m >= d_now[:7])
                s["rates"] = [st[m] for m in s["months"]]
            fut = {"date": d_now, "snaps": snaps, "meetings": meets,
                   "avg1y": r1(fut1, 3), "gap1y": None if fut1 is None else round((fut1 - cur["dot1"]) * 100, 1),
                   "tsy_minus_fut": None if fut1 is None else round((cur["m1"] - fut1) * 100, 1),
                   "peak": max(strip.values()), "peak_month": max(strip, key=strip.get), "last_month": max(strip)}
    cur["dot_path"] = [{"date": date.fromordinal(t).isoformat(), "v": round(v, 3)} for t, v in knots]

    # ----- 일별 시계열 (차트용) -----
    dd = [state(d) for d in dates if d >= sep_dates[0]]
    dd = [r for r in dd if r]
    daily = {"dates": [r["date"] for r in dd], "m2": [r["m2"] for r in dd], "dot2": [r["dot2"] for r in dd],
             "gap": [r["gap"] for r in dd], "mid": [r["mid"] for r in dd],
             "fwd": [r["fwd"] for r in dd], "neutral": [r["neutral"] for r in dd]}

    cols = ["date", "month", "sep", "mid", "y2", "m2", "dot2", "gap", "s1", "fwd", "neutral", "stance", "s2",
            "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    with open(HERE / "signals_monthly.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["decision_date", "apply_month", "sep_date", "policy_mid", "ust_2y", "market_2y_avg", "dots_2y_avg",
                    "path_gap_bp", "score_policy", "fwd_1y1y", "neutral", "stance_bp", "score_stance", "regime",
                    "next_d2y_bp", "next_d5y_bp", "next_d10y_bp", "next_d30y_bp", "next_d2s10s_bp", "next_d5s30s_bp"])
        for r in monthly:
            w.writerow(["" if r[c] is None else r[c] for c in cols])

    keys = ["date", "month", "sep", "gap", "s1", "stance", "s2", "regime", "d2", "d5", "d10", "d30", "d2s10s", "d5s30s"]
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"), "asof": asof,
        "thresholds": {"gap": TH_GAP, "stance": TH_STANCE},
        "split": {"start": BT_START, "test_start": TEST_START, "end": done[-1]["month"]},
        "current": cur, "futures": fut, "regimes": regimes, "daily": daily,
        "monthly": {k: [r[k] for r in monthly] for k in keys},
        "events": events, "event_stats": {"by_era": by_era, "by_year": by_year},
        "bt": {"level": bt_level, "slope": bt_slope, "stance": bt_stance},
    }
    (HERE / "signals.js").write_text(
        "window.POLICY_SIGNALS = " + json.dumps(out, ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")

    # ----- 콘솔 요약 -----
    sc = lambda s: {1: "+1", 0: " 0", -1: "−1", None: " ?"}[s]
    print(f"\n[현재 판정] 기준일 {asof} · 국면 {REGIME_KO[cur['regime']]} · 목표 범위 {cur['lower']}~{cur['upper']}% · 직전 SEP {cur['sep']}")
    print(f"  경로 괴리 {sc(cur['s1'])}  (시장 2년 평균 {cur['m2']:.2f}% − 점도표 2년 평균 {cur['dot2']:.2f}% = {cur['gap']:+.0f}bp)")
    print(f"  정책 기조 {sc(cur['s2'])}  (1y1y {cur['fwd']:.2f}% − 중립 {cur['neutral']:.2f}% = {cur['stance']:+.0f}bp)")
    if fut:
        print(f"  선물 교차 확인 ({fut['date']}): 1년 평균 {fut['avg1y']}% − 점도표 1년 평균 {cur['dot1']}% = {fut['gap1y']:+.0f}bp"
              f"  (국채 기준 1년 괴리 {cur['gap1']:+.0f}bp, 국채 − 선물 {fut['tsy_minus_fut']:+.0f}bp)")
        for m in fut["meetings"]:
            print(f"    {m['date']} 회의 뒤 {m['post']:.3f}%  ({m['move']:+5.1f}bp, 누적 {m['cum']:+5.1f}bp, 점도표 경로 {m['dot']:.3f}%)")
    for title, bt, unit in (("Q2 경로 괴리 → 다음 달 2년 금리", bt_level, "Δ2y"), ("Q3 경로 괴리 → 다음 달 2s10s", bt_slope, "Δ2s10s"),
                            ("Q4 정책 기조 → 다음 달 2s10s", bt_stance, "Δ2s10s")):
        print(f"\n[{title}]  (평균 {unit} bp / 적중률)")
        for s in bt["samples"] + bt["regimes"]:
            by = "  ".join(f"{sc(g['score'])}: n={g['n']:<3d} {'' if g['mean'] is None else format(g['mean'], '+.1f'):>6s}"
                           f"{'' if g['hit'] is None else ' (' + str(g['hit']) + '%)':>7s}" for g in s["by"])
            print(f"  {s['label']:6s} n={s['n']:<3d} {by}  | 신호 적중 {s['signal']['hits']}/{s['signal']['n']}"
                  f" 기준선 {s['base']}%  (+1)−(−1)={s['spread']} t={s['t']}")
    print("\n[Q1 FOMC 결정일]  2년 금리 10bp당")
    for e in by_era:
        print(f"  {e['label']:10s} n={e['n']:<3d} 10y {e['slope10']}bp (R² {e['r2_10']}, t {e['t10']})  30y {e['slope30']}bp (R² {e['r2_30']}, t {e['t30']})"
              f"  평소 10y {e['slope10_other']}bp | |Δ2y| 결정일 {e['abs_fomc2']} vs 평소 {e['abs_other2']}bp (SEP 있는 회의 {e['abs_sep2']}, 없는 회의 {e['abs_nosep2']})")
    print(f"\n→ signals.js, signals_monthly.csv 저장 (월 {len(monthly)}개, FOMC {len(events)}회)")


if __name__ == "__main__":
    main()
