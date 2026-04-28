#!/usr/bin/env python3
"""
app.py — 未来志向の株価予測（強化版）
- 価格予測：対数回帰・指数回帰・線形回帰の3モデル
- ボラティリティ補正：ATRベース
- ニュース未来志向ワード抽出：スコア化
- Copilot（AI）に未来方向性を評価させる
- 総合スコアをLINE Messaging APIで通知
"""

import os
import math
import numpy as np
import pandas as pd
import requests
import yfinance as yf
from datetime import datetime, timedelta

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
    "パワーエックス": "485A",
    "iシェアーズオートメーション&ロボットETF": "2522",
    "nikkei": "1321.T",
    "topix": "1306.T"

}

LOOKBACK = 60


# ============================
# 価格データ取得
# ============================
def fetch_price(ticker):
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
# 価格予測（3モデル）
# ============================
def predict_price(close):
    y = close.values.astype(float)
    N = len(y)
    t = np.arange(1, N + 1)

    # 線形回帰
    a1, b1 = np.polyfit(t, y, 1)
    pred_linear = float(a1) * (N + 1) + float(b1)

    # 対数回帰
    y_log = np.log(y)
    a2, b2 = np.polyfit(t, y_log, 1)
    pred_log = math.exp(float(a2) * (N + 1) + float(b2))

    # 指数回帰
    a3, b3 = np.polyfit(t, np.log(y), 1)
    pred_exp = math.exp(float(a3) * (N + 1) + float(b3))

    preds = [pred_linear, pred_log, pred_exp]
    preds = [p for p in preds if p > 0 and not math.isnan(p)]

    if len(preds) == 0:
        return None

    return sum(preds) / len(preds)


# ============================
# ボラティリティ補正（ATR-lite）
# ============================
def volatility_adjust(df, predicted, current):
    df["HL"] = df["High"] - df["Low"]
    atr = df["HL"].mean()
    vol_factor = 1 + (atr / current) * 0.5
    return predicted / vol_factor


# ============================
# ニュース未来志向ワード抽出
# ============================
FUTURE_WORDS = {
    "増産": 2,
    "受注": 2,
    "設備投資": 3,
    "新工場": 3,
    "AI": 2,
    "半導体": 2,
    "需要拡大": 3,
    "黒字転換": 3,
    "上方修正": 3,
    "戦略提携": 2,
    "大型契約": 3,
}

def news_future_score(text):
    score = 0
    for w, s in FUTURE_WORDS.items():
        if w in text:
            score += s
    return score


# ============================
# Copilot に未来方向性を評価させる
# ============================
def copilot_future_score(name, news_text, trend_info):
    """
    Copilot に「未来方向性」を評価させる
    """
    prompt = f"""
あなたは金融アナリストです。
以下の銘柄について、未来方向性を -5〜+5 で評価してください。

【銘柄】{name}
【ニュース】{news_text}
【価格トレンド】{trend_info}

出力形式：
score: 数値
reason: 簡潔な理由
"""

    # Copilot API（あなたの predict_ai.py と同じ構造でOK）
    url = "https://api.githubcopilot.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {os.environ.get('COPILOT_API_KEY')}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        data = r.json()
        text = data["choices"][0]["message"]["content"]

        # score: X を抽出
        import re
        m = re.search(r"score:\s*([-+]?\d+)", text)
        score = int(m.group(1)) if m else 0
        return score
    except:
        return 0


# ============================
# LINE Messaging API
# ============================
def send_line(text):
    token = os.environ.get("CHANNEL_ACCESS_TOKEN")
    user_id = os.environ.get("USER_ID")

    url = "https://api.line.me/v2/bot/message/push"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {"to": user_id, "messages": [{"type": "text", "text": text}]}

    requests.post(url, headers=headers, json=payload)


# ============================
# メイン処理
# ============================
def main():
    results = []

    for name, code in WATCHLIST.items():
        ticker = f"{code}.T" if code.isdigit() else code

        df = fetch_price(ticker)
        if df is None:
            continue

        close = df["Close"]
        current = close.iloc[-1]

        # 価格予測
        pred = predict_price(close)
        if pred is None:
            continue  # ← これが超重要

        pred_adj = volatility_adjust(df, pred, current)
        trend_info = f"現在 {current:.2f} → 予測 {pred_adj:.2f}"

        # ニュース（ダミー）
        news_text = f"{name} が設備投資を拡大し、新工場を建設する計画が報じられた。"
        news_score = news_future_score(news_text)

        # Copilot未来方向性
        ai_score = copilot_future_score(name, news_text, trend_info)

        # 総合スコア
        total = (
            ((pred_adj / current - 1) * 100) * 0.4
            + news_score * 0.3
            + ai_score * 0.3
        )

        results.append((name, current, pred_adj, news_score, ai_score, total))

    # スコア順に並べる
    results.sort(key=lambda x: x[5], reverse=True)

    # LINEメッセージ
    msg = "【未来志向スコアランキング】\n"
    for r in results:
        msg += (
            f"{r[0]}：総合 {r[5]:+.2f}\n"
            f"  現在 {r[1]:.2f} → 予測 {r[2]:.2f}\n"
            f"  ニュース {r[3]} / AI {r[4]}\n\n"
        )

    send_line(msg)


if __name__ == "__main__":
    main()
