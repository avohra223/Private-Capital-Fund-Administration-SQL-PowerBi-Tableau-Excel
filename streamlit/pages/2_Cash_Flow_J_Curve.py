import streamlit as st
import sys, os
import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.load_data import query_df, load_sheet

st.title("Cash Flow & J-Curve Analysis")
st.markdown(
    "Fund-level cash flow analysis. **Capital calls and management fees are inflows (+)** to the fund; "
    "**distributions and expenses are outflows (-)** from the fund."
)
st.markdown("---")

# --- Fund selector ---
funds = query_df("SELECT Fund_ID, Fund_Name FROM Funds ORDER BY Fund_Name")
fund_options = {"All Funds": "ALL"} | dict(zip(funds["Fund_Name"], funds["Fund_ID"]))
selected_fund = st.sidebar.selectbox("Select Fund", list(fund_options.keys()))
fund_filter = fund_options[selected_fund]

# --- Build quarterly cash flow data (SQL + pandas) ---
if fund_filter == "ALL":
    txn_sql = """
        SELECT t.Txn_Date, t.Txn_Type,
               SUM(t.Amount_Fund_Base) AS Amount,
               f.Fund_Name,
               i.Investor_Name
        FROM Transactions t
        JOIN Funds f ON t.Fund_ID = f.Fund_ID
        JOIN Investors i ON t.Investor_ID = i.Investor_ID
        GROUP BY t.Txn_Date, t.Txn_Type
        ORDER BY t.Txn_Date
    """
    nav_sql = """
        SELECT Quarter_End_Date,
               SUM(Net_NAV_Fund_Base) AS Net_NAV,
               SUM(Total_Called_To_Date) AS Called_To_Date,
               SUM(Total_Distributed_To_Date) AS Distributed_To_Date
        FROM NAV_Quarterly
        GROUP BY Quarter_End_Date
        ORDER BY Quarter_End_Date
    """
else:
    txn_sql = f"""
        SELECT t.Txn_Date, t.Txn_Type,
               SUM(t.Amount_Fund_Base) AS Amount,
               f.Fund_Name,
               i.Investor_Name
        FROM Transactions t
        JOIN Funds f ON t.Fund_ID = f.Fund_ID
        JOIN Investors i ON t.Investor_ID = i.Investor_ID
        WHERE t.Fund_ID = '{fund_filter}'
        GROUP BY t.Txn_Date, t.Txn_Type
        ORDER BY t.Txn_Date
    """
    nav_sql = f"""
        SELECT Quarter_End_Date, Net_NAV_Fund_Base AS Net_NAV,
               Total_Called_To_Date AS Called_To_Date,
               Total_Distributed_To_Date AS Distributed_To_Date
        FROM NAV_Quarterly
        WHERE Fund_ID = '{fund_filter}'
        ORDER BY Quarter_End_Date
    """

txns = query_df(txn_sql)
nav = query_df(nav_sql)

# --- Pandas transformations ---
txns["Txn_Date"] = pd.to_datetime(txns["Txn_Date"])
txns["Quarter"] = txns["Txn_Date"].dt.to_period("Q").dt.to_timestamp()

quarterly = txns.groupby(["Quarter", "Txn_Type"])["Amount"].sum().unstack(fill_value=0).reset_index()
for col in ["Capital Call", "Distribution", "Management Fee", "Other Expense"]:
    if col not in quarterly.columns:
        quarterly[col] = 0

# FUND PERSPECTIVE:
#   Capital Calls    = LP contributions flowing IN   (+)
#   Management Fees  = Fee income from LPs flowing IN (+)
#   Distributions    = Returns paid OUT to LPs       (-)
#   Other Expenses   = Fund operating costs OUT      (-)
quarterly["Net_CF"] = (
    quarterly["Capital Call"].abs()             # contributions IN  (+)
    + quarterly["Management Fee"].abs()         # fee income IN     (+)
    - quarterly["Distribution"].abs()           # distributions OUT (-)
    - quarterly["Other Expense"].abs()          # expenses OUT      (-)
)
quarterly["Cumulative_CF"] = quarterly["Net_CF"].cumsum()
quarterly["Status"] = quarterly["Cumulative_CF"].apply(
    lambda x: "Above Water" if x >= 0 else "Below Water"
)

# Clean quarter labels
quarterly["Q_Label"] = quarterly["Quarter"].dt.to_period("Q").astype(str)

# --- KPI cards ---
deepest_cf = quarterly["Cumulative_CF"].min()
current_cf = quarterly["Cumulative_CF"].iloc[-1] if len(quarterly) > 0 else 0
total_called = quarterly["Capital Call"].abs().sum()
total_distributed = quarterly["Distribution"].abs().sum()

nav["Quarter_End_Date"] = pd.to_datetime(nav["Quarter_End_Date"])
latest_nav = nav.iloc[-1] if len(nav) > 0 else None

c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Called (Inflows)", f"${total_called/1e6:,.1f}M")
c2.metric("Total Distributed (Outflows)", f"${total_distributed/1e6:,.1f}M")
c3.metric("Latest NAV", f"${latest_nav['Net_NAV']/1e6:,.1f}M" if latest_nav is not None else "N/A")
c4.metric("Current Net CF", f"${current_cf/1e6:,.1f}M")

st.markdown("---")

# --- J-Curve chart ---
st.subheader("J-Curve: Cumulative Net Cash Flow (Fund Perspective)")

positive = quarterly[quarterly["Cumulative_CF"] >= 0]
negative = quarterly[quarterly["Cumulative_CF"] < 0]

fig_jcurve = go.Figure()
if len(negative) > 0:
    fig_jcurve.add_trace(go.Scatter(
        x=negative["Quarter"], y=negative["Cumulative_CF"],
        mode="lines+markers", line=dict(color="#ef553b", width=2),
        name="Below Water", fill="tozeroy",
        fillcolor="rgba(239,85,59,0.2)",
    ))
if len(positive) > 0:
    fig_jcurve.add_trace(go.Scatter(
        x=positive["Quarter"], y=positive["Cumulative_CF"],
        mode="lines+markers", line=dict(color="#00cc96", width=2),
        name="Above Water", fill="tozeroy",
        fillcolor="rgba(0,204,150,0.2)",
    ))

fig_jcurve.add_trace(go.Scatter(
    x=quarterly["Quarter"], y=quarterly["Cumulative_CF"],
    mode="lines+markers", line=dict(color="#636efa", width=3),
    name="Cumulative Net CF",
))

fig_jcurve.add_hline(y=0, line_dash="dash", line_color="gray", annotation_text="Breakeven")
fig_jcurve.update_layout(
    height=450, xaxis_title="Quarter", yaxis_title="Cumulative Net Cash Flow ($)",
    yaxis_tickformat="$,.0f", legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_jcurve, use_container_width=True)

# --- Quarterly inflow/outflow bar chart (fund perspective) ---
st.subheader("Quarterly Cash Inflows vs Outflows")

fig_waterfall = go.Figure()
fig_waterfall.add_trace(go.Bar(
    x=quarterly["Q_Label"],
    y=quarterly["Capital Call"].abs(),
    name="Capital Calls (In)",
    marker_color="#00cc96",
))
fig_waterfall.add_trace(go.Bar(
    x=quarterly["Q_Label"],
    y=quarterly["Management Fee"].abs(),
    name="Management Fees (In)",
    marker_color="#636efa",
))
fig_waterfall.add_trace(go.Bar(
    x=quarterly["Q_Label"],
    y=-quarterly["Distribution"].abs(),
    name="Distributions (Out)",
    marker_color="#ef553b",
))
if quarterly["Other Expense"].abs().sum() > 0:
    fig_waterfall.add_trace(go.Bar(
        x=quarterly["Q_Label"],
        y=-quarterly["Other Expense"].abs(),
        name="Other Expenses (Out)",
        marker_color="#ffa15a",
    ))

fig_waterfall.update_layout(
    barmode="relative", height=400,
    xaxis_title="Quarter", yaxis_title="Cash Flow ($)",
    yaxis_tickformat="$,.0f",
    legend=dict(orientation="h", yanchor="bottom", y=1.02),
)
st.plotly_chart(fig_waterfall, use_container_width=True)

# --- Quarterly detail table ---
st.subheader("Quarterly Detail")
detail = quarterly[["Q_Label", "Capital Call", "Distribution", "Management Fee", "Other Expense", "Net_CF", "Cumulative_CF", "Status"]].copy()

# Format: calls and fees positive (inflows), distributions and expenses negative (outflows)
detail["Capital Call"] = detail["Capital Call"].abs().apply(lambda x: f"${x/1e6:,.1f}M")
detail["Management Fee"] = detail["Management Fee"].abs().apply(lambda x: f"${x/1e6:,.1f}M")
detail["Distribution"] = detail["Distribution"].abs().apply(lambda x: f"-${x/1e6:,.1f}M" if x > 0 else "$0.0M")
detail["Other Expense"] = detail["Other Expense"].abs().apply(lambda x: f"-${x/1e6:,.1f}M" if x > 0 else "$0.0M")
detail["Net_CF"] = detail["Net_CF"].apply(lambda x: f"${x/1e6:,.1f}M")
detail["Cumulative_CF"] = detail["Cumulative_CF"].apply(lambda x: f"${x/1e6:,.1f}M")

detail.columns = ["Quarter", "Calls (+)", "Distributions (-)", "Fees (+)", "Expenses (-)", "Net CF", "Cumulative CF", "Status"]
st.dataframe(detail, use_container_width=True, hide_index=True)
