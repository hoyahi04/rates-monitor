import streamlit as st

st.set_page_config(page_title="Y-FoRM Rates Monitor", layout="wide")

page = st.navigation(
    {
        "시장 모니터링": [
            st.Page("pages/yield_curve.py", title="01 수익률곡선", default=True),
            st.Page("pages/yield_decomposition.py", title="02 금리 분해"),
            st.Page("pages/auction.py", title="03 국채 경매"),
            st.Page("pages/supply.py", title="04 국채 수급"),
            st.Page("pages/monetary_policy.py", title="05 통화정책"),
        ],
        "전략과 성과": [
            st.Page("pages/strategy.py", title="06 상대가치·포지셔닝"),
            st.Page("pages/risk.py", title="07 포트폴리오·리스크"),
        ],
    }
)

with st.sidebar.expander("Market Event Calendar · 작업 예정"):
    st.write("FOMC, CPI·PCE, 고용, 국채 경매 및 Quarterly Refunding")

page.run()
