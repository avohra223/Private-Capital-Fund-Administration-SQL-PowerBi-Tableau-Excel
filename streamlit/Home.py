import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from db.load_data import init_db, query_df

# Initialize database on first run
init_db()

st.set_page_config(
    page_title="Private Markets Fund Administration",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.sidebar.markdown("### Private Markets\n### Fund Administration")
st.sidebar.markdown("---")
st.sidebar.caption("Akhil Vohra | Data & Reporting Analyst")

st.title("Private Markets Fund Administration Dashboard")
st.markdown("---")

# --- Summary KPIs ---
funds = query_df("SELECT * FROM Funds")
total_aum = funds["Fund_Size"].sum()
num_funds = len(funds)
num_investors = query_df("SELECT COUNT(DISTINCT Investor_ID) AS n FROM Investors")["n"][0]
num_txns = query_df("SELECT COUNT(*) AS n FROM Transactions")["n"][0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total AUM", f"${total_aum / 1e9:.2f}B")
c2.metric("Funds", num_funds)
c3.metric("Investors (LPs)", num_investors)
c4.metric("Transactions", num_txns)

st.markdown("---")

# --- Fund Summary Table ---
st.subheader("Fund Register")
fund_display = funds[["Fund_Name", "Strategy", "Vintage_Year", "Base_Currency", "Fund_Size", "Mgmt_Fee_Rate", "Carry_Rate"]].copy()
fund_display["Fund_Size"] = fund_display["Fund_Size"].apply(lambda x: f"${x/1e6:,.0f}M")
fund_display["Mgmt_Fee_Rate"] = fund_display["Mgmt_Fee_Rate"].apply(lambda x: f"{x:.1%}")
fund_display["Carry_Rate"] = fund_display["Carry_Rate"].apply(lambda x: f"{x:.0%}")
fund_display.columns = ["Fund", "Strategy", "Vintage", "Currency", "Size", "Mgmt Fee", "Carry"]
st.dataframe(fund_display, use_container_width=True, hide_index=True)

st.markdown("---")

st.markdown(
    """
**Navigate using the sidebar** to explore:
- **LP Portfolio Explorer** — Drill into any investor's cross-fund position
- **Cash Flow & J-Curve** — Interactive J-curve analysis with Above/Below Water status
- **FX Exposure Analytics** — Currency risk and FX impact on transactions
- **Data Quality Monitor** — Automated operational audit with health checks

*Built with Python, Streamlit, SQLite, pandas & Plotly.*
"""
)
