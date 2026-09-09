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

# Benchmark comparison & Index value calculations
if 'Nifty50_Price' in df_perf.columns and 'Nifty500_Price' in df_perf.columns:
    base_n50 = df_perf['Nifty50_Price'].dropna().iloc[0] if not df_perf['Nifty50_Price'].dropna().empty else 1.0
    base_n500 = df_perf['Nifty500_Price'].dropna().iloc[0] if not df_perf['Nifty500_Price'].dropna().empty else 1.0
    
    cur_n50 = df_perf['Nifty50_Price'].dropna().iloc[-1] if not df_perf['Nifty50_Price'].dropna().empty else base_n50
    cur_n500 = df_perf['Nifty500_Price'].dropna().iloc[-1] if not df_perf['Nifty500_Price'].dropna().empty else base_n500
    
    n50_ret = ((cur_n50 - base_n50) / base_n50) * 100
    n500_ret = ((cur_n500 - base_n500) / base_n500) * 100
else:
    cur_n50, cur_n500 = 0.0, 0.0
    n50_ret, n500_ret = 0.0, 0.0

# 1. KPI Metric Cards Layout (Matching Image 2)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Portfolio Value", f"₹{cur_val:,.2f}", f"{tot_ret:+.2f}%")
col2.metric("Available Cash", f"₹{state['cash']:,.2f}")
col3.metric("Nifty 50", f"{cur_n50:,.2f}" if cur_n50 > 0 else "N/A", f"{n50_ret:+.2f}%")
col4.metric("Nifty 500", f"{cur_n500:,.2f}" if cur_n500 > 0 else "N/A", f"{n500_ret:+.2f}%")

st.markdown("---")

# Fetch Live Individual Stock Prices
if not df_holdings.empty:
    symbols = [f"{t}.NS" for t in df_holdings['Ticker']]
    try:
        live_data = yf.download(symbols, period="5d", progress=False)['Close']
        cur_prices, pnl_vals, pnl_pcts, pnl_nums = [], [], [], []
        
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
            pnl_nums.append(round(pnl_pct, 2))
            
        df_holdings['Current Price'] = cur_prices
        df_holdings['P&L (₹)'] = pnl_vals
        df_holdings['Return (%)'] = pnl_pcts
        df_holdings['Return_Num'] = pnl_nums
    except Exception as e:
        st.warning(f"Could not update live prices: {e}")

# 2. Unrealized PnL (%) by Position Bar Chart (Matching Image 3)
if not df_holdings.empty and 'Return_Num' in df_holdings.columns:
    st.subheader("📊 Unrealized PnL (%) by Position")
    df_pnl_chart = df_holdings.sort_values(by="Return_Num", ascending=False).reset_index(drop=True)
    
    colors = ['#00E676' if val >= 0 else '#FF5252' for val in df_pnl_chart['Return_Num']]
    text_labels = [f"{val:+.2f}%" for val in df_pnl_chart['Return_Num']]
    
    fig_pnl = go.Figure()
    fig_pnl.add_trace(go.Bar(
        x=df_pnl_chart['Ticker'],
        y=df_pnl_chart['Return_Num'],
        text=text_labels,
        textposition='outside',
        marker_color=colors,
        cliponaxis=False
    ))
    
    fig_pnl.update_layout(
        template="plotly_dark",
        xaxis_title="",
        yaxis_title="",
        yaxis=dict(ticksuffix="%"),
        xaxis=dict(tickangle=-45),
        height=420,
        margin=dict(l=20, r=20, t=30, b=80),
        showlegend=False
    )
    st.plotly_chart(fig_pnl, use_container_width=True)

# 3. Multi-Trace Normalized Performance Chart vs Benchmarks
st.subheader("Performance Comparison vs Benchmarks (%)")
fig_perf = go.Figure()

base_port = df_perf['Portfolio_Value'].iloc[0]
df_perf['Portfolio_Return_Pct'] = ((df_perf['Portfolio_Value'] - base_port) / base_port) * 100
fig_perf.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Portfolio_Return_Pct'], mode='lines+markers', name='Strategy Portfolio', line=dict(color='#00E676', width=3)))

if 'Nifty50_Price' in df_perf.columns and not df_perf['Nifty50_Price'].dropna().empty:
    b50_base = df_perf['Nifty50_Price'].dropna().iloc[0]
    df_perf['Nifty50_Return_Pct'] = ((df_perf['Nifty50_Price'] - b50_base) / b50_base) * 100
    fig_perf.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Nifty50_Return_Pct'], mode='lines+markers', name='Nifty 50', line=dict(color='#FFB74D', width=2, dash='dot')))

if 'Nifty500_Price' in df_perf.columns and not df_perf['Nifty500_Price'].dropna().empty:
    b500_base = df_perf['Nifty500_Price'].dropna().iloc[0]
    df_perf['Nifty500_Return_Pct'] = ((df_perf['Nifty500_Price'] - b500_base) / b500_base) * 100
    fig_perf.add_trace(go.Scatter(x=df_perf['Date'], y=df_perf['Nifty500_Return_Pct'], mode='lines+markers', name='Nifty 500', line=dict(color='#4FC3F7', width=2, dash='dot')))

fig_perf.update_layout(template="plotly_dark", xaxis_title="Date", yaxis_title="Cumulative Return (%)", hovermode="x unified", height=380)
st.plotly_chart(fig_perf, use_container_width=True)

# 4. Current Holdings & Closed Trades Tables
c1, c2 = st.columns(2)
with c1:
    st.subheader("Current Holdings")
    if 'Return_Num' in df_holdings.columns:
        display_holdings = df_holdings.drop(columns=['Return_Num'])
    else:
        display_holdings = df_holdings
    st.dataframe(display_holdings, use_container_width=True)

with c2:
    st.subheader("Recent Closed Trades")
    st.dataframe(df_trades, use_container_width=True)
