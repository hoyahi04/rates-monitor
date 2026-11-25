"""매크로 · 정책 경로 데이터 수집: FRED + ALFRED + 연준 홈페이지 + Yahoo Finance → data.js + CSV 4개

1) 정책금리 (FRED, 일별)                  → policy_daily.csv
   목표 범위 상단(DFEDTARU)·하단(DFEDTARL), 실효 연방기금금리(EFFR), SOFR
2) 점도표 중간값 (ALFRED 빈티지)            → dots.csv
   SEP 발표일마다 "그날 공개된" 연말 정책금리 전망 중간값(FEDTARMD)과 장기 중립금리(FEDTARMDLR).
   FRED는 소수 첫째 자리로 반올림해 주므로 1/8%p 단위로 되돌린다(예: 4.1 → 4.125).
   FEDTARMD의 첫 빈티지가 2015-12-16이라 그 전 4회(2014-12 ~ 2015-09)는 아래 EARLY_DOTS에 직접 적었다.
3) FOMC 회의일 (연준 홈페이지)              → fomc_dates.csv
   결정 발표일(회의 마지막 날). 임시 회의는 kind=unscheduled. 앞으로 열릴 회의도 포함.
4) 연방기금금리 선물 (Yahoo Finance, ZQ)   → ff_futures.csv
   지금 거래 중인 월물의 일별 종가. 내재 금리 = 100 − 가격.
   ⚠️ Yahoo는 만기가 지난 월물을 지운다. 그래서 선물로는 "현재의 내재 경로"만 그릴 수 있고,
      2015년부터의 백테스트는 2년 국채 금리를 시장 내재 경로의 대용치로 쓴다(analyze.py 참고).

실행:  python3 fetch_data.py          (수집 후 analyze.py까지 이어서 실행)
       python3 fetch_data.py --no-analyze

연준 홈페이지나 Yahoo가 막히면 그 파일만 예전 것을 그대로 두고 경고를 낸다.
"""
import csv, io, json, re, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).parent
START = "2010-01-01"       # 2015년 시작 + 룩백 여유
DAILY = [("upper", "DFEDTARU"), ("lower", "DFEDTARL"), ("effr", "EFFR"), ("sofr", "SOFR")]
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
UA_YAHOO = {"User-Agent": "Mozilla/5.0"}   # Yahoo는 긴 브라우저 UA와 curl UA에 429를 준다
FIRST_VINTAGE = "2015-12-16"   # ALFRED에 FEDTARMD 빈티지가 있는 첫 SEP
# 그 전 SEP의 중간값. 2015-09는 연준 발표 표, 나머지 3회는 연준이 중간값을 따로 싣지 않던 때라 점도표에서 읽은 값이다.
EARLY_DOTS = {
    "2014-12-17": {2014: 0.125, 2015: 1.125, 2016: 2.5, 2017: 3.625},
    "2015-03-18": {2015: 0.625, 2016: 1.875, 2017: 3.125},
    "2015-06-17": {2015: 0.625, 2016: 1.625, 2017: 2.875},
    "2015-09-17": {2015: 0.375, 2016: 1.375, 2017: 2.625, 2018: 3.375},
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
          "november", "december"]
FUT_CODES = "FGHJKMNQUVXZ"   # 선물 월물 코드 (1월 F ~ 12월 Z)


def get(url, headers=UA, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                return r.read().decode("utf-8-sig", "ignore")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def num(s):
    try:
        return float((s or "").strip())
    except ValueError:
        return None


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def fred(fid, start=START):
    text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={start}")
    out = []
    for r in csv.DictReader(io.StringIO(text)):
        v = num(r.get(fid))
        if v is not None:
            out.append((r.get("observation_date") or r.get("DATE"), v))
    print(f"  {fid} ok", file=sys.stderr)
    return out


# ---------- 1) 정책금리 ----------
def policy_daily():
    rows = {}
    for name, fid in DAILY:
        for d, v in fred(fid):
            rows.setdefault(d, {})[name] = v
    dates = [d for d in sorted(rows) if datetime.strptime(d, "%Y-%m-%d").weekday() < 5]   # 주말 제외
    out = []
    for d in dates:
        r = rows[d]
        mid = None if r.get("upper") is None or r.get("lower") is None else round((r["upper"] + r["lower"]) / 2, 4)
        out.append([d, r.get("upper"), r.get("lower"), mid, r.get("effr"), r.get("sofr")])
    write_csv(HERE / "policy_daily.csv", ["date", "upper", "lower", "mid", "effr", "sofr"], out)
    last = [r for r in out if r[1] is not None][-1]
    print(f"policy    일별 {len(out)}개, 현재 목표 범위 {last[2]}~{last[1]}% ({last[0]})")
    return out


# ---------- 2) 점도표 ----------
def eighth(v):
    """FRED가 소수 첫째 자리로 반올림한 값을 1/8%p 단위로 되돌린다."""
    return round(round(v * 8) / 8, 3)


def dots():
    lr = dict(fred("FEDTARMDLR", "2012-01-01"))            # 관측일 = SEP 발표일
    seps = sorted(d for d in lr if d >= min(EARLY_DOTS))
    table = {d: dict(v) for d, v in EARLY_DOTS.items()}
    todo = [d for d in seps if d >= FIRST_VINTAGE]
    for i in range(0, len(todo), 12):
        chunk = todo[i:i + 12]
        url = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv?"
               f"id={','.join(['FEDTARMD'] * len(chunk))}&cosd=2012-01-01&vintage_date={','.join(chunk)}")
        rows = list(csv.reader(io.StringIO(get(url))))
        if len(rows[0]) != len(chunk) + 1:
            raise RuntimeError(f"FEDTARMD: 빈티지 열 수가 요청과 다름 ({len(rows[0]) - 1} vs {len(chunk)})")
        for j, d in enumerate(chunk, start=1):
            v = {int(r[0][:4]): eighth(num(r[j])) for r in rows[1:] if len(r) > j and num(r[j]) is not None}
            if not v or min(v) != int(d[:4]):
                raise RuntimeError(f"FEDTARMD {d}: 빈티지가 SEP 날짜와 맞지 않음 {sorted(v)}")
            table[d] = v
        print(f"  FEDTARMD 빈티지 {chunk[0]} ~ {chunk[-1]} ok", file=sys.stderr)
    out = []
    for d in seps:
        if d not in table:
            continue
        for y in sorted(table[d]):
            out.append([d, y, table[d][y]])
        out.append([d, "LR", eighth(lr[d])])
    write_csv(HERE / "dots.csv", ["sep_date", "target", "median"], out)
    last = seps[-1]
    print(f"dots      SEP {len(table)}회, 최신 {last}: "
          + ", ".join(f"{y}년 말 {v}%" for y, v in sorted(table[last].items())) + f", 장기 {eighth(lr[last])}%")
    return out


# ---------- 3) FOMC 회의일 ----------
def meeting_date(year, month_text, day_text):
    """('2019', 'April/May', '30-1') → '2019-05-01' (결정 발표일 = 마지막 날)"""
    names = [m for m in re.split(r"[/\s]+", month_text.lower()) if m]
    days = [int(x) for x in re.findall(r"\d+", day_text)]
    if not names or not days:
        return None
    idx = [i for i, m in enumerate(MONTHS) if m.startswith(names[-1][:3])]
    return f"{int(year):04d}-{idx[0] + 1:02d}-{days[-1]:02d}" if idx else None


def fomc_dates(sep_dates):
    found = {}
    def add(year, month, days, label):
        low = label.lower()
        if "notation" in low or "cancel" in low:
            return
        d = meeting_date(year, month, days)
        if d:
            found[d] = "unscheduled" if "unscheduled" in low else "scheduled"
    cal = get("https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm", UA_BROWSER)
    parts = re.split(r"(\d{4}) FOMC Meetings</a></h4>", cal)
    years = []
    for i in range(1, len(parts), 2):
        years.append(int(parts[i]))
        for month, days in re.findall(r'fomc-meeting__month[^>]*><strong>(.*?)</strong></div>\s*'
                                      r'<div class="fomc-meeting__date[^>]*>(.*?)</div>', parts[i + 1], flags=re.S):
            add(parts[i], month, days, days)
    for y in range(2015, min(years)):
        page = get(f"https://www.federalreserve.gov/monetarypolicy/fomchistorical{y}.htm", UA_BROWSER)
        for title in re.findall(r"<h5[^>]*>(.*?)</h5>", page):
            m = re.match(r"([A-Za-z/]+)\s+([\d-]+)\s*(.*?)-\s*(\d{4})", title.strip())
            if m and ("Meeting" in title or "unscheduled" in title):
                add(m.group(4), m.group(1), m.group(2), m.group(3))
        print(f"  FOMC {y} ok", file=sys.stderr)
    if len(found) < 80:
        raise RuntimeError(f"FOMC 회의일이 너무 적게 읽힘 ({len(found)}개)")
    sep = set(sep_dates)
    out = [[d, found[d], int(d in sep)] for d in sorted(found)]
    write_csv(HERE / "fomc_dates.csv", ["date", "kind", "sep"], out)
    n = sum(1 for r in out if r[1] == "scheduled")
    print(f"fomc      정례 {n}회 + 임시 {len(out) - n}회, {out[0][0]} ~ {out[-1][0]}")
    return out


# ---------- 4) 연방기금금리 선물 ----------
def futures():
    now = datetime.now(timezone.utc)
    y, m, rows, miss, got = now.year, now.month, [], 0, []
    while miss < 3 and len(got) < 48:
        sym = f"ZQ{FUT_CODES[m - 1]}{y % 100:02d}.CBT"
        try:
            j = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d",
                               UA_YAHOO, tries=2))
            res = j["chart"]["result"][0]
            off = res["meta"].get("gmtoffset", 0)
            seen = {}
            for ts, c in zip(res["timestamp"], res["indicators"]["quote"][0]["close"]):
                if c is not None:
                    seen[datetime.fromtimestamp(ts + off, timezone.utc).strftime("%Y-%m-%d")] = round(c, 4)
            rows += [[d, f"{y:04d}-{m:02d}", p] for d, p in sorted(seen.items())]
            got.append(f"{y:04d}-{m:02d}")
            miss = 0
        except Exception:
            miss += 1
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    if len(got) < 6:
        raise RuntimeError(f"선물 월물이 {len(got)}개만 읽힘")
    rows.sort()
    write_csv(HERE / "ff_futures.csv", ["date", "contract", "price"], rows)
    print(f"futures   월물 {len(got)}개 ({got[0]} ~ {got[-1]}), 최신 {rows[-1][0]}")
    return rows


def keep_old(name, fn, *args):
    """막혀도 다른 수집은 계속한다. 실패하면 예전 파일을 그대로 둔다."""
    try:
        return fn(*args)
    except Exception as e:
        state = "예전 파일 유지" if (HERE / name).exists() else "파일 없음"
        print(f"⚠️  {name} 수집 실패 ({state}): {e}")
        return None


def read_rows(name):
    with open(HERE / name, encoding="utf-8") as f:
        return list(csv.reader(f))[1:]


def main():
    pol = policy_daily()
    dot = dots()
    seps = sorted({r[0] for r in dot})
    keep_old("fomc_dates.csv", fomc_dates, seps)
    keep_old("ff_futures.csv", futures)

    fomc = read_rows("fomc_dates.csv")
    cols = list(zip(*pol))
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FRED, ALFRED (Federal Reserve Board, New York Fed), federalreserve.gov, Yahoo Finance (CBOT ZQ)",
        "series": {n: f for n, f in DAILY},
        "daily": {"dates": cols[0], "upper": cols[1], "lower": cols[2], "mid": cols[3], "effr": cols[4]},
        "dots": [{"sep": d, "lr": next(r[2] for r in dot if r[0] == d and r[1] == "LR"),
                  "years": {str(r[1]): r[2] for r in dot if r[0] == d and r[1] != "LR"}} for d in seps],
        "fomc": [{"date": r[0], "kind": r[1], "sep": int(r[2])} for r in fomc],
    }
    (HERE / "data.js").write_text(
        "window.POLICY_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    if "--no-analyze" not in sys.argv and (HERE / "analyze.py").exists():
        sys.dont_write_bytecode = True   # __pycache__ 폴더를 만들지 않는다
        import analyze
        analyze.main()


if __name__ == "__main__":
    main()
