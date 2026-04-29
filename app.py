#!/usr/bin/env python3
"""
app.py — Google RSS × 材料性スコア × Buy/中立/注意 × TOP3
テンプレニュース完全廃止版
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import math
import json
import datetime
import feedparser

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import jpholiday


# ============================
# 手動実行判定
# ============================
def is_manual_run():
    return os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch"


# ============================
# 祝日スキップ判定
# ============================
def should_skip_today():
    if is_manual_run():
        print("手動実行のため祝日スキップを無効化します")
        return False
    return jpholiday.is_holiday(datetime.date.today())


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
    "純金信託": "1540",
    "ロボットETF": "2638",
    "三菱HCキャピタル": "8593",
    "クオリプス": "4894",
    "トリケミカル": "4369",
    "iシェアーズオートメーション&ロボットETF": "2522",
}

LOOKBACK = 60


# ============================
# Google RSS ニュース取得（今日＋昨日）
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

            # 今日＋昨日のニュースを取得
            if pub_date >= today - datetime.timedelta(days=1):
                headlines.append(entry.title)

    return headlines


# ============================
# 材料性スコア（相場仕様）
# ============================
NEWS_KEYWORDS = {
    # 企業材料
    "上方修正": 3, "増益": 3, "黒字": 3, "受注": 3, "大型": 3,
    "設備投資": 2, "提携": 2, "新工場": 2,
    "EV": 1, "半導体": 1, "AI": 1,

    # ネガティブ
    "下方修正": -3, "減益": -3, "赤字": -3, "不祥事": -3,
    "リコール": -2,

    # 金融動向
    "利上げ": 3, "利下げ": -3,
    "金利上昇": 3, "金利低下": -2,
    "長期金利": 2, "短期金利": 1,
    "国債利回り": 2,
    "金融引き締め": 3, "金融緩和": -2,
    "政策金利": 2,
    "日銀": 2, "FRB": 2, "ECB": 2, "FOMC": 3,

    # 日本市場
    "日経平均": 2, "TOPIX": 2, "東証": 1,
    "買い越し": 2, "売り越し": -2,
    "海外勢": 2,
    "需給改善": 2,
    "決算": 2,
    "配当": 1,
    "自社株買い": 3,

    # 海外市場
    "NYダウ": 2, "S&P500": 2, "ナスダック": 2,
    "米株": 2, "欧州株": 1, "中国株": 1,
    "上海総合": 1, "香港ハンセン": 1,

    # コモディティ・為替
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
# OpenAI まとめ評価（1回）
# ============================
def copilot_future_score_batch(items):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("OPENAI_ERROR: OPENAI_API_KEY is not set", flush=True)
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
  }},
  ...
]

上記以外の文章は一切書かないこと。
"""

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini-2024-07-18",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=60)
        data = r.json()
        print("OPENAI_API_RAW:", data, flush=True)

        if "error" in data:
            print("OPENAI_ERROR_MSG:", data["error"], flush=True)
            return []

        text = data["choices"][0]["message"]["content"]
        print("OPENAI_RAW_RESPONSE:", text, flush=True)

        return json.loads(text)

    except Exception as e:
        print("OPENAI_ERROR:", e, flush=True)
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
    try:
        requests.post(url, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print("LINE_ERROR:", e, flush=True)


# ============================
# Buy／中立／注意 分類（修正版）
# ============================
def classify(gap, news_score, ai_score):

    # Buy：強い銘柄（ニュース弱くてもOK）
    if gap > 3 and ai_score >= 1 and news_score >= -1:
        return "Buy"

    # 中立：普通
    if 0 <= gap <= 3 and -1 <= ai_score <= 1:
        return "中立"

    # 注意：弱い or リスク
    return "注意"


# ============================
# メイン処理
# ============================
def main():

    if should_skip_today():
        print("今日は祝日 → スキップ")
        return

    temp_results = []
    items_for_ai = []

    for name, code in WATCHLIST.items():

        ticker = f"{code}.T"
        df = fetch_price(ticker)
        if df is None:
            continue

        close = df["Close"]
        current = float(close.iloc[-1])

        # 5営業日前の価格
        if len(close) >= 6:
            price_5d_ago = float(close.iloc[-6])
        else:
            price_5d_ago = current

        # 5営業日前乖離率
        gap = (current / price_5d_ago - 1) * 100

        # Google RSS ニュース（今日＋昨日）
        headlines = fetch_google_news_headlines(name)
        news_score = score_news_headlines(headlines)

        items_for_ai.append({
            "name": name,
            "news": headlines,
            "gap_pct": gap,
        })

        temp_results.append({
            "name": name,
            "current": current,
            "gap": gap,
            "news_score": news_score,
            "headlines": headlines,
        })

    # AI判定
    ai_results = copilot_future_score_batch(items_for_ai)
    ai_map = {item["name"]: item["score"] for item in ai_results}
    ai_reason_map = {item["name"]: item["reason"] for item in ai_results}

    results = []
    for item in temp_results:
        name = item["name"]
        current = item["current"]
        gap = item["gap"]
        news_score = item["news_score"]
        headlines = item["headlines"]

        ai_score = ai_map.get(name, 0)
        reason = ai_reason_map.get(name, "AI理由なし")

        category = classify(gap, news_score, ai_score)

        total = gap * 0.5 + news_score * 0.3 + ai_score * 0.2

        results.append(
            (name, current, gap, news_score, ai_score, total, headlines, category, reason)
        )

    # スコア順
    results.sort(key=lambda x: x[5], reverse=True)

    # TOP3
    top3 = results[:3]

    msg = "【本日の注目銘柄 TOP3（Buy／中立／注意）】\n\n"

    for r in top3:
        name, current, gap, news_score, ai_score, total, headlines, category, reason = r

        msg += (
            f"■ {name}（{category}）\n"
            f"現在値：{current:.2f} 円\n"
            f"5営業日前乖離率：{gap:+.2f}%\n"
            f"材料：{headlines[0] if headlines else '（本日・昨日ニュースなし）'}\n"
            f"AI判定：{ai_score}（理由：{reason}）\n"
            f"総合スコア：{total:+.2f}\n\n"
        )

    send_line(msg)


if __name__ == "__main__":
    main()
