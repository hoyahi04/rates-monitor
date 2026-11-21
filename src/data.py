"""앱 페이지에서 쓰는 데이터 로더. 페이지는 원천을 몰라도 id로 지표를 불러온다."""

from __future__ import annotations

import json

import pandas as pd

from src.config import RAW_DIR, Indicator, load_config

# 수익률곡선 지표 id와 만기(년)
CURVE_TENORS: dict[str, float] = {
    "ust_1m": 1 / 12, "ust_3m": 0.25, "ust_6m": 0.5, "ust_1y": 1, "ust_2y": 2, "ust_3y": 3,
    "ust_5y": 5, "ust_7y": 7, "ust_10y": 10, "ust_20y": 20, "ust_30y": 30,
}


def indicators() -> dict[str, Indicator]:
    return {ind.id: ind for ind in load_config()[1]}


def load_series(indicator_id: str) -> pd.Series:
    """지표 하나를 date 인덱스 Series로 읽는다. 파일이 없거나 비어 있으면 빈 Series."""
    ind = indicators()[indicator_id]
    if not ind.path.exists():
        return pd.Series(dtype=float, name=indicator_id)
    df = pd.read_csv(ind.path, parse_dates=["date"])
    return df.set_index("date")["value"].rename(indicator_id).sort_index()


def load_many(indicator_ids: list[str]) -> pd.DataFrame:
    return pd.concat([load_series(i) for i in indicator_ids], axis=1)


def load_curve() -> pd.DataFrame:
    """행은 날짜, 열은 만기 id인 수익률곡선. 모든 만기가 빈 날은 제외."""
    return load_many(list(CURVE_TENORS)).dropna(how="all")


def fetch_meta() -> dict:
    path = RAW_DIR / "_meta.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
