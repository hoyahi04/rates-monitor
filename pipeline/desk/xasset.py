"""크로스에셋 탭 자료: 다른 시장이 미국 국채와 어떤 짝으로 움직이는지 → desk_data.js의 xa

build_data.py가 부른다. 표준 라이브러리만 쓴다.

국면 보드
  자산마다 '짝'을 정해 일별 변화의 상관을 60영업일, 250영업일(약 1년) 창으로 잰다.
  국채 가격 = −(10년 금리 변화)  ← +면 국채 강세. 유가는 10년 BEI, 금은 10년 실질금리 하락과 짝을 짓는다.
  |상관| < 0.2 → 불분명. 60일과 1년이 다른 칸이면 '전환 중'. 이름은 60일 쪽을 따른다.
"""
from common import clean, corr, mean, pctile, r

TH = 0.2            # 국면 경계 (60개 표본의 상관은 우연만으로도 ±0.13쯤 흔들린다)
W_FAST, W_SLOW = 60, 250
SINCE = "2016-01-01"

# key, 이름, 짝 설명, 자산 열, 변화 방식, 짝 열, 짝 부호, (+국면, 톤), (−국면, 톤), (불분명 이름, 톤)
PAIRS = [
    ("sp", "주식 (S&P 500)", "주가 × 국채 가격", "sp500", "pct", "y10", -1,
     ("인플레 주도", "bad"), ("성장 주도 · 국채가 헤지", "good"), ("불분명", "mid")),
    ("vix", "VIX", "VIX × 국채 가격", "vix", "diff", "y10", -1,
     ("공포에 국채 매수", "good"), ("동반 매도", "bad"), ("불분명", "mid")),
    ("dxy", "달러", "달러 × 국채 가격", "dxy", "pct", "y10", -1,
     ("안전자산 주도", "mid"), ("금리차 주도", "mid"), ("불분명", "mid")),
    ("jpy", "엔/달러", "엔/달러 × 국채 가격", "usdjpy", "pct", "y10", -1,
     ("일본발 매도", "bad"), ("금리차 주도", "mid"), ("불분명", "mid")),
    ("wti", "원유 (WTI)", "유가 × 10년 BEI", "wti", "pct", "bei10", 1,
     ("인플레 채널 강함", "bad"), ("역전", "mid"), ("인플레 채널 약함", "mid")),
    ("gold", "금", "금 × 실질금리 하락", "gold", "pct", "real10", -1,
     ("실질금리 연동", "mid"), ("역전", "bad"), ("실질금리와 분리", "bad")),
    ("cu", "구리", "구리 × 국채 가격", "copper", "pct", "y10", -1,
     ("드문 역전", "mid"), ("경기 채널 작동", "mid"), ("경기 채널 약함", "mid")),
    ("move", "MOVE", "MOVE × 국채 가격", "move", "diff", "y10", -1,
     ("랠리형 변동성", "good"), ("매도형 변동성", "bad"), ("불분명", "mid")),
]


def changes(vals, how):
    """연속한 두 영업일 값이 모두 있을 때만 변화를 낸다."""
    out = [None]
    for a, b in zip(vals[:-1], vals[1:]):
        if a is None or b is None or (how == "pct" and a == 0):
            out.append(None)
        else:
            out.append(b / a - 1 if how == "pct" else b - a)
    return out


def rolling(a, b, w, idx):
    return [corr(a[max(0, i - w + 1):i + 1], b[max(0, i - w + 1):i + 1]) if i >= w - 1 else None for i in idx]


def zone(x):
    return None if x is None else ("pos" if x >= TH else "neg" if x <= -TH else "mid")


def regime(p, r60, r250):
    names = {"pos": p[7], "neg": p[8], "mid": p[9]}
    z60, z250 = zone(r60), zone(r250)
    if z60 is None:
        return {"regime": "자료 부족", "tone": "mid", "turn": False}
    lab, tone = names[z60]
    return {"regime": lab, "tone": tone, "turn": z250 is not None and z250 != z60}


def pair_block(p, grid, src):
    a, b = changes(src[p[3]], p[4]), changes(src[p[5]], "diff")
    b = [None if v is None else v * p[6] for v in b]
    n = len(grid)
    last = max((i for i in range(n) if a[i] is not None and b[i] is not None), default=None)
    if last is None:
        return None
    i1m = max(0, last - 21)
    r60, r250 = corr(a[last - W_FAST + 1:last + 1], b[last - W_FAST + 1:last + 1]), corr(a[last - W_SLOW + 1:last + 1], b[last - W_SLOW + 1:last + 1])
    r60_1m = corr(a[i1m - W_FAST + 1:i1m + 1], b[i1m - W_FAST + 1:i1m + 1])
    k0 = next(i for i, d in enumerate(grid) if d >= SINCE)
    idx = list(range(last, k0 - 1, -5))[::-1]                    # 마지막 날에서 5영업일 간격 (2016년부터)
    h60, h250 = rolling(a, b, W_FAST, idx), rolling(a, b, W_SLOW, idx)
    era = lambda lo, hi: corr([a[i] for i in range(n) if lo <= grid[i] < hi], [b[i] for i in range(n) if lo <= grid[i] < hi])
    out = {"key": p[0], "label": p[1], "pair": p[2], "date": grid[last], "r60": r(r60, 2), "r250": r(r250, 2), "r60_1m": r(r60_1m, 2),
           "pre": r(era("2016-01-01", "2022-01-01"), 2), "post": r(era("2022-01-01", "2100-01-01"), 2),
           "hist": {"d": [grid[i] for i in idx], "r60": [r(v, 3) for v in h60], "r250": [r(v, 3) for v in h250]}}
    out.update(regime(p, r60, r250))
    return out


def last_val(vals, upto=None):
    i = (len(vals) if upto is None else upto + 1) - 1
    while i >= 0 and vals[i] is None:
        i -= 1
    return (vals[i], i) if i >= 0 else (None, None)


def ago(vals, i, days):
    v, _ = last_val(vals, max(0, i - days))
    return v


def monthly_pickup(intl):
    """환헤지 후 미 10년 금리 − 자국 10년 금리 (%p). 헤지 비용 ≈ 미국 3개월 − 자국 3개월. OECD 월별."""
    S = (intl or {}).get("series") or {}
    get = lambda c, k: dict(zip(((S.get(c) or {}).get(k) or {}).get("d", []), ((S.get(c) or {}).get(k) or {}).get("v", [])))
    us10, us3 = get("US", "y10"), get("US", "r3m")
    out = {"d": sorted(d for d in us10 if d >= SINCE and d in us3)}
    for c in ("JP", "DE"):
        y, s3 = get(c, "y10"), get(c, "r3m")
        out[c.lower()] = [r(us10[d] - (us3[d] - s3[d]) - y[d], 2) if d in y and d in s3 else None for d in out["d"]]
    return out


def build(grid, src):
    """src: 날짜 격자에 맞춘 열 {sp500, vix, dxy, usdjpy, wti, gold, copper, move, y10, bei10, bei5, real10, intl}"""
    pairs = [x for x in (pair_block(p, grid, src) for p in PAIRS) if x]
    tally = {t: sum(1 for x in pairs if x["tone"] == t) for t in ("good", "bad", "mid")}

    # 주식-채권: 최근 60일 중 '둘 다 손실'(주가↓·금리↑)과 '헤지 성공'(주가↓·금리↓) 날
    ra, dy = changes(src["sp500"], "pct"), changes(src["y10"], "diff")
    pts = [(x, y) for x, y in zip(ra, dy) if x is not None and y is not None][-W_FAST:]
    sb = {"both_loss": sum(1 for x, y in pts if x < 0 and y > 0), "hedge": sum(1 for x, y in pts if x < 0 and y < 0), "n": len(pts)}

    # 변동성 지도: 최근 3년(756영업일) VIX·MOVE, 각각의 80%분위
    vm = [(i, v, m) for i, (v, m) in enumerate(zip(src["vix"], src["move"])) if v is not None and m is not None]
    w3 = vm[-756:]
    q80 = lambda xs: sorted(xs)[int(0.8 * (len(xs) - 1))] if xs else None
    vix_now, move_now = w3[-1][1], w3[-1][2]
    dy10 = changes(src["y10"], "diff")
    rv = []                                            # 10년 금리 20일 실현변동성 (bp, 연율) — MOVE가 끊길 때 대신 쓴다
    for i in range(len(grid)):
        w = clean(dy10[max(0, i - 19):i + 1])
        rv.append(None if len(w) < 15 else (sum((x - mean(w)) ** 2 for x in w) / (len(w) - 1)) ** .5 * 100 * 252 ** .5)
    vol = {"pts": [[r(v, 1), r(m, 1)] for _, v, m in w3[::5]], "now": [r(vix_now, 1), r(move_now, 1)], "date": grid[w3[-1][0]],
           "p80": [r(q80([v for _, v, _ in w3]), 1), r(q80([m for _, _, m in w3]), 1)],
           "pct": [r(pctile([v for _, v, _ in w3], vix_now), 0), r(pctile([m for _, _, m in w3], move_now), 0)],
           "rv20": r(last_val(rv)[0], 1), "rv_corr": r(corr(src["move"], rv), 2)}

    # 원자재: 유가와 10년 BEI (최근 1년), 금과 실질금리 (월말), 구리/금 비율이 말하는 10년 금리
    wv, wi = last_val(src["wti"])
    oil = {"d": grid[-250:], "wti": [r(x, 2) for x in src["wti"][-250:]], "bei10": [r(x, 3) for x in src["bei10"][-250:]],
           "wti_m1": r((wv / ago(src["wti"], wi, 21) - 1) * 100, 1)}
    bv, bi = last_val(src["bei5"])
    oil["bei5_m1"] = r((bv - ago(src["bei5"], bi, 21)) * 100, 0)
    oil["shock"] = abs(oil["wti_m1"]) >= 15 and abs(oil["bei5_m1"]) >= 10 and (oil["wti_m1"] > 0) == (oil["bei5_m1"] > 0)
    me = [i for i in range(len(grid)) if grid[i] >= SINCE and (i == len(grid) - 1 or grid[i + 1][:7] != grid[i][:7])]
    gp = [(grid[i][:4], last_val(src["real10"], i)[0], last_val(src["gold"], i)[0]) for i in me]
    gp = [(y, a, b) for y, a, b in gp if a is not None and b is not None]
    lvl = lambda lo, hi: r(corr([a for y, a, _ in gp if lo <= y < hi], [b for y, _, b in gp if lo <= y < hi]), 2)
    gold = {"pts": [[r(a, 2), r(b, 0), int(y)] for y, a, b in gp], "lvl_pre": lvl("2016", "2022"), "lvl_post": lvl("2022", "2100")}
    cg = [(c / g, y) for c, g, y in zip(src["copper"][-756:], src["gold"][-756:], src["y10"][-756:]) if c and g and y is not None]
    fair = None
    if len(cg) > 100:
        mx, my = mean([x for x, _ in cg]), mean([y for _, y in cg])
        beta = sum((x - mx) * (y - my) for x, y in cg) / sum((x - mx) ** 2 for x, _ in cg)
        fair = {"y10_fair": r(my + beta * (cg[-1][0] - mx), 2), "y10": r(cg[-1][1], 2), "corr3y": r(corr([x for x, _ in cg], [y for _, y in cg]), 2)}

    return {"pairs": pairs, "tally": tally, "stockbond": sb, "vol": vol, "oil": oil, "gold": gold, "cg": fair,
            "pickup": monthly_pickup(src.get("intl")), "th": TH}
