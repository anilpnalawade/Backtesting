import os
import datetime
import pytz
import pandas as pd
from kiteconnect import KiteConnect
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("API_KEY")
access_token = os.getenv("ACCESS_TOKEN")
kite = KiteConnect(api_key=api_key)
kite.set_access_token(access_token)

quantity = 75
sl_pct = 0.30
target_pct = 0.50

results = []

def get_previous_trading_days(n=5):
    tz = pytz.timezone("Asia/Kolkata")
    today = datetime.datetime.now(tz).date()
    days = []
    while len(days) < n:
        today -= datetime.timedelta(days=1)
        if today.weekday() < 5:  # Mon–Fri
            days.append(today)
    return days[::-1]

def get_ist_datetime(date, hour, minute):
    tz = pytz.timezone("Asia/Kolkata")
    return tz.localize(datetime.datetime.combine(date, datetime.time(hour, minute)))

def get_atm_strike(price):
    return round(price / 50) * 50

def get_option_token(symbol):
    instruments = kite.instruments("NFO")
    for ins in instruments:
        if ins["tradingsymbol"] == symbol:
            return ins["instrument_token"]
    raise ValueError(f"Token not found for {symbol}")

def fetch_data(token, from_dt, to_dt):
    return kite.historical_data(token, from_dt, to_dt, "5minute")

def get_expiry_code(date):
    return date.strftime("%d%b%y").upper()  # e.g. 25JUL24

def get_next_thursday(date):
    days_ahead = 3 - date.weekday()  # Thursday = 3
    if days_ahead < 0:
        days_ahead += 7
    return date + datetime.timedelta(days=days_ahead)

def backtest_day(date):
    print(f"\n📅 Backtesting {date.strftime('%d-%b-%Y')}")

    spot_price = kite.ltp("NSE:NIFTY 50")["NSE:NIFTY 50"]["last_price"]
    atm = get_atm_strike(spot_price)
    expiry_date = get_next_thursday(date)
    expiry = get_expiry_code(expiry_date)

    ce_symbol = f"NIFTY{expiry}{atm}CE"
    pe_symbol = f"NIFTY{expiry}{atm}PE"

    try:
        ce_token = get_option_token(ce_symbol)
        pe_token = get_option_token(pe_symbol)
    except Exception as e:
        print(f"❌ {e}")
        return None

    from_time = get_ist_datetime(date, 9, 20)
    to_time = get_ist_datetime(date, 15, 15)

    ce_data = fetch_data(ce_token, from_time, to_time)
    pe_data = fetch_data(pe_token, from_time, to_time)

    ce_df = pd.DataFrame(ce_data)
    pe_df = pd.DataFrame(pe_data)

    if ce_df.empty or pe_df.empty:
        print("❌ No option data found.")
        return None

    ce_entry = ce_df.iloc[0]["open"]
    pe_entry = pe_df.iloc[0]["open"]

    ce_target = ce_entry * (1 + target_pct)
    ce_sl = ce_entry * (1 - sl_pct)

    pe_target = pe_entry * (1 + target_pct)
    pe_sl = pe_entry * (1 - sl_pct)

    for i in range(1, len(ce_df)):
        if ce_df.iloc[i]["high"] >= ce_target or ce_df.iloc[i]["low"] <= ce_sl:
            ce_exit = ce_df.iloc[i]["close"]
            pe_exit = pe_df.iloc[i]["close"]
            break
        if pe_df.iloc[i]["high"] >= pe_target or pe_df.iloc[i]["low"] <= pe_sl:
            pe_exit = pe_df.iloc[i]["close"]
            ce_exit = ce_df.iloc[i]["close"]
            break
    else:
        ce_exit = ce_df.iloc[-1]["close"]
        pe_exit = pe_df.iloc[-1]["close"]

    ce_pnl = (ce_exit - ce_entry) * quantity
    pe_pnl = (pe_exit - pe_entry) * quantity
    total_pnl = ce_pnl + pe_pnl

    print(f"  CE: ₹{ce_entry:.2f} → ₹{ce_exit:.2f}, P&L: ₹{ce_pnl:.2f}")
    print(f"  PE: ₹{pe_entry:.2f} → ₹{pe_exit:.2f}, P&L: ₹{pe_pnl:.2f}")
    print(f"  📊 Total Day P&L: ₹{total_pnl:.2f}")

    return {
        "Date": date.strftime("%Y-%m-%d"),
        "ATM Strike": atm,
        "Expiry": expiry,
        "CE Entry": ce_entry,
        "CE Exit": ce_exit,
        "PE Entry": pe_entry,
        "PE Exit": pe_exit,
        "CE P&L": ce_pnl,
        "PE P&L": pe_pnl,
        "Total P&L": total_pnl
    }

# === Run Backtest ===
total = 0
days = get_previous_trading_days(5)

for day in days:
    result = backtest_day(day)
    if result:
        results.append(result)
        total += result["Total P&L"]

# Export to CSV
df = pd.DataFrame(results)
df.to_csv("backtest_results.csv", index=False)

print("\n==============================")
print(f"✅ 5-Day Total P&L: ₹{total:.2f}")
print(f"📁 Results saved to backtest_results.csv")
print("==============================")

