import streamlit as st
import requests
import pandas as pd
import yfinance as yf
import numpy as np

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
        if pd.isna(x):
            return "-"
        return f"{float(x):.{digits}f}"
    except Exception:
        return "-"

def safe_float(x, default=0.0):
    try:
        v = float(x)
        if pd.isna(v):
            return default
        return v
    except Exception:
        return default

def safe_int(x, default=0):
    try:
        return int(float(x))
    except Exception:
        return default

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

def is_us_symbol(symbol: str) -> bool:
    s = (symbol or "").strip().upper()
    if not s:
        return False
    return s.isalpha()

def market_label(symbol: str) -> str:
    return "美股" if is_us_symbol(symbol) else "台股"

def get_secret(name: str, default: str = "") -> str:
    try:
        return str(st.secrets[name])
    except Exception:
        return default


# =========================
# 側邊欄：專業作戰時程表
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
                <div>• 任務：執行盤後分析，確認美股收盤漲跌與高檔結構標的。</div>
                <div>• 核心：依美股動能、籌碼與隔日劇本，先定好當日計畫。</div>
            </div>

            <div style="margin-bottom: 12px;">
                <div style="font-weight: 700; color: #d97706;">
                    • 🔥 早上 09:00 - 11:00【黃金實戰扣動期】
                </div>
                <div>• 任務：切換盤中判斷，監控即時價位。</div>
                <div>• 核心：只依壓力 / 支撐與停損紀律執行，不憑感覺追單。</div>
            </div>

            <div>
                <div style="font-weight: 700; color: #6b7280;">
                    • 💤 早上 11:00 之後【收盤與身心休養】
                </div>
                <div>• 任務：停止新開倉動作。</div>
                <div>• 核心：讓獲利奔跑或交由停損單處理，回歸正常作息。</div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# 頂部時間紅綠燈
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
            margin-bottom:10px;">
            目前系統時間：{now.strftime("%Y-%m-%d %H:%M:%S")}　{msg}
        </div>
        """,
        unsafe_allow_html=True
    )


# =========================
# 頁籤專屬使用時段提示
# =========================
def render_after_usage_note():
    st.markdown(
        """
        <div style="
            border:1px solid #2e7d32;
            background:#e8f5e9;
            color:#1b5e20;
            padding:12px 14px;
            border-radius:10px;
            font-weight:700;
            margin-bottom:12px;">
            盤後分析使用時段：建議於凌晨 05:00 - 08:00 閱讀
            <br>
            建議用途：確認美股收盤、籌碼方向與隔日主要劇本。
        </div>
        """,
        unsafe_allow_html=True
    )

def render_intra_usage_note():
    st.markdown(
        """
        <div style="
            border:1px solid #ef6c00;
            background:#fff3e0;
            color:#e65100;
            padding:12px 14px;
            border-radius:10px;
            font-weight:700;
            margin-bottom:12px;">
            盤中判斷使用時段：建議於早上 09:00 - 11:00 使用
            <br>
            建議用途：依壓力 / 支撐與即時價位執行進場、停損與分批賣出。
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
        res = requests.get(FINMIND_BASE_URL, params=params, timeout=20)
        res.raise_for_status()
        payload = res.json()
    except Exception:
        return None

    if "data" not in payload:
        return None

    return pd.DataFrame(payload["data"])


# =========================
# 台股 / 美股 基本資料
# =========================
@st.cache_data(ttl=3600)
def fetch_stock_info(stock_id):
    if is_us_symbol(stock_id):
        return {
            "stock_id": stock_id.upper(),
            "stock_name": stock_id.upper(),
            "industry_category": "美股",
            "type": "US"
        }

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
    if is_us_symbol(stock_id):
        return None

    df = fetch_finmind_dataset("TaiwanStockMonthRevenue", data_id=stock_id, start_date="2023-01-01")
    if df is None or df.empty:
        return None

    sort_cols = [c for c in ["revenue_year", "revenue_month"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols).reset_index(drop=True)

    latest = df.iloc[-1].to_dict()
    prev = df.iloc[-2].to_dict() if len(df) >= 2 else None
    return latest, prev


# =========================
# yfinance 日線整理
# =========================
def _normalize_yf_frame(df):
    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        out = pd.DataFrame(index=df.index)
        mapping = {
            "Open": "open",
            "Close": "close",
            "High": "max",
            "Low": "min",
            "Volume": "Trading_Volume"
        }
        for src, dst in mapping.items():
            try:
                obj = df[src]
                out[dst] = pd.to_numeric(obj.iloc[:, 0] if isinstance(obj, pd.DataFrame) else obj, errors="coerce")
            except Exception:
                return None
        out["date"] = df.index
        return out.reset_index(drop=True)

    mapping = {
        "Open": "open",
        "Close": "close",
        "High": "max",
        "Low": "min",
        "Volume": "Trading_Volume"
    }

    for c in mapping:
        if c not in df.columns:
            return None

    out = df.rename(columns=mapping).reset_index()
    if "Date" in out.columns:
        out = out.rename(columns={"Date": "date"})
    return out


@st.cache_data(ttl=1800)
def fetch_us_daily_data(symbol, period="6mo"):
    try:
        df = yf.download(
            symbol.upper(),
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=False,
            group_by="column"
        )
    except Exception:
        return None

    out = _normalize_yf_frame(df)
    if out is None:
        return None

    for c in ["open", "close", "max", "min", "Trading_Volume"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")

    out = out.dropna(subset=["open", "close", "max", "min", "Trading_Volume"]).reset_index(drop=True)
    if len(out) < 20:
        return None
    return out


@st.cache_data(ttl=3600)
def fetch_daily_data(stock_id, start_date="2023-01-01"):
    if is_us_symbol(stock_id):
        return fetch_us_daily_data(stock_id)

    df = fetch_finmind_dataset("TaiwanStockPrice", data_id=stock_id, start_date=start_date)
    if df is None or df.empty:
        return None

    required = ["date", "open", "close", "max", "min", "Trading_Volume"]
    for c in required:
        if c not in df.columns:
            return None

    df = df.sort_values("date").reset_index(drop=True)

    for c in ["open", "close", "max", "min", "Trading_Volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df = df.dropna(subset=["open", "close", "max", "min", "Trading_Volume"]).reset_index(drop=True)

    if len(df) < 10:
        return None

    return df


# =========================
# 基本面摘要
# =========================
def build_auto_fundamental_summary(stock_id):
    if is_us_symbol(stock_id):
        info = fetch_stock_info(stock_id)
        name = info.get("stock_name", stock_id.upper()) if info else stock_id.upper()
        return f"{name}目前以美股價格與技術結構為主進行判讀，基本面摘要建議搭配公司財報、財測與產業趨勢另行交叉比對。(更新時間: {now_hhmm()})"

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

        if prev and latest.get("revenue") is not None and prev.get("revenue") is not None:
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
def map_us_indices(industry_category):
    text = (industry_category or "").strip()

    if any(k in text for k in ["半導體", "電子", "通訊"]):
        return ["^SOX", "^IXIC"], "費半 / 那指"
    if any(k in text for k in ["金融", "鋼鐵", "塑膠", "水泥"]):
        return ["^DJI"], "道瓊"
    if any(k in text for k in ["AI", "雲端", "軟體", "生技", "醫療", "網通"]):
        return ["^IXIC"], "那指"
    return ["^IXIC"], "那指"


@st.cache_data(ttl=3600)
def fetch_us_index_change(ticker):
    try:
        df = yf.download(
            ticker,
            period="7d",
            interval="1d",
            progress=False,
            auto_adjust=False,
            group_by="column"
        )
    except Exception:
        return None

    if df is None or df.empty:
        return None

    try:
        if isinstance(df.columns, pd.MultiIndex):
            close_obj = df["Close"]
            close = pd.to_numeric(close_obj.iloc[:, 0] if isinstance(close_obj, pd.DataFrame) else close_obj, errors="coerce").dropna()
        else:
            close = pd.to_numeric(df["Close"], errors="coerce").dropna()
    except Exception:
        return None

    if len(close) < 2:
        return None

    latest = float(close.iloc[-1])
    prev = float(close.iloc[-2])
    if prev == 0:
        return None

    pct = (latest - prev) / prev * 100
    return {
        "ticker": ticker,
        "latest_close": latest,
        "prev_close": prev,
        "change_pct": round(pct, 2)
    }


def summarize_us_bias(indices):
    if not indices:
        return "中性"

    avg_pct = float(np.mean([i["change_pct"] for i in indices]))
    if avg_pct > 0.8:
        return "偏多"
    if avg_pct < -0.8:
        return "偏空"
    return "中性"


def build_us_correlation_block(stock_id):
    info = fetch_stock_info(stock_id)
    industry = info["industry_category"] if info else ""

    if is_us_symbol(stock_id):
        tickers, label = ["^IXIC", "^GSPC"], "Nasdaq / S&P 500"
    else:
        tickers, label = map_us_indices(industry)

    data = []
    for t in tickers:
        item = fetch_us_index_change(t)
        if item:
            data.append(item)

    return {
        "industry": industry,
        "mapping_label": label,
        "indices": data,
        "bias": summarize_us_bias(data)
    }
    # =========================
# 籌碼：400張以上大戶持股比例
# =========================
@st.cache_data(ttl=3600)
def fetch_400_holder_ratio(stock_id):
    if is_us_symbol(stock_id):
        return None

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
    df[percent_col] = pd.to_numeric(df[percent_col], errors="coerce")
    df = df.dropna(subset=[percent_col])

    df_400 = df[df[level_col].str.contains("400|600|800|1000", na=False)].copy()
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
    if is_us_symbol(stock_id):
        return {
            "available": False,
            "latest_ratio": None,
            "prev_ratio": None,
            "change": None,
            "warning": False,
            "severity": "none",
            "message": f"美股不適用400張以上大戶持股統計。(更新時間: {now_hhmm()})"
        }

    df = fetch_400_holder_ratio(stock_id)
    if df is None or len(df) < 2:
        return {
            "available": False,
            "latest_ratio": None,
            "prev_ratio": None,
            "change": None,
            "warning": False,
            "severity": "none",
            "message": f"無足夠400張以上大戶持股資料。(更新時間: {now_hhmm()})"
        }

    latest = df.iloc[-1]
    prev = df.iloc[-2]

    latest_ratio = float(latest["holder_400_ratio"])
    prev_ratio = float(prev["holder_400_ratio"])
    change = latest_ratio - prev_ratio

    warning = change < -0.5

    if change <= -1.0:
        severity = "strong"
        message = f"400張以上大戶持股比例較上一期下降 {abs(change):.2f}% ，屬強警戒區。(更新時間: {now_hhmm()})"
    elif change < -0.5:
        severity = "mild"
        message = f"400張以上大戶持股比例較上一期下降 {abs(change):.2f}% ，屬輕度警戒區。(更新時間: {now_hhmm()})"
    elif change > 0:
        severity = "positive"
        message = f"400張以上大戶持股比例較上一期增加 {change:.2f}% (更新時間: {now_hhmm()})"
    else:
        severity = "neutral"
        message = f"400張以上大戶持股比例與上一期大致持平 (更新時間: {now_hhmm()})"

    return {
        "available": True,
        "latest_ratio": round(latest_ratio, 2),
        "prev_ratio": round(prev_ratio, 2),
        "change": round(change, 2),
        "warning": warning,
        "severity": severity,
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


def build_after_levels(close_price, high_price, low_price, direction="多", stage="③"):
    range_val = max(high_price - low_price, 0.01)

    if direction == "多":
        pressure1 = round(high_price, 2)
        if stage in ["③", "④"]:
            pressure2 = round(high_price + range_val * 0.8, 2)
        elif stage == "⑤":
            pressure2 = round(high_price + range_val * 0.4, 2)
        else:
            pressure2 = round(high_price + range_val * 0.25, 2)

        support1 = round(low_price, 2)

        if stage == "⑥":
            stop_loss = round(close_price * 0.99, 2)
        else:
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
# 階段判斷
# =========================
def detect_stage_advanced(df, stock_id):
    if df is None or len(df) < 30:
        return {
            "stage": "-",
            "stage_name": "資料不足",
            "stage_desc": f"資料不足，無法進行階段判斷。(更新時間: {now_hhmm()})",
            "chip_warning": False,
            "chip_message": f"無法判斷籌碼變化。(更新時間: {now_hhmm()})",
            "fake_break": False,
            "upper_shadow_pct": 0.0
        }

    d = df.copy().reset_index(drop=True)
    d["ma5"] = d["close"].rolling(5).mean()
    d["ma10"] = d["close"].rolling(10).mean()
    d["ma20"] = d["close"].rolling(20).mean()
    d["vol5"] = d["Trading_Volume"].rolling(5).mean()

    t = d.iloc[-1]
    prev = d.iloc[-2]

    close_now = float(t["close"])
    open_now = float(t["open"])
    high_now = float(t["max"])
    low_now = float(t["min"])

    high20 = float(d["max"].iloc[-20:].max())
    low20 = float(d["min"].iloc[-20:].min())
    pos20 = (close_now - low20) / (high20 - low20 + 1e-6)

    ret5 = (close_now - float(d.iloc[-6]["close"])) / float(d.iloc[-6]["close"]) * 100 if len(d) >= 6 else 0
    vol_ma5 = d["vol5"].iloc[-1]
    vol_ratio = float(t["Trading_Volume"]) / float(vol_ma5) if pd.notna(vol_ma5) and vol_ma5 != 0 else 1

    ma_bull = (
        pd.notna(t["ma5"]) and pd.notna(t["ma10"]) and pd.notna(t["ma20"]) and
        close_now > float(t["ma5"]) > float(t["ma10"]) > float(t["ma20"])
    )
    ma_slope = pd.notna(t["ma5"]) and pd.notna(prev["ma5"]) and float(t["ma5"]) > float(prev["ma5"])

    recent_high_10 = float(d["max"].iloc[-10:-1].max())
    fake_break = high_now > recent_high_10 and close_now < recent_high_10
    upper_shadow_pct = ((high_now - max(open_now, close_now)) / close_now * 100) if close_now != 0 else 0

    if pos20 < 0.20:
        stage = "①"
        stage_name = "底部"
        desc = "仍在低檔整理，尚未形成有效攻擊結構。"
    elif pos20 < 0.45:
        stage = "②"
        stage_name = "起漲"
        desc = "股價開始脫離低檔，屬起漲初期。"
    elif pos20 < 0.65 and ma_bull and ma_slope:
        stage = "③"
        stage_name = "攻擊"
        desc = "主升段啟動，結構明顯轉強。"
    elif pos20 < 0.80 and ma_bull and vol_ratio > 1.2:
        stage = "④"
        stage_name = "軋空"
        desc = "量價同步加速，進入強勢推升區。"
    elif pos20 < 0.92 and ret5 > 6:
        stage = "⑤"
        stage_name = "末段攻擊"
        desc = "股價已接近高檔，但仍維持末段攻擊結構。"
    else:
        stage = "⑥"
        stage_name = "噴出"
        desc = "短線已進入噴出區，追價風險顯著提高。"

    if fake_break:
        desc += " 目前出現假突破跡象。"

    if upper_shadow_pct > 2.0:
        desc += " 上影較長，需防沖高回落。"

    chip = check_400_holder_change(stock_id)

    return {
        "stage": stage,
        "stage_name": stage_name,
        "stage_desc": f"{desc} (更新時間: {now_hhmm()})",
        "chip_warning": chip["warning"],
        "chip_message": chip["message"],
        "fake_break": fake_break,
        "upper_shadow_pct": round(upper_shadow_pct, 2)
    }


# =========================
# AI 權重預測：四情境
# =========================
def build_next_day_scenarios(df, stage, chip_change=0.0, us_bias="中性"):
    scenarios = {
        "開高走高": 25,
        "開高走低": 25,
        "開低走高": 25,
        "開低走低": 25
    }

    if df is None or len(df) < 30:
        main_name = max(scenarios, key=scenarios.get)
        return {
            "scenarios": scenarios,
            "main_scenario": main_name,
            "response_note": f"資料不足，先以保守觀察為主。(更新時間: {now_hhmm()})"
        }

    d = df.copy().reset_index(drop=True)
    t = d.iloc[-1]
    p = d.iloc[-2]

    close_now = float(t["close"])
    open_now = float(t["open"])
    high_now = float(t["max"])
    low_now = float(t["min"])
    prev_close = float(p["close"])

    daily_change = (close_now - prev_close) / prev_close * 100 if prev_close != 0 else 0
    intraday_body = (close_now - open_now) / open_now * 100 if open_now != 0 else 0
    upper_shadow = (high_now - max(close_now, open_now)) / close_now * 100 if close_now != 0 else 0
    vol_ma5 = d["Trading_Volume"].rolling(5).mean().iloc[-1]
    vol_ratio = float(t["Trading_Volume"]) / float(vol_ma5) if pd.notna(vol_ma5) and vol_ma5 != 0 else 1
    close_pos = (close_now - low_now) / (high_now - low_now + 1e-6)

    if stage == "①":
        scenarios = {"開高走高": 10, "開高走低": 20, "開低走高": 30, "開低走低": 40}
    elif stage == "②":
        scenarios = {"開高走高": 25, "開高走低": 20, "開低走高": 35, "開低走低": 20}
    elif stage == "③":
        scenarios = {"開高走高": 35, "開高走低": 20, "開低走高": 30, "開低走低": 15}
    elif stage == "④":
        scenarios = {"開高走高": 38, "開高走低": 27, "開低走高": 22, "開低走低": 13}
    elif stage == "⑤":
        scenarios = {"開高走高": 20, "開高走低": 30, "開低走高": 20, "開低走低": 30}
    else:
        scenarios = {"開高走高": 12, "開高走低": 38, "開低走高": 10, "開低走低": 40}

    if close_pos > 0.7:
        scenarios["開高走高"] += 6
        scenarios["開低走高"] += 3
        scenarios["開低走低"] -= 5
    elif close_pos < 0.3:
        scenarios["開低走低"] += 8
        scenarios["開高走低"] += 4
        scenarios["開高走高"] -= 5

    if daily_change > 2 and intraday_body > 1 and vol_ratio > 1.2:
        scenarios["開高走高"] += 6
        scenarios["開低走高"] += 4
        scenarios["開高走低"] -= 5
        scenarios["開低走低"] -= 5

    if upper_shadow > 2:
        scenarios["開高走低"] += 8
        scenarios["開低走低"] += 4
        scenarios["開高走高"] -= 6
        scenarios["開低走高"] -= 6

    if daily_change < -1 and vol_ratio > 1.1:
        scenarios["開低走低"] += 8
        scenarios["開高走低"] += 4
        scenarios["開高走高"] -= 6
        scenarios["開低走高"] -= 6

    if chip_change < -1.0:
        scenarios["開高走低"] += 8
        scenarios["開低走低"] += 10
        scenarios["開高走高"] -= 8
        scenarios["開低走高"] -= 6
    elif chip_change < -0.5:
        scenarios["開高走低"] += 5
        scenarios["開低走低"] += 6
        scenarios["開高走高"] -= 5
    elif chip_change > 0.5:
        scenarios["開高走高"] += 5
        scenarios["開低走高"] += 4
        scenarios["開低走低"] -= 4

    if us_bias == "偏多":
        scenarios["開高走高"] += 5
        scenarios["開低走高"] += 3
        scenarios["開低走低"] -= 5
    elif us_bias == "偏空":
        scenarios["開高走低"] += 4
        scenarios["開低走低"] += 6
        scenarios["開高走高"] -= 5

    for k in scenarios:
        scenarios[k] = max(5, scenarios[k])

    total = sum(scenarios.values())
    scenarios = {k: round(v / total * 100) for k, v in scenarios.items()}

    diff = 100 - sum(scenarios.values())
    if diff != 0:
        main_key = max(scenarios, key=scenarios.get)
        scenarios[main_key] += diff

    main_name = max(scenarios, key=scenarios.get)

    response_map = {
        "開高走高": f"主要劇本為開高走高，盤前應對以順勢突破追蹤為主。(更新時間: {now_hhmm()})",
        "開高走低": f"主要劇本為開高走低，盤前應對應避免開盤追價，慎防沖高回落。(更新時間: {now_hhmm()})",
        "開低走高": f"主要劇本為開低走高，盤前應對宜等回穩後再介入，不宜急單。(更新時間: {now_hhmm()})",
        "開低走低": f"主要劇本為開低走低，盤前應對以防守為主，不主動追多。(更新時間: {now_hhmm()})"
    }

    return {
        "scenarios": scenarios,
        "main_scenario": main_name,
        "response_note": response_map[main_name]
    }
    # =========================
# 交易員一句話結論
# =========================
def build_trader_comment(stage, chip_warning, main_scenario, us_bias="中性"):
    if chip_warning and stage in ["⑤", "⑥"]:
        return f"高檔籌碼轉弱，優先防守 (更新時間: {now_hhmm()})"

    if stage == "⑥":
        return f"噴出過熱，嚴禁追價 (更新時間: {now_hhmm()})"

    if stage == "⑤":
        if main_scenario in ["開高走低", "開低走低"]:
            return f"末段攻擊仍在，但隔日拉回風險偏高 (更新時間: {now_hhmm()})"
        return f"末段攻擊延續，但仍須控管追價風險 (更新時間: {now_hhmm()})"

    if stage in ["③", "④"] and us_bias == "偏空":
        return f"主升段結構仍在，但外部環境偏空 (更新時間: {now_hhmm()})"

    if stage in ["③", "④"]:
        return f"主升段延續，結構健康 (更新時間: {now_hhmm()})"

    if stage == "②":
        return f"起漲初期，可持續觀察 (更新時間: {now_hhmm()})"

    if stage == "①":
        return f"仍在築底，暫不介入 (更新時間: {now_hhmm()})"

    return f"結構不明，建議觀望 (更新時間: {now_hhmm()})"


# =========================
# 相對有利區：整合 stage + 劇本 + 籌碼
# =========================
def build_favorable_zone(stage, main_scenario, chip_warning):
    if chip_warning and stage in ["⑤", "⑥"]:
        return "🔴 警戒：主力出貨中"

    if stage in ["③", "④"]:
        return "是（主升段）"

    if stage == "⑤":
        if main_scenario in ["開高走低", "開低走低"]:
            return "否（高檔拉回風險升高）"
        return "有限有利（末段攻擊）"

    if stage == "⑥":
        return "❌ 否（風險極高）"

    if stage == "②":
        return "觀察"

    return "否"


# =========================
# 勝率 AI 模型
# =========================
def ai_winrate_model(df, stage, chip_warning, us_block):
    score = 50

    if df is None or len(df) < 20:
        return 50, "資料不足"

    d = df.copy().reset_index(drop=True)
    t = d.iloc[-1]
    p = d.iloc[-2]

    close = float(t["close"])
    open_p = float(t["open"])
    high = float(t["max"])
    low = float(t["min"])
    prev_close = float(p["close"])

    if close > open_p:
        score += 5
    else:
        score -= 5

    pos = (close - low) / (high - low + 1e-6)
    if pos > 0.7:
        score += 8
    elif pos < 0.3:
        score -= 8

    change = (close - prev_close) / prev_close * 100 if prev_close != 0 else 0
    if change > 2:
        score += 6
    elif change < -2:
        score -= 6

    vol_ma5 = d["Trading_Volume"].rolling(5).mean().iloc[-1]
    if pd.notna(vol_ma5) and vol_ma5 != 0:
        vol_ratio = float(t["Trading_Volume"]) / float(vol_ma5)
        if vol_ratio > 1.2:
            score += 6
        elif vol_ratio < 0.8:
            score -= 4

    if stage in ["③", "④"]:
        score += 10
    elif stage == "⑤":
        score -= 5
    elif stage == "⑥":
        score -= 12
    elif stage == "①":
        score -= 8

    if chip_warning:
        score -= 15
    else:
        score += 5

    if us_block and us_block["indices"]:
        for idx in us_block["indices"]:
            pct = idx.get("change_pct", 0)
            if pct > 1:
                score += 5
            elif pct < -1:
                score -= 5

    score = max(5, min(95, int(score)))

    if score >= 70:
        risk = "低風險（偏多）"
    elif score >= 55:
        risk = "中性偏多"
    elif score >= 45:
        risk = "震盪"
    elif score >= 30:
        risk = "偏空風險"
    else:
        risk = "高風險（不建議交易）"

    return score, risk


def ai_final_decision(winrate, stage, main_scenario, chip_warning):
    if chip_warning and stage in ["⑤", "⑥"]:
        return "❌ 主力出貨中，不可進場"

    if winrate >= 70:
        return "✅ 可積極操作（順勢）"

    if winrate >= 55:
        return "⚠️ 可小倉操作"

    if winrate >= 45:
        return "⚖️ 觀望為主"

    return "🚫 不建議進場"


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

    backtest_result = backtest_strategy(df)

    t = df.iloc[-1]
    close_price = round(float(t["close"]), 2)
    high_price = round(float(t["max"]), 2)
    low_price = round(float(t["min"]), 2)

    stage_info = detect_stage_advanced(df, stock_id)
    us_block = build_us_correlation_block(stock_id)
    chip_info = check_400_holder_change(stock_id)

    levels = build_after_levels(
        close_price,
        high_price,
        low_price,
        direction,
        stage=stage_info["stage"]
    )

    scenario_info = build_next_day_scenarios(
        df,
        stage_info["stage"],
        chip_change=chip_info["change"] if chip_info["change"] is not None else 0.0,
        us_bias=us_block["bias"]
    )

    favorable_zone = build_favorable_zone(
        stage_info["stage"],
        scenario_info["main_scenario"],
        stage_info["chip_warning"]
    )

    comment = build_trader_comment(
        stage_info["stage"],
        stage_info["chip_warning"],
        scenario_info["main_scenario"],
        us_bias=us_block["bias"]
    )

    winrate_ai, risk_ai = ai_winrate_model(
        df,
        stage_info["stage"],
        stage_info["chip_warning"],
        us_block
    )

    final_ai_decision = ai_final_decision(
        winrate_ai,
        stage_info["stage"],
        scenario_info["main_scenario"],
        stage_info["chip_warning"]
    )

    risk_level = (
        "高"
        if favorable_zone in ["🔴 警戒：主力出貨中", "❌ 否（風險極高）", "否（高檔拉回風險升高）"]
        else "中"
        if favorable_zone in ["有限有利（末段攻擊）", "觀察"]
        else "低"
    )

    return {
        "stock": stock_id,
        "close": close_price,
        "high": high_price,
        "low": low_price,
        "score": score_value,
        "backtest": backtest_result,
        "pressure1": levels["pressure1"],
        "pressure2": levels["pressure2"],
        "support1": levels["support1"],
        "stop_loss": levels["stop_loss"],
        "stage": stage_info["stage"],
        "stage_name": stage_info["stage_name"],
        "stage_desc": stage_info["stage_desc"],
        "chip_warning": stage_info["chip_warning"],
        "chip_message": chip_info["message"],
        "chip_severity": chip_info["severity"],
        "favorable_zone": favorable_zone,
        "comment": comment,
        "scenario_info": scenario_info,
        "us_block": us_block,
        "risk_level": risk_level,
        "market_label": market_label(stock_id),
        "winrate_ai": winrate_ai,
        "risk_ai": risk_ai,
        "final_ai_decision": final_ai_decision
    }


# =========================
# 盤中即時：台股 / 美股雙市場
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


def fetch_us_intraday_quote(symbol):
    try:
        ticker = yf.Ticker(symbol.upper())
        hist = ticker.history(period="2d", interval="1m")

        if hist is None or hist.empty:
            hist = ticker.history(period="5d", interval="1d")
            if hist is None or hist.empty:
                return None

            last = hist.iloc[-1]
            prev_close = hist["Close"].iloc[-2] if len(hist) >= 2 else last["Close"]
            last_price = float(last["Close"])
            open_price = float(last["Open"])
            high_price = float(last["High"])
            low_price = float(last["Low"])
            ref_price = float(prev_close)
            change_pct = (last_price - ref_price) / ref_price * 100 if ref_price != 0 else 0

            return {
                "lastPrice": last_price,
                "openPrice": open_price,
                "highPrice": high_price,
                "lowPrice": low_price,
                "referencePrice": ref_price,
                "changePercent": round(change_pct, 2)
            }

        last_row = hist.iloc[-1]
        open_price = float(hist["Open"].iloc[0])
        high_price = float(hist["High"].max())
        low_price = float(hist["Low"].min())
        last_price = float(last_row["Close"])

        daily = ticker.history(period="5d", interval="1d")
        ref_price = float(daily["Close"].iloc[-2]) if daily is not None and len(daily) >= 2 else open_price
        change_pct = (last_price - ref_price) / ref_price * 100 if ref_price != 0 else 0

        return {
            "lastPrice": last_price,
            "openPrice": open_price,
            "highPrice": high_price,
            "lowPrice": low_price,
            "referencePrice": ref_price,
            "changePercent": round(change_pct, 2)
        }
    except Exception:
        return None


def fetch_live_quote(symbol):
    if is_us_symbol(symbol):
        return fetch_us_intraday_quote(symbol)

    api_key = get_secret("FUGLE_API_KEY", "")
    if not api_key:
        return None

    return fugle_quote(symbol, api_key)


# =========================
# 盤中獨立模式：即時結構計算
# =========================
def build_intraday_independent_levels(price, open_price, high, low, ref_price, direction="多"):
    price = safe_float(price)
    open_price = safe_float(open_price)
    high = safe_float(high)
    low = safe_float(low)
    ref_price = safe_float(ref_price)

    range_now = max(high - low, 0.01)
    pivot = round((high + low + price) / 3, 2)

    if direction == "多":
        support1 = round(max(low, min(open_price, price)), 2)
        support2 = round(low, 2)

        pressure1 = round(max(pivot, price + range_now * 0.25), 2)
        pressure2 = round(max(high, pressure1 + range_now * 0.35), 2)
        strong_pressure = round(max(high, pressure2 + range_now * 0.25), 2)

        entry_price = round(max(price, support1 + range_now * 0.3), 2)
        stop_loss = round(support2, 2)
        tp1 = pressure1
        tp2 = pressure2

        if high > ref_price and price > open_price and price >= support1:
            status = f"盤中獨立模式：屬強勢震盪結構，但須等重新站穩確認位後再偏多操作。(更新時間: {now_hhmm()})"
        elif price < open_price and price <= support1:
            status = f"盤中獨立模式：早盤轉弱，先以防守為主。(更新時間: {now_hhmm()})"
        else:
            status = f"盤中獨立模式：高檔震盪中，暫不宜追價。(更新時間: {now_hhmm()})"

    else:
        pressure1 = round(max(high, price), 2)
        pressure2 = round(pressure1 + range_now * 0.3, 2)
        strong_pressure = pressure2
        support1 = round(min(low, price - range_now * 0.25), 2)
        support2 = round(low, 2)

        entry_price = support1
        stop_loss = round(pressure1, 2)
        tp1 = round(support1 - range_now * 0.3, 2)
        tp2 = round(support1 - range_now * 0.6, 2)

        if price < open_price and price < ref_price:
            status = f"盤中獨立模式：空方偏強，可留意跌破支撐後的續弱訊號。(更新時間: {now_hhmm()})"
        else:
            status = f"盤中獨立模式：尚未形成明確空方結構。(更新時間: {now_hhmm()})"

    return {
        "mode": "盤中獨立模式",
        "pressure1": pressure1,
        "pressure2": pressure2,
        "strong_pressure": strong_pressure,
        "support1": support1,
        "support2": support2,
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "status": status
    }


# =========================
# 盤中承接模式：沿用盤後基準
# =========================
def build_intraday_plan(price, open_price, high, low, ref_price, pressure, support, direction="多"):
    if direction == "多":
        entry_price = round(pressure, 2)
        stop_loss = round(max(support, pressure * 0.995), 2)
        tp1 = round(pressure + (pressure - support) * 0.5, 2)
        tp2 = round(pressure + (pressure - support) * 1.0, 2)

        chase_gap = ((price - entry_price) / entry_price * 100) if entry_price != 0 else 0

        if price > pressure and price >= open_price and price >= ref_price and chase_gap <= 1.5:
            status = f"盤後承接模式：已突破壓力，可依紀律追蹤。(更新時間: {now_hhmm()})"
        elif price > pressure and chase_gap > 1.5:
            status = f"盤後承接模式：已突破但乖離偏大，不宜追價。(更新時間: {now_hhmm()})"
        elif high > pressure and price < pressure:
            status = f"盤後承接模式：盤中假突破，需防回落。(更新時間: {now_hhmm()})"
        else:
            status = f"盤後承接模式：尚未突破壓力。(更新時間: {now_hhmm()})"

    else:
        entry_price = round(support, 2)
        stop_loss = round(pressure * 1.015, 2)
        tp1 = round(support - (pressure - support) * 0.5, 2)
        tp2 = round(support - (pressure - support) * 1.0, 2)

        if price < support and price <= open_price and price <= ref_price:
            status = f"盤後承接模式：已跌破支撐，空方延續。(更新時間: {now_hhmm()})"
        elif low < support and price > support:
            status = f"盤後承接模式：盤中假跌破，空方追擊風險高。(更新時間: {now_hhmm()})"
        else:
            status = f"盤後承接模式：尚未跌破支撐。(更新時間: {now_hhmm()})"

    return {
        "mode": "盤後承接模式",
        "entry_price": entry_price,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "status": status
    }


# =========================
# 盤中 AI 決策 / 自動交易
# =========================
def dynamic_intraday_levels(data, base_pressure, base_support):
    price = safe_float(data.get("lastPrice"))
    high = safe_float(data.get("highPrice"))
    low = safe_float(data.get("lowPrice"))

    new_pressure = max(base_pressure, high)
    new_support = min(base_support, low)

    return {
        "pressure": round(new_pressure, 2),
        "support": round(new_support, 2),
        "mid": round((new_pressure + new_support) / 2, 2)
    }


def intraday_ai_decision(data, pressure, support):
    price = safe_float(data.get("lastPrice"))
    open_p = safe_float(data.get("openPrice"))
    high = safe_float(data.get("highPrice"))
    low = safe_float(data.get("lowPrice"))
    ref = safe_float(data.get("referencePrice"))

    decision = ""
    strength = ""
    action = ""

    if price > pressure:
        if price > open_p and price > ref:
            decision = "有效突破"
            strength = "多方強勢"
            action = "可順勢做多"
        else:
            decision = "假突破"
            strength = "誘多"
            action = "禁止追價"
    elif price < support:
        decision = "跌破支撐"
        strength = "空方轉強"
        action = "避免做多"
    elif high >= pressure * 0.98:
        decision = "高檔震盪"
        strength = "動能不足"
        action = "不追 / 逢高減碼"
    elif low <= support:
        decision = "支撐反彈"
        strength = "短線止跌"
        action = "可小倉試單"
    else:
        decision = "盤整"
        strength = "方向不明"
        action = "觀望"

    return {
        "decision": decision,
        "strength": strength,
        "action": action
    }


def generate_trade_plan(pressure, support, direction="多"):
    if direction == "多":
        entry = pressure
        stop = support
        tp1 = round(pressure + (pressure - support) * 0.5, 2)
        tp2 = round(pressure + (pressure - support) * 1.0, 2)
    else:
        entry = support
        stop = pressure
        tp1 = round(support - (pressure - support) * 0.5, 2)
        tp2 = round(support - (pressure - support) * 1.0, 2)

    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "tp1": tp1,
        "tp2": tp2
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
    render_after_usage_note()
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
            us_block = res["us_block"]

            st.session_state.after_result = {
                "stock": stock_id,
                "stock_name": stock_name,
                "market": market if market else res["market_label"],
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
                "scenario_info": res["scenario_info"],
                "us_block": us_block,
                "risk_level": res["risk_level"],
                "market_label": res["market_label"],
                "winrate_ai": res["winrate_ai"],
                "risk_ai": res["risk_ai"],
                "final_ai_decision": res["final_ai_decision"]
            }

            st.subheader("AI勝率分析")
            c1, c2 = st.columns(2)
            c1.metric("今日勝率", f"{res['winrate_ai']}%")
            c2.metric("風險等級", res["risk_ai"])

            st.subheader("AI最終決策")
            st.markdown(f"### {res['final_ai_decision']}")

            st.subheader("交易員判讀結論")
            st.markdown(f"### {res['comment']}")

            st.subheader("市場別")
            st.write(f"{res['market_label']} (更新時間: {now_hhmm()})")

            st.subheader("風險燈號")
            risk_color = "#16a34a" if res["risk_level"] == "低" else "#d97706" if res["risk_level"] == "中" else "#dc2626"
            st.markdown(
                f"<div style='font-weight:700;color:{risk_color};'>風險等級：{res['risk_level']} (更新時間: {now_hhmm()})</div>",
                unsafe_allow_html=True
            )

            st.subheader("基本面摘要")
            st.write(auto_fundamental)

            st.subheader("美股連動觀測")
            st.write(f"對位邏輯：{us_block['mapping_label']} (更新時間: {now_hhmm()})")
            st.write(f"美股連動偏向：{us_block['bias']} (更新時間: {now_hhmm()})")
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

            if res["favorable_zone"] in ["🔴 警戒：主力出貨中", "❌ 否（風險極高）", "否（高檔拉回風險升高）"]:
                c2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#ff4b4b;padding-top:0.4rem;'>"
                    f"{res['favorable_zone']} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            elif res["favorable_zone"] in ["有限有利（末段攻擊）", "觀察"]:
                c2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#d97706;padding-top:0.4rem;'>"
                    f"{res['favorable_zone']} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            else:
                c2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#16a34a;padding-top:0.4rem;'>"
                    f"{res['favorable_zone']} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )

            st.write(res["stage_desc"])

            st.subheader("大戶籌碼增減狀況")
            if res["chip_warning"]:
                st.markdown(
                    f"<span style='color:#ff4b4b;font-weight:700;'>{res['chip_message']}</span>",
                    unsafe_allow_html=True
                )
            else:
                st.write(res["chip_message"])

            st.subheader("明日走勢推演（盤前規劃用）")
            s = res["scenario_info"]["scenarios"]
            g1, g2 = st.columns(2)
            g3, g4 = st.columns(2)

            g1.metric("開高走高", f"{s['開高走高']}%")
            g2.metric("開高走低", f"{s['開高走低']}%")
            g3.metric("開低走高", f"{s['開低走高']}%")
            g4.metric("開低走低", f"{s['開低走低']}%")

            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("主要劇本")
            st.write(f"{res['scenario_info']['main_scenario']} (更新時間: {now_hhmm()})")

            st.subheader("盤前應對")
            st.write(res["scenario_info"]["response_note"])

            st.subheader("關鍵價位")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("壓力一", fmt_num(res["pressure1"]))
            d2.metric("壓力二", fmt_num(res["pressure2"]))
            d3.metric("支撐", fmt_num(res["support1"]))
            d4.metric("停損", fmt_num(res["stop_loss"]))
            st.caption(f"更新時間: {now_hhmm()}")

with tab2:
    render_intra_usage_note()
    st.title("盤中判斷")

    after_data = st.session_state.after_result

    default_stock = after_data["stock"] if after_data else "4906"
    default_name = after_data["stock_name"] if after_data else ""
    default_market = after_data["market"] if after_data else market_label("4906")
    default_cost = after_data["cost"] if after_data else ""
    default_direction = after_data["direction"] if after_data else "多"
    default_pressure = float(after_data["pressure1"]) if after_data else None
    default_support = float(after_data["support1"]) if after_data else None
    default_fundamental = after_data["auto_fundamental"] if after_data else build_auto_fundamental_summary(default_stock)
    default_stage = after_data["stage"] if after_data else "-"
    default_stage_name = after_data["stage_name"] if after_data else "未判斷"
    default_stage_desc = after_data["stage_desc"] if after_data else f"未偵測到盤後分析結果，系統將改用盤中獨立模式。(更新時間: {now_hhmm()})"
    default_favorable = after_data["favorable_zone"] if after_data else "盤中獨立判斷"
    default_chip_warning = after_data["chip_warning"] if after_data else False
    default_comment = after_data["comment"] if after_data else f"未偵測到盤後分析結果，系統已切換為盤中獨立判斷模式。(更新時間: {now_hhmm()})"
    default_us_block = after_data["us_block"] if after_data else build_us_correlation_block(default_stock)
    default_main_scenario = after_data["scenario_info"]["main_scenario"] if after_data else "盤中獨立模式"
    default_risk_level = after_data["risk_level"] if after_data else "未知"
    default_market_label = after_data["market_label"] if after_data else market_label(default_stock)
    default_winrate_ai = after_data["winrate_ai"] if after_data else 50
    default_risk_ai = after_data["risk_ai"] if after_data else "資料不足"
    default_final_ai_decision = after_data["final_ai_decision"] if after_data else "⚖️ 觀望為主"

    with st.form("intra_form"):
        stock_i = st.text_input("股票代號", value=default_stock).strip()
        stock_name_i = st.text_input("股票名稱", value=default_name).strip()
        market_i = st.text_input("市場別", value=default_market).strip()
        cost_i = st.text_input("買進或放空成本", value=default_cost)
        direction_i = st.selectbox("操作方向", ["多", "空"], index=0 if default_direction == "多" else 1)

        if after_data:
            pressure_i = st.number_input("壓力", value=default_pressure, step=0.1, format="%.2f")
            support_i = st.number_input("支撐", value=default_support, step=0.1, format="%.2f")
        else:
            st.caption("未偵測到盤後分析結果，將使用盤中獨立模式自動計算關鍵價位。")
            pressure_i = None
            support_i = None

        submitted_intra = st.form_submit_button("更新盤中判斷")

    if submitted_intra:
        data = fetch_live_quote(stock_i)

        if not data:
            st.error("抓不到盤中資料，請確認股票代號、網路來源或目前是否有行情")
        else:
            if after_data and pressure_i is not None and support_i is not None:
                dyn = dynamic_intraday_levels(data, pressure_i, support_i)
                plan = build_intraday_plan(
                    price=safe_float(data.get("lastPrice", 0)),
                    open_price=safe_float(data.get("openPrice", 0)),
                    high=safe_float(data.get("highPrice", 0)),
                    low=safe_float(data.get("lowPrice", 0)),
                    ref_price=safe_float(data.get("referencePrice", 0)),
                    pressure=float(dyn["pressure"]),
                    support=float(dyn["support"]),
                    direction=direction_i
                )
                ai = intraday_ai_decision(data, dyn["pressure"], dyn["support"])
                trade = generate_trade_plan(dyn["pressure"], dyn["support"], direction_i)
                current_mode = "盤後承接模式"
                show_pressure = dyn["pressure"]
                show_support = dyn["support"]
            else:
                plan = build_intraday_independent_levels(
                    price=safe_float(data.get("lastPrice", 0)),
                    open_price=safe_float(data.get("openPrice", 0)),
                    high=safe_float(data.get("highPrice", 0)),
                    low=safe_float(data.get("lowPrice", 0)),
                    ref_price=safe_float(data.get("referencePrice", 0)),
                    direction=direction_i
                )
                ai = intraday_ai_decision(data, plan["pressure1"], plan["support1"])
                trade = generate_trade_plan(plan["pressure1"], plan["support1"], direction_i)
                current_mode = "盤中獨立模式"
                show_pressure = plan["pressure1"]
                show_support = plan["support1"]

            st.subheader("AI勝率分析")
            c1, c2 = st.columns(2)
            c1.metric("盤前勝率參考", f"{default_winrate_ai}%")
            c2.metric("風險等級", default_risk_ai)

            st.subheader("AI最終決策")
            st.markdown(f"### {default_final_ai_decision}")

            st.subheader("交易員判讀結論")
            st.markdown(f"### {default_comment}")

            st.subheader("目前模式")
            st.write(f"{current_mode} (更新時間: {now_hhmm()})")

            st.subheader("市場別")
            st.write(f"{default_market_label if market_i == default_market else market_label(stock_i)} (更新時間: {now_hhmm()})")

            st.subheader("風險燈號")
            risk_color = "#16a34a" if default_risk_level == "低" else "#d97706" if default_risk_level == "中" else "#dc2626"
            st.markdown(
                f"<div style='font-weight:700;color:{risk_color};'>風險等級：{default_risk_level} (更新時間: {now_hhmm()})</div>",
                unsafe_allow_html=True
            )

            st.subheader("基本面摘要")
            st.write(default_fundamental)

            st.subheader("美股連動觀測")
            st.write(f"對位邏輯：{default_us_block['mapping_label']} (更新時間: {now_hhmm()})")
            st.write(f"美股連動偏向：{default_us_block['bias']} (更新時間: {now_hhmm()})")
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

            if default_favorable in ["🔴 警戒：主力出貨中", "❌ 否（風險極高）", "否（高檔拉回風險升高）"]:
                s2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#ff4b4b;padding-top:0.4rem;'>"
                    f"{default_favorable} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            elif default_favorable in ["有限有利（末段攻擊）", "觀察"]:
                s2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#d97706;padding-top:0.4rem;'>"
                    f"{default_favorable} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )
            else:
                s2.markdown(
                    f"<div style='font-size:1.02rem;font-weight:700;color:#16a34a;padding-top:0.4rem;'>"
                    f"{default_favorable} (更新時間: {now_hhmm()})</div>",
                    unsafe_allow_html=True
                )

            st.write(default_stage_desc)
            st.write(f"主要劇本：{default_main_scenario} (更新時間: {now_hhmm()})")

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

            st.subheader("盤中動態結構")
            x1, x2, x3 = st.columns(3)
            x1.metric("動態壓力", fmt_num(show_pressure))
            x2.metric("動態支撐", fmt_num(show_support))
            x3.metric("模式", current_mode)
            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("AI盤中決策")
            a1, a2, a3 = st.columns(3)
            a1.metric("判斷", ai["decision"])
            a2.metric("結構", ai["strength"])
            a3.metric("行動", ai["action"])

            st.subheader("自動交易計畫")
            t1, t2, t3, t4 = st.columns(4)
            t1.metric("進場價", fmt_num(trade["entry"]))
            t2.metric("停損價", fmt_num(trade["stop"]))
            t3.metric("第一賣出", fmt_num(trade["tp1"]))
            t4.metric("第二賣出", fmt_num(trade["tp2"]))
            st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("盤中關鍵價位（09:00-11:00 執行用）")
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("進場價", fmt_num(plan["entry_price"]))
            d2.metric("停損價", fmt_num(plan["stop_loss"]))
            d3.metric("第一賣出價", fmt_num(plan["tp1"]))
            d4.metric("第二賣出價", fmt_num(plan["tp2"]))
            st.caption(f"更新時間: {now_hhmm()}")

            if current_mode == "盤中獨立模式":
                st.subheader("盤中獨立模式參考區間")
                x1, x2, x3 = st.columns(3)
                x1.metric("短壓", fmt_num(plan["pressure1"]))
                x2.metric("強壓", fmt_num(plan["pressure2"]))
                x3.metric("防守支撐", fmt_num(plan["support1"]))
                st.caption(f"更新時間: {now_hhmm()}")

            st.subheader("盤中狀態")
            st.write(plan["status"])
            
