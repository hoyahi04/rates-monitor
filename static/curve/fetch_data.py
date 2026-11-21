"""Tab 1 데이터 수집: 미 국채 CMT(Par) 금리 일별 시계열 → data.js

소스
  1) FRED (H.15 / Treasury CMT) : 1990-01-01 이후 장기 이력
  2) U.S. Treasury Daily Par Yield Curve (당해·전년) : FRED보다 1영업일 빠른 최신값으로 덮어씀
실행:  python3 fetch_data.py   (같은 폴더에 data.js 생성)
"""
import csv, io, json, sys, time, urllib.request
from datetime import date, datetime
from pathlib import Path

START = "1990-01-01"
# (라벨, 만기(년), FRED ID, Treasury CSV 컬럼)
TENORS = [
    ("1M", 1/12, "DGS1MO", "1 Mo"), ("3M", 0.25, "DGS3MO", "3 Mo"), ("6M", 0.5, "DGS6MO", "6 Mo"),
    ("1Y", 1, "DGS1", "1 Yr"), ("2Y", 2, "DGS2", "2 Yr"), ("3Y", 3, "DGS3", "3 Yr"),
    ("5Y", 5, "DGS5", "5 Yr"), ("7Y", 7, "DGS7", "7 Yr"), ("10Y", 10, "DGS10", "10 Yr"),
    ("20Y", 20, "DGS20", "20 Yr"), ("30Y", 30, "DGS30", "30 Yr"),
]
UA = {"User-Agent": "curl/8.7.1"}  # FRED는 브라우저형 UA를 지연/차단함


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


def main():
    rows = {}  # 'YYYY-MM-DD' -> {label: value}
    for lab, _, fid, _ in TENORS:  # 시리즈별로 받아야 타임아웃이 덜 남
        text = get(f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={fid}&cosd={START}")
        for r in csv.DictReader(io.StringIO(text)):
            v = num(r.get(fid))
            if v is not None:
                rows.setdefault(r.get("observation_date") or r.get("DATE"), {})[lab] = v
        print(f"  {fid} ok", file=sys.stderr)
    n_fred = len(rows)

    n_tsy = 0
    this_year = date.today().year
    for y in (this_year - 1, this_year):
        url = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
               f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve"
               f"&field_tdr_date_value={y}&page&_format=csv")
        try:
            text = get(url)
        except Exception as e:  # Treasury 실패 시 FRED만 사용
            print(f"[warn] Treasury {y} 실패: {e}", file=sys.stderr)
            continue
        for r in csv.DictReader(io.StringIO(text)):
            d = datetime.strptime(r["Date"], "%m/%d/%Y").strftime("%Y-%m-%d")
            vals = {lab: num(r.get(col)) for lab, _, _, col in TENORS}
            if any(v is not None for v in vals.values()):
                base = rows.get(d, {})
                base.update({k: v for k, v in vals.items() if v is not None})
                rows[d] = base
                n_tsy += 1

    dates = sorted(rows)
    out = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": "FRED (Treasury CMT, H.15) + U.S. Treasury Daily Par Yield Curve",
        "tenors": [{"label": l, "years": round(y, 4), "fred": f} for l, y, f, _ in TENORS],
        "dates": dates,
        "yields": {l: [rows[d].get(l) for d in dates] for l, *_ in TENORS},
    }
    js = "window.UST_DATA = " + json.dumps(out, separators=(",", ":")) + ";\n"
    p = Path(__file__).with_name("data.js")
    p.write_text(js, encoding="utf-8")
    print(f"FRED {n_fred}행, Treasury {n_tsy}행 병합 → {len(dates)}영업일 "
          f"({dates[0]} ~ {dates[-1]}), {p.stat().st_size/1e6:.2f} MB")


if __name__ == "__main__":
    main()
