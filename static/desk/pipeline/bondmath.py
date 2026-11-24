"""미국 국채 계산 (반기 이자, Actual/Actual, street convention). 표준 라이브러리만 쓴다.

`2. portfolio/initial_portfolio_wip/engine.py`의 수식을 옮긴 것이다 (그 폴더는 git에 올라가지 않아 자동 갱신에서 쓸 수 없다).
화면 쪽 `assets/bondmath.js`가 같은 수식을 쓴다. 두 구현이 같은 값을 내는지는 `python3 bondmath.py`로 확인한다.
"""
from datetime import date, datetime, timedelta


def to_date(x):
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return datetime.strptime(str(x)[:10], "%Y-%m-%d").date()


def _month_end_day(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day


def _is_month_end(d):
    return d.day == _month_end_day(d.year, d.month)


def _shift_months(d, n, eom):
    """d에서 n개월 이동. eom이면 항상 그 달 말일 (월말 만기물의 이자일 규칙)."""
    k = d.year * 12 + d.month - 1 + n
    y, m = k // 12, k % 12 + 1
    last = _month_end_day(y, m)
    return date(y, m, last if eom else min(d.day, last))


def add_months(d, n):
    d = to_date(d)
    return _shift_months(d, n, _is_month_end(d))


def _add_years(d, n):
    try:
        return date(d.year + n, d.month, d.day)
    except ValueError:
        return date(d.year + n, 2, 28)


def years_between(d0, d1):
    """달력 기준 연수: 꽉 찬 햇수 + 남은 일수 / 그 해의 일수."""
    d0, d1 = to_date(d0), to_date(d1)
    if d1 < d0:
        return -years_between(d1, d0)
    n = d1.year - d0.year
    if _add_years(d0, n) > d1:
        n -= 1
    a, b = _add_years(d0, n), _add_years(d0, n + 1)
    return n + (d1 - a).days / (b - a).days


def next_business_day(d):
    """주말만 건너뛴다 (공휴일은 보지 않는다)."""
    d = to_date(d) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def coupon_dates(maturity, settle):
    """(직전 이자일, 다음 이자일, 남은 이자 지급 횟수)."""
    maturity, settle = to_date(maturity), to_date(settle)
    if settle >= maturity:
        raise ValueError("settle %s 가 만기 %s 이후입니다" % (settle, maturity))
    eom = _is_month_end(maturity)
    k = max(((maturity.year - settle.year) * 12 + maturity.month - settle.month) // 6, 0)
    while _shift_months(maturity, -6 * k, eom) > settle:
        k += 1
    while k > 0 and _shift_months(maturity, -6 * (k - 1), eom) <= settle:
        k -= 1
    return _shift_months(maturity, -6 * k, eom), _shift_months(maturity, -6 * (k - 1), eom), k


def _frame(maturity, settle):
    prev, nxt, n = coupon_dates(maturity, settle)
    w = (nxt - to_date(settle)).days / (nxt - prev).days   # 다음 이자일까지 남은 기간 (반기 단위)
    return prev, nxt, n, w


def accrued_interest(coupon_pct, maturity, settle):
    prev, nxt, _ = coupon_dates(maturity, settle)
    return coupon_pct / 2.0 * (to_date(settle) - prev).days / (nxt - prev).days


def cashflows(coupon_pct, maturity, settle):
    """[(지급일, 결제일부터의 연수, 금액)] 액면 100 기준."""
    maturity = to_date(maturity)
    prev, nxt, n, w = _frame(maturity, settle)
    eom = _is_month_end(maturity)
    return [(_shift_months(maturity, -6 * (n - 1 - k), eom), (w + k) / 2.0,
             coupon_pct / 2.0 + (100.0 if k == n - 1 else 0.0)) for k in range(n)]


def dirty_from_yield(coupon_pct, maturity, settle, yield_pct):
    """더티가격 (액면 100당). 마지막 이자기간은 단리."""
    _, _, n, w = _frame(maturity, settle)
    c, y = coupon_pct / 2.0, yield_pct / 200.0
    if n == 1:
        return (100.0 + c) / (1.0 + w * y)
    v = 1.0 / (1.0 + y)
    return sum(c * v ** (w + k) for k in range(n)) + 100.0 * v ** (w + n - 1)


def yield_from_price(coupon_pct, maturity, settle, clean_price):
    """클린가격 → 만기수익률(%). 뉴턴법, 실패하면 이분법."""
    target = clean_price + accrued_interest(coupon_pct, maturity, settle)
    f = lambda y: dirty_from_yield(coupon_pct, maturity, settle, y) - target
    y = coupon_pct if coupon_pct > 0 else 3.0
    for _ in range(60):
        fy = f(y)
        if abs(fy) < 1e-11:
            return y
        h = 1e-5
        dd = (f(y + h) - f(y - h)) / (2 * h)
        if dd == 0:
            break
        step = fy / dd
        if not (-50.0 < y - step < 200.0):
            break
        y -= step
        if abs(step) < 1e-12:
            return y
    lo, hi = -50.0, 200.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if f(mid) > 0:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def analytics(coupon_pct, maturity, settle, clean_price=None, yield_pct=None):
    """가격이나 수익률 하나를 주면 나머지와 위험 지표를 돌려준다.
    dv01_per_1m = 액면 100만당 금리 1bp에 대한 가격 변화(달러)."""
    if (clean_price is None) == (yield_pct is None):
        raise ValueError("clean_price와 yield_pct 중 하나만")
    ai = accrued_interest(coupon_pct, maturity, settle)
    if yield_pct is None:
        yield_pct = yield_from_price(coupon_pct, maturity, settle, clean_price)
    dirty = dirty_from_yield(coupon_pct, maturity, settle, yield_pct)
    if clean_price is None:
        clean_price = dirty - ai
    _, _, n, w = _frame(maturity, settle)
    c, y = coupon_pct / 2.0, yield_pct / 200.0
    if n == 1:
        mac = w / 2.0
        mod = mac / (1.0 + w * y)
        conv = 2.0 * (w / 2.0) ** 2 / (1.0 + w * y) ** 2
    else:
        v = 1.0 / (1.0 + y)
        s1 = s2 = 0.0
        for k in range(n):
            tau = w + k
            pv = (c + (100.0 if k == n - 1 else 0.0)) * v ** tau
            s1 += tau * pv
            s2 += tau * (tau + 1.0) * pv
        mac = s1 / dirty / 2.0
        mod = mac * v
        conv = s2 * v * v / dirty / 4.0
    return {"clean": clean_price, "accrued": ai, "dirty": dirty, "ytm": yield_pct, "mdur": mod, "mac": mac,
            "conv": conv, "dv01_per_1m": dirty * mod}


# ───────────────────────── par 채권 (만기 정수 반기, 이자일에 평가) ─────────────────────────
def par_mod_dur(years, yield_pct):
    """금리 = 쿠폰인 채권(액면가)의 수정듀레이션."""
    h = yield_pct / 200.0
    return (1 - (1 + h) ** (-2 * years)) / (yield_pct / 100.0) if abs(h) > 1e-9 else years


def interp(xs, ys, t):
    """직선 보간. 양 끝 밖은 끝값."""
    if t <= xs[0]:
        return ys[0]
    if t >= xs[-1]:
        return ys[-1]
    for j in range(len(xs) - 1):
        if xs[j] <= t <= xs[j + 1]:
            return ys[j] + (ys[j + 1] - ys[j]) * (t - xs[j]) / (xs[j + 1] - xs[j])
    return ys[-1]


def _selftest():
    ok = True

    def check(name, got, want, tol):
        nonlocal ok
        good = abs(got - want) <= tol
        ok &= good
        print(("PASS" if good else "FAIL"), name, round(got, 6), "기대", want)

    # 이자일에 평가한 par 채권: 가격 100, 경과이자 0
    a = analytics(4.0, "2036-11-15", "2026-11-15", yield_pct=4.0)
    check("par 가격", a["clean"], 100.0, 1e-9)
    check("par 경과이자", a["accrued"], 0.0, 1e-12)
    check("par 수정듀레이션 = 닫힌 식", a["mdur"], par_mod_dur(10, 4.0), 1e-9)
    # 가격 ↔ 수익률 왕복
    b = analytics(2.875, "2029-04-30", "2026-11-19", clean_price=95.53125)
    c = analytics(2.875, "2029-04-30", "2026-11-19", yield_pct=b["ytm"])
    check("왕복 가격", c["clean"], 95.53125, 1e-8)
    # 수치 미분과 비교
    h = 0.01
    up = dirty_from_yield(2.875, "2029-04-30", "2026-11-19", b["ytm"] + h)
    dn = dirty_from_yield(2.875, "2029-04-30", "2026-11-19", b["ytm"] - h)
    check("수정듀레이션 = 수치 미분", b["mdur"], -(up - dn) / (2 * h / 100) / b["dirty"], 1e-5)
    check("볼록성 = 수치 2차 미분", b["conv"], (up + dn - 2 * b["dirty"]) / (h / 100) ** 2 / b["dirty"], 1e-3)
    print("전체", "PASS" if ok else "FAIL")
    return ok


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) > 1 and sys.argv[1] == "json":   # bondmath.js와 비교할 기준값
        cases = [(2.875, "2029-04-30", "2026-11-19", 95.53125), (4.75, "2045-02-15", "2026-11-19", 91.9375),
                 (4.625, "2028-11-30", "2026-11-30", 99.859), (1.625, "2026-12-31", "2026-11-24", 99.75),
                 (0.625, "2027-12-31", "2026-11-20", 95.65625)]
        out = []
        for cpn, mat, stl, px in cases:
            a = analytics(cpn, mat, stl, clean_price=px)
            a["case"] = [cpn, mat, stl, px]
            a["n_cf"] = len(cashflows(cpn, mat, stl))
            out.append(a)
        print(json.dumps(out))
    else:
        sys.exit(0 if _selftest() else 1)
