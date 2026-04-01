import streamlit as st
import sys, os
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.load_data import query_df, load_sheet

st.title("FX Exposure Analytics")
st.markdown("Analyze currency exposure, FX rate trends, and the impact of exchange rate movements on fund transactions.")
st.markdown("---")

# --- FX rate trends (SQL) ---
fx_rates = query_df("""
    SELECT Date, From_Currency, To_Currency, FX_Rate,
           From_Currency || '/' || To_Currency AS Pair
    FROM FX_Rates
    ORDER BY Date
""")
fx_rates["Date"] = pd.to_datetime(fx_rates["Date"])

# --- Transaction currency breakdown (SQL) ---
currency_volume = query_df("""
    SELECT Txn_Currency,
           COUNT(*) AS Txn_Count,
           SUM(Amount_Fund_Base) AS Total_Volume
    FROM Transactions
    GROUP BY Txn_Currency
    ORDER BY Total_Volume DESC
""")

# --- Sidebar filters ---
pairs = fx_rates["Pair"].unique().tolist()
selected_pair = st.sidebar.multiselect("Currency Pairs", pairs, default=pairs)

# --- KPIs ---
non_usd_txns = query_df("SELECT COUNT(*) AS n FROM Transactions WHERE Txn_Currency != 'USD'")["n"][0]
total_txns = query_df("SELECT COUNT(*) AS n FROM Transactions")["n"][0]
fx_pct = non_usd_txns / total_txns * 100 if total_txns > 0 else 0
currencies_used = query_df("SELECT COUNT(DISTINCT Txn_Currency) AS n FROM Transactions")["n"][0]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Currencies Used", currencies_used)
c2.metric("FX Transactions", non_usd_txns)
c3.metric("% FX Exposure", f"{fx_pct:.1f}%")
c4.metric("FX Rate Observations", len(fx_rates))

st.markdown("---")

# --- FX Rate Trends ---
st.subheader("FX Rate Trends Over Time")
filtered_fx = fx_rates[fx_rates["Pair"].isin(selected_pair)]
fig_fx = px.line(
    filtered_fx, x="Date", y="FX_Rate", color="Pair",
    labels={"FX_Rate": "Exchange Rate", "Date": ""},
    color_discrete_sequence=px.colors.qualitative.Set2,
)
fig_fx.update_layout(height=400, legend=dict(orientation="h", yanchor="bottom", y=1.02))
st.plotly_chart(fig_fx, use_container_width=True)

# --- Currency volume breakdown ---
col1, col2 = st.columns(2)

with col1:
    st.subheader("Transaction Volume by Currency")
    fig_pie = px.pie(
        currency_volume, values="Total_Volume", names="Txn_Currency",
        color_discrete_sequence=px.colors.qualitative.Set2,
        hole=0.4,
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    fig_pie.update_layout(height=400)
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    st.subheader("Transaction Count by Currency")
    fig_bar = px.bar(
        currency_volume, x="Txn_Currency", y="Txn_Count",
        color="Txn_Currency", text="Txn_Count",
        labels={"Txn_Count": "# Transactions", "Txn_Currency": "Currency"},
        color_discrete_sequence=px.colors.qualitative.Set2,
    )
    fig_bar.update_traces(textposition="outside")
    fig_bar.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig_bar, use_container_width=True)

st.markdown("---")

# --- FX Impact Analysis (pandas) ---
st.subheader("FX Impact Analysis")
st.markdown("Estimated translation impact: difference between transacting at actual FX rate vs. rate of 1.0 (no conversion).")

txns = load_sheet("Transactions")
txns["Txn_Date"] = pd.to_datetime(txns["Txn_Date"])
fx_txns = txns[txns["Txn_Currency"] != "USD"].copy()

if len(fx_txns) > 0:
    fx_txns["FX_Impact"] = fx_txns["Amount_Fund_Base"] - fx_txns["Amount_Local"]
    fx_txns["FX_Impact_Abs"] = fx_txns["FX_Impact"].abs()
    fx_txns = fx_txns.sort_values("FX_Impact_Abs", ascending=False)

    # Summary by currency
    impact_summary = fx_txns.groupby("Txn_Currency").agg(
        Txn_Count=("Txn_ID", "count"),
        Total_Local=("Amount_Local", "sum"),
        Total_Fund_Base=("Amount_Fund_Base", "sum"),
        Net_FX_Impact=("FX_Impact", "sum"),
        Avg_FX_Rate=("FX_To_Fund_Base", "mean"),
    ).reset_index()

    st.dataframe(
        impact_summary.style.format({
            "Total_Local": "${:,.0f}",
            "Total_Fund_Base": "${:,.0f}",
            "Net_FX_Impact": "${:,.0f}",
            "Avg_FX_Rate": "{:.4f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # Top FX impact transactions
    st.subheader("Transactions with Largest FX Impact")
    top_fx = fx_txns.head(15)[["Txn_ID", "Fund_ID", "Investor_ID", "Txn_Date", "Txn_Type",
                                "Amount_Local", "Txn_Currency", "FX_To_Fund_Base",
                                "Amount_Fund_Base", "FX_Impact"]].copy()
    top_fx["Txn_Date"] = top_fx["Txn_Date"].dt.strftime("%Y-%m-%d")
    st.dataframe(
        top_fx.style.format({
            "Amount_Local": "${:,.0f}",
            "Amount_Fund_Base": "${:,.0f}",
            "FX_Impact": "${:,.0f}",
            "FX_To_Fund_Base": "{:.4f}",
        }),
        use_container_width=True, hide_index=True,
    )

    # FX impact over time
    st.subheader("FX Impact Over Time")
    fx_txns["Quarter"] = fx_txns["Txn_Date"].dt.to_period("Q").astype(str)
    quarterly_impact = fx_txns.groupby("Quarter")["FX_Impact"].sum().reset_index()
    fig_impact = px.bar(
        quarterly_impact, x="Quarter", y="FX_Impact",
        labels={"FX_Impact": "Net FX Impact ($)", "Quarter": ""},
        color="FX_Impact",
        color_continuous_scale=["#ef553b", "#f0f0f0", "#00cc96"],
        color_continuous_midpoint=0,
    )
    fig_impact.update_layout(height=350, yaxis_tickformat="$,.0f")
    st.plotly_chart(fig_impact, use_container_width=True)
else:
    st.info("No non-USD transactions found in the dataset.")
