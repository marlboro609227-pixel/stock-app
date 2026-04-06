import streamlit as st
import requests
import pandas as pd
import yfinance as yf

from datetime import datetime, timedelta, timezone

st.set_page_config(page_title="專業當沖輔助系統", layout="centered")

FUGLE_BASE_URL = "https://api.fugle.tw/marketdata/v1.0/stock"
FINMIND_BASE_URL = "https://api.finmindtrade.com/api/v4/data"
TW_TZ = timezone(timedelta(hours=8))


# =========================
# 基礎工具
# =========================
def tw_now():
    return datetime.now(TW_TZ)

def now_hhmm():
    return tw_now().strftime("%H:%M")

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

def safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default


# =========================
# 專業作戰時程表
# =========================
def render_battle_timetable():
    st.sidebar.markdown(
        """
        <div style="
            border: 2px solid #d0d7de;
            border-radius: 12px;
            padding: 14px;
            background-color: #f8fafc;
            margin-bottom: 12px;
        ">
            <div style="font-size: 1.1rem; font-weight: 700; margin-bottom: 10px;">
                🛡️ 專業作戰時程指引
            </div>

            <div style="margin-bottom: 12px;">
                <div style="font-weight: 700; color: #0f9d58;">
                    • 🟢 凌晨 05:00 - 08:30【最佳盤後分析期】
                </div>
                <div>• 任務：執行 tab1 分析，確認美股收盤漲跌與 ⑤ 號門標的。</div>
                <div>• 核心：根據大戶籌碼與美股動能，定下今日「計畫性交易」目標。</div>
            </div>

            <div style="margin-bottom: 12px;">
                <div style="font-weight: 700; color: #d97706;">
                    • 🔥 早上 09:00 - 11:00【黃金實戰扣動期】
                </div>
                <div>• 任務：切換 tab2 盤中判斷，監控即時價位。</div>
                <div>• 核心：嚴格執行壓力位突破進場，並守好 App 算出的停損價位。</div>
            </div>

            <div>
                <div style="font-weight: 700; color: #6b7280;">
                    • 💤 早上 11:00 之後【收盤與身心休養】
                </div>
                <div>• 任務：停止新開倉動作。</div>
                <div>• 核心：讓獲利奔跑或交由停損單自動執行，回歸正常作息。</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# 時間紅綠燈
# =========================
def render_time_banner():
    now = tw_now()
    hhmm = now.hour * 100 + now.minute

    if 500 <= hhmm <= 850:
        msg = "🔥 美股已收盤，數據最精準，適合晨間作戰規劃"
        color = "#0f9d58"
        bg = "#e8f5e9"
    elif 900 <= hhmm <= 1335:
        msg = "⚠️ 台股交易中，美股為昨日數據，請留意盤中波動"
        color = "#b26a00"
        bg = "#fff8e1"
    else:
        msg = "💤 盤後結算中，請等待傍晚籌碼更新"
        color = "#666666"
        bg = "#f2f2f2"

    st.markdown(
        f"""
        <div style="
            background:{bg};
            color:{color};
            padding:10px 14px;
            border-radius:10px;
            font-weight:700;
            margin-bottom:8px;">
            目前系統時間：{now.strftime("%Y-%m-%d %H:%M:%S")}　{msg}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# FinMind API
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

@st.cache_data(ttl=3600)
def fetch_daily_data(stock_id, start_date="2023-01-01"):
    df = fetch_finmind_dataset("TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    if df is None or df.empty or len(df) < 40:
        return None

    df = df.sort_values("date").reset_index(drop=True)
    return df


# =========================
# 基本面摘要
# =========================
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
        return f"未成功抓取最新公開基本面資料。(更新時間: {now_hhmm()})"

    return "；".join(parts) + f"。(更新時間: {now_hhmm()})"


# =========================
# 美股連動
# =========================
def map_us_indices(industry_category: str):
    text = (industry_category or "").strip()

    semi_keywords = ["半導體", "電子", "通訊"]
    cyc_keywords = ["金融", "鋼鐵", "塑膠", "水泥"]

    if any(k in text for k in semi_keywords):
        return ["^SOX", "^IXIC"], "費半 / 那指"
    if any(k in text for k in cyc_keywords):
        return ["^DJI"], "道瓊"
    return ["^IXIC"], "那指"

@st.cache_data(ttl=3600)
def fetch_us_index_change(ticker):
    try:
        df = yf.download(ticker, period="7d", interval="1d", progress=False, auto_adjust=False)
    except Exception:
        return None

    if df is None or df.empty or "Close" not in df.columns or len(df) < 2:
        return None

    close_series = df["Close"].dropna()
    if len(close_series) < 2:
        return None

    latest = float(close_series.iloc[-1])
    prev = float(close_series.iloc[-2])
    pct = (latest - prev) / prev * 100
    return {
        "ticker": ticker,
        "latest_close": latest,
        "prev_close": prev,
        "change_pct": round(pct, 2)
    }

def build_us_correlation_block(stock_id):
    info = fetch_stock_info(stock_id)
    industry = info["industry_category"] if info else ""
    tickers, label = map_us_indices(industry)

    data = []
    for t in tickers:
        res = fetch_us_index_change(t)
        if res:
            data.append(res)

    return {
        "industry": industry,
        "mapping_label": label,
        "indices": data
    }


# =========================
# 籌碼：400張以上大戶持股比例
# =========================
@st.cache_data(ttl=3600)
def fetch_400_holder_ratio(stock_id):
    df = fetch_finmind_dataset(
        "TaiwanStockHoldingSharesPer",
        data_id=stock_id,
        start_date="2024-01-01"
    )
    if df is None or df.empty:
        return None

    cols = set(df.columns)
    if "date" not in cols:
        return None

    level_col = None
    percent_col = None

    for c in ["HoldingSharesLevel", "holding_shares_level", "shares_level"]:
        if c in cols:
            level_col = c
            break

    for c in ["percent", "Percent", "percentage"]:
        if c in cols:
            percent_col = c
            break

    if level_col is None or percent_col is None:
        return None

    df = df.copy()
    df[level_col] = df[level_col].astype(str)

    # 400張以上
    df_400 = df[df[level_col].str.contains("400", na=False)].copy()
    if df_400.empty:
        return None

    grouped = (
        df_400.groupby("date", as_index=False)[percent_col]
        .sum()
        .sort_values("date")
        .reset_index(drop=True)
    )

    if len(grouped) < 2:
        return None

    grouped = grouped.rename(columns={percent_col: "holder_400_ratio"})
    return grouped

def check_400_holder_change(stock_id):
    df = fetch_400_holder_ratio(stock_id)
    if df is None or len(df) < 2:
        return {
            "available": False,
            "latest_ratio": None,
            "prev_ratio": None,
            "change": None,
            "warning": False,
            "message": f"無足夠400張以上大戶持股資料。(更新時間: {now_hhmm()})"
        }

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    latest_ratio = float(latest["holder_400_ratio"])
    prev_ratio = float(prev["holder_400_ratio"])
    change = latest_ratio - prev_ratio

    warning = change < -0.5

    if warning:
        message = f"400張以上大戶持股比例較上一期下降 {abs(change):.2f}% (更新時間: {now_hhmm()})"
    elif change > 0:
        message = f"400張以上大戶持股比例較上一期增加 {change:.2f}% (更新時間: {now_hhmm()})"
    else:
        message = f"400張以上大戶持股比例與上一期大致持平 (更新時間: {now_hhmm()})"

    return {
        "available": True,
        "latest_ratio": round(latest_ratio, 2),
        "prev_ratio": round(prev_ratio, 2),
        "change": round(change, 2),
        "warning": warning,
        "message": message
    }


# =========================
# 技術模型
# =========================
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


# =========================
# 進階階段判斷 + 一句話結論
# =========================
def detect_stage_advanced(df, stock_id):
    if df is None or len(df) < 30:
        return {
            "stage": "-",
            "stage_name": "資料不足",
            "stage_desc": "資料不足，無法進行階段判斷。",
            "favorable_zone": "未知",
            "chip_warning": False,
            "chip_message": f"無法判斷籌碼變化。(更新時間: {now_hhmm()})"
        }

    d = df.copy().reset_index(drop=True)
    d["ma5"] = d["close"].rolling(5).mean()
    d["ma10"] = d["close"].rolling(10).mean()
    d["ma20"] = d["close"].rolling(20).mean()
    d["vol5"] = d["Trading_Volume"].rolling(5).mean()

    t = d.iloc[-1]
    prev = d.iloc[-2]

    close_now = float(t["close"])
    high20 = float(d["max"].iloc[-20:].max())
    low20 = float(d["min"].iloc[-20:].min())
    pos20 = (close_now - low20) / (high20 - low20 + 1e-6)

    ret5 = (close_now - float(d.iloc[-6]["close"])) / float(d.iloc[-6]["close"]) * 100 if len(d) >= 6 else 0
    vol_ratio = float(t["Trading_Volume"]) / float(d["Trading_Volume"].rolling(5).mean().iloc[-1]) if pd.notna(d["Trading_Volume"].rolling(5).mean().iloc[-1]) else 1
    breakout = close_now >= float(d["max"].iloc[-10:-1].max())

    ma_bull = (
        pd.notna(t["ma5"]) and pd.notna(t["ma10"]) and pd.notna(t["ma20"]) and
        close_now > float(t["ma5"]) > float(t["ma10"]) > float(t["ma20"])
    )
    ma_slope = pd.notna(t["ma5"]) and pd.notna(prev["ma5"]) and float(t["ma5"]) > float(prev["ma5"])

    fake_break = (float(t["max"]) > high20) and (close_now < high20)

    if pos20 < 0.20:
        stage = "①"
        stage_name = "底部"
        desc = "仍在低檔整理，尚未形成有效攻擊結構。"
        favorable = "否"
    elif pos20 < 0.45:
        stage = "②"
        stage_name = "起漲"
        desc = "股價開始脫離低檔，屬起漲初期。"
        favorable = "觀察"
    elif pos20 < 0.65 and ma_bull and ma_slope:
        stage = "③"
        stage_name = "攻擊"
        desc = "主升段啟動，結構明顯轉強。"
        favorable = "是"
    elif pos20 < 0.80 and ma_bull and vol_ratio > 1.2:
        stage = "④"
        stage_name = "軋空"
        desc = "量價同步加速，進入強勢推升區。"
        favorable = "是"
    elif pos20 < 0.92 and ret5 > 6:
        stage = "⑤"
        stage_name = "末段攻擊"
        desc = "股價已接近高檔，但仍維持末段攻擊結構。"
        favorable = "是"
    else:
        stage = "⑥"
        stage_name = "噴出"
        desc = "短線已進入噴出區，追價風險顯著提高。"
        favorable = "❌ 否（風險極高）"

    if fake_break:
        desc += " 目前存在假突破跡象。"

    chip = check_400_holder_change(stock_id)

    if stage in ["⑤", "⑥"] and chip["warning"]:
        favorable = "🔴 警戒：主力出貨中"
        desc = "目前位於高檔階段，但400張以上大戶持股比例較前一期下降超過0.5%，疑似主力出貨。"

    if stage == "⑥" and not chip["warning"]:
        desc += " 現階段不宜聽信內線追高。"

    return {
        "stage": stage,
        "stage_name": stage_name,
        "stage_desc": f"{desc} (更新時間: {now_hhmm()})",
        "favorable_zone": favorable,
        "chip_warning": chip["warning"],
        "chip_message": chip["message"]
    }

def build_trader_comment(stage, chip_warning):
    if stage == "⑥":
        return f"噴出過熱，嚴禁追價 (更新時間: {now_hhmm()})"
    if stage == "⑤" and chip_warning:
        return f"末段攻擊但籌碼轉弱 (更新時間: {now_hhmm()})"
    if stage in ["③", "④"]:
        return f"主升段延續，結構健康 (更新時間: {now_hhmm()})"
    if stage == "②":
        return f"起漲初期，可持續觀察 (更新時間: {now_hhmm()})"
    if stage == "①":
        return f"仍在築底，暫不介入 (更新時間: {now_hhmm()})"
    return f"結構不明，建議觀望 (更新時間: {now_hhmm()})"


# =========================
# 盤後分析主函式
# =========================
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

    close_price = round(float(t["close"]), 2)
    high_price = round(float(t["max"]), 2)
    low_price = round(float(t["min"]), 2)

    up_prob, side_prob, down_prob = forecast_tomorrow(score_value, win_rate, avg_return)
    levels = build_after_levels(close_price, high_price, low_price, direction)
    stage_info = detect_stage_advanced(df, stock_id)
    comment = build_trader_comment(stage_info["stage"], stage_info["chip_warning"])

    return {
        "stock": stock_id,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "up_prob": up_prob,
        "side_prob": side_prob,
        "down_prob": down_prob,
        "pressure1": levels["pressure1"],
        "pressure2": levels["pressure2"],
        "support1": levels["support1"],
        "stop_loss": levels["stop_loss"],
        "stage": stage_info["stage"],
        "stage_name": stage_info["stage_name"],
        "stage_desc": stage_info["stage_desc"],
        "favorable_zone": stage_info["favorable_zone"],
        "chip_warning": stage_info["chip_warning"],
        "chip_message": stage_info["chip_message"],
        "comment": comment
    }


# =========================
# Fugle 盤中即時
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
            status = f"已突破壓力 (更新時間: {now_hhmm()})"
        elif high > pressure and price < pressure:
            status = f"盤中假突破 (更新時間: {now_hhmm()})"
        else:
            status = f"尚未突破壓力 (更新時間: {now_hhmm()})"

    else:
        entry_price = round(support, 2)
        stop_loss = round(pressure * 1.015, 2)
        tp1 = round(support - (pressure - support) * 0.5, 2)
        tp2 = round(support - (pressure - support) * 1.0, 2)

        if price < support and price <= open_price and price <= ref_price:
            status = f"已跌破支撐 (更新時間: {now_hhmm()})"
        elif low < support and price > support:
            status = f"盤中假跌破 (更新時間: {now_hhmm()})"
        else:
            status = f"尚未跌破支撐 (更新時間: {now_hhmm()})"

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
render_battle_timetable()
render_time_banner()

tab1, tab2 = st.tabs(["盤後分析", "盤中判斷"])

with tab1:
    st.title("盤後分析")

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
            us_block = build_us_correlation_block(stock_id)

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
                "stop_loss": res["stop_loss"],
                "stage": res["stage"],
                "stage_name": res["stage_name"],
                "stage_desc": res["stage_desc"],
                "favorable_zone": res["favorable_zone"],
                "chip_warning": res["chip_warning"],
                "chip_message": res["chip_message"],
                "comment": res["comment"],
                "us_block": us_block
            }

            st.subheader("交易員判讀結論")
            st.markdown(f"### {res['comment']}")

            st.subheader("基本面摘要")
            st.write(auto_fundamental)

            st.subheader("美股連動觀測")
            st.write(f"對位邏輯：{us_block['mapping_label']} (更新時間: {now_hhmm()})")
            if us_block["indices"]:
                cols = st.columns(len(us_block["indices"]))
                for i, item in enumerate(us_block["indices"]):
                    cols[i].metric(
                        item["ticker"],
                        f"{item['change_pct']}%",
                        f"收盤 {fmt_num(item['latest_close'])}"
                    )
            else:
                st.write(f"無法取得對應美股指數資料 (更新時間: {now_hhmm()})")

            st.subheader("目前階段")
            c1, c2 = st.columns([1, 2])
            c1.metric("階段", f"{res['stage']} {res['stage_name']}")

            if res["favorable_zone"] in ["🔴 警戒：主力出貨中", "❌ 否（風險極高）"]:
                c2.markdown(
                    f"<div style='font-size:1.05rem;font-weight:700;color:#ff4b4b;padding-top:0.4rem;'>"
                    f"{res['favorable_zone']} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            else:
                c2.metric("相對有利區", f"{res['favorable_zone']} (更新時間: {now_hhmm()})")

            st.write(res["stage_desc"])

            st.subheader("大戶籌碼增減狀況")
            if res["chip_warning"]:
                st.markdown(
                    f"<span style='color:#ff4b4b;font-weight:700;'>{res['chip_message']}</span>",
                    unsafe_allow_html=True
                )
            else:
                st.write(res["chip_message"])

            st.subheader("明日走勢機率")
            p1, p2, p3 = st.columns(3)
            p1.metric("上攻", f"{res['up_prob']}%")
            p2.metric("震盪", f"{res['side_prob']}%")
            p3.metric("下跌", f"{res['down_prob']}%")
            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("關鍵價位")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("壓力一", fmt_num(res["pressure1"]))
            d2.metric("壓力二", fmt_num(res["pressure2"]))
            d3.metric("支撐", fmt_num(res["support1"]))
            d4.metric("停損", fmt_num(res["stop_loss"]))
            st.caption(f"更新時間: {now_hhmm()}")

with tab2:
    st.title("盤中判斷")

    after_data = st.session_state.after_result
    default_stock = after_data["stock"] if after_data else "4906"
    default_name = after_data["stock_name"] if after_data else ""
    default_market = after_data["market"] if after_data else "台股"
    default_cost = after_data["cost"] if after_data else ""
    default_direction = after_data["direction"] if after_data else "多"
    default_pressure = float(after_data["pressure1"]) if after_data else 42.0
    default_support = float(after_data["support1"]) if after_data else 39.0
    default_fundamental = after_data["auto_fundamental"] if after_data else build_auto_fundamental_summary(default_stock)
    default_stage = after_data["stage"] if after_data else "-"
    default_stage_name = after_data["stage_name"] if after_data else "未判斷"
    default_stage_desc = after_data["stage_desc"] if after_data else f"請先進行盤後分析。(更新時間: {now_hhmm()})"
    default_favorable = after_data["favorable_zone"] if after_data else "未知"
    default_chip_warning = after_data["chip_warning"] if after_data else False
    default_comment = after_data["comment"] if after_data else f"請先進行盤後分析。(更新時間: {now_hhmm()})"
    default_us_block = after_data["us_block"] if after_data else build_us_correlation_block(default_stock)

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
                price=safe_float(data.get("lastPrice", 0)),
                open_price=safe_float(data.get("openPrice", 0)),
                high=safe_float(data.get("highPrice", 0)),
                low=safe_float(data.get("lowPrice", 0)),
                ref_price=safe_float(data.get("referencePrice", 0)),
                pressure=float(pressure_i),
                support=float(support_i),
                direction=direction_i
            )

            st.subheader("交易員判讀結論")
            st.markdown(f"### {default_comment}")

            st.subheader("基本面摘要")
            st.write(default_fundamental)

            st.subheader("美股連動觀測")
            st.write(f"對位邏輯：{default_us_block['mapping_label']} (更新時間: {now_hhmm()})")
            if default_us_block["indices"]:
                cols = st.columns(len(default_us_block["indices"]))
                for i, item in enumerate(default_us_block["indices"]):
                    cols[i].metric(
                        item["ticker"],
                        f"{item['change_pct']}%",
                        f"收盤 {fmt_num(item['latest_close'])}"
                    )
            else:
                st.write(f"無法取得對應美股指數資料 (更新時間: {now_hhmm()})")

            st.subheader("目前階段")
            s1, s2 = st.columns([1, 2])
            s1.metric("階段", f"{default_stage} {default_stage_name}")

            if default_favorable in ["🔴 警戒：主力出貨中", "❌ 否（風險極高）"]:
                s2.markdown(
                    f"<div style='font-size:1.05rem;font-weight:700;color:#ff4b4b;padding-top:0.4rem;'>"
                    f"{default_favorable} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            else:
                s2.metric("相對有利區", f"{default_favorable} (更新時間: {now_hhmm()})")

            st.write(default_stage_desc)
            if default_chip_warning:
                st.warning("近5日400張以上大戶持股比例下降，盤中應降低追價意願。")

            st.subheader("盤中即時資訊")
            c1, c2, c3, c4, c5 = st.columns(5)
            c1.metric("現價", fmt_num(data.get("lastPrice", 0)))
            c2.metric("開盤", fmt_num(data.get("openPrice", 0)))
            c3.metric("高點", fmt_num(data.get("highPrice", 0)))
            c4.metric("低點", fmt_num(data.get("lowPrice", 0)))
            c5.metric("漲跌幅", f"{fmt_num(data.get('changePercent', 0))}%")
            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("盤中關鍵價位")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("進場價", fmt_num(plan["entry_price"]))
            d2.metric("停損價", fmt_num(plan["stop_loss"]))
            d3.metric("第一賣出價", fmt_num(plan["tp1"]))
            d4.metric("第二賣出價", fmt_num(plan["tp2"]))
            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("盤中狀態")
            st.write(plan["status"])
