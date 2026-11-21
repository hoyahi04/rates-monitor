"""매크로 · 성장·고용 데이터 수집: FRED + ALFRED → data.js + CSV

1) 최신 개정치 (FRED)            → jobs_monthly.csv, claims_weekly.csv, data.js
   월별: 비농업 고용(PAYEMS, 천 명), 실업률(UNRATE, %)
   주별: 신규 실업수당 청구건수(ICSA)와 4주 평균(IC4WSA), 천 건
   파생: NFP 전월 대비 증감, 3개월·12개월 평균 증감, 그 차이(모멘텀) / 실업률 3개월 평균과 그 3개월 변화
2) 발표 당시 값 (ALFRED 빈티지)   → realtime_releases.csv
   고용보고서 발표일마다 "그날 공개돼 있던" 수치로 계산한 값. 백테스트는 반드시 이 파일을 쓴다.
3) 컨센서스 입력 틀               → nfp_consensus.csv   (survey 열은 Bloomberg에서 직접 입력, 다시 실행해도 보존)
4) ISM 제조업 입력 틀             → ism_manufacturing.csv (FRED에 없음. pmi 열은 직접 입력, 다시 실행해도 보존)
5) 정책금리 목표 상단 변경일      → policy_rate.csv     (국면 구분용)

실행:  python3 fetch_data.py          (analyze.py가 있으면 이어서 실행)
       python3 fetch_data.py --no-analyze

주의
- jobs_monthly.csv의 날짜는 '발표일'이 아니라 '기준월'이고 값은 최신 개정치다.
- claims_weekly.csv의 날짜는 주 마감일(토요일)이다. 발표는 보통 그다음 목요일(5일 뒤)이다.
- 2025년 10월 실업률은 없다(셧다운으로 가계조사 미실시). 실업률 3개월 평균은 3개 중 2개 이상 있을 때만 계산한다.
- 2025년 9월분은 11월 20일에, 10·11월분은 12월 16일에 한꺼번에 발표됐다(realtime_releases.csv에 그대로 반영).
"""
import csv, io, json, sys, time, urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).parent
START = "2010-01-01"       # 2015년 시작 + 12개월 평균·룩백 여유
RT_START = "2013-06-01"    # 빈티지 수집 시작(2015년 백테스트 + 직전 12개월 평균 여유)
MONTHLY = [("payems", "PAYEMS"), ("unrate", "UNRATE")]
WEEKLY = [("icsa_k", "ICSA"), ("ic4wsa_k", "IC4WSA")]
SCALE = {"icsa_k": 1e-3, "ic4wsa_k": 1e-3}  # FRED 원자료가 건 → 천 건
RELEASE_ID = 50            # ALFRED release id: Employment Situation
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
RT_COLS = ["series", "release_date", "ref_month", "is_new", "level", "chg_1m",
           "chg_3m_avg", "chg_12m_avg", "mom_gap", "rev_prev", "lvl_3m_avg", "lvl_3m_avg_chg3"]


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


def avg_chg(v, ref, n):
    """기준월 ref까지 n개월간 월평균 증감. v = {기준월: 수준}."""
    a, b = v.get(ref), v.get(month_back(ref, n))
    return None if a is None or b is None else round((a - b) / n, 1)


def avg3(v, ref):
    """ref 포함 최근 3개월 평균. 값이 2개 미만이면 None (2025-10 실업률 결측 대응)."""
    xs = [v.get(month_back(ref, k)) for k in range(3)]
    xs = [x for x in xs if x is not None]
    return round(sum(xs) / len(xs), 3) if len(xs) >= 2 else None


def diff(a, b, nd=3):
    return None if a is None or b is None else round(a - b, nd)


def derive(series, v, ref):
    """한 빈티지(v)와 기준월(ref)에서 파생값 계산. 최신 개정치와 발표 당시 값에 같은 식을 쓴다."""
    if series == "payems":
        c3, c12 = avg_chg(v, ref, 3), avg_chg(v, ref, 12)
        return {"chg_1m": avg_chg(v, ref, 1), "chg_3m_avg": c3, "chg_12m_avg": c12, "mom_gap": diff(c3, c12, 1)}
    a3 = avg3(v, ref)
    return {"chg_1m": diff(v.get(ref), v.get(month_back(ref, 1)), 2),
            "lvl_3m_avg": a3, "lvl_3m_avg_chg3": diff(a3, avg3(v, month_back(ref, 3)))}


def write_csv(path, cols, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(cols)
        for r in rows:
            w.writerow(["" if v is None else v for v in r])


# ---------- 1) 최신 개정치 ----------
def fetch(series):
    rows = {}  # 'YYYY-MM-DD' -> {name: value}
    for name, fid in series:
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={START}")
        for r in csv.DictReader(io.StringIO(text)):
            v = num(r.get(fid))
            if v is not None:
                rows.setdefault(r.get("observation_date") or r.get("DATE"), {})[name] = round(v * SCALE.get(name, 1), 3)
        print(f"  {fid} ok", file=sys.stderr)
    return rows


def read_ism():
    """ism_manufacturing.csv에서 직접 입력한 pmi를 읽는다. 없으면 빈 dict."""
    path = HERE / "ism_manufacturing.csv"
    if not path.exists():
        return {}
    return {r["ref_month"]: num(r.get("pmi")) for r in csv.DictReader(open(path, encoding="utf-8"))
            if num(r.get("pmi")) is not None}


def latest_vintage():
    m_rows, w_rows = fetch(MONTHLY), fetch(WEEKLY)
    m_dates = sorted(m_rows)
    lv = {n: {d: m_rows[d][n] for d in m_dates if n in m_rows[d]} for n, _ in MONTHLY}
    pay = [derive("payems", lv["payems"], d) for d in m_dates]
    une = [derive("unrate", lv["unrate"], d) for d in m_dates]
    monthly = {
        "payems": [lv["payems"].get(d) for d in m_dates],
        "payems_chg": [x["chg_1m"] for x in pay],
        "payems_chg_3m_avg": [x["chg_3m_avg"] for x in pay],
        "payems_chg_12m_avg": [x["chg_12m_avg"] for x in pay],
        "payems_mom_gap": [x["mom_gap"] for x in pay],
        "unrate": [lv["unrate"].get(d) for d in m_dates],
        "unrate_3m_avg": [x["lvl_3m_avg"] for x in une],
        "unrate_3m_avg_chg3": [x["lvl_3m_avg_chg3"] for x in une],
    }
    w_dates = sorted(w_rows)
    weekly = {n: [w_rows[d].get(n) for d in w_dates] for n, _ in WEEKLY}

    # ISM 입력 틀: 기준월만 채워 두고 pmi는 직접 입력. 이미 입력한 값은 보존.
    ism = read_ism()
    write_csv(HERE / "ism_manufacturing.csv", ["ref_month", "pmi"], [[d[:7], ism.get(d[:7])] for d in m_dates])

    write_csv(HERE / "jobs_monthly.csv", ["date"] + list(monthly),
              [[d] + [monthly[c][i] for c in monthly] for i, d in enumerate(m_dates)])
    write_csv(HERE / "claims_weekly.csv", ["week_ending"] + list(weekly),
              [[d] + [weekly[c][i] for c in weekly] for i, d in enumerate(w_dates)])
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FRED (BLS, Department of Labor)" + (" · ISM (직접 입력)" if ism else ""),
        "series": {n: f for n, f in MONTHLY + WEEKLY},
        "units": {"payems": "천 명", "unrate": "%", "icsa_k": "천 건", "ic4wsa_k": "천 건"},
        "monthly": {"dates": m_dates, **monthly, "ism_pmi": [ism.get(d[:7]) for d in m_dates]},
        "weekly": {"dates": w_dates, **weekly},
    }
    (HERE / "data.js").write_text(
        "window.GROWTH_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n", encoding="utf-8")
    for name, _ in MONTHLY:
        print(f"{name:9s} 월별 {len(lv[name])}개, 최신 {max(lv[name])[:7]}")
    for name, _ in WEEKLY:
        last = max(d for d in w_dates if w_rows[d].get(name) is not None)
        print(f"{name:9s} 주별 {sum(v is not None for v in weekly[name])}개, 최신 {last}")
    print(f"ism_pmi   직접 입력 {len(ism)}개" + ("" if ism else " (ism_manufacturing.csv의 pmi 열이 비어 있음)"))


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
            # cosd가 첫 열에만 적용되므로 날짜로 한 번 더 거른다
            out[d] = {r[0]: num(r[j]) for r in rows[1:] if r[0] >= cosd and len(r) > j and num(r[j]) is not None}
        print(f"  {fid} 빈티지 {chunk[0]} ~ {chunk[-1]} ok", file=sys.stderr)
    return out


def realtime():
    path = HERE / "realtime_releases.csv"
    have = {}
    if path.exists():
        for r in csv.DictReader(open(path, encoding="utf-8")):
            have[(r["series"], r["release_date"])] = r
    dates = release_dates(RELEASE_ID)
    rows = []
    for name, fid in MONTHLY:
        todo = [d for d in dates if (name, d) not in have]
        vint = vintages(fid, todo) if todo else {}
        last_ref, prev = "", None  # prev = (직전 발표의 기준월, 그때 발표된 전월 대비 증감)
        for d in dates:
            if (name, d) in have:
                r = have[(name, d)]
                rows.append([r.get(c, "") for c in RT_COLS])
                if r["is_new"] == "1":
                    prev = (r["ref_month"] + "-01", num(r["chg_1m"]))
                last_ref = max(last_ref, r["ref_month"])
                continue
            v = vint.get(d) or {}
            if not v:
                continue
            ref = max(v)
            is_new = int(ref[:7] > last_ref)
            x = derive(name, v, ref)
            # 직전 달 수정폭: 지난번에 발표한 증감이 이번 발표에서 얼마나 바뀌었나 (NFP만)
            rev = None
            if name == "payems" and is_new and prev and prev[1] is not None:
                rev = diff(avg_chg(v, prev[0], 1), prev[1], 1)
            rows.append([name, d, ref[:7], is_new, v[ref]] + [x.get(c) if c != "rev_prev" else rev for c in RT_COLS[5:]])
            if is_new:
                prev = (ref, x["chg_1m"])
            last_ref = max(last_ref, ref[:7])
        n = sum(1 for r in rows if r[0] == name)
        print(f"{name:9s} 발표일 {n}개 (신규 수집 {len(todo)}개), 최신 발표 {dates[-1]}")
    write_csv(path, RT_COLS, rows)
    return rows


# ---------- 3) 컨센서스 입력 틀 ----------
def consensus_template(rt_rows):
    """발표일·첫 발표치를 채워 두고 survey 열만 비워 둔다. 이미 입력한 survey는 보존."""
    path = HERE / "nfp_consensus.csv"
    keep = {}
    if path.exists():
        keep = {r["release_date"]: r.get("survey", "") for r in csv.DictReader(open(path, encoding="utf-8"))}
    rows = [[r[1], r[2], r[5], keep.get(r[1], "")] for r in rt_rows
            if r[0] == "payems" and str(r[3]) == "1" and r[1] >= "2015-01-01"]
    write_csv(path, ["release_date", "ref_month", "actual_first_print", "survey"], rows)
    filled = sum(1 for r in rows if str(r[3]).strip())
    print(f"consensus 발표 {len(rows)}회, survey 입력 {filled}개")


# ---------- 4) 정책금리 ----------
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
    consensus_template(realtime())
    policy_rate()
    if "--no-analyze" not in sys.argv and (HERE / "analyze.py").exists():
        sys.dont_write_bytecode = True   # __pycache__ 폴더를 만들지 않는다
        import analyze
        analyze.main()


if __name__ == "__main__":
    main()
