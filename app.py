#!/usr/bin/env python3
"""
app.py — TOP3 ＋ ETF ＋ 反転シグナル（4銘柄）
LINE 通知は 1 本に統合
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import json
import datetime
import feedparser
import requests
import yfinance as yf
import jpholiday
import pandas as pd


# ============================
# 手動実行判定
# ============================
def is_manual_run():
    return os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


# ============================
# 土日・祝日スキップ判定
# ============================
def should_skip_today():
    if is_manual_run():
        print("手動実行 → スキップ無効化")
        return False

    today = datetime.date.today()

    if today.weekday() >= 5:
        return True

    if jpholiday.is_holiday(today):
        return True

    return False


# ============================
# 監視銘柄
# ============================
WATCHLIST = {
    "三菱重工": "7011",
    "ビジネスエンジ": "4828",
    "三井住友FG": "8316",
    "三菱UFJ": "8306",
    "千葉銀行": "8331",
    "信越化学": "4063",
    "村田製作所": "6981",
    "INPEX": "1605",
    "三井海洋": "6269",
    "日揮": "1963",
    "オリックス": "8591",
    "ヒューリック": "3003",
    "伊藤忠": "8001",
    "三菱商事": "8058",
    "NTT": "9432",
    "KDDI": "9433",
    "住友電工": "5802",
    "イオン": "8267",
    "三菱ガス化学": "4182",

    # ETF
    "純金信託": "1540",
    "ロボットETF": "2638",
    "iシェアーズオートメーション&ロボットETF": "2522",

    "三菱HCキャピタル": "8593",
    "クオリプス": "4894",
    "トリケミカル": "4369",
}

ETF_LIST = ["1540", "2638", "2522"]
LOOKBACK = 60


# ============================
# セクター分類
# ============================
SECTOR_MAP = {
    "三菱重工": "機械",
    "ビジネスエンジ": "情報通信",
    "三井住友FG": "銀行",
    "三菱UFJ": "銀行",
    "千葉銀行": "銀行",
    "信越化学": "化学",
    "村田製作所": "電気機器",
    "INPEX": "鉱業",
    "三井海洋": "機械",
    "日揮": "建設",
    "オリックス": "その他金融",
    "ヒューリック": "不動産",
    "伊藤忠": "卸売",
    "三菱商事": "卸売",
    "NTT": "情報通信",
    "KDDI": "情報通信",
    "住友電工": "非鉄金属",
    "イオン": "小売",
    "三菱ガス化学": "化学",
    "三菱HCキャピタル": "その他金融",
    "クオリプス": "医薬品",
    "トリケミカル": "化学",

    "純金信託": "ETF",
    "ロボットETF": "ETF",
    "iシェアーズオートメーション&ロボットETF": "ETF",
}


# ============================
# Google RSS ニュース
# ============================
def fetch_google_news_headlines(name):
    url = f"https://news.google.com/rss/search?q={name}"
    feed = feedparser.parse(url)

    today = datetime.date.today()
    headlines = []

    for entry in feed.entries:
        if hasattr(entry, "published_parsed"):
            pub = entry.published_parsed
            pub_date = datetime.date(pub.tm_year, pub.tm_mon, pub.tm_mday)
            if pub_date >= today - datetime.timedelta(days=1):
                headlines.append(entry.title)

    return headlines


# ============================
# 材料性スコア
# ============================
NEWS_KEYWORDS = {
    "上方修正": 3, "増益": 3, "黒字": 3, "受注": 3, "大型": 3,
    "設備投資": 2, "提携": 2, "新工場": 2,
    "EV": 1, "半導体": 1, "AI": 1,
    "下方修正": -3, "減益": -3, "赤字": -3, "不祥事": -3,
    "リコール": -2,
    "利上げ": 3, "利下げ": -3,
    "金利上昇": 3, "金利低下": -2,
    "長期金利": 2, "短期金利": 1,
    "国債利回り": 2,
    "金融引き締め": 3, "金融緩和": -2,
    "政策金利": 2,
    "日銀": 2, "FRB": 2, "ECB": 2, "FOMC": 3,
    "日経平均": 2, "TOPIX": 2, "東証": 1,
    "買い越し": 2, "売り越し": -2,
    "海外勢": 2,
    "需給改善": 2,
    "決算": 2,
    "配当": 1,
    "自社株買い": 3,
    "NYダウ": 2, "S&P500": 2, "ナスダック": 2,
    "米株": 2, "欧州株": 1, "中国株": 1,
    "上海総合": 1, "香港ハンセン": 1,
    "原油高": 3, "原油安": -3,
    "WTI": 2, "ブレント": 2,
    "ドル高": 2, "ドル安": -2,
    "円安": 2, "円高": -2,
}


def score_news_headlines(headlines):
    score = 0
    for h in headlines:
        for kw, val in NEWS_KEYWORDS.items():
            if kw in h:
                score += val
    return score


# ============================
# 出来高トレンド
# ============================
def calc_volume_trend(df):
    if len(df) < 6:
        return 1.0

    today_vol = float(df["Volume"].iloc[-1])
    avg5 = float(df["Volume"].iloc[-6:-1].mean())

    if avg5 == 0:
        return 1.0

    return today_vol / avg5


# ============================
# セクター地合い
# ============================
def calc_sector_trend(sector, temp_results):
    values = [item["gap"] for item in temp_results if SECTOR_MAP.get(item["name"]) == sector]
    return sum(values) / len(values) if values else 0


# ============================
# 価格データ取得
# ============================
def fetch_price(ticker: str):
    df = yf.download(
        ticker,
        period=f"{LOOKBACK + 10}d",
        interval="1d",
        auto_adjust=True,
        progress=False,
    )
    if df.empty:
        return None
    return df.tail(LOOKBACK)


# ============================
# OpenAI AI判定
# ============================
def copilot_future_score_batch(items):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_ERROR: OPENAI_API_KEY is not set")
        return []

    prompt = f"""
あなたは金融アナリストです。
以下の複数銘柄について、未来方向性を -5〜+5 で評価してください。

入力データ:
{json.dumps(items, ensure_ascii=False, indent=2)}

必ず次の形式の JSON 配列で返してください：

[
  {{
    "name": "銘柄名",
    "score": 数値,
    "reason": "理由"
  }}
]
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "gpt-4o-mini-2024-07-18",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        data = r.json()

        if "error" in data:
            print("OPENAI_ERROR:", data["error"])
            return []

        text = data["choices"][0]["message"]["content"]
        return json.loads(text)

    except Exception as e:
        print("OPENAI_ERROR:", e)
        return []


# ============================
# LINE Messaging API
# ============================
def send_line(text: str):
    token = os.environ.get("CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("USER_ID")

    if not token or not user_id:
        print("LINE_ERROR: token or user_id missing")
        return

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    chunks = [text[i:i+2000] for i in range(0, len(text), 2000)]
    messages = [{"type": "text", "text": chunk} for chunk in chunks]

    payload = {"to": user_id, "messages": messages}
    requests.post(url, headers=headers, json=payload, timeout=10)

# ============================
# Buy／中立／注意 分類
# ============================
def classify(gap, news_score, ai_score):
    if gap > 3 and ai_score >= 1 and news_score >= -1:
        return "Buy"
    if 0 <= gap <= 3 and -1 <= ai_score <= 1:
        return "中立"
    return "注意"


# ============================
# 反転ロジック
# ============================
def add_basic_indicators(df):
    df = df.copy()

    # ★ これが重要：Close を Series に強制変換
    close = df["Close"].squeeze()

    df["MA25"] = close.rolling(25).mean()
    df["VOL5"] = df["Volume"].rolling(5).mean()

    import ta
    df["RSI"] = ta.momentum.RSIIndicator(close, 14).rsi()

    macd = ta.trend.MACD(close)
    df["MACD"] = macd.macd()
    df["MACD_SIGNAL"] = macd.macd_signal()

    return df

def check_reversal(df, label):
    last = df.iloc[-1]
    prev = df.iloc[-2]
    signals = []

    # 共通ロジック
    if float(prev["Close"]) < float(prev["MA25"]) and float(last["Close"]) > float(last["MA25"]):
        signals.append("25日線上抜け")

    if float(prev["RSI"]) < 40 < float(last["RSI"]):
        signals.append("RSI反転")

    if float(last["Volume"]) > 1.5 * float(last["VOL5"]):
        signals.append("出来高急増")

    if float(prev["MACD"]) < float(prev["MACD_SIGNAL"]) and float(last["MACD"]) > float(last["MACD_SIGNAL"]):
        signals.append("MACDゴールデンクロス")

    # 浜松ホトニクスだけ追加ロジック
    if label == "浜松ホトニクス":
        if 1650 <= float(last["Close"]) <= 1700:
            signals.append("押し目価格帯（1650〜1700）")
        if float(last["RSI"]) < 40:
            signals.append("RSI売られすぎ")
        if float(last["Volume"]) < float(last["VOL5"]) * 0.8:
            signals.append("出来高減少（売り枯れ）")
        if float(last["Low"]) < float(prev["Low"]) and float(last["Close"]) > float(last["Open"]):
            signals.append("下ヒゲ陽線（反転初期）")

    if signals:
        return f"【{label} 反転シグナル】\n- " + "\n- ".join(signals)
    else:
        return f"【{label}】反転シグナルなし"

# ============================
# メイン処理（TOP3＋ETF＋反転を1本化）
# ============================
def main():

    if should_skip_today():
        print("今日はスキップ")
        return

    # ============================
    # TOP3 ロジック
    # ============================
    temp_results = []
    items_for_ai = []

    for name, code in WATCHLIST.items():
        ticker = f"{code}.T"
        df = fetch_price(ticker)
        if df is None:
            continue

        close = df["Close"]
        current = float(close.iloc[-1])
        price_5d_ago = float(close.iloc[-6]) if len(close) >= 6 else current
        gap = (current / price_5d_ago - 1) * 100

        volume_trend = calc_volume_trend(df)
        sector = SECTOR_MAP.get(name, "その他")

        headlines = fetch_google_news_headlines(name)
        news_score = score_news_headlines(headlines)

        items_for_ai.append({
            "name": name,
            "news": headlines,
            "gap_pct": gap,
            "volume_trend": volume_trend,
        })

        temp_results.append({
            "name": name,
            "code": code,
            "current": current,
            "gap": gap,
            "news_score": news_score,
            "headlines": headlines,
            "volume_trend": volume_trend,
            "sector": sector,
        })

    # AI 判定
    ai_results = copilot_future_score_batch(items_for_ai)
    ai_map = {item["name"]: item["score"] for item in ai_results}
    ai_reason_map = {item["name"]: item["reason"] for item in ai_results}

    stock_results = []
    etf_results = []

    for item in temp_results:
        name = item["name"]
        code = item["code"]
        current = item["current"]
        gap = item["gap"]
        news_score = item["news_score"]
        headlines = item["headlines"]
        volume_trend = item["volume_trend"]
        sector = item["sector"]

        ai_score = ai_map.get(name, 0)
        reason = ai_reason_map.get(name, "AI理由なし")

        # ETF
        if code in ETF_LIST:
            etf_score = gap * 0.7 + ai_score * 0.3
            etf_results.append({
                "name": name,
                "code": code,
                "gap": gap,
                "ai": ai_score,
                "score": etf_score,
            })
            continue

        # 個別株
        sector_trend = calc_sector_trend(sector, temp_results)
        category = classify(gap, news_score, ai_score)

        total = (
            gap * 0.4 +
            news_score * 0.2 +
            ai_score * 0.2 +
            volume_trend * 0.1 +
            sector_trend * 0.1
        )

        stock_results.append(
            (name, current, gap, news_score, ai_score, total,
             headlines, category, reason, volume_trend, sector_trend)
        )

    # TOP3
    stock_results.sort(key=lambda x: x[5], reverse=True)
    top3 = stock_results[:3]

    msg = "【本日の注目銘柄 TOP3（個別株）】\n\n"

    for r in top3:
        name, current, gap, news_score, ai_score, total, headlines, category, reason, volume_trend, sector_trend = r
        msg += (
            f"■ {name}（{category}）\n"
            f"現在値：{current:.2f} 円\n"
            f"5営業日前乖離率：{gap:+.2f}%\n"
            f"出来高トレンド：{volume_trend:.2f}\n"
            f"セクター地合い：{sector_trend:+.2f}%\n"
            f"材料：{headlines[0] if headlines else '（本日・昨日ニュースなし）'}\n"
            f"AI判定：{ai_score}（理由：{reason}）\n"
            f"総合スコア：{total:+.2f}\n\n"
        )

    # ETF
    msg += "【本日のETF 注目銘柄】\n\n"
    etf_results.sort(key=lambda x: x["score"], reverse=True)

    for e in etf_results:
        msg += (
            f"■ {e['name']}（{e['code']}）\n"
            f"5営業日前乖離率：{e['gap']:+.2f}%\n"
            f"AI判定：{e['ai']}\n"
            f"ETFスコア：{e['score']:+.2f}\n\n"
        )

    # ============================
    # 反転シグナル（4銘柄）
    # ============================
    msg += "【反転シグナル（4銘柄）】\n\n"

    targets = [
        ("フジクラ", "5803.T"),
        ("村田製作所", "6981.T"),
        ("住友電工", "5802.T"),
        ("浜松ホトニクス", "6965.T"),
    ]

    for label, ticker in targets:
        df = fetch_price(ticker)
        if df is not None:
            df = add_basic_indicators(df)
            msg += check_reversal(df, label) + "\n\n"
        else:
            msg += f"【{label}】データ取得エラー\n\n"

    # 日付
    today = datetime.date.today().strftime("%Y-%m-%d")
    msg = f"📅 {today}\n\n" + msg

    send_line(msg)


if __name__ == "__main__":
    main()
