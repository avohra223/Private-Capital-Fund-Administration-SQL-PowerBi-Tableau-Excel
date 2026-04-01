import streamlit as st
import sys, os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.load_data import query_df, load_sheet

st.title("LP Portfolio Explorer")
st.markdown("Select an investor to view their full cross-fund position, transaction history, and key metrics.")
st.markdown("---")

# --- Investor selector ---
investors = query_df("""
    SELECT Investor_ID, Investor_Name, Investor_Type, Country, Reporting_Currency
    FROM Investors
    ORDER BY CASE WHEN Investor_Name LIKE 'Caledonian%' THEN 0 ELSE 1 END, Investor_Name
""")
investor_options = dict(zip(investors["Investor_Name"], investors["Investor_ID"]))
selected_name = st.sidebar.selectbox("Select Investor", list(investor_options.keys()))
inv_id = investor_options[selected_name]
inv_row = investors[investors["Investor_ID"] == inv_id].iloc[0]

st.sidebar.markdown("---")
st.sidebar.markdown(f"**Type:** {inv_row['Investor_Type']}")
st.sidebar.markdown(f"**Country:** {inv_row['Country']}")
st.sidebar.markdown(f"**Currency:** {inv_row['Reporting_Currency']}")

# --- Per-fund breakdown (SQL) ---
breakdown = query_df("""
    WITH Called AS (
        SELECT Fund_ID, Investor_ID,
               SUM(CASE WHEN Txn_Type = 'Capital Call' THEN Amount_Fund_Base ELSE 0 END) AS Total_Called,
               SUM(CASE WHEN Txn_Type = 'Distribution' THEN Amount_Fund_Base ELSE 0 END) AS Total_Distributed,
               SUM(CASE WHEN Txn_Type = 'Management Fee' THEN Amount_Fund_Base ELSE 0 END) AS Total_Fees
        FROM Transactions
        WHERE Investor_ID = ?
        GROUP BY Fund_ID, Investor_ID
    )
    SELECT f.Fund_Name,
           c.Commitment_Amount,
           COALESCE(ca.Total_Called, 0) AS Total_Called,
           COALESCE(ca.Total_Distributed, 0) AS Total_Distributed,
           COALESCE(ca.Total_Fees, 0) AS Total_Fees,
           c.Commitment_Amount - COALESCE(ca.Total_Called, 0) AS Unfunded,
           ROUND(COALESCE(ca.Total_Called, 0) * 100.0 / c.Commitment_Amount, 1) AS Pct_Utilized
    FROM Commitments c
    JOIN Funds f ON c.Fund_ID = f.Fund_ID
    LEFT JOIN Called ca ON ca.Fund_ID = c.Fund_ID AND ca.Investor_ID = c.Investor_ID
    WHERE c.Investor_ID = ?
    ORDER BY f.Fund_Name
""", params=(inv_id, inv_id))

# --- KPI cards ---
total_committed = breakdown["Commitment_Amount"].sum()
total_called = breakdown["Total_Called"].sum()
total_distributed = breakdown["Total_Distributed"].sum()
total_fees = breakdown["Total_Fees"].sum()
net_position = total_distributed - total_called
dpi = total_distributed / total_called if total_called > 0 else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Committed", f"${total_committed/1e6:,.1f}M")
c2.metric("Called", f"${total_called/1e6:,.1f}M")
c3.metric("Distributed", f"${total_distributed/1e6:,.1f}M")
c4.metric("Net Cash Position", f"${net_position/1e6:,.1f}M")
c5.metric("Weighted DPI", f"{dpi:.3f}x")

st.markdown("---")

# --- Fund breakdown table ---
st.subheader("Per-Fund Breakdown")
display_df = breakdown.copy()
for col in ["Commitment_Amount", "Total_Called", "Total_Distributed", "Total_Fees", "Unfunded"]:
    display_df[col] = display_df[col].apply(lambda x: f"${x/1e6:,.1f}M")
display_df["Pct_Utilized"] = display_df["Pct_Utilized"].apply(lambda x: f"{x}%")
display_df.columns = ["Fund", "Committed", "Called", "Distributed", "Fees", "Unfunded", "% Utilized"]
st.dataframe(display_df, use_container_width=True, hide_index=True)

# --- Utilization bar chart ---
st.subheader("Commitment Utilization by Fund")
fig_util = px.bar(
    breakdown,
    x="Fund_Name",
    y="Pct_Utilized",
    color="Fund_Name",
    text="Pct_Utilized",
    labels={"Pct_Utilized": "% Utilized", "Fund_Name": ""},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_util.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
fig_util.update_layout(showlegend=False, yaxis_range=[0, 110], height=350)
st.plotly_chart(fig_util, use_container_width=True)

# --- Transaction timeline (pandas) ---
st.subheader("Transaction Timeline")
st.markdown(
    f"*LP perspective: capital calls/fees are **outflows (-)**, distributions are **inflows (+)** for {selected_name}.*"
)
txns = load_sheet("Transactions")
funds_lookup = load_sheet("Funds")[["Fund_ID", "Fund_Name"]]
txns = txns.merge(funds_lookup, on="Fund_ID", how="left")
txns = txns[txns["Investor_ID"] == inv_id].copy()
txns["Txn_Date"] = pd.to_datetime(txns["Txn_Date"])
txns = txns.sort_values("Txn_Date")

# Sign logic: Distributions are inflows (+), everything else is an outflow (-)
# Handle edge cases like negative capital calls (reversals) which flip sign
def signed_amount(row):
    amt = row["Amount_Fund_Base"]
    if row["Txn_Type"] == "Distribution":
        return abs(amt)  # always positive
    else:
        return -abs(amt)  # Capital Call, Management Fee, Other Expense always negative

txns["Display_Amount"] = txns.apply(signed_amount, axis=1)

color_map = {
    "Capital Call": "#ef553b",
    "Distribution": "#00cc96",
    "Management Fee": "#636efa",
    "Other Expense": "#ffa15a",
}

fig_txn = go.Figure()
for txn_type in txns["Txn_Type"].unique():
    subset = txns[txns["Txn_Type"] == txn_type]
    fig_txn.add_trace(go.Bar(
        x=subset["Txn_Date"],
        y=subset["Display_Amount"],
        name=txn_type,
        marker_color=color_map.get(txn_type, "#ab63fa"),
        width=86400000 * 20,  # 20 days in milliseconds for visible bars
        hovertemplate=(
            "<b>%{x|%Y-%m-%d}</b><br>"
            + txn_type + "<br>"
            + "Amount: %{customdata[0]}<br>"
            + "Fund: %{customdata[1]}<br>"
            + "Investor: %{customdata[2]}<br>"
            + "Currency: %{customdata[3]}<br>"
            + "Ref: %{customdata[4]}<extra></extra>"
        ),
        customdata=list(zip(
            subset["Amount_Fund_Base"].apply(lambda x: f"${abs(x):,.0f}"),
            subset["Fund_Name"],
            [selected_name] * len(subset),
            subset["Txn_Currency"],
            subset["Reference"],
        )),
    ))

fig_txn.update_layout(
    barmode="relative",
    height=400,
    xaxis_title="",
    yaxis_title="Amount ($)",
    yaxis_tickformat="$,.0f",
    legend_title="Transaction Type",
)
st.plotly_chart(fig_txn, use_container_width=True)

# --- Cumulative cash flow ---
st.subheader("Cumulative Net Cash Flow")
txns["Cash_Flow"] = txns.apply(signed_amount, axis=1)
txns["Cumulative_CF"] = txns["Cash_Flow"].cumsum()

fig_cum = go.Figure()
fig_cum.add_trace(go.Scatter(
    x=txns["Txn_Date"],
    y=txns["Cumulative_CF"],
    mode="lines+markers",
    line=dict(color="#636efa", width=2),
    name="Cumulative Net CF",
))
fig_cum.add_hline(y=0, line_dash="dash", line_color="gray")
fig_cum.update_layout(
    height=350,
    xaxis_title="",
    yaxis_title="Cumulative Net Cash Flow ($)",
    yaxis_tickformat="$,.0f",
)
st.plotly_chart(fig_cum, use_container_width=True)
