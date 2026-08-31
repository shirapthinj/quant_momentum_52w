import os
import io
import json
import requests
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime

# CORE CONFIGURATION (+52.15% ATH BREAKOUT MODEL)
TARGET_POSITIONS = 10
MAX_HOLD_RANK = 25
ATR_MULTIPLIER = 3.5
MIN_TURNOVER = 50000000        # ₹5 Crore Daily Turnover Floor
MIN_STOCK_PRICE = 20.0         # ₹20 Minimum Stock Price Floor

SLIPPAGE_BUY = 1.0015          # 0.15% Buy Friction
SLIPPAGE_SELL = 0.9985         # 0.15% Sell Friction

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
STREAMLIT_URL = "https://quantmomentum52w-cabwqvmv4e7tyi9x7upauk.streamlit.app"

def send_telegram(msg):
    if TELEGRAM_TOKEN and TELEGRAM_CHAT_ID:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID, 
            "text": msg, 
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        try:
            requests.post(url, json=payload, timeout=10)
        except Exception as e:
            print(f"Telegram Dispatch Error: {e}")

def fetch_universe():
    url = "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        res = requests.get(url, headers=headers, timeout=15)
        if res.status_code == 200:
            df = pd.read_csv(io.StringIO(res.text))
            return [f"{sym.strip()}.NS" for sym in df['Symbol'].dropna()]
    except Exception as e:
        print(f"Universe fetch warning: {e}")
    return ['RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 'BHARTIARTL.NS', 'ICICIBANK.NS']

def run_live_scan():
    today_str = datetime.now().strftime("%Y-%m-%d")
    is_monday = datetime.now().weekday() == 0

    if not os.path.exists("portfolio.json"):
        state = {"cash": 500000.0, "initial_capital": 500000.0, "holdings": {}}
    else:
        with open("portfolio.json", "r") as f:
            state = json.load(f)

    cash = state["cash"]
    holdings = state["holdings"]
    initial_cap = state.get("initial_capital", 500000.0)
    
    is_rebalance_day = is_monday or (len(holdings) == 0)

    tickers = fetch_universe()
    n50_sym = '^NSEI'
    n500_sym = '^CRSLDX'
    all_symbols = list(set(tickers + [n50_sym, n500_sym]))
    
    print(f"Downloading historical market data for {len(all_symbols)} tickers...")
    raw = yf.download(all_symbols, period="2y", progress=False)
    
    if isinstance(raw.columns, pd.MultiIndex):
        close_df = raw['Close'].ffill()
        high_df = raw['High'].ffill()
        low_df = raw['Low'].ffill()
        volume_df = raw['Volume'].fillna(0)
    else:
        close_df = raw[['Close']].ffill()
        high_df = raw[['High']].ffill()
        low_df = raw[['Low']].ffill()
        volume_df = raw[['Volume']].fillna(0)

    # Technical Indicators
    sma200_df = close_df.rolling(200).mean()
    high52w_df = high_df.rolling(252).max()
    ret3m_df = close_df.pct_change(63) * 100
    ret6m_df = close_df.pct_change(126) * 100
    ret12m_df = close_df.pct_change(252) * 100
    turnover_df = close_df * volume_df

    prev_close = close_df.shift(1)
    tr = np.maximum(high_df - low_df, np.maximum((high_df - prev_close).abs(), (low_df - prev_close).abs()))
    atr14_df = tr.rolling(14).mean()
    atr_pct_df = (atr14_df / close_df) * 100

    trade_logs = []
    action_items = []
    stop_risk_list = []

    # 1. DAILY EXIT EVALUATION (3.5x ATR Trailing Stop)
    sold_tickers = []
    for ticker, pos in list(holdings.items()):
        if ticker not in close_df.columns:
            continue
        cur_p = close_df[ticker].iloc[-1]
        s_atr = atr14_df[ticker].iloc[-1]
        
        pos['peak_price'] = max(pos['peak_price'], cur_p)
        stop_price = pos['peak_price'] - (ATR_MULTIPLIER * s_atr) if not pd.isna(s_atr) else pos['peak_price'] * 0.85
        
        dist_to_stop = ((cur_p - stop_price) / cur_p) * 100
        stop_risk_list.append({'ticker': ticker.replace('.NS',''), 'dist': dist_to_stop, 'stop': stop_price, 'price': cur_p})

        if cur_p < stop_price:
            exit_price = cur_p * SLIPPAGE_SELL
            proceeds = pos['shares'] * exit_price
            cash += proceeds
            ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
            
            action_items.append(f"🔴 *SELL (3.5x ATR Stop)*: {ticker.replace('.NS', '')}\n   • Exit Price: ₹{exit_price:.2f} ({ret_pct:+.2f}%)")
            trade_logs.append({
                'Ticker': ticker.replace('.NS', ''),
                'Entry Date': pos['entry_date'],
                'Entry Price': pos['entry_price'],
                'Exit Date': today_str,
                'Exit Price': round(exit_price, 2),
                'Return (%)': round(ret_pct, 2),
                'Exit Reason': '3.5x ATR Trailing Stop'
            })
            sold_tickers.append(ticker)

    for t in sold_tickers:
        del holdings[t]

    # 2. REBALANCE & CANDIDATE EVALUATION
    if is_rebalance_day:
        n500_3m = ret3m_df[n500_sym].iloc[-1] if n500_sym in ret3m_df.columns else 0.0
        if pd.isna(n500_3m):
            n500_3m = 0.0
        
        candidates = []
        for ticker in tickers:
            if ticker not in close_df.columns:
                continue
            p = close_df[ticker].iloc[-1]
            sma200 = sma200_df[ticker].iloc[-1]
            h52w = high52w_df[ticker].iloc[-1]
            r3m, r6m, r12m = ret3m_df[ticker].iloc[-1], ret6m_df[ticker].iloc[-1], ret12m_df[ticker].iloc[-1]
            atr_pct = atr_pct_df[ticker].iloc[-1]
            to = turnover_df[ticker].iloc[-1]
            
            if pd.isna(p) or pd.isna(sma200) or pd.isna(h52w) or pd.isna(r3m) or pd.isna(r6m) or pd.isna(r12m) or pd.isna(atr_pct) or pd.isna(to) or h52w <= 0:
                continue
                
            alpha_3m = r3m - n500_3m
            if p >= MIN_STOCK_PRICE and to >= MIN_TURNOVER and p > sma200 and alpha_3m > 0:
                smooth_mom = (0.6 * r6m) + (0.4 * r12m)
                score = (smooth_mom / max(atr_pct, 0.5)) * ((p / h52w) ** 4)
                candidates.append({'ticker': ticker, 'price': p, 'score': score})

        if candidates:
            cand_df = pd.DataFrame(candidates).sort_values('score', ascending=False).reset_index(drop=True)
            cand_df['rank'] = cand_df.index + 1
            rank_lookup = dict(zip(cand_df['ticker'], cand_df['rank']))

            # Rank Decay Exits (> Top 25 Cutoff)
            rank_sells = []
            for ticker, pos in list(holdings.items()):
                r = rank_lookup.get(ticker, 999)
                if r > MAX_HOLD_RANK:
                    cur_p = close_df[ticker].iloc[-1]
                    exit_price = cur_p * SLIPPAGE_SELL
                    cash += (pos['shares'] * exit_price)
                    ret_pct = ((exit_price - pos['entry_price']) / pos['entry_price']) * 100
                    
                    action_items.append(f"🟠 *SELL (Rank Decay #{r})*: {ticker.replace('.NS', '')}\n   • Exit Price: ₹{exit_price:.2f} ({ret_pct:+.2f}%)")
                    trade_logs.append({
                        'Ticker': ticker.replace('.NS', ''),
                        'Entry Date': pos['entry_date'],
                        'Entry Price': pos['entry_price'],
                        'Exit Date': today_str,
                        'Exit Price': round(exit_price, 2),
                        'Return (%)': round(ret_pct, 2),
                        'Exit Reason': f'Rank Decay Exit (#{r})'
                    })
                    rank_sells.append(ticker)

            for t in rank_sells:
                del holdings[t]

            # Buy New Candidates to Fill Slots
            portfolio_val = cash + sum(pos['shares'] * close_df[t].iloc[-1] for t, pos in holdings.items() if t in close_df.columns)
            open_slots = TARGET_POSITIONS - len(holdings)
            
            if open_slots > 0 and cash > 5000:
                buys = cand_df[~cand_df['ticker'].isin(holdings.keys())].head(open_slots)
                alloc = portfolio_val / TARGET_POSITIONS
                
                for _, row in buys.iterrows():
                    stk, p = row['ticker'], row['price']
                    buy_price = p * SLIPPAGE_BUY
                    shares = int(np.floor(min(cash, alloc) / buy_price))
                    
                    if shares > 0 and cash >= (shares * buy_price):
                        holdings[stk] = {
                            'shares': shares,
                            'entry_price': buy_price,
                            'peak_price': p,
                            'entry_date': today_str
                        }
                        cash -= (shares * buy_price)
                        action_items.append(f"🟢 *BUY ORDER*: {stk.replace('.NS', '')}\n   • Buy: {shares} shares @ ₹{buy_price:.2f}")

    # CALCULATE METRICS & BENCHMARKS
    total_val = cash + sum(pos['shares'] * close_df[t].iloc[-1] for t, pos in holdings.items() if t in close_df.columns)
    tot_ret_pct = ((total_val - initial_cap) / initial_cap) * 100

    n50_p = close_df[n50_sym].iloc[-1] if n50_sym in close_df.columns else np.nan
    n500_p = close_df[n500_sym].iloc[-1] if n500_sym in close_df.columns else np.nan
    
    n50_prev = close_df[n50_sym].iloc[-2] if n50_sym in close_df.columns and len(close_df) > 1 else n50_p
    n500_prev = close_df[n500_sym].iloc[-2] if n500_sym in close_df.columns and len(close_df) > 1 else n500_p

    n50_daily_pct = ((n50_p - n50_prev) / n50_prev) * 100 if n50_prev > 0 else 0.0
    n500_daily_pct = ((n500_p - n500_prev) / n500_prev) * 100 if n500_prev > 0 else 0.0

    # SAVE STATE & HOLDINGS (ALWAYS OVERWRITES FULL FILE)
    state['cash'] = cash
    state['holdings'] = holdings

    with open("portfolio.json", "w") as f:
        json.dump(state, f, indent=2)

    holdings_rows = [{'Ticker': k.replace('.NS',''), 'Shares': v['shares'], 'Entry Price': round(v['entry_price'],2), 'Peak Price': round(v['peak_price'],2), 'Entry Date': v['entry_date']} for k,v in holdings.items()]
    pd.DataFrame(holdings_rows).to_csv("current_holdings.csv", index=False)

    # DUPLICATE-SAFE PERFORMANCE HISTORY LOGGING
    new_perf_row = {
        'Date': today_str, 
        'Portfolio_Value': round(total_val, 2), 
        'Cash': round(cash, 2), 
        'Positions': len(holdings),
        'Nifty50_Price': round(n50_p, 2) if not pd.isna(n50_p) else np.nan,
        'Nifty500_Price': round(n500_p, 2) if not pd.isna(n500_p) else np.nan
    }

    if os.path.exists("performance_history.csv"):
        existing_perf = pd.read_csv("performance_history.csv")
        # Remove existing record for today if present to prevent duplicate date rows
        existing_perf = existing_perf[existing_perf['Date'] != today_str]
        updated_perf = pd.concat([existing_perf, pd.DataFrame([new_perf_row])], ignore_index=True)
    else:
        updated_perf = pd.DataFrame([new_perf_row])

    updated_perf.to_csv("performance_history.csv", index=False)

    # DUPLICATE-SAFE TRADE LOGGING
    if trade_logs:
        new_trades_df = pd.DataFrame(trade_logs)
        if os.path.exists("trade_log.csv"):
            existing_trades = pd.read_csv("trade_log.csv")
            updated_trades = pd.concat([existing_trades, new_trades_df], ignore_index=True).drop_duplicates()
            updated_trades.to_csv("trade_log.csv", index=False)
        else:
            new_trades_df.to_csv("trade_log.csv", index=False)

    # CONSTRUCT TELEGRAM MESSAGE
    msg_lines = []
    
    if len(action_items) == 0:
        msg_lines.append(f"🟢 *STATUS: NO ACTION REQUIRED TODAY*")
        msg_lines.append(f"📅 *Date*: `{today_str}`\n")
    else:
        msg_lines.append(f"🚨 *STATUS: ACTION REQUIRED ({len(action_items)} ORDERS)*")
        msg_lines.append(f"📅 *Date*: `{today_str}`\n")
        msg_lines.append("*REQUIRED BROKER EXECUTIONS:*")
        for item in action_items:
            msg_lines.append(item)
        msg_lines.append("")

    msg_lines.append("*PORTFOLIO PERFORMANCE:*")
    msg_lines.append(f"• Total Equity: ₹{total_val:,.2f} ({tot_ret_pct:+.2f}% Overall)")
    msg_lines.append(f"• Cash Balance: ₹{cash:,.2f}")
    msg_lines.append(f"• Holdings: {len(holdings)}/{TARGET_POSITIONS} Slots\n")

    msg_lines.append("*TODAY'S BENCHMARK MOVEMENT:*")
    msg_lines.append(f"• Nifty 50  : {n50_daily_pct:+.2f}%")
    msg_lines.append(f"• Nifty 500 : {n500_daily_pct:+.2f}%\n")

    if stop_risk_list:
        stop_risk_list.sort(key=lambda x: x['dist'])
        msg_lines.append("*CLOSEST TO ATR TRAILING STOP:*")
        for item in stop_risk_list[:3]:
            msg_lines.append(f"• `{item['ticker']}`: +{item['dist']:.2f}% above stop (₹{item['stop']:.2f})")
        msg_lines.append("")

    msg_lines.append(f"🔗 [View Live Streamlit Dashboard]({STREAMLIT_URL})")

    send_telegram("\n".join(msg_lines))

if __name__ == "__main__":
    run_live_scan()
