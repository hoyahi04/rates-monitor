"""공통 도구: 내려받기, FRED, js 읽고 쓰기, 날짜, 통계. 표준 라이브러리만 쓴다."""
import csv, io, json, math, sys, time, urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
DESK = HERE.parent                 # 4. desk/
ROOT = DESK.parent                 # static/ (curve/, macro/ 가 있는 곳)
RAW = DESK / "data" / "raw"
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
UA_YAHOO = {"User-Agent": "Mozilla/5.0"}  # Yahoo는 긴 브라우저 UA와 curl UA에 429를 준다


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def get_bytes(url, headers=UA, tries=3, timeout=90, data=None):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers=headers, data=data)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def get(url, headers=UA, tries=3, timeout=90):
    return get_bytes(url, headers, tries, timeout).decode("utf-8-sig", errors="replace")


def num(s):
    try:
        v = float(str(s).strip())
        return v if math.isfinite(v) else None
    except (TypeError, ValueError):
        return None


def fred(series_id, start="2010-01-01"):
    """FRED 한 시리즈 → [(날짜, 값)] (빈 값은 뺀다). API 키가 필요 없는 그래프용 CSV 경로."""
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}&cosd={start}")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        d = r.get("observation_date") or r.get("DATE")
        v = num(r.get(series_id))
        if d and v is not None:
            out.append((d, v))
    if not out:
        raise ValueError(f"FRED {series_id}: 값이 없음")
    return out


def load_js(path):
    """`window.X = {...};` 꼴 파일에서 객체만 읽는다."""
    s = Path(path).read_text(encoding="utf-8")
    return json.loads(s[s.index("{"): s.rindex("}") + 1])


def write_js(path, name, obj):
    Path(path).write_text(f"window.{name} = " + json.dumps(obj, ensure_ascii=False, separators=(",", ":")) + ";\n",
                          encoding="utf-8")


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, obj):
    Path(path).write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")


def d(s):
    return date.fromisoformat(str(s)[:10])


def r(x, n=4):
    return None if x is None else round(float(x), n)


# ───────────────────────── 통계 ─────────────────────────
def clean(xs):
    return [x for x in xs if x is not None]


def mean(xs):
    xs = clean(xs)
    return sum(xs) / len(xs) if xs else None


def stdev(xs):
    xs = clean(xs)
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))


def zscore(window, x):
    """x가 window(과거 값들)의 평균에서 표준편차 몇 개만큼 떨어져 있나."""
    s = stdev(window)
    return None if (x is None or not s) else (x - mean(window)) / s


def pctile(window, x):
    """window 안에서 x 이하인 값의 비율(0~100)."""
    w = clean(window)
    if x is None or not w:
        return None
    return 100.0 * sum(1 for v in w if v <= x) / len(w)


def last_valid(xs, i=None):
    """i번째(없으면 끝)에서 거슬러 올라가 처음 만나는 값과 그 위치."""
    i = len(xs) - 1 if i is None else i
    while i >= 0 and xs[i] is None:
        i -= 1
    return (xs[i], i) if i >= 0 else (None, -1)


def ffill(xs):
    out, cur = [], None
    for x in xs:
        cur = x if x is not None else cur
        out.append(cur)
    return out


def corr(a, b):
    p = [(x, y) for x, y in zip(a, b) if x is not None and y is not None]
    if len(p) < 10:
        return None
    ma, mb = sum(x for x, _ in p) / len(p), sum(y for _, y in p) / len(p)
    va, vb = sum((x - ma) ** 2 for x, _ in p), sum((y - mb) ** 2 for _, y in p)
    if va <= 0 or vb <= 0:
        return None
    return sum((x - ma) * (y - mb) for x, y in p) / math.sqrt(va * vb)


def idx_on_or_before(dates, target):
    """정렬된 날짜 문자열 목록에서 target 이하인 마지막 위치 (없으면 -1)."""
    lo, hi = 0, len(dates)
    while lo < hi:
        mid = (lo + hi) // 2
        if dates[mid] <= target:
            lo = mid + 1
        else:
            hi = mid
    return lo - 1


def back(s, days=0, months=0, years=0):
    """날짜 문자열을 달력 기준으로 과거 쪽으로 옮긴다 (말일 넘침은 그 달 말일로)."""
    x = d(s)
    if months or years:
        k = x.year * 12 + x.month - 1 - months - years * 12
        y, m = k // 12, k % 12 + 1
        last = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)).day
        x = date(y, m, min(x.day, last))
    return (x - timedelta(days=days)).isoformat()
