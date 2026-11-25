"""지표 데이터를 수집해 data/raw/<source>/<id>.csv(date,value)로 저장한다.

사용법 (저장소 루트에서)
    python -m src.fetch                 # 전체 FRED 지표 수집 + 수동 CSV 점검
    python -m src.fetch ust_10y sofr    # 일부 지표만
    python -m src.fetch --start 2020-01-01

FRED_API_KEY 환경변수가 있으면 FRED 공식 API를, 없으면 키 없이 쓰는
fredgraph CSV 주소를 사용한다. GitHub Actions에서는 Secrets의 FRED_API_KEY를 쓴다.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import pandas as pd

from src.config import MANUAL_DIR, RAW_DIR, Indicator, load_config

FRED_API = "https://api.stlouisfed.org/fred/series/observations"
FRED_CSV = "https://fred.stlouisfed.org/graph/fredgraph.csv"
META_PATH = RAW_DIR / "_meta.json"


def _get(url: str, retries: int = 3) -> bytes:
    # 사용자 지정 User-Agent를 붙이면 FRED가 연결을 끊는다. 기본값을 그대로 쓴다.
    req = urllib.request.Request(url)
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(2 * attempt)
    raise RuntimeError("unreachable")


def fetch_fred(ticker: str, start: str, api_key: str | None = None) -> pd.Series:
    """FRED 시리즈를 date 인덱스의 float Series로 돌려준다. 결측('.')은 버린다."""
    if api_key:
        query = urllib.parse.urlencode(
            {"series_id": ticker, "api_key": api_key, "file_type": "json", "observation_start": start}
        )
        obs = json.loads(_get(f"{FRED_API}?{query}"))["observations"]
        df = pd.DataFrame(obs)[["date", "value"]]
    else:
        query = urllib.parse.urlencode({"id": ticker, "cosd": start})
        df = pd.read_csv(io.BytesIO(_get(f"{FRED_CSV}?{query}")))
        df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna().set_index("date")["value"].sort_index()


def save_series(series: pd.Series, ind: Indicator) -> None:
    ind.path.parent.mkdir(parents=True, exist_ok=True)
    out = series.rename("value").to_frame()
    out.index = out.index.strftime("%Y-%m-%d")
    out.index.name = "date"
    out.to_csv(ind.path)


def ensure_manual_template(ind: Indicator) -> bool:
    """수동 지표 CSV가 없으면 머리글만 있는 빈 파일을 만든다. 데이터가 있으면 True."""
    if not ind.path.exists():
        MANUAL_DIR.mkdir(parents=True, exist_ok=True)
        ind.path.write_text("date,value\n", encoding="utf-8")
        return False
    return len(pd.read_csv(ind.path)) > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("ids", nargs="*", help="수집할 지표 id. 생략하면 전체")
    parser.add_argument("--start", help="수집 시작일 YYYY-MM-DD (기본값은 indicators.yaml의 defaults.start)")
    args = parser.parse_args(argv)

    defaults, indicators = load_config()
    if args.ids:
        unknown = set(args.ids) - {i.id for i in indicators}
        if unknown:
            parser.error(f"indicators.yaml에 없는 id: {', '.join(sorted(unknown))}")
        indicators = [i for i in indicators if i.id in args.ids]
    start = args.start or defaults.get("start", "2015-01-01")
    api_key = os.environ.get("FRED_API_KEY") or None

    meta = json.loads(META_PATH.read_text()) if META_PATH.exists() else {}
    failed: list[str] = []
    for ind in indicators:
        if ind.source == "fred":
            try:
                series = fetch_fred(ind.ticker, start, api_key)
                if series.empty:
                    raise ValueError("관측치가 없다")
                save_series(series, ind)
                meta[ind.id] = {
                    "source": "fred",
                    "ticker": ind.ticker,
                    "rows": int(len(series)),
                    "last_date": series.index[-1].strftime("%Y-%m-%d"),
                    "last_value": float(series.iloc[-1]),
                    "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                }
                print(f"[ok]     {ind.id:<12} {ind.ticker:<13} {len(series):>5}행  최근 {meta[ind.id]['last_date']} = {series.iloc[-1]:g}")
            except Exception as exc:  # 한 지표가 실패해도 나머지는 계속 받는다
                failed.append(ind.id)
                print(f"[fail]   {ind.id:<12} {ind.ticker:<13} {exc}", file=sys.stderr)
        elif ind.source == "manual":
            has_data = ensure_manual_template(ind)
            print(f"[manual] {ind.id:<12} {'데이터 있음' if has_data else '비어 있음 → ' + str(ind.path.relative_to(MANUAL_DIR.parents[1]))}")
        else:
            print(f"[skip]   {ind.id:<12} source={ind.source} 수집기 미구현")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if failed:
        print(f"\n실패 {len(failed)}건: {', '.join(failed)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
