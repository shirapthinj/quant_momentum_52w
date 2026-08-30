import streamlit as st
import pandas as pd
import numpy as np
import yfinance as yf
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

# Portfolio metrics
cur_val = df_perf['Portfolio_Value'].iloc[-1]
init_val = state.get("initial_capital", 500000.0)
tot_ret = ((cur_val - init_val) / init_val) * 100

# Benchmark comparison calculations
if 'Nifty50_Price' in df_perf.columns and 'Nifty500_Price' in df_perf.columns:
    base_n50 = df_perf['Nifty50_Price'].dropna().iloc[0] if not df_perf['Nifty50_Price'].dropna().empty else 1.0
    base_n500 = df_perf['Nifty500_Price'].dropna().iloc[0] if not df_perf['Nifty500_Price'].dropna().empty else 1.0
    
    cur_n50 = df_perf['Nifty50_Price'].dropna().iloc[-1] if not df_perf['Nifty50_Price'].dropna().empty else base_n50
    cur_n500 = df_perf['Nifty500_Price'].dropna().iloc[-1] if not df_perf['Nifty500_Price'].dropna().empty else base_n500
    
    n50_ret = ((cur_n50 - base_n50) / base_n50) * 100
    n500_ret = ((cur_n500 - base_n500) / base_n500) * 100
else:
    n50_ret, n500_ret = 0.0, 0.0

col1, col2, col3, col4, col5 = st.columns(5)
col1.metric("Strategy Portfolio", f"₹{cur_val:,.2f}", f"{tot_ret:+.2f}%")
col2.metric("Nifty 50 Return", f"{n50_ret:+.2f}%")
col3.metric("Nifty 500 Return", f"{n500_ret:+.2f}%")
col4.metric("Available Cash", f"₹{state['cash']:,.2f}")
col5.metric("Active Holdings", f"{len(df_holdings)} / 10")

# Multi-Trace Normalized Performance Chart
st.subheader("Performance Comparison vs Benchmarks (%)")
fig = go.Figure()

# Portfolio % Return line
base_port = df_perf['Portfolio_Value'].iloc[0]
df_perf['Portfolio_Return_Pct'] = ((df_perf['Portfolio_Value'] - base_port) / base_port) * 100
fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Portfolio_Return_Pct'], mode='lines+markers', name='Strategy Portfolio', line=dict(color='#00E676', width=3)))

if 'Nifty50_Price' in df_perf.columns and not df_perf['Nifty50_Price'].dropna().empty:
    b50_base = df_perf['Nifty50_Price'].dropna().iloc[0]
    df_perf['Nifty50_Return_Pct'] = ((df_perf['Nifty50_Price'] - b50_base) / b50_base) * 100
    fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Nifty50_Return_Pct'], mode='lines+markers', name='Nifty 50', line=dict(color='#FFB74D', width=2, dash='dot')))

if 'Nifty500_Price' in df_perf.columns and not df_perf['Nifty500_Price'].dropna().empty:
    b500_base = df_perf['Nifty500_Price'].dropna().iloc[0]
    df_perf['Nifty500_Return_Pct'] = ((df_perf['Nifty500_Price'] - b500_base) / b500_base) * 100
    fig.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Nifty500_Return_Pct'], mode='lines+markers', name='Nifty 500', line=dict(color='#4FC3F7', width=2, dash='dot')))

fig.update_layout(template="plotly_dark", xaxis_title="Date", yaxis_title="Cumulative Return (%)", hovermode="x unified", height=400)
st.plotly_chart(fig, use_container_width=True)

# Fetch Live Individual Stock Prices & Calculate Live Stock P&L / Returns
if not df_holdings.empty:
    st.subheader("Current Holdings (Live Return Breakdown)")
    symbols = [f"{t}.NS" for t in df_holdings['Ticker']]
    
    try:
        live_data = yf.download(symbols, period="5d", progress=False)['Close']
        cur_prices, pnl_vals, pnl_pcts = [], [], []
        
        for idx, row in df_holdings.iterrows():
            sym = f"{row['Ticker']}.NS"
            if isinstance(live_data, pd.DataFrame) and sym in live_data.columns:
                c_p = live_data[sym].dropna().iloc[-1]
            elif isinstance(live_data, pd.Series) and sym in live_data.index:
                c_p = live_data[sym]
            else:
                c_p = row['Entry Price']
                
            cur_prices.append(round(c_p, 2))
            pnl_val = (c_p - row['Entry Price']) * row['Shares']
            pnl_pct = ((c_p - row['Entry Price']) / row['Entry Price']) * 100
            pnl_vals.append(round(pnl_val, 2))
            pnl_pcts.append(f"{pnl_pct:+.2f}%")
            
        df_holdings['Current Price'] = cur_prices
        df_holdings['P&L (₹)'] = pnl_vals
        df_holdings['Return (%)'] = pnl_pcts
    except Exception as e:
        st.warning(f"Could not update live prices: {e}")

c1, c2 = st.columns(2)
with c1:
    st.dataframe(df_holdings, use_container_width=True)

with c2:
    st.subheader("Recent Closed Trades")
    st.dataframe(df_trades, use_container_width=True)
