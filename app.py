import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="單股交易員版", layout="centered")

FUGLE_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"

# =========================
# 盤後：FinMind 日K
# =========================
def fetch_daily_data(stock_id, start_date="2023-01-01"):
    url = "https://api.finmindtrade.com/api/v4/data"
    params = {
        "dataset": "TaiwanStockPrice",
        "data_id": stock_id,
        "start_date": start_date
    }

    try:
        res = requests.get(url, params=params, timeout=20).json()
    except Exception:
        return None

    if "data" not in res or len(res["data"]) < 40:
        return None

    df = pd.DataFrame(res["data"]).sort_values("date").reset_index(drop=True)
    return df

def valid_row(row):
    required = ["open", "close", "max", "min", "Trading_Volume"]
    for c in required:
        if c not in row or pd.isna(row[c]):
            return False
    if row["close"] <= 0 or row["max"] <= row["min"]:
        return False
    return True

def score_today(df):
    t = df.iloc[-1]
    p = df.iloc[-2]

    if not valid_row(t) or not valid_row(p):
        return None

    score = 0

    close_pos = (t["close"] - t["min"]) / (t["max"] - t["min"] + 1e-5)
    if close_pos > 0.7:
        score += 20

    if t["close"] > t["open"]:
        score += 15

    if (t["max"] - t["min"]) / t["close"] > 0.02:
        score += 15

    if p["close"] > 0 and (t["close"] - p["close"]) / p["close"] < 0.05:
        score += 10

    if t["Trading_Volume"] > p["Trading_Volume"]:
        score += 20

    recent_5d_high = df["max"].iloc[-6:-1].max()
    if t["close"] >= recent_5d_high:
        score += 20

    return int(score)

def backtest_strategy(df):
    returns = []

    for i in range(10, len(df) - 1):
        t = df.iloc[i]
        p = df.iloc[i - 1]
        n = df.iloc[i + 1]

        if not valid_row(t) or not valid_row(p) or not valid_row(n):
            continue

        close_pos = (t["close"] - t["min"]) / (t["max"] - t["min"] + 1e-5)

        signal = (
            close_pos > 0.7 and
            t["close"] > t["open"] and
            (t["max"] - t["min"]) / t["close"] > 0.02 and
            (t["close"] - p["close"]) / p["close"] < 0.05 and
            t["Trading_Volume"] > p["Trading_Volume"]
        )

        if signal:
            entry = t["max"]
            exit_price = n["close"]
            ret = (exit_price - entry) / entry
            returns.append(ret)

    if len(returns) == 0:
        return {"win_rate": 0.0, "avg_return": 0.0, "trades": 0}

    win_rate = sum(1 for r in returns if r > 0) / len(returns)
    avg_return = sum(returns) / len(returns)

    return {
        "win_rate": round(win_rate * 100, 2),
        "avg_return": round(avg_return * 100, 2),
        "trades": len(returns)
    }

def forecast_tomorrow(score_value, win_rate):
    if score_value >= 80 and win_rate >= 55:
        return 55, 30, 15, "偏多，可列優先觀察"
    elif score_value >= 70 and win_rate >= 50:
        return 45, 35, 20, "偏多，但仍需盤中突破確認"
    elif score_value >= 50:
        return 30, 40, 30, "中性，僅觀察"
    else:
        return 15, 35, 50, "偏弱，不建議主動出手"

def build_after_decision(score, win_rate, avg_return):
    risks = []

    if win_rate < 40:
        risks.append("勝率偏低")
    if avg_return < 0:
        risks.append("平均報酬為負")
    if score < 50:
        risks.append("今日結構偏弱")

    if win_rate >= 55 and avg_return > 0 and score >= 70:
        decision = "可做：可列入明日重點觀察"
        level = "A級"
    elif win_rate >= 50 and avg_return >= 0 and score >= 60:
        decision = "可觀察：需盤中突破確認後再考慮"
        level = "B級"
    else:
        decision = "不建議做：盤後條件不足"
        level = "C級"

    if not risks:
        risks_text = "低風險結構，仍需盤中確認"
    else:
        risks_text = "、".join(risks)

    return decision, level, risks_text

def analyze_after_stock(stock_id):
    df = fetch_daily_data(stock_id)
    if df is None:
        return {"stock": stock_id, "error": "無資料、資料不足或抓取失敗"}

    score_value = score_today(df)
    if score_value is None:
        return {"stock": stock_id, "error": "資料異常"}

    bt = backtest_strategy(df)
    win_rate = bt["win_rate"]
    avg_return = bt["avg_return"]
    trades = bt["trades"]

    t = df.iloc[-1]

    pressure = round(float(t["max"]), 2)
    support = round(float(t["min"]), 2)
    close = round(float(t["close"]), 2)

    up_prob, side_prob, down_prob, comment = forecast_tomorrow(score_value, win_rate)
    decision, level, risks_text = build_after_decision(score_value, win_rate, avg_return)

    return {
        "stock": stock_id,
        "score": score_value,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "trades": trades,
        "close": close,
        "pressure": pressure,
        "support": support,
        "up_prob": up_prob,
        "side_prob": side_prob,
        "down_prob": down_prob,
        "comment": comment,
        "decision": decision,
        "level": level,
        "risks_text": risks_text
    }

# =========================
# 盤中：Fugle 即時報價
# =========================
def fugle_quote(symbol, api_key):
    headers = {"X-API-KEY": api_key}
    url = f"{FUGLE_BASE_URL}/intraday/quote/{symbol}"
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception:
        return None

def build_trade_plan(pressure, support):
    risk = round(max(pressure - support, 0.01), 2)

    entry_trigger = round(pressure, 2)
    chase_limit = round(pressure * 1.01, 2)
    stop_loss = round(max(support, pressure * 0.995), 2)

    tp1 = round(pressure + risk * 0.5, 2)
    tp2 = round(pressure + risk * 1.0, 2)

    return {
        "entry_trigger": entry_trigger,
        "chase_limit": chase_limit,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "risk": risk
    }

def build_intraday_decision(price, entry_trigger, chase_limit, stop_loss, high_price, pressure):
    risks = []

    breakout = price > entry_trigger
    fake_break = high_price > pressure and price < pressure
    over_chase = price > chase_limit
    broken_stop = price < stop_loss

    if fake_break:
        risks.append("假突破風險")
    if over_chase:
        risks.append("追價過遠")
    if broken_stop:
        risks.append("跌破停損區")

    if breakout and (not fake_break) and (not over_chase) and (not broken_stop):
        decision = "可做：已形成有效進場條件"
        level = "A級"
    elif breakout and over_chase and (not fake_break):
        decision = "可觀察：已突破但不宜追價"
        level = "B級"
    else:
        decision = "不建議做：尚未形成安全進場條件"
        level = "C級"

    if not risks:
        risks_text = "目前無明顯結構風險"
    else:
        risks_text = "、".join(risks)

    return decision, level, risks_text

def analyze_intraday(symbol, pressure, support, api_key):
    data = fugle_quote(symbol, api_key)

    if not data or "lastPrice" not in data:
        return {"symbol": symbol, "error": "抓不到盤中資料，請確認 API Key、股票代號，或目前是否有行情"}

    price = data.get("lastPrice", 0)
    high = data.get("highPrice", 0)
    low = data.get("lowPrice", 0)
    open_price = data.get("openPrice", 0)
    ref_price = data.get("referencePrice", 0)
    avg_price = data.get("avgPrice", 0)
    change_percent = data.get("changePercent", 0)

    plan = build_trade_plan(pressure, support)
    decision, level, risks_text = build_intraday_decision(
        price=price,
        entry_trigger=plan["entry_trigger"],
        chase_limit=plan["chase_limit"],
        stop_loss=plan["stop_loss"],
        high_price=high,
        pressure=pressure
    )

    if price >= plan["tp2"]:
        status = "已達第二停利區"
    elif price >= plan["tp1"]:
        status = "已達第一停利區"
    elif price <= plan["stop_loss"]:
        status = "已跌破停損參考"
    else:
        status = "尚在策略區間內"

    return {
        "symbol": symbol,
        "price": price,
        "open_price": open_price,
        "high": high,
        "low": low,
        "ref_price": ref_price,
        "avg_price": avg_price,
        "change_percent": change_percent,
        "pressure": pressure,
        "support": support,
        "entry_trigger": plan["entry_trigger"],
        "chase_limit": plan["chase_limit"],
        "stop_loss": plan["stop_loss"],
        "tp1": plan["tp1"],
        "tp2": plan["tp2"],
        "level": level,
        "result": decision,
        "status": status,
        "risks_text": risks_text
    }

# =========================
# Session State
# =========================
if "after_result" not in st.session_state:
    st.session_state.after_result = None

# =========================
# UI：雙頁籤
# =========================
tab1, tab2 = st.tabs(["盤後分析", "盤中判斷"])

with tab1:
    st.title("單股盤後交易員版")
    st.caption("收盤後使用：專注 1 檔股票，給出壓力、支撐與隔日觀察方向")

    with st.form("after_form"):
        stock = st.text_input("股票代號", value="4906").strip()
        submitted_after = st.form_submit_button("開始分析")

    if submitted_after:
        res = analyze_after_stock(stock)

        if "error" in res:
            st.error(res["error"])
        else:
            st.session_state.after_result = res

            st.subheader("盤後結果")
            st.write(f"股票：{res['stock']}")
            st.write(f"等級：{res['level']}")
            st.write(f"今日評分：{res['score']}")
            st.write(f"歷史勝率：{res['win_rate']}%")
            st.write(f"平均報酬：{res['avg_return']}%")
            st.write(f"樣本筆數：{res['trades']}")

            st.write("可不可以做：")
            st.write(res["decision"])

            st.write("風險標記：")
            st.write(res["risks_text"])

            st.write("明日走勢機率：")
            st.write(f"上攻：{res['up_prob']}%")
            st.write(f"震盪：{res['side_prob']}%")
            st.write(f"下跌：{res['down_prob']}%")

            st.write("關鍵價位：")
            st.write(f"今日收盤：{res['close']}")
            st.write(f"明日壓力：{res['pressure']}")
            st.write(f"明日支撐：{res['support']}")

            st.write("盤後建議：")
            st.write(res["comment"])

with tab2:
    st.title("單股盤中交易員版")
    st.caption("盤中使用：依盤後帶入的壓力與支撐，判斷是否可進場與如何出場")

    after_result = st.session_state.after_result

    default_stock = after_result["stock"] if after_result else "4906"
    default_pressure = float(after_result["pressure"]) if after_result else 40.0
    default_support = float(after_result["support"]) if after_result else 39.0

    with st.form("intraday_form"):
        api_key = st.text_input("Fugle API Key", value="")
        stock_i = st.text_input("股票代號", value=default_stock).strip()
        pressure_i = st.number_input("壓力", value=default_pressure, step=0.1, format="%.2f")
        support_i = st.number_input("支撐", value=default_support, step=0.1, format="%.2f")

        submitted_intra = st.form_submit_button("更新盤中判斷")

    if submitted_intra:
        res = analyze_intraday(stock_i, pressure_i, support_i, api_key)

        if "error" in res:
            st.error(res["error"])
        else:
            st.subheader("盤中結果")
            st.write(f"股票：{res['symbol']}")
            st.write(f"等級：{res['level']}")
            st.write(f"現價：{res['price']}")
            st.write(f"開盤：{res['open_price']}")
            st.write(f"今高：{res['high']}")
            st.write(f"今低：{res['low']}")
            st.write(f"參考價：{res['ref_price']}")
            st.write(f"均價：{res['avg_price']}")
            st.write(f"漲跌幅：{res['change_percent']}%")

            st.write("進出場策略：")
            st.write(f"進場觸發：突破 {res['entry_trigger']}")
            st.write(f"不追價上限：{res['chase_limit']}")
            st.write(f"停損參考：{res['stop_loss']}")
            st.write(f"第一停利：{res['tp1']}")
            st.write(f"第二停利：{res['tp2']}")

            st.write("可不可以做：")
            st.write(res["result"])

            st.write("風險標記：")
            st.write(res["risks_text"])

            st.write("目前狀態：")
            st.write(res["status"])
