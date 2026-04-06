import streamlit as st
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="專業當沖分析系統", layout="centered")

FINMIND_URL = "https://api.finmindtrade.com/api/v4/data"

# =========================
# 🛡️ 作戰時程（固定最上方）
# =========================
st.markdown("""
<div style="border:1px solid #444;padding:10px;border-radius:10px">
🛡️ 專業作戰時程指引  

🟢 05:00 - 08:30【最佳盤後分析期】  
→ 規劃今日策略  

🔥 09:00 - 11:00【黃金實戰期】  
→ 嚴格依照進場條件操作  

💤 11:00 之後【停止開倉】  
→ 控管風險、收工  
</div>
""", unsafe_allow_html=True)

# =========================
# ⏰ 時間紅綠燈
# =========================
now = datetime.now()
time_str = now.strftime("%H:%M")

if 5 <= now.hour < 9:
    st.success(f"🔥 {time_str} 美股收盤完成，可制定策略")
elif 9 <= now.hour < 13:
    st.warning(f"⚠️ {time_str} 台股盤中，請控風險")
else:
    st.info(f"💤 {time_str} 盤後整理中")

# =========================
# 📊 FinMind
# =========================
@st.cache_data(ttl=3600)
def fetch_data(dataset, stock_id=""):
    params = {"dataset": dataset}
    if stock_id:
        params["data_id"] = stock_id
    res = requests.get(FINMIND_URL, params=params).json()
    return pd.DataFrame(res["data"]) if "data" in res else None

# =========================
# 🧠 階段判斷
# =========================
def detect_stage(df):
    recent = df.tail(20)
    high = recent["max"].max()
    low = recent["min"].min()
    close = df.iloc[-1]["close"]

    pos = (close - low) / (high - low + 1e-5)

    if pos < 0.2:
        return 1, "① 底部"
    elif pos < 0.4:
        return 2, "② 起漲"
    elif pos < 0.6:
        return 3, "③ 攻擊"
    elif pos < 0.75:
        return 4, "④ 震盪"
    elif pos < 0.9:
        return 5, "⑤ 末段攻擊"
    else:
        return 6, "⑥ 噴出"

# =========================
# 🧠 籌碼過濾
# =========================
def get_chip(stock_id):
    df = fetch_data("TaiwanStockHoldingSharesPer", stock_id)
    if df is None or len(df) < 2:
        return None

    df = df.sort_values("date")
    latest = df.iloc[-1]["percent"]
    prev = df.iloc[-2]["percent"]

    diff = latest - prev
    return diff

# =========================
# 🌍 美股連動
# =========================
def get_us():
    sox = yf.Ticker("^SOX").history(period="2d")
    nas = yf.Ticker("^IXIC").history(period="2d")

    return {
        "SOX": round((sox["Close"].iloc[-1]/sox["Close"].iloc[-2]-1)*100,2),
        "NAS": round((nas["Close"].iloc[-1]/nas["Close"].iloc[-2]-1)*100,2)
    }

# =========================
# 📈 明日劇本
# =========================
def build_scenario(stage):
    if stage == 5:
        return {
            "main": "開高震盪偏弱",
            "up": 25,
            "flat": 35,
            "down": 40
        }
    elif stage == 6:
        return {
            "main": "開高走低",
            "up": 15,
            "flat": 25,
            "down": 60
        }
    else:
        return {
            "main": "區間震盪",
            "up": 30,
            "flat": 40,
            "down": 30
        }

# =========================
# 📊 主分析
# =========================
def analyze(stock_id):
    df = fetch_data("TaiwanStockPrice", stock_id)
    if df is None or len(df) < 30:
        return None

    df = df.sort_values("date")

    close = df.iloc[-1]["close"]
    high = df.iloc[-1]["max"]
    low = df.iloc[-1]["min"]

    stage, stage_name = detect_stage(df)
    chip = get_chip(stock_id)
    scenario = build_scenario(stage)
    us = get_us()

    warning = ""
    if stage >= 5 and chip is not None and chip < -0.5:
        warning = "🔴 主力出貨中"

    return {
        "close": close,
        "high": high,
        "low": low,
        "stage": stage_name,
        "chip": chip,
        "warning": warning,
        "scenario": scenario,
        "us": us
    }

# =========================
# 🖥️ UI
# =========================
st.title("📊 盤後分析")

stock = st.text_input("股票代號", "4906")

if st.button("開始分析"):
    res = analyze(stock)

    if not res:
        st.error("無資料")
    else:
        st.subheader("📊 結論")
        st.write(f"{res['stage']} {res['warning']}")

        st.subheader("🌍 美股連動")
        st.metric("費半", f"{res['us']['SOX']}%")
        st.metric("那指", f"{res['us']['NAS']}%")

        st.subheader("🧠 籌碼")
        if res["chip"]:
            st.write(f"大戶變化：{round(res['chip'],2)}%")

        st.subheader("📈 明日劇本")

        st.write(f"主 сценар：{res['scenario']['main']}")
        st.write(f"上漲：{res['scenario']['up']}%")
        st.write(f"震盪：{res['scenario']['flat']}%")
        st.write(f"下跌：{res['scenario']['down']}%")
