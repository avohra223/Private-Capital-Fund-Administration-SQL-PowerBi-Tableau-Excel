import streamlit as st
import sys, os
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from db.load_data import query_df, load_sheet

st.title("Data Quality Monitor")
st.markdown("Automated operational audit — continuous data integrity checks across the fund administration dataset.")
st.markdown("---")


def check_status(issue_count, warning_threshold=0, critical_threshold=1):
    if issue_count == 0:
        return "✅ PASS", "green"
    elif issue_count < critical_threshold:
        return "⚠️ WARNING", "orange"
    else:
        return "❌ FAIL", "red"


results = []

# ============================================================
# CHECK 1: Missing FX Rates
# ============================================================
missing_fx = query_df("""
    SELECT Txn_ID, Fund_ID, Investor_ID, Txn_Date, Txn_Type,
           Amount_Local, Txn_Currency, FX_To_Fund_Base
    FROM Transactions
    WHERE FX_To_Fund_Base IS NULL OR FX_To_Fund_Base = 0
""")
status, color = check_status(len(missing_fx), warning_threshold=0, critical_threshold=1)
results.append({
    "Check": "Missing FX Rates",
    "Description": "Transactions with NULL or zero exchange rates",
    "Issues": len(missing_fx),
    "Status": status,
    "color": color,
    "details": missing_fx,
})

# ============================================================
# CHECK 2: Over-Commitment Detection
# ============================================================
over_committed = query_df("""
    WITH Called AS (
        SELECT Fund_ID, Investor_ID,
               SUM(Amount_Fund_Base) AS Total_Called
        FROM Transactions
        WHERE Txn_Type = 'Capital Call'
        GROUP BY Fund_ID, Investor_ID
    )
    SELECT c.Fund_ID, c.Investor_ID,
           i.Investor_Name,
           c.Commitment_Amount,
           COALESCE(ca.Total_Called, 0) AS Total_Called,
           COALESCE(ca.Total_Called, 0) - c.Commitment_Amount AS Over_Called
    FROM Commitments c
    JOIN Investors i ON c.Investor_ID = i.Investor_ID
    LEFT JOIN Called ca ON ca.Fund_ID = c.Fund_ID AND ca.Investor_ID = c.Investor_ID
    WHERE COALESCE(ca.Total_Called, 0) > c.Commitment_Amount
""")
status, color = check_status(len(over_committed))
results.append({
    "Check": "Over-Commitment Detection",
    "Description": "LPs where total called capital exceeds commitment amount",
    "Issues": len(over_committed),
    "Status": status,
    "color": color,
    "details": over_committed,
})

# ============================================================
# CHECK 3: NAV Reconciliation
# ============================================================
nav_recon = query_df("""
    WITH Ledger AS (
        SELECT Fund_ID,
               SUM(CASE WHEN Txn_Type = 'Capital Call' THEN Amount_Fund_Base ELSE 0 END) AS Ledger_Called,
               SUM(CASE WHEN Txn_Type = 'Distribution' THEN Amount_Fund_Base ELSE 0 END) AS Ledger_Distributed
        FROM Transactions
        GROUP BY Fund_ID
    ),
    Latest_NAV AS (
        SELECT Fund_ID, Total_Called_To_Date, Total_Distributed_To_Date, Quarter_End_Date
        FROM NAV_Quarterly
        WHERE Quarter_End_Date = (SELECT MAX(Quarter_End_Date) FROM NAV_Quarterly n2 WHERE n2.Fund_ID = NAV_Quarterly.Fund_ID)
    )
    SELECT n.Fund_ID,
           f.Fund_Name,
           n.Total_Called_To_Date AS NAV_Called,
           l.Ledger_Called,
           n.Total_Called_To_Date - l.Ledger_Called AS Called_Variance,
           n.Total_Distributed_To_Date AS NAV_Distributed,
           l.Ledger_Distributed,
           n.Total_Distributed_To_Date - l.Ledger_Distributed AS Distributed_Variance
    FROM Latest_NAV n
    JOIN Funds f ON n.Fund_ID = f.Fund_ID
    JOIN Ledger l ON l.Fund_ID = n.Fund_ID
    WHERE ABS(n.Total_Called_To_Date - l.Ledger_Called) > 1
       OR ABS(n.Total_Distributed_To_Date - l.Ledger_Distributed) > 1
""")
status, color = check_status(len(nav_recon))
results.append({
    "Check": "NAV Reconciliation",
    "Description": "Mismatch between NAV-reported vs transaction ledger totals (tolerance: $1)",
    "Issues": len(nav_recon),
    "Status": status,
    "color": color,
    "details": nav_recon,
})

# ============================================================
# CHECK 4: Duplicate Transaction Detection
# ============================================================
duplicates = query_df("""
    SELECT Fund_ID, Investor_ID, Txn_Date, Txn_Type, Amount_Fund_Base,
           COUNT(*) AS Occurrences
    FROM Transactions
    GROUP BY Fund_ID, Investor_ID, Txn_Date, Txn_Type, Amount_Fund_Base
    HAVING COUNT(*) > 1
""")
status, color = check_status(len(duplicates))
results.append({
    "Check": "Duplicate Transaction Detection",
    "Description": "Transactions with identical fund, investor, date, type, and amount",
    "Issues": len(duplicates),
    "Status": status,
    "color": color,
    "details": duplicates,
})

# ============================================================
# CHECK 5: Date Integrity (pandas)
# ============================================================
txns = load_sheet("Transactions")
funds_df = load_sheet("Funds")
txns["Txn_Date"] = pd.to_datetime(txns["Txn_Date"])
funds_df["Final_Close_Date"] = pd.to_datetime(funds_df["Final_Close_Date"])

# Flag transactions before fund final close (should not exist — calls happen after close)
merged = txns.merge(funds_df[["Fund_ID", "Final_Close_Date", "Vintage_Year"]], on="Fund_ID", how="left")
merged["Fund_Inception"] = pd.to_datetime(merged["Vintage_Year"].astype(str) + "-01-01")
date_issues = merged[merged["Txn_Date"] < merged["Fund_Inception"]]
date_issues_display = date_issues[["Txn_ID", "Fund_ID", "Investor_ID", "Txn_Date", "Txn_Type", "Fund_Inception"]].copy()
date_issues_display["Txn_Date"] = date_issues_display["Txn_Date"].dt.strftime("%Y-%m-%d")
date_issues_display["Fund_Inception"] = date_issues_display["Fund_Inception"].dt.strftime("%Y-%m-%d")

status, color = check_status(len(date_issues))
results.append({
    "Check": "Date Integrity",
    "Description": "Transactions dated before fund inception year",
    "Issues": len(date_issues),
    "Status": status,
    "color": color,
    "details": date_issues_display,
})

# ============================================================
# OVERALL HEALTH SCORE
# ============================================================
total_checks = len(results)
passed = sum(1 for r in results if r["Issues"] == 0)
health_pct = passed / total_checks * 100

if health_pct == 100:
    health_color = "green"
    health_emoji = "✅"
elif health_pct >= 60:
    health_color = "orange"
    health_emoji = "⚠️"
else:
    health_color = "red"
    health_emoji = "❌"

c1, c2, c3 = st.columns([2, 1, 1])
c1.metric("Data Health Score", f"{health_emoji} {health_pct:.0f}%")
c2.metric("Checks Passed", f"{passed}/{total_checks}")
c3.metric("Issues Found", sum(r["Issues"] for r in results))

st.markdown("---")

# ============================================================
# CHECK RESULTS
# ============================================================
for r in results:
    with st.expander(f"{r['Status']}  **{r['Check']}** — {r['Issues']} issue(s)", expanded=(r["Issues"] > 0)):
        st.markdown(f"*{r['Description']}*")
        if r["Issues"] == 0:
            st.success("No issues detected.")
        else:
            st.warning(f"{r['Issues']} issue(s) detected. Review details below.")
            st.dataframe(r["details"], use_container_width=True, hide_index=True)

st.markdown("---")
st.caption("Checks run against SQLite database and raw Excel source. Governance controls mirror Power BI and Excel validation logic.")
