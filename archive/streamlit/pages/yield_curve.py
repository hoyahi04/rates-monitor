from pathlib import Path

import pandas as pd
import streamlit as st

from src.data import CURVE_TENORS, fetch_meta, indicators, load_curve

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "treasury_yields_sample.csv"
SAMPLE_COLUMNS = {"3M": "ust_3m", "2Y": "ust_2y", "5Y": "ust_5y", "10Y": "ust_10y", "20Y": "ust_20y", "30Y": "ust_30y"}

st.title("01 수익률곡선")

yields = load_curve()
if yields.empty:
    # 아직 `python -m src.fetch`를 실행하지 않았으면 2024년 11월 표본으로 동작한다.
    yields = pd.read_csv(SAMPLE_PATH, index_col="date", parse_dates=["date"]).rename(columns=SAMPLE_COLUMNS)
    st.warning("data/raw에 수집 데이터가 없어 2024년 11월 표본을 표시한다. `python -m src.fetch`를 먼저 실행한다.")
    source_note = "미국 재무부 파 수익률 표본"
else:
    fetched = fetch_meta().get("ust_10y", {}).get("fetched_at", "?")
    source_note = f"FRED 재무부 CMT 수익률 · 수집 시각 {fetched} (UTC)"
st.caption(f"{source_note} · 금리 단위 %")

dates = [d.strftime("%Y-%m-%d") for d in yields.index]
as_of = st.selectbox("기준일", dates, index=len(dates) - 1)
default_cmp = max(0, len(dates) - 22)  # 기본 비교일: 약 1개월(22영업일) 전
comparison = st.selectbox("비교일", dates, index=min(default_cmp, len(dates) - 2))
as_of, comparison = pd.Timestamp(as_of), pd.Timestamp(comparison)

names = {k: v.name for k, v in indicators().items()}
tenors = [c for c in CURVE_TENORS if c in yields.columns]
curve = pd.DataFrame(
    {
        "만기(년)": [CURVE_TENORS[c] for c in tenors],
        "기준일": yields.loc[as_of, tenors].to_numpy(),
        "비교일": yields.loc[comparison, tenors].to_numpy(),
    }
)
st.line_chart(curve, x="만기(년)", y=["기준일", "비교일"], x_label="만기(년)", y_label="금리(%)")

spread_bp = (yields["ust_10y"] - yields["ust_2y"]) * 100
st.metric(
    "기준일 2s10s",
    f"{spread_bp.loc[as_of]:+.0f} bp",
    f"{spread_bp.loc[as_of] - spread_bp.loc[comparison]:+.0f} bp",
    help="10년물 금리에서 2년물 금리를 뺀 값. 델타는 비교일 대비 변화.",
)
table = yields.loc[list(dict.fromkeys([as_of, comparison])), tenors].rename(columns=names)
table.index = table.index.strftime("%Y-%m-%d")
st.dataframe(table, width="stretch")
st.markdown("[원본 데이터 · FRED Treasury Constant Maturity](https://fred.stlouisfed.org/categories/115)")
