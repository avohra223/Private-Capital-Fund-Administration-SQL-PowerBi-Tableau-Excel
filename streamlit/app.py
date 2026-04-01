import streamlit as st
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from db.load_data import init_db

# Initialize database on first run
init_db()

st.set_page_config(
    page_title="Private Markets Fund Administration",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --- Multi-page navigation with custom labels ---
home = st.Page("pages/0_Home.py", title="Home", icon="🏠", default=True)
lp_explorer = st.Page("pages/1_LP_Portfolio_Explorer.py", title="LP Portfolio Explorer", icon="👤")
cash_flow = st.Page("pages/2_Cash_Flow_J_Curve.py", title="Cash Flow J Curve", icon="📈")
fx_exposure = st.Page("pages/3_FX_Exposure_Analytics.py", title="FX Exposure Analytics", icon="💱")
data_quality = st.Page("pages/4_Data_Quality_Monitor.py", title="Data Quality Monitor", icon="🔍")

pg = st.navigation([home, lp_explorer, cash_flow, fx_exposure, data_quality])

st.sidebar.markdown("---")
st.sidebar.caption("Akhil Vohra | Data & Reporting Analyst")

pg.run()
