import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import json
import os

st.set_page_config(page_title="Quant Momentum Portfolio", layout="wide")
st.title("📈 52W High Breakout Quant Momentum Portfolio")

if not os.path.exists("portfolio.json") or not os.path.exists("performance_history.csv"):
    st.info("System initializing. Trigger the GitHub Action workflow once to generate live portfolio logs.")
    st.stop()

with open("portfolio.json", "r") as f:
    state = json.load(f)

df_perf = pd.read_csv("performance_history.csv")
df_holdings = pd.read_csv("current_holdings.csv") if os.path.exists("current_holdings.csv") else pd.DataFrame()
df_trades = pd.read_csv("trade_log.csv") if os.path.exists("trade_log.csv") else pd.DataFrame()

cur_val = df_perf['Portfolio_Value'].iloc[-1]
init_val = state.get("initial_capital", 500000.0)
tot_ret = ((cur_val - init_val) / init_val) * 100

col1, col2, col3, col4 = st.columns(4)
col1.metric("Portfolio Value", f"₹{cur_val:,.2f}", f"{tot_ret:+.2f}%")
col2.metric("Available Cash", f"₹{state['cash']:,.2f}")
col3.metric("Active Holdings", f"{len(df_holdings)} / 10")
col4.metric("Total Trades", len(df_trades))

st.subheader("Portfolio Growth Curve")
fig = go.Figure()
fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Portfolio_Value'], mode='lines+markers', name='Portfolio Value', line=dict(color='#00E676', width=3)))
fig.update_layout(template="plotly_dark", xaxis_title="Date", yaxis_title="Equity (INR)", height=400)
st.plotly_chart(fig, use_container_width=True)

c1, c2 = st.columns(2)
with c1:
    st.subheader("Current Holdings")
    st.dataframe(df_holdings, use_container_width=True)

with c2:
    st.subheader("Recent Closed Trades")
    st.dataframe(df_trades, use_container_width=True)
