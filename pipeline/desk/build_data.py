"""화면용 자료 한 파일을 만든다 → data/desk_data.js (window.DESK)

읽는 것
  ../2. portfolio/data.js                  재무부 CMT 금리 (11개 만기, 일별)
  ../1. macro/0X_*/data.js, signals.js     다섯 매크로 섹션의 원자료와 신호
  ../1. macro/scoreboard.js                이번 달 판정
  ../3. dashboard/portfolio.js             2015년부터 규칙대로 운용한 모형 포트폴리오
  data/raw/extra.json, fedinvest.csv       fetch_extra.py가 받은 것
  data/raw/korea.json                      fetch_korea.py가 받은 것 (키가 없으면 no_key)
  data/ratings.csv                         (있으면) 손으로 적은 신용등급

화면(index.html, v2.html)은 계산하지 않고 이 파일을 읽어 그리기만 한다. 예외는 채권 상세와 Trade Builder의
가격·물량 계산으로, assets/bondmath.js가 bondmath.py와 같은 수식으로 그 자리에서 계산한다.

실행:  python3 build_data.py     (표준 라이브러리만)
"""
import csv, difflib, io, math, os, re, sys
from datetime import date, timedelta
from pathlib import Path

import bondmath as bm
from common import (DESK, MODEL, RAW, ROOT, back, clean, corr, ffill, idx_on_or_before, last_valid, load_js, log, mean,
                    now_utc, num, pctile, r, read_json, stdev, write_js, write_json, zscore)

START = "2015-01-02"          # 화면에 싣는 시계열의 시작
TEN = [("1M", 1 / 12), ("3M", .25), ("6M", .5), ("1Y", 1), ("2Y", 2), ("3Y", 3), ("5Y", 5), ("7Y", 7), ("10Y", 10),
       ("20Y", 20), ("30Y", 30)]
KR_TEN = [("1Y", 1, "ktb1"), ("2Y", 2, "ktb2"), ("3Y", 3, "ktb3"), ("5Y", 5, "ktb5"), ("10Y", 10, "ktb10"),
          ("20Y", 20, "ktb20"), ("30Y", 30, "ktb30"), ("50Y", 50, "ktb50")]
HOR = ["d1", "w1", "m1", "m3", "ytd", "y1"]
PROBLEMS = []


def warn(msg):
    PROBLEMS.append(msg)
    log("  ! " + msg)


# ───────────────────────── 시계열 도구 ─────────────────────────
def at(dates, vals, target):
    """target 날짜 이하에서 마지막으로 값이 있는 관측."""
    i = idx_on_or_before(dates, target)
    while i >= 0 and vals[i] is None:
        i -= 1
    return vals[i] if i >= 0 else None


def window(dates, vals, lo, hi):
    a, b = idx_on_or_before(dates, lo) + 1, idx_on_or_before(dates, hi) + 1
    return [v for v in vals[max(a, 0):b] if v is not None]


def summarize(dates, vals, scale=1.0, pct_change=False):
    """마지막 값, 기간별 변화, 3년 통계. scale은 변화에 곱하는 값(% → bp면 100). pct_change면 변화를 %로."""
    v, i = last_valid(vals)
    if v is None:
        return None
    d0 = dates[i]
    prev = last_valid(vals, i - 1)[0]
    refs = {"d1": prev, "w1": at(dates, vals, back(d0, days=7)), "m1": at(dates, vals, back(d0, months=1)),
            "m3": at(dates, vals, back(d0, months=3)), "ytd": at(dates, vals, f"{int(d0[:4]) - 1}-12-31"),
            "y1": at(dates, vals, back(d0, years=1))}

    def diff(p):
        if p is None:
            return None
        return r((v / p - 1) * 100, 2) if pct_change else r((v - p) * scale, 2)

    w3 = window(dates, vals, back(d0, years=3), d0)
    w1 = window(dates, vals, back(d0, years=1), d0)
    return {"level": r(v, 4), "date": d0, "chg": {k: diff(p) for k, p in refs.items()},
            "z3y": r(zscore(w3, v), 2) if len(w3) > 120 else None, "z1y": r(zscore(w1, v), 2) if len(w1) > 60 else None,
            "pct3y": r(pctile(w3, v), 0) if len(w3) > 120 else None,
            "lo3y": r(min(w3), 4) if w3 else None, "hi3y": r(max(w3), 4) if w3 else None, "n3y": len(w3)}


def spark(vals, n=260, step=5):
    xs = [v for v in vals[-n:] if v is not None]
    xs = xs[(len(xs) - 1) % step::step] if xs else []
    return [r(v, 3) for v in xs]


def align(pack, grid):
    """{d:[...], v:[...]} 를 날짜 격자에 맞춘다 (그날 값이 없으면 None)."""
    if not pack:
        return [None] * len(grid)
    m = dict(zip(pack["d"], pack["v"]))
    return [m.get(d) for d in grid]


def combo(*cols, f):
    out = []
    for row in zip(*cols):
        out.append(None if any(x is None for x in row) else f(*row))
    return out


def month_ends(dates):
    """날짜 격자에서 달마다 마지막 영업일의 위치."""
    out = []
    for i, d in enumerate(dates):
        if i == len(dates) - 1 or dates[i + 1][:7] != d[:7]:
            out.append(i)
    return out


# ───────────────────────── 입력 ─────────────────────────
def load_inputs():
    I = {}
    I["U"] = load_js(ROOT / "curve" / "data.js")
    m = ROOT / "macro"
    for key, folder in [("pol", "01_policy_path"), ("gro", "02_growth_jobs"), ("inf", "03_inflation"),
                        ("sup", "04_supply_tp"), ("liq", "05_liquidity_vol")]:
        I[key + "_d"] = load_js(m / folder / "data.js")
        I[key + "_s"] = load_js(m / folder / "signals.js")
    I["score"] = load_js(m / "scoreboard.js")
    I["pf"] = load_js(MODEL / "portfolio.js")
    I["extra"] = read_json(RAW / "extra.json", {}) or {}
    kr_path = os.environ.get("DESK_KOREA_JSON") or (RAW / "korea.json")     # 시험할 때만 다른 파일로 바꿔 본다
    I["korea"] = read_json(kr_path, {"status": "no_key"}) or {"status": "no_key"}
    return I


# ───────────────────────── 시장 (커브, 히트맵) ─────────────────────────
def market_block(dates, ys, tenors):
    """dates: 날짜 격자, ys: {만기: 값 목록}, tenors: [(이름, 연수)] → 커브 스냅샷, 만기별 히트맵, 월별 표."""
    names = [t for t, _ in tenors]
    asof = dates[-1]
    snaps = []
    marks = [("now", "오늘", asof), ("d1", "1일 전", dates[-2]), ("w1", "1주 전", back(asof, days=7)),
             ("m1", "1달 전", back(asof, months=1)), ("m3", "3달 전", back(asof, months=3)),
             ("ytd", "작년 말", f"{int(asof[:4]) - 1}-12-31"), ("y1", "1년 전", back(asof, years=1))]
    for key, label, target in marks:
        i = idx_on_or_before(dates, target)
        if i < 0:
            continue
        snaps.append({"key": key, "label": label, "date": dates[i], "y": [r(ffill(ys[t][:i + 1])[-1], 3) for t in names]})
    heat = []
    for t, yrs in tenors:
        s = summarize(dates, ys[t], 100)
        if s:
            s.update({"tenor": t, "years": yrs, "spark": spark(ys[t])})
            heat.append(s)
    me = month_ends(dates)[-37:]
    months, level, chg = [], {t: [] for t in names}, {t: [] for t in names}
    for a, b in zip(me, me[1:]):
        months.append(dates[b][:7])
        for t in names:
            v1, v0 = last_valid(ys[t], b)[0], last_valid(ys[t], a)[0]
            level[t].append(r(v1, 3))
            chg[t].append(None if v1 is None or v0 is None else r((v1 - v0) * 100, 1))
    partial = dates[me[-1]] == asof and not _is_month_last_bday(asof)
    wk_sd = {}
    for t in names:                    # 평소 한 주 움직임: 최근 1년의 5영업일 변화(bp)의 표준편차
        f = ffill(ys[t])[-258:]
        ch = [(f[k] - f[k - 5]) * 100 for k in range(5, len(f)) if f[k] is not None and f[k - 5] is not None]
        if len(ch) > 100:
            wk_sd[t] = r(stdev(ch), 1)
    return {"tenors": names, "years": [y for _, y in tenors], "asof": asof, "snaps": snaps, "heat": heat, "wk_sd": wk_sd,
            "monthly": {"months": months, "level": level, "chg": chg, "partial_last": partial}}


def _is_month_last_bday(s):
    d0 = date.fromisoformat(s)
    nxt = d0 + timedelta(days=1)
    while nxt.weekday() >= 5:
        nxt += timedelta(days=1)
    return nxt.month != d0.month


def curve_at(U, i):
    xs, ys = [], []
    for t, yrs in TEN:
        v = U["yields"][t][i]
        if v is not None:
            xs.append(yrs)
            ys.append(v)
    return xs, ys


# ───────────────────────── 종목 (FedInvest) ─────────────────────────
def local_fit(pts):
    """(잔존만기, 수익률) 점들로 '이웃 종목의 추세선'을 만든다 (국소 선형 회귀, tricube 가중).
    돌려주는 f(t, skip)는 만기 t에서의 추세선 값이고, skip번째 점은 빼고 계산한다(자기 자신을 빼고 이웃과 비교).
    창 너비는 만기에 비례한다: max(0.75년, 만기의 20%)."""
    def f(t, skip=None):
        h = max(0.75, 0.2 * t)
        sw = sx = sy = sxx = sxy = 0.0
        for k, (tj, yj) in enumerate(pts):
            if k == skip:
                continue
            u = abs(tj - t) / h
            if u >= 1:
                continue
            w = (1 - u ** 3) ** 3
            x = tj - t
            sw += w
            sx += w * x
            sy += w * yj
            sxx += w * x * x
            sxy += w * x * yj
        if sw <= 0:
            return None
        den = sw * sxx - sx * sx
        if abs(den) < 1e-9:              # 이웃이 한쪽 만기에만 몰려 있으면 가중 평균으로
            return sy / sw
        return (sy * sxx - sx * sxy) / den
    return f


def bonds_block(I):
    path = RAW / "fedinvest.csv"
    meta = (I["extra"].get("fedinvest") or {})
    if not path.exists() or not meta.get("price_date"):
        warn("FedInvest 종가가 없어 종목 표를 만들지 못함")
        return {"status": "none"}
    U, pdate = I["U"], meta["price_date"]
    settle = bm.next_business_day(pdate)
    ci = idx_on_or_before(U["dates"], pdate)
    cx, cy = curve_at(U, ci)
    sofr = last_valid(I["liq_d"]["daily"]["sofr"])[0]
    auc = I["sup_d"]["auctions"]
    first = {}                       # cusip → (만기 이름, 처음 발행일)
    for c, t, d0 in zip(auc["cusip"], auc["tenor"], auc["issue_date"]):
        if c and (c not in first or d0 < first[c][1]):
            first[c] = (t, d0)
    rows = []
    for x in csv.reader(io.StringIO(path.read_text(encoding="utf-8"))):
        if len(x) < 8 or x[1] not in ("MARKET BASED NOTE", "MARKET BASED BOND"):
            continue
        px, cpn = num(x[7]), num(x[2])
        if not px or cpn is None:
            continue
        mm, dd, yy = x[3].split("/")
        mat = date(int(yy), int(mm), int(dd))
        ttm = bm.years_between(settle, mat)
        if ttm < 0.25:
            continue
        cpn *= 100
        a = bm.analytics(cpn, mat, settle, clean_price=px)
        ten = first.get(x[0])
        rows.append({"cusip": x[0], "type": "Note" if "NOTE" in x[1] else "Bond", "coupon": r(cpn, 3),
                     "maturity": mat.isoformat(), "ttm": r(ttm, 3), "price": r(px, 5), "accrued": r(a["accrued"], 5),
                     "ytm": r(a["ytm"], 4), "mdur": r(a["mdur"], 3), "conv": r(a["conv"], 2),
                     "dv01": r(a["dv01_per_1m"], 1), "orig": ten[0] if ten else None, "issued": ten[1] if ten else None})
    if len(rows) < 50:
        warn(f"FedInvest 종목이 {len(rows)}개뿐이라 종목 표를 만들지 않음")
        return {"status": "none"}
    # 추세선은 2010년 이후 발행 종목으로만 만든다. 그 전에 발행된 옛 30년물은 값이 따로 놀아 이웃의 추세선을 끌어당긴다.
    base = [k for k, b in enumerate(rows) if b["orig"]]
    where = {k: n for n, k in enumerate(base)}
    fit = local_fit([(rows[k]["ttm"], rows[k]["ytm"]) for k in base])
    newest = {}
    for b in rows:
        if b["orig"] and b["issued"] and b["issued"] <= settle.isoformat():
            if b["orig"] not in newest or b["issued"] > newest[b["orig"]]["issued"]:
                newest[b["orig"]] = b
    resid = []
    for k, b in enumerate(rows):
        b["otr"] = b["orig"] if newest.get(b["orig"]) is b else None
        own = fit(b["ttm"], skip=where.get(k))                      # 자기 자신을 뺀 이웃의 추세선
        b["old"] = k not in where
        b["fit_bp"] = None if own is None else r((b["ytm"] - own) * 100, 1)   # + 면 이웃보다 금리가 높다 (싸다)
        if b["fit_bp"] is not None:
            resid.append(b["fit_bp"])
        h = 0.25
        y_now, y_roll = fit(b["ttm"]), fit(max(b["ttm"] - h, 0.3))
        b["roll3m"] = r(-b["mdur"] * (y_roll - y_now) * 100, 1) if (b["ttm"] > h + 0.3 and y_now is not None and y_roll is not None) else None
        b["carry3m"] = None if sofr is None else r((b["ytm"] - sofr) * 0.25 * 100, 1)
        b["par_gap_bp"] = r((b["ytm"] - bm.interp(cx, cy, b["ttm"])) * 100, 1)   # 재무부 par 금리 곡선 대비
        b.pop("issued", None)
    rows.sort(key=lambda b: b["maturity"])
    out = {"status": "ok", "price_date": pdate, "settle": settle.isoformat(), "source": "미 재무부 FedInvest 종가",
           "curve_date": U["dates"][ci], "repo": sofr, "n": len(rows), "list": rows}
    grid_t = [0.5 + 0.25 * k for k in range(119)]
    out["fit"] = {"method": "2010년 이후 발행 종목의 국소 선형 회귀 (창 너비 = max(0.75년, 만기의 20%))", "n_base": len(base),
                  "rmse_bp": r(math.sqrt(sum(x * x for x in resid) / len(resid)), 2) if resid else None,
                  "curve": [[t, r(fit(t), 4)] for t in grid_t if fit(t) is not None]}
    log(f"  종목 {len(rows)}개 (가격 {pdate}), 추세선 대비 잔차 {out['fit']['rmse_bp']}bp, 최근 발행물 {sorted(newest)}")
    return out


# ───────────────────────── 전략 스크리너 ─────────────────────────
def screener_block(dates, ys, repo):
    """par 금리 곡선으로 본 3개월 carry·roll-down과 스프레드·버터플라이의 위치."""
    asof = dates[-1]
    xs = [y for _, y in TEN]
    cur = [last_valid(ys[t])[0] for t, _ in TEN]
    yat = lambda T: bm.interp(xs, cur, T)
    H = 0.25

    def leg(T):
        y, yr = yat(T), yat(T - H)
        d_after = bm.par_mod_dur(T - H, yr)
        carry = (y - repo) * H * 100                 # bp (가격 기준)
        roll = (y - yr) * 100 * d_after              # bp (가격 기준)
        return {"carry": carry, "roll": roll, "total": carry + roll, "be": (carry + roll) / d_after, "dur": d_after}

    legs = {t: leg(yrs) for t, yrs in TEN if yrs >= 1}
    outright = []
    for t, yrs in TEN:
        if yrs < 2:
            continue
        s = summarize(dates, ys[t], 100)
        L = legs[t]
        outright.append({"key": t, "label": f"{t} 매수", "tenor": t, "years": yrs, "yield": s["level"], "m1": s["chg"]["m1"],
                         "z3y": s["z3y"], "pct3y": s["pct3y"], "carry": r(L["carry"], 1), "roll": r(L["roll"], 1),
                         "total": r(L["total"], 1), "be": r(L["be"], 1), "dur": r(L["dur"], 2)})

    def series_of(w):
        cols = [ys[t] for t in w]
        return combo(*cols, f=lambda *v: sum(wi * vi for wi, vi in zip(w.values(), v)) * 100)

    def trade(key, label, kind, w, carry_w, hint):
        """w: 수준(bp)을 만드는 가중치. carry_w: 그 포지션을 DV01 1 단위로 들었을 때 다리별 DV01 부호."""
        ser = series_of(w)
        s = summarize(dates, ser, 1)
        cr = sum(cw * legs[t]["be"] for t, cw in carry_w.items())
        return {"key": key, "label": label, "kind": kind, "legs": list(w.keys()), "level": r(s["level"], 1),
                "m1": s["chg"]["m1"], "w1": s["chg"]["w1"], "z1y": s["z1y"], "z3y": s["z3y"], "pct3y": s["pct3y"],
                "lo3y": r(s["lo3y"], 1), "hi3y": r(s["hi3y"], 1), "cr3m": r(cr, 1), "hint": hint, "spark": spark(ser)}

    curves = [trade(f"{a}{b}", f"{a.replace('Y', '')}s{b.replace('Y', '')}s", "curve", {b: 1, a: -1}, {a: 1, b: -1},
                    f"스티프너 = {a} 매수 · {b} 매도")
              for a, b in [("2Y", "5Y"), ("2Y", "10Y"), ("2Y", "30Y"), ("5Y", "10Y"), ("5Y", "30Y"), ("10Y", "30Y")]]
    flies = [trade(f"{a}{b}{c}", f"{a.replace('Y', '')}s{b.replace('Y', '')}s{c.replace('Y', '')}s", "fly",
                   {b: 2, a: -1, c: -1}, {b: 1, a: -0.5, c: -0.5}, f"벨리 매수 = {b} 매수 · {a}, {c} 매도")
             for a, b, c in [("2Y", "5Y", "10Y"), ("3Y", "5Y", "7Y"), ("5Y", "7Y", "10Y"), ("5Y", "10Y", "30Y"),
                             ("2Y", "10Y", "30Y"), ("10Y", "20Y", "30Y")]]
    return {"asof": asof, "horizon": "3개월", "repo": r(repo, 3), "outright": outright, "curves": curves, "flies": flies}


# ───────────────────────── 모형 포트폴리오 (내 북) ─────────────────────────
EPISODES = [("2013-05-02", "2013-09-05", "2013 테이퍼 탠트럼"), ("2016-11-08", "2016-12-15", "2016 미 대선 뒤 금리 급등"),
            ("2020-02-19", "2020-03-09", "2020 코로나 안전자산 쏠림"), ("2020-03-09", "2020-03-18", "2020 코로나 유동성 위기"),
            ("2022-08-01", "2022-10-24", "2022 가을 긴축 가속"), ("2023-03-08", "2023-03-13", "2023 SVB 사태"),
            ("2023-07-31", "2023-10-19", "2023 가을 장기금리 급등"), ("2024-07-31", "2024-08-05", "2024 8월 고용 쇼크")]



# 키레이트 듀레이션(KRD): 커브의 한 만기만 ±1bp 움직였을 때 값이 얼마 변하나 (중앙 차분)
# 범프 모양은 그 만기에서 1bp, 옆 만기에서 0인 삼각형이다 (첫 만기 앞과 마지막 만기 뒤는 평평).
# 재무부 par 금리를 할인율 곡선으로 쓰고, 오늘 가격과 맞도록 일정한 스프레드를 더한다.
KRD_KEYS = [("1Y", 1), ("2Y", 2), ("3Y", 3), ("5Y", 5), ("7Y", 7), ("10Y", 10), ("20Y", 20), ("30Y", 30)]


def _tri(k, t):
    ks = [x for _, x in KRD_KEYS]
    i = ks.index(k)
    if t <= ks[0]:
        return 1.0 if i == 0 else 0.0
    if t >= ks[-1]:
        return 1.0 if i == len(ks) - 1 else 0.0
    if i > 0 and ks[i - 1] <= t <= k:
        return (t - ks[i - 1]) / (k - ks[i - 1])
    if i < len(ks) - 1 and k <= t <= ks[i + 1]:
        return (ks[i + 1] - t) / (ks[i + 1] - k)
    return 0.0


def krd_per100(coupon, maturity, settle, cx, cy, dirty):
    """액면 100당, 만기 키마다 1bp에 대한 가격 변화 (금리 하락 때 이익이 +)."""
    cfs = [(t, a) for _, t, a in bm.cashflows(coupon, maturity, settle)]
    base = [bm.interp(cx, cy, t) / 100 for _, t in [(None, t) for t, _ in cfs]]

    def price(spread, bump=None):
        tot = 0.0
        for (t, a), z in zip(cfs, base):
            zz = z + spread + (bump(t) if bump else 0.0)
            tot += a / (1 + zz / 2) ** (2 * t)
        return tot

    s = 0.0
    for _ in range(30):          # 오늘 가격과 맞추는 스프레드
        f = price(s) - dirty
        if abs(f) < 1e-10:
            break
        d = (price(s + 1e-6) - price(s - 1e-6)) / 2e-6
        s -= f / d
    out = []
    for _, k in KRD_KEYS:
        up = price(s, lambda t: 1e-4 * _tri(k, t))
        dn = price(s, lambda t: -1e-4 * _tri(k, t))
        out.append((dn - up) / 2)
    return out


def book_block(I):
    P, U = I["pf"], I["U"]
    S, ser, now = P["stats"], P["series"], P["now"]
    dts, navp, navb, exc = ser["dates"], ser["nav_p"], ser["nav_b"], ser["excess_bp"]
    asof = dts[-1]
    nav, navbm = navp[-1], navb[-1]

    def ret(arr, target):
        i = idx_on_or_before(dts, target)
        return None if i < 0 else (arr[-1] / arr[i] - 1) * 100

    def exc_since(target):
        i = idx_on_or_before(dts, target)
        return None if i < 0 else exc[-1] - exc[i]

    marks = {"d1": dts[-2], "w1": back(asof, days=7), "mtd": back(asof[:8] + "01", days=1), "ytd": f"{int(asof[:4]) - 1}-12-31",
             "y1": back(asof, years=1)}
    perf = {k: {"p": r(ret(navp, t), 3), "b": r(ret(navb, t), 3), "ex_bp": r(exc_since(t), 2)} for k, t in marks.items()}
    perf["itd"] = {"p": r(S["cum_p"], 3), "b": r(S["cum_b"], 3), "ex_bp": r(S["excess_cum_bp"], 2)}
    pnl_d1 = navp[-1] - navp[-2]

    # 포지션: 구간마다 모형 채권 한 종목. 리밸런싱일의 par 금리를 쿠폰으로 발행됐다고 보고 오늘 금리로 다시 값을 매긴다.
    # 벤치마크 쪽 모형 채권도 같은 방법으로 오늘 값을 매겨야 듀레이션 차이가 같은 날 기준이 된다.
    ui = idx_on_or_before(U["dates"], asof)
    cx, cy = curve_at(U, ui)
    dx, dy = curve_at(U, idx_on_or_before(U["dates"], now["date"]))
    settle = bm.next_business_day(asof)

    def model_bond(coupon, mat_years):
        mat = date.fromisoformat(now["date"]) + timedelta(days=round(mat_years * 365.25))
        ttm = bm.years_between(settle, mat)
        a = bm.analytics(coupon, mat, settle, yield_pct=bm.interp(cx, cy, ttm))
        a.update({"maturity": mat.isoformat(), "ttm": ttm})
        return a

    pos, tot_dv01_p, tot_dv01_b = [], 0.0, 0.0
    krd_rows = []
    for b in now["buckets"]:
        a = model_bond(b["coupon"], b["mat_p"])
        cb = bm.interp(dx, dy, b["mat_b"])
        ab = model_bond(cb, b["mat_b"])
        mv = nav * b["w_p"] / 100
        dirty = a["clean"] + a["accrued"]
        dirty_b = ab["clean"] + ab["accrued"]
        par_b = nav * b["w_b"] / 100 / dirty_b * 100
        kp = krd_per100(b["coupon"], a["maturity"], settle, cx, cy, dirty)
        kb = krd_per100(cb, ab["maturity"], settle, cx, cy, dirty_b)
        krd_rows.append({"label": b["label"], "p": [r(v * mv / dirty, 0) for v in kp], "b": [r(v * par_b / 100, 0) for v in kb]})
        dv01 = mv * a["mdur"] * 1e-4
        dv01_b = nav * b["w_b"] / 100 * ab["mdur"] * 1e-4
        tot_dv01_p += dv01
        tot_dv01_b += dv01_b
        pos.append({"id": b["id"], "label": b["label"], "name": f"모형 국채 {b['label']}", "coupon": r(b["coupon"], 3),
                    "maturity": a["maturity"], "ttm": r(a["ttm"], 2), "price": r(a["clean"], 3), "accrued": r(a["accrued"], 4),
                    "ytm": r(a["ytm"], 3), "mdur": r(a["mdur"], 3), "conv": r(a["conv"], 2),
                    "par": r(mv / dirty * 100, 0), "mv": r(mv, 0), "w_p": r(b["w_p"], 2), "w_b": r(b["w_b"], 2),
                    "dur_b": r(ab["mdur"], 3), "mat_b": r(ab["ttm"], 2), "dv01": r(dv01, 0), "dv01_b": r(dv01_b, 0),
                    "c_p": r(b["w_p"] / 100 * a["mdur"], 4), "c_b": r(b["w_b"] / 100 * ab["mdur"], 4),
                    "active": r(b["w_p"] / 100 * a["mdur"] - b["w_b"] / 100 * ab["mdur"], 4)})

    # 위험: 과거 일별 손익으로 본 VaR
    lo3 = idx_on_or_before(dts, back(asof, years=3))
    rets = [navp[i] / navp[i - 1] - 1 for i in range(max(lo3, 1), len(navp))]
    dex = [exc[i] - exc[i - 1] for i in range(max(lo3, 1), len(exc))]

    def q(xs, p):
        xs = sorted(xs)
        return xs[max(0, min(len(xs) - 1, int(math.floor(p * len(xs)))))]

    var = {"n": len(rets), "d1_95_pct": r(-q(rets, 0.05) * 100, 3), "d1_99_pct": r(-q(rets, 0.01) * 100, 3),
           "d1_95_usd": r(-q(rets, 0.05) * nav, 0), "d1_99_usd": r(-q(rets, 0.01) * nav, 0),
           "rel_95_bp": r(-q(dex, 0.05), 2), "rel_99_bp": r(-q(dex, 0.01), 2),
           "worst_day": r(min(rets) * 100, 3), "vol_ann_pct": r(stdev(rets) * math.sqrt(252) * 100, 2)}

    # 스트레스: 과거 국면의 금리 변화를 지금 북에 그대로 적용 (듀레이션만, 볼록성과 이자는 뺌)
    stress = []
    for a0, a1, label in EPISODES:
        i0, i1 = idx_on_or_before(U["dates"], a0), idx_on_or_before(U["dates"], a1)
        if i0 < 0 or i1 <= i0:
            continue
        x0, y0 = curve_at(U, i0)
        x1, y1 = curve_at(U, i1)
        rp = rb = 0.0
        for p in pos:
            dy_p = bm.interp(x1, y1, p["ttm"]) - bm.interp(x0, y0, p["ttm"])
            dy_b = bm.interp(x1, y1, p["mat_b"]) - bm.interp(x0, y0, p["mat_b"])
            rp += -p["w_p"] / 100 * p["mdur"] * dy_p
            rb += -p["w_b"] / 100 * p["dur_b"] * dy_b
        d = lambda T: r((bm.interp(x1, y1, T) - bm.interp(x0, y0, T)) * 100, 0)
        stress.append({"label": label, "from": U["dates"][i0], "to": U["dates"][i1], "d2": d(2), "d10": d(10), "d30": d(30),
                       "p_pct": r(rp, 2), "b_pct": r(rb, 2), "active_bp": r((rp - rb) * 100, 1), "p_usd": r(rp / 100 * nav, 0)})

    dur_p = sum(p["w_p"] / 100 * p["mdur"] for p in pos)
    dur_b = sum(p["w_b"] / 100 * p["dur_b"] for p in pos)
    par_shift = [{"bp": s, "p_usd": r(-dur_p * s / 100 / 100 * nav, 0), "p_pct": r(-dur_p * s / 100, 2),
                  "active_bp": r(-(dur_p - dur_b) * s, 1)} for s in (-100, -50, -25, 25, 50, 100)]

    # 귀속: 달별, 연도별, 전략별 누적
    months, cum = [], {"dur": 0.0, "slope": 0.0, "curv": 0.0}
    cum_series = {"month": [], "dur": [], "slope": [], "curv": [], "total": []}
    for m in P["months"]:
        months.append({"month": m["month"], "partial": m["partial"], "ex": r(m["excess_bp"], 1), "dur": r(m["c_dur"], 1),
                       "slope": r(m["c_slope"], 1), "curv": r(m["c_curv"], 1), "ret_p": r(m["ret_p"], 2),
                       "ret_b": r(m["ret_b"], 2), "pos_dur": m["dur"], "pos_slope": m["slope"], "pos_curv": m["curv"],
                       "d10": m["d10y_bp"]})
        cum["dur"] += m["c_dur"]
        cum["slope"] += m["c_slope"]
        cum["curv"] += m["c_curv"]
        cum_series["month"].append(m["month"])
        for k in ("dur", "slope", "curv"):
            cum_series[k].append(r(cum[k], 1))
        cum_series["total"].append(r(sum(cum.values()), 1))

    alt = P.get("alt") or {}
    return {
        "asof": asof, "start": S["start"], "nav0": S["nav0"], "nav": r(nav, 0), "nav_bm": r(navbm, 0),
        "pnl_d1_usd": r(pnl_d1, 0), "perf": perf, "model_note": P["model"]["note"],
        "decision_date": now["date"], "apply_month": P["apply_month"], "position": now["position"],
        "dur_p": r(dur_p, 3), "dur_b": r(dur_b, 3), "active_dur": r(dur_p - dur_b, 3), "rule_active_dur": now["active"],
        "dv01": r(tot_dv01_p, 0), "dv01_b": r(tot_dv01_b, 0), "cs01": 0, "positions": pos,
        "krd": {"keys": [k for k, _ in KRD_KEYS], "rows": krd_rows},
        "stats": {k: S[k] for k in ("years", "ann_p", "ann_b", "excess_ann_bp", "excess_cum_bp", "vol_p", "vol_b", "te_all_bp",
                                    "te_1y_bp", "te_3y_bp", "ir", "mdd_p", "mdd_p_from", "mdd_p_to", "mdd_b", "mdd_rel_bp",
                                    "months", "months_active", "months_win", "n_rebal", "c_dur", "c_slope", "c_curv", "hit",
                                    "best", "worst")},
        "risk": {"te_exante_bp": P["risk"]["te_exante_bp"], "te_max_bp": P["risk"]["te_max_bp"], "budget": P["risk"]["budget"],
                 "scenarios": P["risk"]["scenarios"], "var": var, "stress": stress, "parallel": par_shift},
        "series": {"dates": dts, "nav_p": [round(x) for x in navp], "nav_b": [round(x) for x in navb], "excess_bp": exc,
                   "alt_excess_bp": alt.get("series")},
        "months": months, "years": P["years"], "cum": cum_series,
        "rebalances": [{"date": x["date"], "month": x["month"], "frm": x["frm"], "to": x["to"], "why": x["why"],
                        "ex": r(x["excess_bp"], 1), "partial": x["partial"]} for x in P["rebalances"]],
        "alt": {k: alt.get(k) for k in ("name", "rule", "excess_cum_bp", "excess_ann_bp", "te_bp", "ir", "now", "train", "test")},
        "initial": P["initial"],
    }


# ───────────────────────── 매크로·정책 ─────────────────────────
def _dissents(paras):
    """'Voting against' 문장을 규칙으로 읽어 매파/비둘기파 반대표를 센다.
    raise·easing bias 반대 = 매파, lower·tightening bias 반대 = 비둘기파."""
    txt = " ".join(p for p in paras if "Voting against" in p)
    m = re.search(r"Voting against (?:this|the monetary policy) action (?:was|were) (.*)", txt)
    out = {"hawk": 0, "dove": 0, "other": 0, "names": []}
    if not m:
        return out
    for clause in m.group(1).split(";"):
        names_part, _, why = clause.partition(", who")
        names = re.findall(r"[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+", names_part)
        side = ("hawk" if re.search(r"raise|easing bias", why) else "dove" if re.search(r"lower|tightening bias", why) else "other")
        out[side] += len(names)
        out["names"] += [{"name": n, "side": side} for n in names]
    return out


def fomc_block(st, grid, cols):
    """FOMC 성명 리뷰: 최신 성명과 직전 성명의 단어 단위 비교(레드라인), 회의별 반대표와 2년·10년 금리 당일 반응.
    2년 금리가 성명 당일 ±5bp 이상 움직이면 시장이 예상하지 못한 결과(서프라이즈)로 본다."""
    if not st or len(st) < 2:
        return None
    body = lambda x: [p for p in x["paras"] if not p.startswith("Voting")]
    a, b = " ".join(body(st[-2])).split(), " ".join(body(st[-1])).split()
    segs = []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op == "equal":
            segs.append(["eq", " ".join(a[i1:i2])])
        else:
            if i2 > i1:
                segs.append(["del", " ".join(a[i1:i2])])
            if j2 > j1:
                segs.append(["ins", " ".join(b[j1:j2])])
    changed = sum(len(t.split()) for k, t in segs if k == "ins")
    meetings = []
    for x in st:
        k = idx_on_or_before(grid, x["date"])
        dis = _dissents(x["paras"])
        vote = x.get("vote")
        if not vote:   # 표결 수가 본문에 없으면 찬성 명단을 센다
            yes = " ".join(p for p in x["paras"] if p.startswith("Voting for")).split("Voting against")[0]
            n_yes = len([n for n in re.findall(r"[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+", yes) if n != "Vice Chair"])
            vote = [n_yes, dis["hawk"] + dis["dove"] + dis["other"]] if n_yes else None
        row = {"date": x["date"], "url": x["url"], "vote": vote, "dissent": dis}
        if k >= 1 and grid[k] == x["date"]:
            for key in ("y2", "y10"):
                v1, v0 = cols[key][k], cols[key][k - 1]
                row["d_" + key] = None if v1 is None or v0 is None else r((v1 - v0) * 100, 1)
            row["d_2s10s"] = None if row["d_y2"] is None or row["d_y10"] is None else r(row["d_y10"] - row["d_y2"], 1)
        else:
            row["d_y2"] = row["d_y10"] = row["d_2s10s"] = None
        d2 = row["d_y2"]
        row["surprise"] = None if d2 is None else ("매파적" if d2 >= 5 else "비둘기적" if d2 <= -5 else None)
        meetings.append(row)
    return {"latest": st[-1]["date"], "prev": st[-2]["date"], "url": st[-1]["url"], "redline": segs,
            "changed_words": changed, "total_words": len(b), "meetings": meetings[::-1]}
def sme_block(sme, policy, asof):
    """뉴욕 연은 SME(시장참가자 설문) 중간값 경로를 선물 내재 금리, 점도표와 같은 시점에서 비교한다.
    선물은 월평균 금리라서, 회의가 있는 달은 다음 달 평균(회의 뒤 수준)을 쓴다. 양수 갭 = 선물이 컨센서스보다 높음(매파적)."""
    if not sme or not sme.get("points"):
        return None
    now = next((s for s in policy.get("snaps") or [] if s["key"] == "now"), None)
    fut = dict(zip(now["months"], now["rates"])) if now else {}
    dots = policy.get("dots") or {}
    ym0 = asof[:7]
    rows = []
    for p in sme["points"]:
        if p["month"] < ym0:
            continue
        m = p["month"]
        if p["kind"] == "meeting":
            y, mm = int(m[:4]), int(m[5:]) + 1
            m = f"{y + (mm > 12)}-{(mm - 1) % 12 + 1:02d}"
        f = fut.get(m)
        d = dots.get(p["month"][:4]) if p["month"].endswith("-12") else None
        rows.append({"label": p["label"], "month": p["month"], "sme": p["med"], "p25": p["p25"], "p75": p["p75"],
                     "fut": r(f, 3), "dot": d, "gap_bp": None if f is None else r((f - p["med"]) * 100, 0)})
    yr = int(asof[:4]) + 1
    target = f"{yr}-{asof[5:7]}"
    have = [x for x in rows if x["gap_bp"] is not None]
    head = min(have, key=lambda x: abs(int(x["month"][:4]) * 12 + int(x["month"][5:]) - yr * 12 - int(asof[5:7]))) if have else None
    return {"survey": sme["survey"], "url": sme["url"], "lr": sme.get("lr"), "avg10": sme.get("avg10"),
            "rows": rows, "head": head, "target": target}


TONE_TAG = 0.10          # 발언 하나: 성향 ≥ +0.10 매파, ≤ −0.10 비둘기파
TONE_BAND_DAYS = 90      # 위원 성향 띠: 최근 90일 정책 발언 평균


def tone_block(T, fomc, asof):
    """fed_tone.py가 만든 발언별 성향(−1~+1, + = 매파)을 화면용으로 정리: 발언 로그, 위원 성향 띠, 의장 최근 발언."""
    items = list((T.get("items") or {}).values())
    if not items:
        return None
    voters = set()
    for st in reversed(fomc):                       # 가장 최근에 찬성 명단이 실린 성명
        txt = " ".join(p for p in st["paras"] if p.startswith("Voting for"))
        if txt:
            voters = {n.split()[-1] for n in re.findall(r"[A-Z][a-z]+(?: [A-Z]\.)? [A-Z][a-z]+", txt) if n != "Vice Chair"}
            break
    pcs = sorted((x for x in items if x["kind"] == "기자회견"), key=lambda x: x["date"])
    chair = pcs[-1]["speaker"] if pcs else None
    tag = lambda v: "매" if v >= TONE_TAG else "비" if v <= -TONE_TAG else "중"
    out = []
    for x in sorted(items, key=lambda x: x["date"], reverse=True):
        who = x["speaker"]
        out.append({"date": x["date"], "kind": x["kind"], "speaker": who, "title": x["title"], "url": x["url"], "net": x["net"],
                    "n": x["n"], "tag": tag(x["net"]), "policy": bool(x["policy"]), "chair": who == chair,
                    "voter": who in voters or x["kind"] in ("연설", "의회 증언"),   # 이사회 RSS 발언자는 모두 이사(투표권자)
                    "ex_h": x.get("ex_h", [])[:1], "ex_d": x.get("ex_d", [])[:1]})
    cut = back(asof, days=TONE_BAND_DAYS)
    band = {}
    for x in out:
        if x["date"] >= cut and x["policy"] and x["kind"] in ("연설", "의회 증언", "기자회견"):
            band.setdefault(x["speaker"], []).append(x["net"])
    members = [{"name": k, "avg": r(sum(v) / len(v), 3), "n": len(v), "voter": True, "chair": k == chair}
               for k, v in band.items()]
    members.sort(key=lambda m: m["avg"])
    chair_recent = [x for x in out if x["chair"] and x["policy"]][:3]
    return {"model": T.get("model"), "generated": T.get("generated"), "items": out[:60], "members": members,
            "chair": chair, "chair_recent": chair_recent, "band_days": TONE_BAND_DAYS, "tag_th": TONE_TAG,
            "policy_th": T.get("policy_share_th")}
# 우리 의견 기울기(tilt) 규칙: 연준 트래커 확장안(2026-11-26) 05장
TILT_BP_PER_PT = 25.0               # 점수 1점당 25bp (인하 한 번)
TILT_CAPS = {"start": 25.0, "wide": 50.0, "off": 0.0}
TILT_HIT_WIDE, TILT_HIT_OFF, TILT_MIN_OBS = 0.55, 0.45, 6
GAPB_TH = (25.0, 50.0)              # 괴리 B 신호 문턱 (bp)


def _interp_month(points, ym):
    """[(YYYY-MM, 값)] 정렬 목록에서 ym 값을 월 단위로 선형 보간 (범위 밖이면 None)."""
    toi = lambda m: int(m[:4]) * 12 + int(m[5:7])
    x = toi(ym)
    for (m0, v0), (m1, v1) in zip(points, points[1:]):
        a, b = toi(m0), toi(m1)
        if a <= x <= b and v0 is not None and v1 is not None:
            return v0 + (v1 - v0) * (x - a) / (b - a) if b > a else v0
    return None


def _tilt(s2, s3, cap):
    raw = -TILT_BP_PER_PT * ((s2 or 0) + (s3 or 0)) / 2 + 0.0
    return raw, max(-cap, min(cap, raw))


def _gapb_signal(g):
    if g is None:
        return None
    a, b = GAPB_TH
    if g >= b: return {"code": -2, "ko": "듀레이션 축소 (강)", "why": "우리가 시장보다 훨씬 매파"}
    if g >= a: return {"code": -1, "ko": "듀레이션 축소 (약)", "why": "우리가 시장보다 조금 더 매파"}
    if g <= -b: return {"code": 2, "ko": "듀레이션 확대 (강)", "why": "우리가 시장보다 훨씬 비둘기파"}
    if g <= -a: return {"code": 1, "ko": "듀레이션 확대 (약)", "why": "우리가 시장보다 조금 더 비둘기파"}
    return {"code": 0, "ko": "중립 (포지션 없음)", "why": "차이가 인하 한 번(25bp) 미만"}


def view_block(policy, score, gro, inf, asof):
    """컨센서스(SME 중간값) + 우리 기울기 = 우리 12개월 경로, 괴리 B = 우리 − 선물 → 듀레이션 신호.
    기울기 = −25bp × (P2 성장·고용 + P3 물가) ÷ 2, 한도 밖은 자른다. P2·P3는 팀 스코어보드 점수(+1 = 채권 강세).
    한도는 최근 12개월 적중률로 정한다: 기울기 방향(+ = 금리 상승 예상)과 다음 달 2년 금리 변화 방향이 같으면 적중."""
    sme = policy.get("sme")
    if not sme:
        return None
    # 적중 기록: 팀 스코어보드 월별 점수(2015~)로 거꾸로 계산
    rows = []
    for x in _sig_rows(gro, inf):
        raw, _ = _tilt(x["s2"], x["s3"], 999)
        if raw == 0 or x["d2y"] is None:
            continue
        rows.append({"month": x["apply_month"], "tilt_dir": 1 if raw > 0 else -1, "d2y": x["d2y"],
                     "hit": (raw > 0) == (x["d2y"] > 0)})
    last12 = [x for x in rows if x["month"] > f"{int(asof[:4]) - 1}-{asof[5:7]}"]
    hits = sum(x["hit"] for x in last12)
    rate = hits / len(last12) if last12 else None
    if rate is None or len(last12) < TILT_MIN_OBS:
        cap_key = "start"
    else:
        cap_key = "wide" if rate >= TILT_HIT_WIDE else "off" if rate < TILT_HIT_OFF else "start"
    cap = TILT_CAPS[cap_key]
    all_rate = sum(x["hit"] for x in rows) / len(rows) if rows else None
    # 12개월 뒤 시점
    y, m = int(asof[:4]) + 1, int(asof[5:7])
    target = f"{y}-{m:02d}"
    pts = [(p["month"], p["sme"]) for p in sme["rows"]]
    cons = _interp_month(pts, target)
    now = next((x for x in policy.get("snaps") or [] if x["key"] == "now"), None)
    fut = dict(zip(now["months"], now["rates"])).get(target) if now else None
    out = {"target": target, "consensus": r(cons, 3), "futures": r(fut, 3), "cap": cap, "cap_key": cap_key,
           "hit": {"n12": len(last12), "hits12": hits, "rate12": None if rate is None else r(rate, 3),
                   "n_all": len(rows), "rate_all": None if all_rate is None else r(all_rate, 3),
                   "recent": rows[-12:][::-1]},
           "rules": {"bp_per_pt": TILT_BP_PER_PT, "caps": TILT_CAPS, "hit_wide": TILT_HIT_WIDE, "hit_off": TILT_HIT_OFF,
                     "min_obs": TILT_MIN_OBS, "gapb_th": GAPB_TH}}
    for key, lab in (("current", "적용 중"), ("live", "잠정")):
        L = score.get(key) or {}
        if "s2_growth" not in L:
            continue
        raw, t = _tilt(L["s2_growth"], L["s3_inflation"], cap)
        ours = None if cons is None else cons + t / 100
        gb = None if ours is None or fut is None else (ours - fut) * 100
        out[key] = {"label": lab, "apply_month": L.get("apply_month"), "decision_date": L.get("decision_date"),
                    "p2": L["s2_growth"], "p3": L["s3_inflation"], "tilt_raw": r(raw, 1), "tilt": r(t, 1),
                    "ours": r(ours, 3), "gap_b": r(gb, 1), "signal": _gapb_signal(gb)}
    return out


def _sig_rows(gro, inf):
    """성장·고용, 인플레이션 섹션의 월별 신호 CSV를 판정일로 붙인다."""
    m = ROOT / "macro"
    def rd(folder):
        with open(m / folder / "signals_monthly.csv", encoding="utf-8-sig") as f:
            return {x["decision_date"]: x for x in csv.DictReader(f)}
    G, F_ = rd("02_growth_jobs"), rd("03_inflation")
    out = []
    for d in sorted(set(G) & set(F_)):
        a, b = G[d], F_[d]
        try:
            s2, s3 = int(float(a["score_growth"])), int(float(b["score_momentum"]))
        except (TypeError, ValueError):
            continue
        d2 = a.get("next_d2y_bp")
        out.append({"decision_date": d, "apply_month": a["apply_month"], "s2": s2, "s3": s3,
                    "d2y": float(d2) if d2 not in (None, "") else None})
    return out


# 기조 판정표 (확장안 ③): 다섯 항목 −2~+2, + = 매파
STANCE_W = {"S1": 0.25, "S2": 0.20, "S3": 0.25, "S4": 0.15, "S5": 0.15}
STANCE_GRADES = [(1.0, "매파 강"), (0.3, "매파"), (-0.3, "중립"), (-1.0, "비둘기파")]   # 그 아래 = 비둘기파 강
TONE_STEP = (0.05, 0.15)      # 성향(기준 대비) → 점수: ±0.05 넘으면 ±1, ±0.15 넘으면 ±2  (모델 치우침을 뺀 값 기준, 잠정)
STANCE_LOG = RAW / "fed_stance_log.json"


def _bucket(v, a, b):
    if v is None:
        return None
    return 2 if v >= b else 1 if v >= a else -2 if v <= -b else -1 if v <= -a else 0


def stance_block(policy, sep, T, asof):
    """S1 성명, S2 점도표, S3 의장, S4 위원, S5 반대표 → 기조 점수·등급, 괴리 A(점도표 − 선물, 1년 뒤), 교차 점검.
    S1·S3·S4는 FOMC-RoBERTa 성향에서 '모델 기준선'(최근 1년 정책 발언 성향의 중간값)을 뺀 값으로 매긴다."""
    items = [x for x in (T.get("items") or {}).values() if x.get("policy")]
    if not items:
        return None
    year_ago = back(asof, years=1)
    recent = sorted(x["net"] for x in items if x["date"] >= year_ago)
    base = recent[len(recent) // 2] if recent else 0.0
    parts = {}
    # S1 성명: 최신 성명 성향 − 기준선
    st = sorted((x for x in items if x["kind"] == "성명"), key=lambda x: x["date"])
    if st:
        v = st[-1]["net"] - base
        parts["S1"] = {"name": "성명서", "score": _bucket(v, *TONE_STEP), "basis": f"{st[-1]['date']} 성명 성향 {st[-1]['net']:+.2f} (기준선 {base:+.2f} 대비 {v:+.2f})"}
    # S2 점도표: 내년 말 중간값의 직전 SEP 대비 변화
    if sep and sep.get("median"):
        ny = str(int(sep["date"][:4]) + 1)
        a, b = sep["median"].get(ny), (sep.get("prev_median") or {}).get(ny)
        if a is not None and b is not None:
            dv = (a - b) * 100
            parts["S2"] = {"name": "점도표", "score": _bucket(dv, 20, 45), "basis": f"{ny}년 말 중간값 {b:.1f}% → {a:.1f}% ({dv:+.0f}bp, {sep['date']} SEP)"}
    # S3 의장: 최근 45일 의장 발언(기자회견·연설·증언) 평균, 없으면 마지막 기자회견
    pcs = sorted((x for x in items if x["kind"] == "기자회견"), key=lambda x: x["date"])
    chair = pcs[-1]["speaker"] if pcs else None
    if chair:
        c45 = [x for x in items if x["speaker"] == chair and x["date"] >= back(asof, days=45)] or [pcs[-1]]
        v = sum(x["net"] for x in c45) / len(c45) - base
        parts["S3"] = {"name": f"의장 ({chair})", "score": _bucket(v, *TONE_STEP), "basis": f"최근 발언 {len(c45)}건 평균, 기준선 대비 {v:+.2f}"}
    # S4 위원: 지난 30일 위원 발언 평균 (투표권자 2배; 이사회 RSS 발언자는 모두 투표권자)
    mem = [x for x in items if x["kind"] in ("연설", "의회 증언") and x["speaker"] != chair and x["date"] >= back(asof, days=30)]
    if mem:
        v = sum(x["net"] * 2 for x in mem) / (2 * len(mem)) - base
        parts["S4"] = {"name": "위원 발언", "score": _bucket(v, *TONE_STEP), "basis": f"최근 30일 {len(mem)}건 (투표권자 2배) 평균, 기준선 대비 {v:+.2f}"}
    # S5 반대표: 최근 회의
    fm = policy.get("fomc")
    if fm and fm.get("meetings"):
        ds = fm["meetings"][0]["dissent"]
        net = ds["hawk"] - ds["dove"]
        parts["S5"] = {"name": "반대표", "score": max(-2, min(2, net)), "basis": f"{fm['meetings'][0]['date']} 회의 매파 반대 {ds['hawk']}명, 비둘기파 반대 {ds['dove']}명"}
    have = {k: v for k, v in parts.items() if v["score"] is not None}
    wsum = sum(STANCE_W[k] for k in have)
    score = sum(STANCE_W[k] * v["score"] for k, v in have.items()) / wsum if wsum else None   # 빠진 항목은 나머지로 다시 나눈다
    grade = None if score is None else next((g for th, g in STANCE_GRADES if score >= th), "비둘기파 강")
    # 괴리 A: 점도표 경로(오늘 정책금리 → 연말 중간값 선형) 1년 뒤 − 선물 1년 뒤.  + = 시장이 연준보다 인하를 더 기대
    V = policy.get("view") or {}
    target = V.get("target") or f"{int(asof[:4]) + 1}-{asof[5:7]}"
    mid = (policy["upper"] + policy["lower"]) / 2
    pts = [(asof[:7], mid)] + [(f"{y}-12", v) for y, v in sorted((policy.get("dots") or {}).items())]
    dot12 = _interp_month(pts, target)
    fut = V.get("futures")
    gap_a = None if dot12 is None or fut is None else (dot12 - fut) * 100
    # 지난달 대비 변화(기조 전환 경고): 월별 기록 파일에 이번 달 값을 남긴다
    log_ = read_json(STANCE_LOG, {}) or {}
    ym = asof[:7]
    prev = next((log_[k] for k in sorted(log_, reverse=True) if k < ym), None)
    if score is not None:
        log_[ym] = {"asof": asof, "score": r(score, 2), "grade": grade, "parts": {k: v["score"] for k, v in parts.items()}}
        write_json(STANCE_LOG, log_)
    chg = None if prev is None or score is None else score - prev["score"]
    return {"score": r(score, 2), "grade": grade, "parts": parts, "weights": STANCE_W, "baseline": r(base, 3),
            "gap_a": r(gap_a, 1), "dots_12m": r(dot12, 3), "futures_12m": fut, "target": target,
            "distrust": bool(score is not None and score >= 0.3 and gap_a is not None and gap_a >= 25),
            "prev": prev, "chg": r(chg, 2), "shift_alert": bool(chg is not None and abs(chg) >= 0.5),
            "sep": None if not sep else {"date": sep["date"], "url": sep["url"]}, "tone_step": TONE_STEP}


def _last_rows(folder, n=4):
    with open(ROOT / "macro" / folder / "signals_monthly.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return rows[-n:]


def brief_block(policy, sep, score, asof):
    """연준 기조 브리핑 (확장안 ②): 한 줄 결론, 현재 진단, 매크로 요소 표, 컨센서스 vs 우리, 주의할 점.
    모든 칸은 이미 계산된 값(5필라 신호, SEP, 기조 판정표, 우리 기울기)을 같은 틀에 채운다. 손으로 쓰는 칸 없음."""
    ST, V = policy.get("stance"), policy.get("view")
    if not ST or not V or not V.get("current"):
        return None
    vc = V["current"]
    cur = score.get("current") or {}
    yr = asof[:4]
    E = (sep or {}).get("econ") or {}
    f = lambda x: None if x in (None, "") else float(x)
    G, IN, SU, LQ = _last_rows("02_growth_jobs"), _last_rows("03_inflation"), _last_rows("04_supply_tp"), _last_rows("05_liquidity_vol")
    g, g3, i_, i3, su, lq = G[-1], G[0], IN[-1], IN[0], SU[-1], LQ[-1]
    ism = []
    with open(ROOT / "macro" / "02_growth_jobs" / "ism_manufacturing.csv", encoding="utf-8-sig") as fh:
        ism = [x for x in csv.DictReader(fh) if f(x.get("pmi")) is not None]
    arrow = lambda a, b, eps: None if a is None or b is None else ("↑" if a - b > eps else "↓" if b - a > eps else "→")
    word = {1: "채권 강세 쪽 (+1)", 0: "중립 (0)", -1: "채권 약세 쪽 (−1)"}
    pce12, pce3, une = f(i_["core_pce_12m"]), f(i_["core_pce_3m_ann"]), f(g["unrate"])
    sep_pce, sep_une = E.get("core_pce", {}).get(yr), E.get("unemp", {}).get(yr)
    s2, s3, s4, s5 = cur.get("s2_growth"), cur.get("s3_inflation"), cur.get("s4_supply"), cur.get("s5_liquidity_vol")
    rows = [
        {"factor": "물가", "now": f"근원 PCE {pce12:.2f}% (3개월 연율 {pce3:.2f}%)", "dir": arrow(pce12, f(i3["core_pce_12m"]), 0.05),
         "cons": None if sep_pce is None else f"SEP {yr}년 {sep_pce:.1f}%", "score": word.get(s3, "–"),
         "confirm": "3개월 연율이 12개월보다 계속 낮음" if s3 == 1 else "3개월 연율이 12개월보다 계속 높음" if s3 == -1 else "3개월−12개월 격차가 문턱을 넘음",
         "refute": f"3개월 연율이 SEP 전망({sep_pce}%)보다 0.5%p 이상 높음" if s3 != -1 else "3개월 연율이 12개월보다 낮아짐"},
        {"factor": "고용", "now": f"실업률 {une:.1f}%, 비농업 고용 3개월 평균 {f(g['nfp_3m_avg_k']):.0f}천 명", "dir": arrow(une, f(g3["unrate"]), 0.05),
         "cons": None if sep_une is None else f"SEP {yr}년 실업률 {sep_une:.1f}%", "score": word.get(s2, "–"),
         "confirm": "실업률 3개월 평균 상승, 고용 증가 둔화" if s2 == 1 else "실업률 하락, 고용 증가 가속" if s2 == -1 else "고용 격차나 실업률 변화가 문턱을 넘음",
         "refute": "실업률이 SEP 전망 아래로 떨어짐" if s2 == 1 else "실업률이 SEP 전망보다 0.3%p 이상 높아짐"},
        {"factor": "성장", "now": f"ISM 제조업 {f(ism[-1]['pmi']):.1f} ({ism[-1]['ref_month']})" if ism else "ISM 자료 없음 (팀 파이프라인 ism_manufacturing.csv가 비어 있음)",
         "dir": arrow(f(ism[-1]["pmi"]), f(ism[-4]["pmi"]), 0.5) if len(ism) >= 4 else None,
         "cons": None if not E.get("gdp", {}).get(yr) else f"SEP {yr}년 GDP {E['gdp'][yr]:.1f}%", "score": "5필라에 따로 없음 (성장·고용에 포함)",
         "confirm": "ISM 50 위 유지 = 인하 늦출 근거", "refute": "ISM 48 아래로 하락"},
        {"factor": "금융여건", "now": f"MOVE 월 최고 {f(lq['move_month_peak']):.0f} (3년 {f(lq['vol_pct']):.0f}%분위), VIX {f(lq['vix_pct']):.0f}%분위, Baa 스프레드 {f(lq['baa_spread']):.2f}%",
         "dir": None, "cons": None, "score": word.get(s5, "–").replace("채권 강세 쪽", "안정").replace("채권 약세 쪽", "스트레스"),
         "confirm": "변동성·스프레드 3년 90%분위 아래", "refute": "MOVE·VIX·스프레드 중 2개가 90%분위 위"},
        {"factor": "재정·국채 공급", "now": f"장기물 순발행 가속 {f(su['supply_accel_pct']) * 100:+.0f}%, 10년 기간 프리미엄 {f(su['tp10']):.2f}%",
         "dir": None, "cons": None, "score": {1: "공급 가속 (+1, 스티프닝)", 0: "중립 (0)", -1: "공급 둔화 (−1)"}.get(s4, "–"),
         "confirm": "다음 분기 재무부 발행 계획에서 장기물 비중 유지", "refute": "기간 프리미엄 3개월 +25bp 이상 상승"}]
    # 현재 진단: 두 목표가 연준 전망보다 위/아래
    dp = None if sep_pce is None else pce12 - sep_pce
    du = None if sep_une is None else une - sep_une
    if dp is not None and du is not None:
        worry = "물가" if dp > 0 and dp >= du else "고용" if du > 0.2 else "양쪽 균형"
        diag = (f"근원 물가는 연준 {yr}년 전망보다 {dp:+.1f}%p, 실업률은 {du:+.1f}%p" +
                (" → 물가 쪽 걱정이 우위" if worry == "물가" else " → 고용 쪽 걱정이 우위" if worry == "고용" else " → 양쪽이 균형"))
    else:
        worry, diag = None, "SEP 전망이 없어 진단을 만들지 못했습니다"
    # 주의할 점
    flags = []
    if sep_pce is not None and pce3 - sep_pce >= 0.5:
        flags.append(f"근원 PCE 3개월 연율({pce3:.2f}%)이 연준 전망({sep_pce:.1f}%)보다 0.5%p 이상 높음")
    if du is not None and du >= 0.3:
        flags.append(f"실업률이 연준 전망보다 {du:.1f}%p 높음")
    if ST.get("distrust"):
        flags.append("기조는 매파인데 시장은 연준보다 인하를 더 가격 (시장이 연준을 안 믿는 중)")
    if ST.get("shift_alert"):
        flags.append(f"기조 점수가 지난달보다 {ST['chg']:+.2f} 움직임 (기조 전환 가능성)")
    if lq.get("funding_alarm") not in (None, "", "0"):
        flags.append("단기자금시장 경보 (SOFR−IORB 20일)")
    sig = vc["signal"]
    if ST["score"] is not None and ((ST["score"] >= 0.3 and sig["code"] > 0) or (ST["score"] <= -0.3 and sig["code"] < 0)):
        flags.append("우리 듀레이션 신호가 연준 기조와 반대 방향")
    head = (f"연준은 {ST['grade']}(기조 {ST['score']:+.2f})이고, 1년 뒤 기준 우리 경로는 선물보다 {vc['gap_b']:+.0f}bp → {sig['ko']}.")
    if ST.get("gap_a") is not None:
        head += f" 시장은 점도표보다 {abs(ST['gap_a']):.0f}bp {'높게' if ST['gap_a'] < 0 else '낮게'} 가격 중."
    return {"asof": asof, "headline": head, "diagnosis": diag, "worry": worry, "factors": rows, "flags": flags,
            "three": {"consensus": V["consensus"], "tilt": vc["tilt"], "ours": vc["ours"], "futures": V["futures"], "gap_b": vc["gap_b"],
                      "signal": sig["ko"], "p2": vc["p2"], "p3": vc["p3"], "cap": V["cap"]}}


def meeting_scorecard(policy, sep):
    """회의 리뷰 ⑤: 회의가 있던 달에 적용 중이던 우리 기울기 방향과 회의 당일 2년 금리 방향이 같았나 (○/×).
    기울기가 0이면 채점하지 않는다(–). 점도표 분포(SEP 그림 2)도 회의 리뷰에 붙인다."""
    fm = policy.get("fomc")
    if not fm:
        return
    tilt_by_month = {x["apply_month"]: -TILT_BP_PER_PT * (x["s2"] + x["s3"]) / 2 + 0.0 for x in _sig_rows(None, None)}
    for m in fm["meetings"]:
        t = tilt_by_month.get(m["date"][:7])
        m["tilt"] = t
        m["ox"] = None if t in (None, 0) or m["d_y2"] in (None, 0) else ("○" if (t > 0) == (m["d_y2"] > 0) else "×")
    scored = [m for m in fm["meetings"] if m["ox"]]
    fm["ox_hits"], fm["ox_n"] = sum(m["ox"] == "○" for m in scored), len(scored)
    if sep and sep.get("dots"):
        fm["dots"] = {"date": sep["date"], "url": sep["url"], "dist": sep["dots"], "median": sep.get("median"),
                      "prev_median": sep.get("prev_median"), "prev_label": sep.get("prev_label")}


def macro_block(I, grid, cols, events):
    pol, gro, inf = I["pol_s"], I["gro_s"], I["inf_s"]
    gd, idt, pd = I["gro_d"], I["inf_d"], I["pol_d"]
    asof = grid[-1]

    def nxt(word):
        for e in events:
            if e["date"] >= asof and word in e["title"]:
                return e["date"]
        return None

    gc, ic = gro["current"], inf["current"]
    ge, ie = gro["events"][-1], inf["events"][-1]
    gm = gd["monthly"]
    ur_prev = gm["unrate"][-2] if len(gm["unrate"]) > 1 else None
    mich = [v for v in idt["monthly"]["mich_1y"] if v is not None]
    wk = gd["weekly"]
    proxy = gro.get("event_source") == "proxy"
    releases = [
        {"key": "nfp", "label": "Nonfarm Payrolls", "ko": "비농업 고용 증감", "unit": "천 명", "digits": 0, "ref": gc["ref"],
         "release": gc["release"], "actual": gc["nfp"], "prev": gm["payems_chg"][-2], "exp": ge["exp"], "sur": ge["sur"],
         "d2": ge["d2"], "d10": ge["d10"], "next": nxt("고용보고서"), "dir": 1},
        {"key": "ur", "label": "Unemployment Rate", "ko": "실업률", "unit": "%", "digits": 1, "ref": gc["ref"],
         "release": gc["release"], "actual": gc["ur"], "prev": ur_prev, "exp": None, "sur": None, "d2": None, "d10": None,
         "next": nxt("고용보고서"), "dir": -1},
        {"key": "claims", "label": "Initial Jobless Claims", "ko": "신규 실업수당 청구", "unit": "천 건", "digits": 0,
         "ref": wk["dates"][-1], "release": None, "actual": wk["icsa_k"][-1], "prev": wk["icsa_k"][-2], "exp": None,
         "sur": None, "d2": None, "d10": None, "next": nxt("신규 실업수당"), "dir": -1,
         "note": f"4주 평균 {wk['ic4wsa_k'][-1]:.0f}"},
        {"key": "cpi", "label": "Core CPI m/m", "ko": "근원 소비자물가 전월비", "unit": "%", "digits": 2, "ref": ic["cpi"]["ref"],
         "release": ic["cpi"]["release"], "actual": ic["cpi"]["mom"], "prev": inf["events"][-2]["mom"], "exp": ie["exp"],
         "sur": ie["sur"], "d2": ie["d2"], "d10": ie["d10"], "next": nxt("CPI"), "dir": 1,
         "note": f"3개월 연율 {ic['cpi']['ann3']:.1f}%" if ic["cpi"].get("ann3") is not None else None},
        {"key": "pce", "label": "Core PCE y/y", "ko": "근원 PCE 물가 전년비", "unit": "%", "digits": 2, "ref": ic["pce_ref"],
         "release": ic["pce_release"], "actual": ic["yoy"], "prev": None, "exp": None, "sur": None, "d2": None, "d10": None,
         "next": nxt("PCE"), "dir": 1, "note": f"3개월 연율 {ic['ann3']:.1f}%"},
        {"key": "mich", "label": "UMich 1y Inflation Expectations", "ko": "미시간대 1년 기대 인플레이션", "unit": "%", "digits": 1,
         "ref": None, "release": None, "actual": mich[-1] if mich else None, "prev": mich[-2] if len(mich) > 1 else None,
         "exp": None, "sur": None, "d2": None, "d10": None, "next": None, "dir": 1},
    ]
    pce_prev = [v for v in idt["monthly"]["core_pce_12m"] if v is not None]
    releases[4]["prev"] = pce_prev[-2] if len(pce_prev) > 1 else None

    hist = {"nfp": [{"date": e["date"], "ref": e["ref"], "sur": e["sur"], "d2": e["d2"], "d10": e["d10"]} for e in gro["events"][-18:]],
            "cpi": [{"date": e["date"], "ref": e["ref"], "sur": r(e["sur"] * 100, 1), "d2": e["d2"], "d10": e["d10"]}
                    for e in inf["events"][-18:]]}

    # 월별 지표 표 (기준월 기준). 색은 각 열의 지난 60개월 대비 위치(z-score)에 방향을 곱해 정한다.
    gdates = gm["dates"]
    im = idt["monthly"]

    def month_last(series_dates, vals, ym):
        out = None
        for d0, v in zip(series_dates, vals):
            if d0[:7] == ym and v is not None:
                out = v
        return out

    claims_m = {}
    for d0, v in zip(wk["dates"], wk["ic4wsa_k"]):
        if v is not None:
            claims_m[d0[:7]] = v
    liq = I["liq_d"]["daily"]
    spec = [("nfp", "고용 증감", "고용", "천 명", 0, 1, lambda ym, k: gm["payems_chg"][k]),
            ("ur", "실업률", "고용", "%", 1, -1, lambda ym, k: gm["unrate"][k]),
            ("claims", "실업수당 4주", "고용", "천 건", 0, -1, lambda ym, k: claims_m.get(ym)),
            ("cpi_yoy", "근원 CPI 전년비", "물가", "%", 2, 1, lambda ym, k: im["core_cpi_12m"][k]),
            ("cpi_3m", "근원 CPI 3개월", "물가", "%", 2, 1, lambda ym, k: im["core_cpi_3m_ann"][k]),
            ("pce_yoy", "근원 PCE 전년비", "물가", "%", 2, 1, lambda ym, k: im["core_pce_12m"][k]),
            ("mich", "미시간 1년 기대", "물가", "%", 1, 1, lambda ym, k: im["mich_1y"][k]),
            ("ff", "정책금리 상단", "금리", "%", 2, 1, lambda ym, k: month_last(pd["daily"]["dates"], pd["daily"]["upper"], ym)),
            ("y2", "2년", "금리", "%", 2, 1, lambda ym, k: month_last(grid, cols["y2"], ym)),
            ("y10", "10년", "금리", "%", 2, 1, lambda ym, k: month_last(grid, cols["y10"], ym)),
            ("s2s10s", "2s10s", "금리", "bp", 0, 1, lambda ym, k: month_last(grid, cols["s2s10s"], ym)),
            ("real10", "10년 실질", "금리", "%", 2, 1, lambda ym, k: month_last(grid, cols["real10"], ym)),
            ("move", "MOVE", "위험", "", 0, 1, lambda ym, k: month_last(liq["dates"], liq["move"], ym))]
    n = len(gdates)
    full = {key: [fn(gdates[k][:7], k) for k in range(n)] for key, *_, fn in spec}
    show = list(range(max(0, n - 24), n))
    heat_rows = []
    for k in reversed(show):
        cells = {}
        for key, _, _, _, dg, direction, _ in spec:
            v = full[key][k]
            hist_w = [x for x in full[key][max(0, k - 60):k] if x is not None]
            z = zscore(hist_w, v) if len(hist_w) >= 24 else None
            cells[key] = [r(v, 3), None if z is None else r(z * direction, 2)]
        heat_rows.append({"month": gdates[k][:7], "cells": cells})
    heat = {"cols": [{"key": k, "label": lab, "group": g, "unit": u, "digits": dg} for k, lab, g, u, dg, _, _ in spec],
            "rows": heat_rows}

    # 정책금리 경로
    fut, cur = pol["futures"], pol["current"]
    up = pd["daily"]["upper"]
    last_change = None
    for k in range(len(up) - 1, 0, -1):
        if up[k] is not None and up[k - 1] is not None and up[k] != up[k - 1]:
            last_change = {"date": pd["daily"]["dates"][k], "bp": r((up[k] - up[k - 1]) * 100, 0)}
            break
    nxt_fomc = next((f for f in pd["fomc"] if f["date"] > asof), None)
    policy = {"asof": fut.get("date"), "upper": cur["upper"], "lower": cur["lower"], "effr": cur["effr"],
              "meetings": fut.get("meetings") or [], "snaps": fut.get("snaps") or [],
              "peak": fut.get("peak"), "peak_month": fut.get("peak_month"), "dots": cur.get("dots"), "lr": cur.get("lr"),
              "sep": cur.get("sep"), "gap_bp": cur.get("gap"), "stance_bp": cur.get("stance"), "regime": cur.get("regime"),
              "last_change": last_change,
              "next": None if not nxt_fomc else {"date": nxt_fomc["date"], "sep": bool(nxt_fomc.get("sep")),
                                                 "days": (date.fromisoformat(nxt_fomc["date"]) - date.fromisoformat(asof)).days}}
    policy["fomc"] = fomc_block(I["extra"].get("fomc"), grid, cols)
    policy["sme"] = sme_block(I["extra"].get("sme"), policy, asof)
    policy["tone"] = tone_block(read_json(RAW / "fed_tone.json", {}) or {}, I["extra"].get("fomc") or [], asof)
    policy["view"] = view_block(policy, I["score"], gro, inf, asof)
    policy["stance"] = stance_block(policy, I["extra"].get("sep"), read_json(RAW / "fed_tone.json", {}) or {}, asof)
    policy["brief"] = brief_block(policy, I["extra"].get("sep"), I["score"], asof)
    meeting_scorecard(policy, I["extra"].get("sep"))
    return {"releases": releases, "exp_is_proxy": proxy, "hist": hist, "heat": heat, "policy": policy,
            "infl": {"core_pce_yoy": ic["yoy"], "core_pce_3m": ic["ann3"], "core_pce_6m": ic["ann6"], "pce_ref": ic["pce_ref"],
                     "cpi_3m": ic["cpi"].get("ann3"), "cpi_ref": ic["cpi"]["ref"], "mich": mich[-1] if mich else None}}


# ───────────────────────── 수급·펀딩 ─────────────────────────
def flows_block(I, grid, cols):
    sup, sd, liq = I["sup_s"], I["sup_d"], I["liq_d"]
    ex = I["extra"]
    auc = sd["auctions"]
    size = {(d0, t): (o, c) for d0, t, o, c in zip(auc["auction_date"], auc["tenor"], auc["offering_bn"], auc["coupon"])}
    recent = []
    for e in sup["events"][-14:][::-1]:
        o, c = size.get((e["date"], e["tenor"]), (None, None))
        recent.append({"date": e["date"], "tenor": e["tenor"], "reopen": e["reopen"], "size_bn": o, "coupon": c,
                       "hy": e["hy"], "btc": e["btc"], "btc_avg": e["avg"], "btc_gap": r(e["btc"] - e["avg"], 2) if e["avg"] else None,
                       "dealer": e["dealer"], "dealer_dev": e["dealer_dev"], "d10": e["d10"], "d30": e["d30"]})
    up = [x for x in (ex.get("upcoming") or [])]
    # 최근 입찰 수요: 응찰률이 평소(같은 만기 직전 입찰들의 평균)보다 높았나 낮았나를 최근 3건 평균으로 본다.
    # 약함·강함의 문턱은 정해 둔 숫자가 아니라 2010년 이후 그 값의 아래·위 4분의 1 지점이다.
    gaps = [e["btc"] - e["avg"] for e in sup["events"] if e.get("btc") is not None and e.get("avg")]
    demand = None
    if len(gaps) >= 30:
        roll = sorted(sum(gaps[k - 2:k + 1]) / 3 for k in range(2, len(gaps)))
        now3 = sum(gaps[-3:]) / 3
        q25, q75 = roll[int(0.25 * (len(roll) - 1))], roll[int(0.75 * (len(roll) - 1))]
        dd = [e["dealer_dev"] for e in sup["events"][-3:] if e.get("dealer_dev") is not None]
        demand = {"n": 3, "avg_gap": r(now3, 3), "q25": r(q25, 3), "q75": r(q75, 3),
                  "pct_hist": r(sum(1 for x in roll if x <= now3) / len(roll) * 100, 0),
                  "dealer_dev": r(sum(dd) / len(dd), 1) if dd else None,
                  "state": "weak" if now3 <= q25 else "strong" if now3 >= q75 else "normal", "history_n": len(gaps)}
    m = sd["monthly"]
    k0 = max(0, len(m["dates"]) - 36)
    issuance = {"months": [d0[:7] for d0 in m["dates"][k0:]], "coupon_net_bn": m["coupon_net_bn"][k0:],
                "long_net_bn": m["long_net_bn"][k0:], "bill_share_pct": m["bill_share_pct"][k0:],
                "bills_chg_bn": [None if a is None or b is None else r(a - b, 1)
                                 for a, b in zip(m["bills_bn"][k0:], m["bills_bn"][k0 - 1:-1])] if k0 > 0 else None,
                "outstanding": {k: m[k][-1] for k in ("bills_bn", "notes_bn", "bonds_bn", "tips_bn", "frn_bn", "marketable_bn")},
                "asof": m["dates"][-1]}
    w = sd["weekly"]
    soma = {"asof": w["dates"][-1], "total_bn": w["soma_total_bn"][-1],
            "chg_3m_bn": r(w["soma_total_bn"][-1] - w["soma_total_bn"][-14], 1) if len(w["dates"]) > 14 else None,
            "chg_1y_bn": r(w["soma_total_bn"][-1] - w["soma_total_bn"][-53], 1) if len(w["dates"]) > 53 else None,
            "dates": w["dates"][-260:], "total": w["soma_total_bn"][-260:]}

    cftc = []
    for c in ex.get("cftc") or []:
        if not c["d"]:
            continue
        lo = idx_on_or_before(c["d"], back(c["d"][-1], years=3)) + 1
        row = {"key": c["key"], "name": c["name"], "date": c["d"][-1], "oi_k": r(c["oi"][-1] / 1000, 0)}
        for who in ("am", "lev", "dealer"):
            v = c[who]
            row[who] = {"net_k": r(v[-1] / 1000, 0), "w1_k": r((v[-1] - v[-2]) / 1000, 0) if len(v) > 1 else None,
                        "m1_k": r((v[-1] - v[-5]) / 1000, 0) if len(v) > 5 else None,
                        "pct3y": r(pctile(v[lo:], v[-1]), 0), "share_oi": r(v[-1] / c["oi"][-1] * 100, 1) if c["oi"][-1] else None}
        row["dates"] = c["d"][lo:]
        row["am_s"] = [r(x / 1000, 0) for x in c["am"][lo:]]
        row["lev_s"] = [r(x / 1000, 0) for x in c["lev"][lo:]]
        cftc.append(row)

    ld, lw = liq["daily"], liq["weekly"]
    fund_rows = []
    for key, label, unit, scale, pc in [("sofr", "SOFR", "%", 100, False), ("effr", "EFFR (실효 연방기금금리)", "%", 100, False),
                                        ("reserve_rate", "IORB (지급준비금 이자율)", "%", 100, False),
                                        ("sofr_minus_rr_bp", "SOFR − IORB", "bp", 1, False),
                                        ("effr_minus_rr_bp", "EFFR − IORB", "bp", 1, False),
                                        ("rrp_bn", "역레포 잔액 (ON RRP)", "십억 달러", 1, False)]:
        s = summarize(ld["dates"], ld[key], scale)
        if s:
            fund_rows.append({"key": key, "label": label, "unit": unit, "level": s["level"], "date": s["date"],
                              "d1": s["chg"]["d1"], "w1": s["chg"]["w1"], "m1": s["chg"]["m1"], "y1": s["chg"]["y1"],
                              "pct3y": s["pct3y"], "chg_unit": "bp" if unit in ("%", "bp") else unit})
    for key, label in [("reserves_bn", "지급준비금"), ("tga_bn", "재무부 일반계정 (TGA)")]:
        s = summarize(lw["dates"], lw[key], 1)
        if s:
            fund_rows.append({"key": key, "label": label, "unit": "십억 달러", "level": s["level"], "date": s["date"],
                              "d1": None, "w1": s["chg"]["d1"], "m1": s["chg"]["m1"], "y1": s["chg"]["y1"],
                              "pct3y": s["pct3y"], "chg_unit": "십억 달러"})
    lc = I["liq_s"]["current"]
    off = lc.get("mtd") or lc.get("official") or {}
    th = I["liq_s"]["thresholds"]
    funding = {"rows": fund_rows, "alarm_bp": th.get("fund"), "alarm_days": th.get("fund_days"),
               "fund_avg_bp": off.get("fund"), "alarm_on": bool(off.get("alarm"))}
    return {"auctions": {"upcoming": up, "recent": recent, "tail_note": "발행 전 거래(WI) 금리가 없어 tail은 계산하지 못합니다"},
            "demand": demand, "issuance": issuance, "soma": soma, "cftc": cftc, "funding": funding}


# ───────────────────────── 크레딧·소버린 ─────────────────────────
def credit_block(I, grid, cols):
    ex = I["extra"]
    fd = ex.get("fred_daily") or {}
    ladder = []
    for key, label, grp in [("oas_ig", "투자등급 전체 (IG)", "IG"), ("oas_aaa", "AAA", "IG"), ("oas_aa", "AA", "IG"),
                            ("oas_a", "A", "IG"), ("oas_bbb", "BBB", "IG"), ("oas_hy", "하이일드 전체 (HY)", "HY"),
                            ("oas_bb", "BB", "HY"), ("oas_b", "B", "HY"), ("oas_ccc", "CCC 이하", "HY"),
                            ("oas_em", "신흥국 회사채 (달러 표시)", "EM")]:
        p = fd.get(key)
        if not p:
            continue
        vals = [v * 100 for v in p["v"]]
        s = summarize(p["d"], vals, 1)
        ladder.append({"key": key, "label": label, "group": grp, "level": r(s["level"], 0), "date": s["date"],
                       "w1": s["chg"]["w1"], "m1": s["chg"]["m1"], "m3": s["chg"]["m3"], "y1": s["chg"]["y1"],
                       "pct3y": s["pct3y"], "lo3y": r(s["lo3y"], 0), "hi3y": r(s["hi3y"], 0), "spark": spark(vals)})
    mat = []
    for key, label in [("oas_ig_1_3", "1–3년"), ("oas_ig_3_5", "3–5년"), ("oas_ig_5_7", "5–7년"), ("oas_ig_7_10", "7–10년"),
                       ("oas_ig_10_15", "10–15년"), ("oas_ig_15p", "15년+")]:
        p = fd.get(key)
        if not p:
            continue
        vals = [v * 100 for v in p["v"]]
        s = summarize(p["d"], vals, 1)
        mat.append({"label": label, "now": r(s["level"], 0), "m1": r(s["level"] - (s["chg"]["m1"] or 0), 0),
                    "y1": None if s["chg"]["y1"] is None else r(s["level"] - s["chg"]["y1"], 0), "pct3y": s["pct3y"]})
    quality = []
    for a, b, label in [("oas_bbb", "oas_a", "BBB − A"), ("oas_bb", "oas_bbb", "BB − BBB (투자등급 경계)"),
                        ("oas_ccc", "oas_bb", "CCC − BB"), ("oas_hy", "oas_ig", "HY − IG")]:
        if a in fd and b in fd:
            m = dict(zip(fd[b]["d"], fd[b]["v"]))
            ds = [d0 for d0 in fd[a]["d"] if d0 in m]
            vals = [(v - m[d0]) * 100 for d0, v in zip(fd[a]["d"], fd[a]["v"]) if d0 in m]
            s = summarize(ds, vals, 1)
            quality.append({"label": label, "level": r(s["level"], 0), "m1": s["chg"]["m1"], "y1": s["chg"]["y1"],
                            "pct3y": s["pct3y"], "spark": spark(vals)})

    # 국가 스코어카드 (OECD 월별 자료, FRED 경유)
    intl = ex.get("intl") or {}
    asof = grid[-1]
    stale_before = back(asof, months=5)
    sov = []
    us10 = (intl.get("series") or {}).get("US", {}).get("y10")
    us_map = dict(zip(us10["d"], us10["v"])) if us10 else {}
    for c in intl.get("countries") or []:
        row = (intl.get("series") or {}).get(c["code"]) or {}
        y, r3, un, debt = row.get("y10"), row.get("r3m"), row.get("unemp"), row.get("debt_gdp")
        if c["code"] == "US":      # OECD 실업률은 미국만 오래 끊겨 있어 BLS 값(UNRATE)으로 바꾼다
            gm = I["gro_d"]["monthly"]
            v, k = last_valid(gm["unrate"])
            un = {"d": [gm["dates"][k]], "v": [v]}
        out = {"code": c["code"], "name": c["name"]}
        if y:
            out.update({"y10": r(y["v"][-1], 2), "y10_date": y["d"][-1][:7],
                        "y10_m1": r((y["v"][-1] - y["v"][-2]) * 100, 0) if len(y["v"]) > 1 else None,
                        "y10_y1": r((y["v"][-1] - y["v"][-13]) * 100, 0) if len(y["v"]) > 13 else None,
                        "vs_us": None if y["d"][-1] not in us_map else r((y["v"][-1] - us_map[y["d"][-1]]) * 100, 0),
                        "spark": [r(v, 2) for v in y["v"][-36:]]})
        if r3 and r3["d"][-1] >= stale_before:
            out.update({"r3m": r(r3["v"][-1], 2), "r3m_date": r3["d"][-1][:7]})
            if y and y["d"][-1] == r3["d"][-1]:
                out["slope"] = r((y["v"][-1] - r3["v"][-1]) * 100, 0)
        if un and un["d"][-1] >= stale_before:
            out.update({"unemp": r(un["v"][-1], 1), "unemp_date": un["d"][-1][:7]})
        if debt:
            out.update({"debt_gdp": r(debt["v"][-1], 0), "debt_year": debt["d"][-1][:4]})
        sov.append(out)

    # 종합: 재정·경제 여건을 한 칸으로. 네 지표 모두 낮을수록 좋다고 보고, 나라들 안에서의 순위를 0~100점으로 바꾼다.
    # (순위를 쓰는 까닭: 일본의 정부부채처럼 한 나라 값이 튀어도 나머지 나라의 차이가 묻히지 않는다)
    # 세 갈래를 같은 무게로 평균한다: 재정(정부부채), 경제(실업률), 시장(10년 금리 수준과 1년 변화의 평균).
    # 금리 지표 둘을 따로 세면 시장 쪽이 절반을 차지하므로 하나로 묶었다.
    parts = [("debt_gdp", "정부부채"), ("unemp", "실업률"), ("y10", "10년 금리"), ("y10_y1", "금리 1년 변화")]
    for key, _ in parts:
        have = sorted((x[key], k) for k, x in enumerate(sov) if x.get(key) is not None)
        n = len(have)
        if n < 3:
            continue
        for pos, (v, k) in enumerate(have):
            same = [q for q, (v2, _) in enumerate(have) if v2 == v]            # 같은 값이면 평균 순위
            rank = sum(same) / len(same)
            sov[k].setdefault("score_parts", {})[key] = round((1 - rank / (n - 1)) * 100)
    for x in sov:
        sp = x.get("score_parts") or {}
        mk = [sp[k] for k in ("y10", "y10_y1") if k in sp]
        pillars = {"재정": sp.get("debt_gdp"), "경제": sp.get("unemp"), "시장": round(sum(mk) / len(mk)) if mk else None}
        if all(v is not None for v in pillars.values()):
            x["pillars"] = pillars
            x["score"] = round(sum(pillars.values()) / 3)
            x["verdict"] = "good" if x["score"] >= 60 else "bad" if x["score"] < 40 else "mid"
    sov_parts = [{"key": k, "label": lab} for k, lab in parts]

    ratings, rpath = [], DESK / "data" / "ratings.csv"
    if rpath.exists():
        for x in csv.DictReader(io.StringIO(rpath.read_text(encoding="utf-8-sig"))):
            if (x.get("rating") or "").strip():
                ratings.append({k: (v or "").strip() for k, v in x.items()})
    base = fd.get("oas_ig") or fd.get("oas_hy")
    series = None
    if base:
        cgrid = base["d"]
        series = {"dates": cgrid, "cols": {k: [None if v is None else r(v * 100, 1) for v in align(fd[k], cgrid)]
                                             for k in fd if k.startswith("oas_")}}
    return {"ladder": ladder, "maturity": mat, "quality": quality, "sovereign": sov, "sov_parts": sov_parts, "ratings": ratings, "series": series,
            "oas_from": fd.get("oas_ig", {}).get("d", [None])[0]}


# ───────────────────────── 한국 ─────────────────────────
def korea_block(I, us_grid, us_cols):
    K = I["korea"]
    if K.get("status") != "ok":
        return {"status": K.get("status", "no_key"), "message": K.get("message")}
    D = K["daily"]
    base = D.get("ktb10") or D.get("ktb3")
    grid = [d0 for d0 in base["d"] if d0 >= START]
    ys = {}
    tenors = []
    for name, yrs, key in KR_TEN:
        if key in D:
            ys[name] = align(D[key], grid)
            tenors.append((name, yrs))
    out = {"status": "ok", "source": K.get("source"), "generated": K.get("generated")}
    out.update(market_block(grid, ys, tenors))
    cols = {}
    for key in ("cd91", "call", "kofr", "base", "corp_aa", "corp_bbb", "usdkrw", "msb91"):
        if key in D:
            cols[key] = align(D[key], grid)
    g = lambda t: ys.get(t)
    us10 = dict(zip(us_grid, us_cols["y10"]))
    us2 = dict(zip(us_grid, us_cols["y2"]))
    us3m = dict(zip(us_grid, us_cols["y3m"]))
    if g("3Y") and g("10Y"):
        cols["kr3s10s"] = combo(g("10Y"), g("3Y"), f=lambda a, b: (a - b) * 100)
    if g("10Y") and g("30Y"):
        cols["kr10s30s"] = combo(g("30Y"), g("10Y"), f=lambda a, b: (a - b) * 100)
    if g("10Y"):
        cols["us_kr_10y"] = [None if (a is None or us10.get(d0) is None) else (us10[d0] - a) * 100 for d0, a in zip(grid, g("10Y"))]
    if g("3Y") and "base" in cols:
        cols["kr3y_base"] = combo(g("3Y"), cols["base"], f=lambda a, b: (a - b) * 100)
    if g("3Y") and "corp_aa" in cols:
        cols["kr_aa_spread"] = combo(cols["corp_aa"], g("3Y"), f=lambda a, b: (a - b) * 100)
    if g("3Y") and "corp_bbb" in cols:
        cols["kr_bbb_spread"] = combo(cols["corp_bbb"], g("3Y"), f=lambda a, b: (a - b) * 100)
    if "cd91" in cols:        # 금리차로 본 환헤지 비용 근사 (통화스왑 베이시스는 빠져 있다)
        cols["hedge_3m"] = [None if (a is None or us3m.get(d0) is None) else (us3m[d0] - a) for d0, a in zip(grid, cols["cd91"])]
    rows = []
    for key, label, grp, unit, scale in [("kr3s10s", "국고 3s10s", "금리", "bp", 1), ("kr10s30s", "국고 10s30s", "금리", "bp", 1),
                                         ("us_kr_10y", "미국 10년 − 한국 10년", "금리", "bp", 1),
                                         ("kr3y_base", "국고 3년 − 기준금리", "금리", "bp", 1),
                                         ("kr_aa_spread", "회사채 AA- 3년 − 국고 3년", "크레딧", "bp", 1),
                                         ("kr_bbb_spread", "회사채 BBB- 3년 − 국고 3년", "크레딧", "bp", 1),
                                         ("hedge_3m", "미국 3개월 − CD 91일 (헤지 비용 근사)", "펀딩", "%", 100)]:
        if key in cols:
            s = summarize(grid, cols[key], scale)
            if s:
                rows.append(spread_row(key, label, grp, unit, "KR", s, cols[key]))
    out["spreads"] = rows
    bs = cols.get("base")
    if bs:
        v, k = last_valid(bs)
        last_change = None
        for j in range(k, 0, -1):
            if bs[j] is not None and bs[j - 1] is not None and bs[j] != bs[j - 1]:
                last_change = {"date": grid[j], "bp": r((bs[j] - bs[j - 1]) * 100, 0)}
                break
        out["bok"] = {"base": v, "date": grid[k], "last_change": last_change,
                      "cd91": last_valid(cols["cd91"])[0] if "cd91" in cols else None,
                      "call": last_valid(cols["call"])[0] if "call" in cols else None,
                      "ktb3": last_valid(g("3Y"))[0] if g("3Y") else None}
    cpi = (K.get("monthly") or {}).get("cpi")
    if cpi and len(cpi["v"]) > 12:
        out["cpi_yoy"] = r((cpi["v"][-1] / cpi["v"][-13] - 1) * 100, 2)
        out["cpi_date"] = cpi["d"][-1][:7]
    out["series"] = {"dates": grid, "cols": {k: [r(x, 3) for x in v] for k, v in {**{f"y_{t}": ys[t] for t in ys}, **cols}.items()}}
    if "usdkrw" in cols:
        s = summarize(grid, cols["usdkrw"], 1, pct_change=True)
        out["usdkrw"] = s
    return out


def spread_row(key, label, group, unit, region, s, vals):
    return {"key": key, "label": label, "group": group, "unit": unit, "region": region, "level": s["level"], "date": s["date"],
            "d1": s["chg"]["d1"], "w1": s["chg"]["w1"], "m1": s["chg"]["m1"], "m3": s["chg"]["m3"], "y1": s["chg"]["y1"],
            "z3y": s["z3y"], "pct3y": s["pct3y"], "lo3y": s["lo3y"], "hi3y": s["hi3y"], "spark": spark(vals)}


# ───────────────────────── 조립 ─────────────────────────
def main():
    I = load_inputs()
    U = I["U"]
    i0 = idx_on_or_before(U["dates"], START)
    if U["dates"][i0] != START:
        i0 += 1
    grid = U["dates"][i0:]
    asof = grid[-1]
    log(f"기준일 {asof}")
    ys_full = {t: U["yields"][t] for t, _ in TEN}                 # 1990년부터 (통계 창에 쓴다)
    ys = {t: U["yields"][t][i0:] for t, _ in TEN}
    ex = I["extra"]
    fd = ex.get("fred_daily") or {}
    yh = ex.get("yahoo") or {}
    liq, inf, sup = I["liq_d"]["daily"], I["inf_d"]["daily"], I["sup_d"]["daily"]

    def from_section(sec, key):
        return align({"d": sec["dates"], "v": sec[key]}, grid)

    cols = {
        "y3m": ys["3M"], "y2": ys["2Y"], "y5": ys["5Y"], "y10": ys["10Y"], "y30": ys["30Y"],
        "s2s10s": combo(ys["10Y"], ys["2Y"], f=lambda a, b: (a - b) * 100),
        "s5s30s": combo(ys["30Y"], ys["5Y"], f=lambda a, b: (a - b) * 100),
        "s2s30s": combo(ys["30Y"], ys["2Y"], f=lambda a, b: (a - b) * 100),
        "s3m10y": combo(ys["10Y"], ys["3M"], f=lambda a, b: (a - b) * 100),
        "fly2s5s10s": combo(ys["5Y"], ys["2Y"], ys["10Y"], f=lambda b, a, c: (2 * b - a - c) * 100),
        "fly5s10s30s": combo(ys["10Y"], ys["5Y"], ys["30Y"], f=lambda b, a, c: (2 * b - a - c) * 100),
        "bei10": from_section(inf, "bei_10y"), "f5y5y": from_section(inf, "fwd_5y5y"),
        "bei5": align(fd.get("bei5"), grid), "real10": align(fd.get("real10"), grid), "real5": align(fd.get("real5"), grid),
        "real30": align(fd.get("real30"), grid),
        "tp10": from_section(sup, "acm_tp10"), "tp5": from_section(sup, "acm_tp5"), "tp2": from_section(sup, "acm_tp2"),
        "rn10": from_section(sup, "acm_rn10"),
        "move": from_section(liq, "move"), "vix": from_section(liq, "vix"),
        "sofr": from_section(liq, "sofr"), "effr": from_section(liq, "effr"), "iorb": from_section(liq, "reserve_rate"),
        "sofr_iorb": from_section(liq, "sofr_minus_rr_bp"), "effr_iorb": from_section(liq, "effr_minus_rr_bp"),
        "rrp": from_section(liq, "rrp_bn"),
        "baa": [None if v is None else v * 100 for v in from_section(liq, "baa_spread")],
        "oas_ig": [None if v is None else v * 100 for v in align(fd.get("oas_ig"), grid)],
        "oas_hy": [None if v is None else v * 100 for v in align(fd.get("oas_hy"), grid)],
    }
    xa = {"sp500": align(fd.get("sp500"), grid), "nasdaq": align(fd.get("nasdaq"), grid), "kospi": align(yh.get("kospi"), grid),
          "dxy": align(fd.get("dxy_broad"), grid), "usdkrw": align(fd.get("usdkrw"), grid), "usdjpy": align(fd.get("usdjpy"), grid),
          "eurusd": align(fd.get("eurusd"), grid), "wti": align(fd.get("wti"), grid), "gold": align(yh.get("gold"), grid)}

    # 시장
    us = market_block(grid, ys, TEN)
    for h in us["heat"]:                  # 3년 통계는 화면 시작(2015) 이전 값도 쓸 수 있도록 전체 이력으로 다시 계산
        s = summarize(U["dates"], ys_full[h["tenor"]], 100)
        h.update({k: s[k] for k in ("z3y", "z1y", "pct3y", "lo3y", "hi3y")})
    spreads = []
    for key, label, grp, unit, scale in [
            ("s2s10s", "2s10s", "커브", "bp", 1), ("s5s30s", "5s30s", "커브", "bp", 1), ("s2s30s", "2s30s", "커브", "bp", 1),
            ("s3m10y", "3m10y", "커브", "bp", 1), ("fly2s5s10s", "2s5s10s Fly", "커브", "bp", 1),
            ("fly5s10s30s", "5s10s30s Fly", "커브", "bp", 1),
            ("bei10", "10년 BEI (기대 인플레이션)", "물가·실질", "%", 100), ("f5y5y", "5y5y 선도 BEI", "물가·실질", "%", 100),
            ("real10", "10년 실질금리 (TIPS)", "물가·실질", "%", 100), ("tp10", "10년 기간 프리미엄 (ACM)", "물가·실질", "%", 100),
            ("oas_ig", "투자등급 OAS", "크레딧", "bp", 1), ("oas_hy", "하이일드 OAS", "크레딧", "bp", 1),
            ("baa", "Baa − 10년 국채", "크레딧", "bp", 1),
            ("sofr_iorb", "SOFR − IORB", "펀딩", "bp", 1), ("effr_iorb", "EFFR − IORB", "펀딩", "bp", 1)]:
        s = summarize(grid, cols[key], scale)
        if s:
            spreads.append(spread_row(key, label, grp, unit, "US", s, cols[key]))
        else:
            warn(f"스프레드 {label}: 값이 없음")

    d10 = [None] + [None if (a is None or b is None) else a - b for a, b in zip(ys["10Y"][1:], ys["10Y"][:-1])]
    xasset = []
    for key, label, grp, unit, pc in [("sp500", "S&P 500", "주식", "", True), ("nasdaq", "Nasdaq 종합", "주식", "", True),
                                      ("kospi", "KOSPI", "주식", "", True), ("dxy", "달러 지수 (연준 광의)", "통화", "", True),
                                      ("usdkrw", "원/달러", "통화", "원", True), ("usdjpy", "엔/달러", "통화", "엔", True),
                                      ("eurusd", "달러/유로", "통화", "달러", True), ("wti", "WTI 원유", "원자재", "달러", True),
                                      ("gold", "금 (선물)", "원자재", "달러", True), ("vix", "VIX (주식 변동성)", "변동성", "", False),
                                      ("move", "MOVE (채권 변동성)", "변동성", "", False)]:
        vals = xa.get(key) if key in xa else cols[key]
        s = summarize(grid, vals, 1, pct_change=pc)
        if not s:
            warn(f"크로스에셋 {label}: 값이 없음")
            continue
        f = ffill(vals)
        chg = [None] + [None if (a is None or b is None or b == 0) else (a / b - 1 if pc else a - b) for a, b in zip(f[1:], f[:-1])]
        xasset.append({"key": key, "label": label, "group": grp, "unit": unit, "pct": pc, "level": s["level"], "date": s["date"],
                       "d1": s["chg"]["d1"], "w1": s["chg"]["w1"], "m1": s["chg"]["m1"], "ytd": s["chg"]["ytd"], "y1": s["chg"]["y1"],
                       "pct3y": s["pct3y"], "corr60": r(corr(chg[-60:], d10[-60:]), 2), "spark": spark(vals)})

    # 일정 (연준·BEA·FRED 달력 + 이표채 입찰)
    events = [dict(e, region="US") for e in (ex.get("calendar") or [])]
    for a in ex.get("upcoming") or []:
        if a["type"] == "Bill":
            continue
        kind = "TIPS" if a.get("tips") else "FRN" if a.get("frn") else ""
        size = f" {a['offering_bn'] * 10:,.0f}억 달러" if a.get("offering_bn") else ""
        events.append({"date": a["auction_date"], "time": "13:00", "kind": "입찰", "region": "US", "src": "재무부",
                       "title": f"{a['term'].replace('-Year', '년')} {'리오픈 ' if a['reopening'] else ''}{kind} 입찰{size}".replace("  ", " "),
                       "imp": 2 if a["term"] in ("10-Year", "30-Year", "2-Year", "5-Year") and not kind else 1,
                       "note": "잠정 일정" if a.get("tentative") else ""})
    events.sort(key=lambda e: (e["date"], -e["imp"]))

    log("[종목]")
    bonds = bonds_block(I)
    log("[전략 스크리너]")
    repo = last_valid(cols["sofr"])[0]
    rv = {"screener": screener_block(U["dates"], ys_full, repo)}
    tp_rows = []
    for key, label in [("tp2", "2년"), ("tp5", "5년"), ("tp10", "10년")]:
        s = summarize(grid, cols[key], 100)
        if s:
            tp_rows.append({"key": key, "label": label, "level": s["level"], "date": s["date"], "m1": s["chg"]["m1"],
                            "y1": s["chg"]["y1"], "pct3y": s["pct3y"], "z3y": s["z3y"]})
    rn = summarize(grid, cols["rn10"], 100)
    rv["tp"] = {"rows": tp_rows, "rn10": rn["level"] if rn else None, "source": "뉴욕 연준 ACM 모형"}
    log("[내 북]")
    book = book_block(I)
    rv["backtest"] = {"split": I["score"]["split"], "record": {k: I["score"]["record"][k] for k in ("duration", "slope", "curvature", "months")},
                      "freq": I["score"]["freq"]}
    log("[매크로]")
    macro = macro_block(I, grid, cols, events)
    log("[수급]")
    flows = flows_block(I, grid, cols)
    log("[크레딧]")
    credit = credit_block(I, grid, cols)
    log("[한국]")
    kr = korea_block(I, grid, cols)
    if kr["status"] == "ok":
        flows["fxhedge"] = {"status": "proxy"}
    else:
        flows["fxhedge"] = {"status": "none"}

    sc = I["score"]
    keep = ("decision_date", "apply_month", "s1_policy", "s2_growth", "s3_inflation", "s4_supply", "s5_liquidity_vol",
            "view_level", "view_slope", "view_curvature", "fly_z_3y", "duration_active_yr", "slope_position",
            "curvature_position", "carry_rolldown", "position_ko")
    score = {"asof": sc["asof"], "signals": sc["signals"], "official": {k: sc["official"].get(k) for k in keep},
             "live": {k: sc["live"].get(k) for k in keep + ("month_end", "is_month_end")}, "changes": sc.get("changes"),
             "sections": [{"key": s["key"], "name": s["name"], "short": s["short"], "th": s.get("th_ko"),
                           "official": s["official"], "live": s["live"]} for s in sc["sections"]]}

    status = ex.get("status") or {}
    for k, v in status.items():
        if not v.get("ok"):
            warn(f"수집 실패({k}): 지난번 값을 씀 — {'; '.join(v.get('problems') or [])[:160]}")
    out = {
        "meta": {"generated": now_utc(), "asof": asof, "problems": PROBLEMS, "extra_generated": ex.get("generated"),
                 "korea": kr["status"],
                 "sources": ["미 재무부 (CMT 금리, FedInvest 종가, 입찰)", "FRED", "연준 (일정, 보도자료)", "뉴욕 연준 (SOFR, SOMA, ACM)",
                             "CFTC (TFF 보고서)", "BEA", "ICE BofA 지수 (FRED 경유)", "Yahoo Finance (MOVE, 금, KOSPI, 연방기금 선물)",
                             "한국은행 ECOS"]},
        "us": us, "kr": kr, "spreads": spreads, "xasset": xasset,
        "series": {"dates": grid, "cols": {k: [r(x, 3) for x in v] for k, v in {**{f"y_{t}": ys[t] for t in ys}, **cols, **xa}.items()}},
        "bonds": bonds, "macro": macro, "flows": flows, "rv": rv, "credit": credit, "book": book,
        "events": events, "news": ex.get("news") or [], "score": score,
    }
    path = DESK / "data" / "desk_data.js"
    write_js(path, "DESK", out)
    log(f"저장 {path.name}  {path.stat().st_size / 1e6:.2f}MB  (알림 {len(PROBLEMS)}건)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
