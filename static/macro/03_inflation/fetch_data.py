"""매크로 · 인플레이션 데이터 수집: FRED + ALFRED → data.js + CSV

1) 최신 개정치 (FRED)            → inflation_monthly.csv, inflation_daily.csv, data.js
   월별: Core CPI(CPILFESL), Core PCE(PCEPILFE), 미시간 1년 기대(MICH)
   일별: 10년 BEI(T10YIE), 5y5y 기대 인플레이션(T5YIFR)
   파생: Core CPI·Core PCE의 3개월 연율, 6개월 연율, 12개월 상승률 (%)
2) 발표 당시 값 (ALFRED 빈티지)   → realtime_releases.csv
   발표일마다 "그날 공개돼 있던" Core CPI·Core PCE로 계산한 전월비·3개월 연율·12개월 상승률.
   백테스트는 반드시 이 파일을 쓴다(미래 정보·사후 개정치 차단).
3) 정책금리 목표 상단 변경일 (FRED DFEDTARU) → policy_rate.csv  (국면 구분용)

실행:  python3 fetch_data.py          (수집 후 analyze.py까지 이어서 실행)
       python3 fetch_data.py --no-analyze

주의: inflation_monthly.csv의 날짜는 '발표일'이 아니라 '기준월'이고 값은 최신 개정치다.
"""
import csv, io, json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
START = "2010-01-01"       # 2015년 시작 + 12개월 상승률·룩백 여유
RT_START = "2013-06-01"    # 빈티지 수집 시작(2015년 백테스트 + 직전 12개월 평균 여유)
MONTHLY = [("core_cpi", "CPILFESL"), ("core_pce", "PCEPILFE"), ("mich_1y", "MICH")]
DAILY = [("bei_10y", "T10YIE"), ("fwd_5y5y", "T5YIFR")]
INDEXES = ["core_cpi", "core_pce"]  # 지수 수준 → 상승률 계산 대상
RELEASES = [("core_cpi", "CPILFESL", 10), ("core_pce", "PCEPILFE", 54)]  # (이름, FRED ID, ALFRED release id)
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
RT_COLS = ["series", "release_date", "ref_month", "is_new", "level", "mom", "ann3", "ann6", "yoy"]


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read().decode("utf-8-sig")
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def num(s):
    s = (s or "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def month_back(d, n):
    y, m = int(d[:4]), int(d[5:7])
    k = y * 12 + (m - 1) - n
    return f"{k // 12:04d}-{k % 12 + 1:02d}-01"


def pct(a, b, n):
    """n개월 전(b) 대비 연율 상승률(%). 둘 중 하나라도 없으면 None."""
    if a is None or b is None:
        return None
    return round(((a / b) ** (12 / n) - 1) * 100, 3)


# ---------- 1) 최신 개정치 ----------
def fetch(series):
    rows = {}  # 'YYYY-MM-DD' -> {name: value}
    for name, fid in series:
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={START}")
        for r in csv.DictReader(io.StringIO(text)):
            v = num(r.get(fid))
            if v is not None:
                rows.setdefault(r.get("observation_date") or r.get("DATE"), {})[name] = v
        print(f"  {fid} ok", file=sys.stderr)
    return rows


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


def latest_vintage():
    m_rows, d_rows = fetch(MONTHLY), fetch(DAILY)
    m_dates = sorted(m_rows)
    monthly = {n: [m_rows[d].get(n) for d in m_dates] for n, _ in MONTHLY}
    for name in INDEXES:
        for n, tag in ((3, "3m_ann"), (6, "6m_ann"), (12, "12m")):
            monthly[f"{name}_{tag}"] = [
                pct(m_rows[d].get(name), m_rows.get(month_back(d, n), {}).get(name), n) for d in m_dates]
    d_dates = sorted(d_rows)
    daily = {n: [d_rows[d].get(n) for d in d_dates] for n, _ in DAILY}

    write_csv(HERE / "inflation_monthly.csv", ["date"] + list(monthly),
              [[d] + [monthly[c][i] for c in monthly] for i, d in enumerate(m_dates)])
    write_csv(HERE / "inflation_daily.csv", ["date"] + list(daily),
              [[d] + [daily[c][i] for c in daily] for i, d in enumerate(d_dates)])
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FRED (BLS, BEA, University of Michigan, Federal Reserve)",
        "series": {n: f for n, f in MONTHLY + DAILY},
        "monthly": {"dates": m_dates, **monthly},
        "daily": {"dates": d_dates, **daily},
    }
    (HERE / "data.js").write_text(
        "window.INFLATION_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    for name, _ in MONTHLY:
        last = max(d for d in m_dates if m_rows[d].get(name) is not None)
        print(f"{name:9s} 월별 {sum(v is not None for v in monthly[name])}개, 최신 {last[:7]}")
    for name, _ in DAILY:
        last = max(d for d in d_dates if d_rows[d].get(name) is not None)
        print(f"{name:9s} 일별 {sum(v is not None for v in daily[name])}개, 최신 {last}")


# ---------- 2) 발표 당시 값 ----------
def release_dates(rid):
    text = get(f"https://alfred.stlouisfed.org/release/downloaddates?rid={rid}&ff=txt")
    out = [ln.strip() for ln in text.splitlines()
           if len(ln.strip()) == 10 and ln.strip()[4] == "-" and ln.strip()[:4].isdigit()]
    return sorted(d for d in set(out) if d >= RT_START)


def vintages(fid, dates, size=12):
    """발표일 목록 → {발표일: {기준월: 값}}. ALFRED 그래프 CSV는 한 번에 여러 빈티지를 준다."""
    out = {}
    for i in range(0, len(dates), size):
        chunk = dates[i:i + size]
        cosd = month_back(chunk[0], 20)
        url = ("https://alfred.stlouisfed.org/graph/alfredgraph.csv?"
               f"id={','.join([fid] * len(chunk))}&cosd={cosd}&vintage_date={','.join(chunk)}")
        rows = list(csv.reader(io.StringIO(get(url))))
        if len(rows[0]) != len(chunk) + 1:
            raise RuntimeError(f"{fid}: 빈티지 열 수가 요청과 다름 ({len(rows[0]) - 1} vs {len(chunk)})")
        for j, d in enumerate(chunk, start=1):
            out[d] = {r[0]: num(r[j]) for r in rows[1:] if len(r) > j and num(r[j]) is not None}
        print(f"  {fid} 빈티지 {chunk[0]} ~ {chunk[-1]} ok", file=sys.stderr)
    return out


def realtime():
    path = HERE / "realtime_releases.csv"
    have = {}
    if path.exists():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            have[(r["series"], r["release_date"])] = r
    rows = []
    for name, fid, rid in RELEASES:
        dates = release_dates(rid)
        todo = [d for d in dates if (name, d) not in have]
        vint = vintages(fid, todo) if todo else {}
        last_ref = ""
        for d in dates:
            if (name, d) in have:
                r = have[(name, d)]
                rows.append([r[c] for c in RT_COLS])
                last_ref = max(last_ref, r["ref_month"])
                continue
            v = vint.get(d) or {}
            if not v:
                continue
            ref = max(v)
            lv = lambda n: v.get(month_back(ref, n))
            rows.append([name, d, ref[:7], int(ref[:7] > last_ref), v[ref],
                         None if lv(1) is None else round((v[ref] / lv(1) - 1) * 100, 4),
                         pct(v[ref], lv(3), 3), pct(v[ref], lv(6), 6), pct(v[ref], lv(12), 12)])
            last_ref = max(last_ref, ref[:7])
        n = sum(1 for r in rows if r[0] == name)
        print(f"{name:9s} 발표일 {n}개 (신규 {len(todo)}개), 최신 발표 {dates[-1]}")
    write_csv(path, RT_COLS, rows)


# ---------- 3) 정책금리 ----------
def policy_rate():
    text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd=2008-12-16")
    rows, prev = [], None
    for r in csv.DictReader(io.StringIO(text)):
        v = num(r.get("DFEDTARU"))
        if v is not None and v != prev:
            rows.append([r.get("observation_date") or r.get("DATE"), v])
            prev = v
    write_csv(HERE / "policy_rate.csv", ["date", "upper"], rows)
    print(f"policy    변경 {len(rows) - 1}회, 현재 상단 {rows[-1][1]}% ({rows[-1][0]}~)")


def main():
    latest_vintage()
    realtime()
    policy_rate()
    if "--no-analyze" not in sys.argv and (HERE / "analyze.py").exists():
        sys.dont_write_bytecode = True   # __pycache__ 폴더를 만들지 않는다
        import analyze
        analyze.main()


if __name__ == "__main__":
    main()
