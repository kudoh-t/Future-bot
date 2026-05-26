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

    # === 生データ ===
    price = float(last["Close"])
    price_prev = float(prev["Close"])
    price_diff = price - price_prev
    price_pct = (price / price_prev - 1) * 100 if price_prev > 0 else 0

    vol_today = float(last["Volume"])
    vol_avg5 = float(last["VOL5"]) if float(last["VOL5"]) > 0 else 1
    vol_ratio = vol_today / vol_avg5

    rsi_prev = float(prev["RSI"])
    rsi_last = float(last["RSI"])
    rsi_diff = rsi_last - rsi_prev

    macd_prev = float(prev["MACD"])
    macd_last = float(last["MACD"])
    macd_diff = macd_last - macd_prev

    timestamp = last.name.strftime("%Y-%m-%d %H:%M")

    signals = []

    # === シグナル判定 ===
    if price > float(last["MA25"]) and price_prev < float(prev["MA25"]):
        signals.append("25日線上抜け")

    if rsi_prev < 40 < rsi_last:
        signals.append(f"RSI反転（{rsi_prev:.1f} → {rsi_last:.1f}）")

    if vol_ratio > 1.5:
        signals.append(f"出来高急増（{vol_ratio:.2f}倍）")

    if macd_prev < macd_last:
        signals.append("MACD上昇")

    if macd_prev < float(prev["MACD_SIGNAL"]) and macd_last > float(last["MACD_SIGNAL"]):
        signals.append("MACDゴールデンクロス")

    # === 浜松ホトニクスだけ追加 ===
    if label == "浜松ホトニクス":
        if 1650 <= price <= 1700:
            signals.append("押し目価格帯（1650〜1700）")
        if rsi_last < 40:
            signals.append(f"RSI売られすぎ（{rsi_last:.1f}）")
        if vol_ratio < 0.8:
            signals.append(f"出来高減少（{vol_ratio:.2f}倍）")
        if float(last["Low"]) < float(prev["Low"]) and price > float(last["Open"]):
            signals.append("下ヒゲ陽線（反転初期）")

    # === 反転強度（生データベース） ===
    strength = vol_ratio + (rsi_diff / 10) + (macd_diff / 100)

    # === 出力メッセージ ===
    msg = f"【{label} 反転シグナル】\n"
    msg += f"- 時刻：{timestamp}\n"
    msg += f"- 株価：{price:.0f} 円（前日比 {price_pct:+.2f}% / {price_diff:+.0f} 円）\n"
    msg += f"- 出来高：{vol_ratio:.2f} 倍（今日 {vol_today:,.0f} / 平均 {vol_avg5:,.0f}）\n"
    msg += f"- RSI：{rsi_prev:.1f} → {rsi_last:.1f}\n"
    msg += f"- MACD：{macd_prev:.2f} → {macd_last:.2f}\n"

    if signals:
        msg += "- 材料：\n"
        for s in signals:
            msg += f"   • {s}\n"
    else:
        msg += "- 材料：なし\n"

    return msg, strength



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
    # 反転シグナル（順位付け）
    # ============================
    reversal_list = []

    # 監視対象（反転＋過熱）
    targets = [
        ("アドバンテスト", "6857.T"),
        ("ファナック", "6954.T"),
        ("安川電機", "6506.T"),
        ("トヨタ", "7203.T"),
        ("フジクラ", "5803.T"),
        ("住友電工", "5802.T"),
        ("村田製作所", "6981.T"),
        ("浜松ホトニクス", "6965.T"),
        ("IHI", "7013.T"),
        ("TDK", "6762.T"),
    ]

    # --- 反転強度ラベル ---
    def classify_reversal_strength(strength):
        if strength > 2.0:
            return "強"
        elif strength > 1.0:
            return "中"
        else:
            return "弱"

    # --- 過熱シグナル ---
    def check_overheat(df, label):
        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = float(last["Close"])
        price_prev = float(prev["Close"])
        gap = (price / price_prev - 1) * 100 if price_prev > 0 else 0

        rsi = float(last["RSI"])
        vol_today = float(last["Volume"])
        vol_avg5 = float(last["VOL5"]) if float(last["VOL5"]) > 0 else 1
        vol_ratio = vol_today / vol_avg5

        macd_prev = float(prev["MACD"])
        macd_last = float(last["MACD"])
        macd_diff = macd_last - macd_prev

        timestamp = last.name.strftime("%Y-%m-%d %H:%M")

        level = 0
        reasons = []

        # RSI
        if rsi > 80:
            level = max(level, 3)
            reasons.append(f"RSI過熱（{rsi:.1f}）")
        elif rsi > 75:
            level = max(level, 2)
            reasons.append(f"RSI高水準（{rsi:.1f}）")
        elif rsi > 70:
            level = max(level, 1)
            reasons.append(f"RSI上昇（{rsi:.1f}）")

        # 乖離
        if gap > 20:
            level = max(level, 3)
            reasons.append(f"5日乖離 +{gap:.1f}%（異常値）")
        elif gap > 10:
            level = max(level, 2)
            reasons.append(f"5日乖離 +{gap:.1f}%")
        elif gap > 5:
            level = max(level, 1)
            reasons.append(f"5日乖離 +{gap:.1f}%")

        # 出来高減少で上昇
        if vol_ratio < 0.8 and price > price_prev:
            level = max(level, 3)
            reasons.append(f"出来高減少（{vol_ratio:.2f}倍）で上昇")

        if level == 0:
            return None

        msg = f"■ {label}（過熱 Lv{level}）\n"
        msg += f"- 取得時刻：{timestamp}\n"
        msg += f"- 株価：{price:.0f} 円（前日比 {gap:+.2f}%）\n"
        msg += f"- 出来高：{vol_today:,.0f}（5日平均 {vol_avg5:,.0f} / 比率 {vol_ratio:.2f}）\n"
        msg += f"- RSI：{rsi:.1f}\n"
        msg += f"- MACD前日比：{macd_diff:+.2f}\n"
        msg += "- 危険理由：\n"
        for r in reasons:
            msg += f"   • {r}\n"

        return msg, level

    # --- 反転シグナル（RSI前日比・MACD前日比・出来高絶対値入り） ---
    def check_reversal(df, label):
        last = df.iloc[-1]
        prev = df.iloc[-2]

        price = float(last["Close"])
        price_prev = float(prev["Close"])
        price_diff = price - price_prev
        price_pct = (price / price_prev - 1) * 100 if price_prev > 0 else 0

        vol_today = float(last["Volume"])
        vol_avg5 = float(last["VOL5"]) if float(last["VOL5"]) > 0 else 1
        vol_ratio = vol_today / vol_avg5

        rsi_prev = float(prev["RSI"])
        rsi_last = float(last["RSI"])
        rsi_diff = rsi_last - rsi_prev

        macd_prev = float(prev["MACD"])
        macd_last = float(last["MACD"])
        macd_diff = macd_last - macd_prev

        timestamp = last.name.strftime("%Y-%m-%d %H:%M")

        signals = []

        if price > float(last["MA25"]) and price_prev < float(prev["MA25"]):
            signals.append("25日線上抜け")

        if rsi_prev < 40 < rsi_last:
            signals.append(f"RSI反転（{rsi_prev:.1f} → {rsi_last:.1f}）")

        if vol_ratio > 1.5:
            signals.append(f"出来高急増（{vol_ratio:.2f}倍）")

        if macd_prev < macd_last:
            signals.append("MACD上昇")

        if macd_prev < float(prev["MACD_SIGNAL"]) and macd_last > float(last["MACD_SIGNAL"]):
            signals.append("MACDゴールデンクロス")

        if label == "浜松ホトニクス":
            if 1650 <= price <= 1700:
                signals.append("押し目価格帯（1650〜1700）")
            if rsi_last < 40:
                signals.append(f"RSI売られすぎ（{rsi_last:.1f}）")
            if vol_ratio < 0.8:
                signals.append(f"出来高減少（{vol_ratio:.2f}倍）")
            if float(last["Low"]) < float(prev["Low"]) and price > float(last["Open"]):
                signals.append("下ヒゲ陽線（反転初期）")

        strength = vol_ratio + (rsi_diff / 10) + (macd_diff / 100)

        msg = f"【{label} 反転シグナル】\n"
        msg += f"- 取得時刻：{timestamp}\n"
        msg += f"- 株価：{price:.0f} 円（前日比 {price_pct:+.2f}% / {price_diff:+.0f} 円）\n"
        msg += f"- 出来高：{vol_today:,.0f}（5日平均 {vol_avg5:,.0f} / 比率 {vol_ratio:.2f}）\n"
        msg += f"- RSI：{rsi_prev:.1f} → {rsi_last:.1f}（前日比 {rsi_diff:+.2f}）\n"
        msg += f"- MACD：{macd_prev:.2f} → {macd_last:.2f}（前日比 {macd_diff:+.2f}）\n"

        if signals:
            msg += "- 材料：\n"
            for s in signals:
                msg += f"   • {s}\n"
        else:
            msg += "- 材料：なし\n"

        return msg, strength

    # --- 反転処理 ---
    for label, ticker in targets:
        df = fetch_price(ticker)
        if df is not None:
            df = add_basic_indicators(df)
            msg_rev, strength = check_reversal(df, label)

            strength_label = classify_reversal_strength(strength)
            msg_rev = msg_rev.replace("反転シグナル】", f"反転シグナル（{strength_label}）】")

            reversal_list.append((label, msg_rev, strength))
        else:
            reversal_list.append((label, f"【{label}】データ取得エラー", -999))

    reversal_list.sort(key=lambda x: x[2], reverse=True)

    msg += "【反転シグナル（強い順）】\n\n"
    for _, m, _ in reversal_list:
        msg += m + "\n\n"

    top_label, _, _ = reversal_list[0]
    msg += f"【本日の結論】\n→ 最も反転の強さが見られたのは **{top_label}** です。\n\n"

    # ============================
    # 過熱シグナル
    # ============================
    msg += "【過熱シグナル（天井圏・警戒）】\n\n"

    overheat_list = []
    for label, ticker in targets:
        df = fetch_price(ticker)
        if df is not None:
            df = add_basic_indicators(df)
            result = check_overheat(df, label)
            if result:
                msg_oh, level = result
                overheat_list.append((label, msg_oh, level))

    overheat_list.sort(key=lambda x: x[2], reverse=True)

    if overheat_list:
        for _, m, _ in overheat_list:
            msg += m + "\n"
    else:
        msg += "（過熱シグナルなし）\n"

    send_line(msg)


if __name__ == "__main__":
    main()
    

