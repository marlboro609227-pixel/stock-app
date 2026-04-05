import streamlit as st
import requests
import pandas as pd

st.set_page_config(page_title="單股盤後盤中分析系統", layout="centered")

FUGLE_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"
FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4/data"

# =========================
# 工具函式
# =========================
def fmt_num(x, digits=2):
    try:
        return f"{float(x):.{digits}f}"
    except Exception:
        return "-"

def volume_to_human(v):
    try:
        v = float(v)
    except Exception:
        return "-"
    if v >= 100000000:
        return f"{v/100000000:.2f}億"
    if v >= 10000:
        return f"{v/10000:.2f}萬"
    return f"{int(v)}"

# =========================
# FinMind：快取資料
# =========================
@st.cache_data(ttl=3600)
def fetch_finmind_dataset(dataset, data_id="", start_date="2023-01-01"):
    params = {
        "dataset": dataset,
        "start_date": start_date
    }
    if data_id:
        params["data_id"] = data_id

    try:
        res = requests.get(FINMIND_BASE_URL, params=params, timeout=20).json()
    except Exception:
        return None

    if "data" not in res:
        return None

    return pd.DataFrame(res["data"])

@st.cache_data(ttl=3600)
def fetch_stock_info(stock_id):
    df = fetch_finmind_dataset("TaiwanStockInfo", start_date="2000-01-01")
    if df is None or df.empty or "stock_id" not in df.columns:
        return None

    target = df[df["stock_id"].astype(str) == str(stock_id)]
    if target.empty:
        return None

    row = target.iloc[0]
    return {
        "stock_id": str(row.get("stock_id", "")),
        "stock_name": str(row.get("stock_name", "")),
        "industry_category": str(row.get("industry_category", "")),
        "type": str(row.get("type", ""))
    }

@st.cache_data(ttl=3600)
def fetch_month_revenue(stock_id):
    df = fetch_finmind_dataset("TaiwanStockMonthRevenue", data_id=stock_id, start_date="2023-01-01")
    if df is None or df.empty:
        return None

    sort_cols = [c for c in ["revenue_year", "revenue_month"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    latest = df.iloc[-1].to_dict()
    prev = df.iloc[-2].to_dict() if len(df) >= 2 else None
    return latest, prev

def build_auto_fundamental_summary(stock_id):
    info = fetch_stock_info(stock_id)
    rev_data = fetch_month_revenue(stock_id)

    parts = []

    if info:
        name = info.get("stock_name", "")
        industry = info.get("industry_category", "")
        if name and industry:
            parts.append(f"{name}所屬產業類別為{industry}")
        elif name:
            parts.append(f"{name}為目前查得之公司名稱")

    if rev_data:
        latest, prev = rev_data
        y = latest.get("revenue_year", "")
        m = latest.get("revenue_month", "")
        revenue = latest.get("revenue", None)

        if y and m and revenue is not None:
            parts.append(f"最新月營收資料為{y}年{m}月，單月營收約{volume_to_human(revenue)}元")

        if prev and latest.get("revenue", None) is not None and prev.get("revenue", None) is not None:
            try:
                mom = (float(latest["revenue"]) - float(prev["revenue"])) / float(prev["revenue"]) * 100
                if mom > 0:
                    parts.append(f"月營收較前一期增加約{mom:.2f}%")
                elif mom < 0:
                    parts.append(f"月營收較前一期減少約{abs(mom):.2f}%")
                else:
                    parts.append("月營收與前一期大致持平")
            except Exception:
                pass

    if not parts:
        return "未成功抓取最新公開基本面資料。"

    return "；".join(parts) + "。"

# =========================
# 盤後：日K資料
# =========================
@st.cache_data(ttl=3600)
def fetch_daily_data(stock_id, start_date="2023-01-01"):
    df = fetch_finmind_dataset("TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    if df is None or df.empty or len(df) < 40:
        return None

    df = df.sort_values("date").reset_index(drop=True)
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

def forecast_tomorrow(score_value, win_rate, avg_return):
    if score_value >= 80 and win_rate >= 55 and avg_return > 0:
        return 55, 30, 15
    elif score_value >= 70 and win_rate >= 50:
        return 45, 35, 20
    elif score_value >= 50:
        return 30, 40, 30
    else:
        return 20, 35, 45

def build_after_levels(close_price, high_price, low_price, direction="多"):
    if direction == "多":
        pressure1 = round(high_price, 2)
        pressure2 = round(high_price * 1.03, 2)
        support1 = round(low_price, 2)
        stop_loss = round(min(low_price, close_price * 0.985), 2)
    else:
        pressure1 = round(high_price, 2)
        pressure2 = round(high_price * 1.02, 2)
        support1 = round(low_price, 2)
        stop_loss = round(high_price * 1.015, 2)

    return {
        "pressure1": pressure1,
        "pressure2": pressure2,
        "support1": support1,
        "stop_loss": stop_loss
    }

def analyze_after_stock(stock_id, direction="多"):
    df = fetch_daily_data(stock_id)
    if df is None:
        return {"stock": stock_id, "error": "無資料、資料不足或抓取失敗"}

    score_value = score_today(df)
    if score_value is None:
        return {"stock": stock_id, "error": "資料異常"}

    bt = backtest_strategy(df)
    win_rate = bt["win_rate"]
    avg_return = bt["avg_return"]

    t = df.iloc[-1]
    p = df.iloc[-2]

    close_price = round(float(t["close"]), 2)
    high_price = round(float(t["max"]), 2)
    low_price = round(float(t["min"]), 2)

    up_prob, side_prob, down_prob = forecast_tomorrow(score_value, win_rate, avg_return)
    levels = build_after_levels(close_price, high_price, low_price, direction)

    return {
        "stock": stock_id,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "vol_now": int(t["Trading_Volume"]),
        "vol_prev": int(p["Trading_Volume"]),
        "up_prob": up_prob,
        "side_prob": side_prob,
        "down_prob": down_prob,
        "pressure1": levels["pressure1"],
        "pressure2": levels["pressure2"],
        "support1": levels["support1"],
        "stop_loss": levels["stop_loss"]
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

def build_intraday_plan(price, open_price, high, low, ref_price, pressure, support, direction="多"):
    if direction == "多":
        entry_price = round(pressure, 2)
        stop_loss = round(max(support, pressure * 0.995), 2)
        tp1 = round(pressure + (pressure - support) * 0.5, 2)
        tp2 = round(pressure + (pressure - support) * 1.0, 2)

        if price > pressure and price >= open_price and price >= ref_price:
            status = "已突破壓力"
        elif high > pressure and price < pressure:
            status = "盤中假突破"
        else:
            status = "尚未突破壓力"

    else:
        entry_price = round(support, 2)
        stop_loss = round(pressure * 1.015, 2)
        tp1 = round(support - (pressure - support) * 0.5, 2)
        tp2 = round(support - (pressure - support) * 1.0, 2)

        if price < support and price <= open_price and price <= ref_price:
            status = "已跌破支撐"
        elif low < support and price > support:
            status = "盤中假跌破"
        else:
            status = "尚未跌破支撐"

    return {
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "status": status
    }

# =========================
# Session
# =========================
if "after_result" not in st.session_state:
    st.session_state.after_result = None

# =========================
# UI
# =========================
tab1, tab2 = st.tabs(["盤後分析", "盤中判斷"])

with tab1:
    st.title("單股盤後分析")
    st.caption("收盤後使用：自動抓取最新公開基本面資料，並顯示明日三種走勢機率與關鍵價位")

    with st.form("after_form"):
        stock_id = st.text_input("股票代號", value="4906").strip()
        stock_name = st.text_input("股票名稱", value="").strip()
        market = st.text_input("市場別", value="台股").strip()
        direction = st.selectbox("操作方向", ["多", "空"])
        cost = st.text_input("買進或放空成本", value="")
        submitted_after = st.form_submit_button("開始分析")

    if submitted_after:
        res = analyze_after_stock(stock_id, direction)

        if "error" in res:
            st.error(res["error"])
        else:
            auto_fundamental = build_auto_fundamental_summary(stock_id)

            st.session_state.after_result = {
                "stock": stock_id,
                "stock_name": stock_name,
                "market": market,
                "cost": cost,
                "direction": direction,
                "auto_fundamental": auto_fundamental,
                "pressure1": res["pressure1"],
                "pressure2": res["pressure2"],
                "support1": res["support1"],
                "stop_loss": res["stop_loss"]
            }

            st.subheader("基本面摘要")
            st.write(auto_fundamental)

            st.subheader("明日走勢機率")
            c1, c2, c3 = st.columns(3)
            c1.metric("上攻", f"{res['up_prob']}%")
            c2.metric("震盪", f"{res['side_prob']}%")
            c3.metric("下跌", f"{res['down_prob']}%")

            st.subheader("關鍵價位")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("壓力一", fmt_num(res["pressure1"]))
            d2.metric("壓力二", fmt_num(res["pressure2"]))
            d3.metric("支撐", fmt_num(res["support1"]))
            d4.metric("停損", fmt_num(res["stop_loss"]))

with tab2:
    st.title("單股盤中判斷")
    st.caption("盤中使用：明確顯示進場價、停損價、第一賣出價、第二賣出價")

    after_data = st.session_state.after_result
    default_stock = after_data["stock"] if after_data else "4906"
    default_name = after_data["stock_name"] if after_data else ""
    default_market = after_data["market"] if after_data else "台股"
    default_cost = after_data["cost"] if after_data else ""
    default_direction = after_data["direction"] if after_data else "多"
    default_pressure = float(after_data["pressure1"]) if after_data else 42.0
    default_support = float(after_data["support1"]) if after_data else 39.0
    default_fundamental = after_data["auto_fundamental"] if after_data else build_auto_fundamental_summary(default_stock)

    with st.form("intra_form"):
        stock_i = st.text_input("股票代號", value=default_stock).strip()
        stock_name_i = st.text_input("股票名稱", value=default_name).strip()
        market_i = st.text_input("市場別", value=default_market).strip()
        cost_i = st.text_input("買進或放空成本", value=default_cost)
        direction_i = st.selectbox("操作方向", ["多", "空"], index=0 if default_direction == "多" else 1)
        pressure_i = st.number_input("壓力", value=default_pressure, step=0.1, format="%.2f")
        support_i = st.number_input("支撐", value=default_support, step=0.1, format="%.2f")
        submitted_intra = st.form_submit_button("更新盤中判斷")

    if submitted_intra:
        try:
            api_key = st.secrets["FUGLE_API_KEY"]
        except Exception:
            st.error("尚未在 Streamlit Secrets 設定 FUGLE_API_KEY")
            st.stop()

        data = fugle_quote(stock_i, api_key)

        if not data:
            st.error("抓不到盤中資料，請確認股票代號或目前是否有行情")
        else:
            plan = build_intraday_plan(
                price=float(data.get("lastPrice", 0) or 0),
                open_price=float(data.get("openPrice", 0) or 0),
                high=float(data.get("highPrice", 0) or 0),
                low=float(data.get("lowPrice", 0) or 0),
                ref_price=float(data.get("referencePrice", 0) or 0),
                pressure=float(pressure_i),
                support=float(support_i),
                direction=direction_i
            )

            st.subheader("基本面摘要")
            st.write(default_fundamental)

            st.subheader("盤中即時資訊")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("現價", fmt_num(data.get("lastPrice", 0)))
            c2.metric("開盤", fmt_num(data.get("openPrice", 0)))
            c3.metric("高點", fmt_num(data.get("highPrice", 0)))
            c4.metric("低點", fmt_num(data.get("lowPrice", 0)))
            c5.metric("漲跌幅", f"{fmt_num(data.get('changePercent', 0))}%")

            st.subheader("關鍵價位")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("進場價", fmt_num(plan["entry_price"]))
            d2.metric("停損價", fmt_num(plan["stop_loss"]))
            d3.metric("第一賣出價", fmt_num(plan["tp1"]))
            d4.metric("第二賣出價", fmt_num(plan["tp2"]))

            st.subheader("盤中狀態")
            st.write(plan["status"])
