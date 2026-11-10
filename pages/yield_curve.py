from pathlib import Path

import pandas as pd
import streamlit as st

SAMPLE_PATH = Path(__file__).resolve().parents[1] / "data" / "treasury_yields_sample.csv"
TREASURY_SOURCE = (
    "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
    "TextView?field_tdr_date_value=202411&type=daily_treasury_yield_curve"
)

st.title("01 수익률곡선")
st.caption("2024년 11월 미국 국채 파 수익률 표본 · 금리 단위 %")

yields = pd.read_csv(SAMPLE_PATH, index_col="date").sort_index()
dates = yields.index.tolist()
as_of = st.selectbox("기준일", dates, index=len(dates) - 1)
comparison = st.selectbox("비교일", dates, index=len(dates) - 2)

curve = pd.DataFrame({"기준일": yields.loc[as_of], "비교일": yields.loc[comparison]})
curve.insert(0, "만기(개월)", [3, 24, 60, 120, 240, 360])
st.line_chart(curve, x="만기(개월)", y=["기준일", "비교일"], x_label="만기(개월)", y_label="금리(%)")

spread_bp = (yields["10Y"] - yields["2Y"]) * 100
st.metric(
    "기준일 2s10s",
    f"{spread_bp.loc[as_of]:+.0f} bp",
    f"{spread_bp.loc[as_of] - spread_bp.loc[comparison]:+.0f} bp",
    help="10년물 금리에서 2년물 금리를 뺀 값. 델타는 비교일 대비 변화.",
)
st.dataframe(yields.loc[list(dict.fromkeys([as_of, comparison]))], width="stretch")
st.markdown(f"[원본 데이터 · 미국 재무부]({TREASURY_SOURCE})")
