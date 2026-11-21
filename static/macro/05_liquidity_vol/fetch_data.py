"""매크로 · 유동성·변동성 데이터 수집: FRED + Yahoo Finance → data.js + CSV 2개

시리즈
  일별: VIX(VIXCLS), MOVE(Yahoo ^MOVE), SOFR, EFFR, IORB(2021-07-29~) / IOER(~2021-07-28),
        역레포 잔액(RRPONTSYD), 하이일드 OAS(BAMLH0A0HYM2), 투자등급 OAS(BAMLC0A0CM),
        Baa − 10년 국채 스프레드(BAA10Y, 신용 스프레드의 장기 시계열 대용)
  주별: 지급준비금(WRESBAL), 재무부 일반계정 TGA(WTREGEN) — 수요일 기준
        시카고 연은 금융여건지수(NFCI), 세인트루이스 연은 금융스트레스지수(STLFSI4) — 금요일 기준, 교차 확인용
파생(일별): 준비금 금리(IORB와 IOER를 이은 것), SOFR − 준비금 금리, EFFR − 준비금 금리 (bp)
실행:  python3 fetch_data.py   (같은 폴더에 data.js, liquidity_daily.csv, liquidity_weekly.csv, policy_rate.csv 생성.
       끝나면 analyze.py까지 실행해 signals.js, signals_monthly.csv를 만든다. 수집만 하려면 --no-analyze)

주의: MOVE는 FRED에 없다. 같은 폴더의 MOVE_index_daily_weekly.xlsx(직접 받은 자료)를 우선 쓰고,
      엑셀에 없는 날짜(2018-04 이전, 2026-09-22 이후)만 Yahoo Finance로 채운다.
      move_src 열이 날짜별 출처(file / yahoo)다. Yahoo는 비공식 경로라 막힐 수 있다.
"""
import csv, io, json, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

START = "2010-01-01"  # 2015년 시작 + 룩백 여유
DAILY = [("vix", "VIXCLS"), ("sofr", "SOFR"), ("effr", "EFFR"), ("iorb", "IORB"), ("ioer", "IOER"),
         ("rrp_bn", "RRPONTSYD"), ("hy_oas", "BAMLH0A0HYM2"), ("ig_oas", "BAMLC0A0CM"),
         ("baa_spread", "BAA10Y")]
WEEKLY = [("reserves_bn", "WRESBAL"), ("tga_bn", "WTREGEN"), ("nfci", "NFCI"), ("stlfsi", "STLFSI4")]
SCALE = {"reserves_bn": 1e-3, "tga_bn": 1e-3}  # FRED 원자료가 백만 달러 → 십억 달러
MOVE_FILE = "MOVE_index_daily_weekly.xlsx"  # 직접 받아 둔 MOVE (2018-04-02 ~ 2026-09-22)
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함
UA_BROWSER = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 "
                            "(KHTML, like Gecko) Version/17.0 Safari/605.1.15"}


def get(url, headers=UA, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
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


def fetch(series):
    rows = {}  # 'YYYY-MM-DD' -> {name: value}
    for name, fid in series:
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={START}")
        k = SCALE.get(name, 1)
        for r in csv.DictReader(io.StringIO(text)):
            v = num(r.get(fid))
            if v is not None:
                rows.setdefault(r.get("observation_date") or r.get("DATE"), {})[name] = round(v * k, 4)
        print(f"  {fid} ok", file=sys.stderr)
    return rows


def fetch_move():
    """Yahoo Finance ^MOVE 일별 종가. yfinance가 있으면 그것을 쓰고(직접 호출은 429로 자주 막힘),
    없으면 직접 호출한다. 둘 다 실패하면 빈 dict."""
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import yfinance as yf
        h = yf.Ticker("^MOVE").history(start=START, auto_adjust=False)["Close"].dropna()
        if len(h):
            print("  ^MOVE ok (yfinance)", file=sys.stderr)
            return {d.strftime("%Y-%m-%d"): round(float(v), 2) for d, v in h.items()}
    except Exception as e:
        print(f"  yfinance 실패({e}) → 직접 호출 시도", file=sys.stderr)
    p1 = int(datetime.strptime(START, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/%5EMOVE"
           f"?period1={p1}&period2={int(time.time())}&interval=1d")
    try:
        res = json.loads(get(url, headers=UA_BROWSER))["chart"]["result"][0]
        closes = res["indicators"]["quote"][0]["close"]
        out = {}
        for ts, c in zip(res["timestamp"], closes):
            if c is not None:
                out[datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")] = round(c, 2)
        print("  ^MOVE ok", file=sys.stderr)
        return out
    except Exception as e:
        print(f"  ^MOVE 실패({e}) → MOVE 열은 비워 둠", file=sys.stderr)
        return {}


def read_move_file(path):
    """직접 받아 둔 MOVE 엑셀('daily' 시트: Date, 현재가). 없거나 못 읽으면 빈 dict."""
    if not path.exists():
        return {}
    try:
        import warnings
        warnings.filterwarnings("ignore")
        import openpyxl
        ws = openpyxl.load_workbook(path, data_only=True)["daily"]
        out = {r[0].strftime("%Y-%m-%d"): round(float(r[1]), 2)
               for r in ws.iter_rows(min_row=2, values_only=True) if r[0] and r[1] is not None}
        print(f"  {path.name} ok ({len(out)}일)", file=sys.stderr)
        return out
    except Exception as e:
        print(f"  {path.name} 읽기 실패({e})", file=sys.stderr)
        return {}


def main():
    here = Path(__file__).parent
    d_rows, w_rows = fetch(DAILY), fetch(WEEKLY)
    # MOVE: 직접 받은 엑셀이 우선, 엑셀에 없는 날짜만 Yahoo로 채운다
    # (Yahoo는 2023-03-15, 2023-06-20 두 날의 값이 엑셀과 다르다)
    own = read_move_file(here / MOVE_FILE)
    for d, v in {**fetch_move(), **own}.items():
        d_rows.setdefault(d, {})["move"] = v
        d_rows[d]["move_src"] = "file" if d in own else "yahoo"

    # 준비금 금리: IORB가 있으면 IORB, 없으면 그 전 제도인 IOER
    for d, r in d_rows.items():
        rate = r.get("iorb", r.get("ioer"))
        if rate is None:
            continue
        r["reserve_rate"] = rate
        for name in ("sofr", "effr"):
            if r.get(name) is not None:
                r[f"{name}_minus_rr_bp"] = round((r[name] - rate) * 100, 1)

    d_cols = ["vix", "move", "move_src", "sofr", "effr", "reserve_rate", "sofr_minus_rr_bp", "effr_minus_rr_bp",
              "rrp_bn", "hy_oas", "ig_oas", "baa_spread"]
    w_cols = [n for n, _ in WEEKLY]
    # 준비금 금리는 주말·공휴일에도 값이 있으므로, 다른 시장 지표가 하나라도 있는 날만 남긴다
    market = [c for c in d_cols if c != "reserve_rate"]
    d_dates = sorted(d for d in d_rows if any(d_rows[d].get(c) is not None for c in market))
    w_dates = sorted(w_rows)
    daily = {c: [d_rows[d].get(c) for d in d_dates] for c in d_cols}
    weekly = {c: [w_rows[d].get(c) for d in w_dates] for c in w_cols}

    for path, dates, cols, table in ((here / "liquidity_daily.csv", d_dates, d_cols, daily),
                                     (here / "liquidity_weekly.csv", w_dates, w_cols, weekly)):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date"] + cols)
            for i, d in enumerate(dates):
                w.writerow([d] + ["" if table[c][i] is None else table[c][i] for c in cols])

    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FRED (Federal Reserve, NY Fed, Cboe, ICE BofA), Yahoo Finance (ICE BofA MOVE)",
        "series": {**{n: f for n, f in DAILY + WEEKLY}, "move": "^MOVE (Yahoo Finance)"},
        "daily": {"dates": d_dates, **daily},
        "weekly": {"dates": w_dates, **weekly},
    }
    js = "window.LIQUIDITY_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n"
    (here / "data.js").write_text(js, encoding="utf-8")

    for label, dates, cols, table in (("일별", d_dates, d_cols, daily), ("주별", w_dates, w_cols, weekly)):
        for c in cols:
            have = [d for d, v in zip(dates, table[c]) if v is not None]
            if have:
                print(f"{c:17s} {label} {len(have):5d}개  {have[0]} ~ {have[-1]}  최신값 {table[c][dates.index(have[-1])]}")
            else:
                print(f"{c:17s} {label}     0개  (받지 못함)")

    policy_rate(here)
    if "--no-analyze" not in sys.argv and (here / "analyze.py").exists():
        sys.dont_write_bytecode = True   # __pycache__ 폴더를 만들지 않는다
        import analyze
        analyze.main()


def policy_rate(here):
    """정책금리 상단이 바뀐 날짜만 저장 (국면 구분용, 03_inflation과 같은 형식)."""
    text = get("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU&cosd=2008-12-16")
    rows, prev = [], None
    for r in csv.DictReader(io.StringIO(text)):
        v = num(r.get("DFEDTARU"))
        if v is not None and v != prev:
            rows.append([r.get("observation_date") or r.get("DATE"), v])
            prev = v
    with open(here / "policy_rate.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "upper"])
        w.writerows(rows)
    print(f"policy            변경 {len(rows) - 1}회, 현재 상단 {rows[-1][1]}% ({rows[-1][0]}~)")


if __name__ == "__main__":
    main()
