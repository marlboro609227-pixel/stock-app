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

def safe_text(x):
    return str(x).strip() if x is not None else ""

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
    if df is None or df.empty:
        return None

    if "stock_id" not in df.columns:
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
        return "未成功抓取最新公開基本面資料，建議後續補充月營收或產業題材後再行比對。"

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

def build_after_decision(score, win_rate, avg_return, close_price, pressure, support, direction="多"):
    if direction == "多":
        if win_rate >= 55 and avg_return > 0 and score >= 70:
            action = "偏多"
        elif win_rate >= 50 and score >= 60:
            action = "續抱"
        elif score >= 50:
            action = "偏保守"
        else:
            action = "汰弱"

        stop_loss = round(min(support, close_price * 0.985), 2)
        pressure1 = round(pressure, 2)
        pressure2 = round(pressure * 1.03, 2)
        support1 = round(support, 2)

    else:
        if win_rate >= 55 and avg_return < 0 and score <= 40:
            action = "偏空"
        elif score <= 50:
            action = "反彈調節"
        else:
            action = "偏保守"

        pressure1 = round(pressure, 2)
        pressure2 = round(pressure * 1.02, 2)
        support1 = round(support, 2)
        stop_loss = round(pressure * 1.015, 2)

    return {
        "action": action,
        "pressure1": pressure1,
        "pressure2": pressure2,
        "support1": support1,
        "stop_loss": stop_loss
    }

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
    p = df.iloc[-2]

    return {
        "stock": stock_id,
        "score": score_value,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "trades": trades,
        "close": round(float(t["close"]), 2),
        "open": round(float(t["open"]), 2),
        "high": round(float(t["max"]), 2),
        "low": round(float(t["min"]), 2),
        "vol_now": int(t["Trading_Volume"]),
        "vol_prev": int(p["Trading_Volume"])
    }

# =========================
# 盤中：Fugle即時報價
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
        breakout = price > pressure
        fake_break = high > pressure and price < pressure
        strong = price >= open_price and price >= ref_price
        chase_limit = round(pressure * 1.01, 2)
        stop_loss = round(max(support, pressure * 0.995), 2)
        tp1 = round(pressure + (pressure - support) * 0.5, 2)
        tp2 = round(pressure + (pressure - support) * 1.0, 2)

        if breakout and strong and price <= chase_limit:
            action = "偏多"
            comment = "股價已有效突破盤後壓力區，短線可依紀律偏多操作。"
        elif breakout and price > chase_limit:
            action = "偏保守"
            comment = "股價雖已突破，但短線乖離偏大，不宜追價，宜待拉回確認。"
        elif fake_break:
            action = "反彈調節"
            comment = "盤中一度越過壓力後又回落，屬假突破型態，宜保守應對。"
        else:
            action = "偏保守"
            comment = "尚未形成有效突破，建議持續觀察，不宜提前追價。"

    else:
        breakout = price < support
        fake_break = low < support and price > support
        strong = price <= open_price and price <= ref_price
        chase_limit = round(support * 0.99, 2)
        stop_loss = round(pressure * 1.015, 2)
        tp1 = round(support - (pressure - support) * 0.5, 2)
        tp2 = round(support - (pressure - support) * 1.0, 2)

        if breakout and strong and price >= chase_limit:
            action = "偏空"
            comment = "股價已跌破盤後支撐區，空方延續力道具備，可依紀律偏空操作。"
        elif fake_break:
            action = "偏保守"
            comment = "跌破後迅速站回支撐，屬假跌破，空方追擊風險偏高。"
        else:
            action = "反彈調節"
            comment = "尚未形成明確空方破位訊號，建議以反彈調節與觀察為主。"

    return {
        "action": action,
        "comment": comment,
        "stop_loss": stop_loss,
        "tp1": tp1,
        "tp2": tp2
    }

# =========================
# 輸出文字
# =========================
def build_after_speech(stock_id, stock_name, market, cost, direction, auto_fundamental, res, plan):
    name_show = stock_name if stock_name else "未填名稱"
    market_show = market if market else "未填市場"
    cost_text = safe_text(cost) if safe_text(cost) else "未填成本"

    tech_text = (
        f"技術面與籌碼面重點：\n"
        f"今日收盤 {fmt_num(res['close'])}，日內高低區間為 {fmt_num(res['low'])} 至 {fmt_num(res['high'])}。"
        f"今日評分 {res['score']} 分，歷史勝率 {res['win_rate']}%，平均報酬 {res['avg_return']}%，樣本筆數 {res['trades']}。"
        f"若以成交量觀察，今日成交量與前一日相比 {'放大' if res['vol_now'] > res['vol_prev'] else '未明顯放大'}，"
        f"現階段壓力區先看 {fmt_num(plan['pressure1'])}，支撐區先看 {fmt_num(plan['support1'])}。"
    )

    if direction == "多":
        op_text = (
            f"操作建議：\n"
            f"操作方向：{plan['action']}\n"
            f"壓力價：{fmt_num(plan['pressure1'])} / {fmt_num(plan['pressure2'])}\n"
            f"支撐價：{fmt_num(plan['support1'])}\n"
            f"停損價：{fmt_num(plan['stop_loss'])}\n"
            f"建議說明：若後續能帶量突破壓力區，短線結構才有機會轉強；若跌破停損價，則原先多方假設失效，宜嚴守紀律。"
        )
    else:
        op_text = (
            f"操作建議：\n"
            f"操作方向：{plan['action']}\n"
            f"壓力價：{fmt_num(plan['pressure1'])} / {fmt_num(plan['pressure2'])}\n"
            f"支撐價：{fmt_num(plan['support1'])}\n"
            f"停損價：{fmt_num(plan['stop_loss'])}\n"
            f"建議說明：反彈至壓力區若無法突破，仍可視為空方觀察區；若上破停損價，則空方假設失效，宜立即修正。"
        )

    return (
        f"{stock_id} {name_show} {market_show} {cost_text} {direction}\n\n"
        f"基本面摘要：\n{auto_fundamental}\n\n"
        f"{tech_text}\n\n"
        f"{op_text}"
    )

def build_intraday_speech(stock_id, stock_name, market, cost, direction, auto_fundamental, quote, pressure, support, plan):
    name_show = stock_name if stock_name else "未填名稱"
    market_show = market if market else "未填市場"
    cost_text = safe_text(cost) if safe_text(cost) else "未填成本"

    tech_text = (
        f"技術面與籌碼面重點：\n"
        f"盤中現價 {fmt_num(quote.get('lastPrice', 0))}，開盤 {fmt_num(quote.get('openPrice', 0))}，"
        f"盤中高低為 {fmt_num(quote.get('lowPrice', 0))} 至 {fmt_num(quote.get('highPrice', 0))}，"
        f"參考價 {fmt_num(quote.get('referencePrice', 0))}，漲跌幅 {fmt_num(quote.get('changePercent', 0))}%。"
        f"目前盤後帶入壓力位 {fmt_num(pressure)}，支撐位 {fmt_num(support)}。"
    )

    if direction == "多":
        op_text = (
            f"操作建議：\n"
            f"操作方向：{plan['action']}\n"
            f"壓力價：{fmt_num(pressure)} / {fmt_num(pressure * 1.02)}\n"
            f"支撐價：{fmt_num(support)}\n"
            f"停損價：{fmt_num(plan['stop_loss'])}\n"
            f"建議說明：{plan['comment']} 第一停利可參考 {fmt_num(plan['tp1'])}，第二停利可參考 {fmt_num(plan['tp2'])}。"
        )
    else:
        op_text = (
            f"操作建議：\n"
            f"操作方向：{plan['action']}\n"
            f"壓力價：{fmt_num(pressure)} / {fmt_num(pressure * 1.02)}\n"
            f"支撐價：{fmt_num(support)}\n"
            f"停損價：{fmt_num(plan['stop_loss'])}\n"
            f"建議說明：{plan['comment']} 第一回補區可參考 {fmt_num(plan['tp1'])}，第二回補區可參考 {fmt_num(plan['tp2'])}。"
        )

    return (
        f"{stock_id} {name_show} {market_show} {cost_text} {direction}\n\n"
        f"基本面摘要：\n{auto_fundamental}\n\n"
        f"{tech_text}\n\n"
        f"{op_text}"
    )

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
    st.title("單股盤後投顧版")
    st.caption("收盤後使用：輸入單一標的，系統自動抓取最新公開基本面資料並整理盤後觀察重點")

    with st.form("after_form"):
        stock_id = st.text_input("股票代號", value="4906").strip()
        stock_name = st.text_input("股票名稱", value="").strip()
        market = st.text_input("市場別", value="台股").strip()
        direction = st.selectbox("操作方向", ["多", "空"])
        cost = st.text_input("買進或放空成本", value="")
        submitted_after = st.form_submit_button("開始分析")

    if submitted_after:
        res = analyze_after_stock(stock_id)

        if "error" in res:
            st.error(res["error"])
        else:
            plan = build_after_decision(
                score=res["score"],
                win_rate=res["win_rate"],
                avg_return=res["avg_return"],
                close_price=res["close"],
                pressure=res["high"],
                support=res["low"],
                direction=direction
            )

            auto_fundamental = build_auto_fundamental_summary(stock_id)

            st.session_state.after_result = {
                "stock": stock_id,
                "stock_name": stock_name,
                "market": market,
                "cost": cost,
                "direction": direction,
                "res": res,
                "plan": plan,
                "auto_fundamental": auto_fundamental
            }

            st.subheader("盤後結果")
            st.write(f"股票：{stock_id}")
            st.write(f"等級：{plan['action']}")
            st.write(f"今日評分：{res['score']}")
            st.write(f"歷史勝率：{res['win_rate']}%")
            st.write(f"平均報酬：{res['avg_return']}%")
            st.write(f"樣本筆數：{res['trades']}")

            st.write("操作重點：")
            st.write(f"壓力：{fmt_num(plan['pressure1'])} / {fmt_num(plan['pressure2'])}")
            st.write(f"支撐：{fmt_num(plan['support1'])}")
            st.write(f"停損：{fmt_num(plan['stop_loss'])}")

            speech = build_after_speech(
                stock_id=stock_id,
                stock_name=stock_name,
                market=market,
                cost=cost,
                direction=direction,
                auto_fundamental=auto_fundamental,
                res=res,
                plan=plan
            )

            st.subheader("操作建議")
            st.text_area("可直接複製使用", value=speech, height=420)

with tab2:
    st.title("單股盤中投顧版")
    st.caption("盤中使用：依盤後壓力與支撐搭配即時報價，自動給出盤中操作判斷")

    after_data = st.session_state.after_result
    default_stock = after_data["stock"] if after_data else "4906"
    default_name = after_data["stock_name"] if after_data else ""
    default_market = after_data["market"] if after_data else "台股"
    default_cost = after_data["cost"] if after_data else ""
    default_direction = after_data["direction"] if after_data else "多"
    default_pressure = float(after_data["plan"]["pressure1"]) if after_data else 42.0
    default_support = float(after_data["plan"]["support1"]) if after_data else 39.0
    default_fundamental = after_data["auto_fundamental"] if after_data else build_auto_fundamental_summary(default_stock)

    with st.form("intra_form"):
        api_key = st.text_input("Fugle API Key", value="", type="password")
        stock_i = st.text_input("股票代號", value=default_stock).strip()
        stock_name_i = st.text_input("股票名稱", value=default_name).strip()
        market_i = st.text_input("市場別", value=default_market).strip()
        cost_i = st.text_input("買進或放空成本", value=default_cost)
        direction_i = st.selectbox("操作方向", ["多", "空"], index=0 if default_direction == "多" else 1)
        pressure_i = st.number_input("壓力", value=default_pressure, step=0.1, format="%.2f")
        support_i = st.number_input("支撐", value=default_support, step=0.1, format="%.2f")
        submitted_intra = st.form_submit_button("更新盤中判斷")

    if submitted_intra:
        data = fugle_quote(stock_i, api_key)

        if not data:
            st.error("抓不到盤中資料，請確認 API Key、股票代號，或目前是否有行情")
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

            st.subheader("盤中結果")
            st.write(f"股票：{stock_i}")
            st.write(f"操作方向：{plan['action']}")
            st.write(f"現價：{fmt_num(data.get('lastPrice', 0))}")
            st.write(f"開盤：{fmt_num(data.get('openPrice', 0))}")
            st.write(f"高點：{fmt_num(data.get('highPrice', 0))}")
            st.write(f"低點：{fmt_num(data.get('lowPrice', 0))}")
            st.write(f"漲跌幅：{fmt_num(data.get('changePercent', 0))}%")
            st.write(f"停損：{fmt_num(plan['stop_loss'])}")
            st.write(f"第一目標：{fmt_num(plan['tp1'])}")
            st.write(f"第二目標：{fmt_num(plan['tp2'])}")

            speech = build_intraday_speech(
                stock_id=stock_i,
                stock_name=stock_name_i,
                market=market_i,
                cost=cost_i,
                direction=direction_i,
                auto_fundamental=default_fundamental,
                quote=data,
                pressure=pressure_i,
                support=support_i,
                plan=plan
            )

            st.subheader("操作建議")
            st.text_area("可直接複製使用", value=speech, height=420)
