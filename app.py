#!/usr/bin/env python3
"""
app.py — 未来志向の株価予測
祝日対応＋業界別ニュース＋金利ワード対応＋OpenAIまとめ評価（1回）
"""

import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import os
import math
import json
import datetime

import numpy as np
import pandas as pd
import requests
import yfinance as yf
import jpholiday

# ============================
# 祝日判定
# ============================
def is_japanese_holiday():
    today = datetime.date.today()
    return jpholiday.is_holiday(today)

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
    "nikkei": "NIKKEI225",
    "topix": "TOPIXETF",
}

LOOKBACK = 60

# ============================
# 業界マップ
# ============================
SECTOR_MAP = {
    "三菱重工": "heavy",
    "INPEX": "heavy",
    "三井海洋": "heavy",
    "日揮": "heavy",
    "三菱ガス化学": "heavy",
    "住友電工": "heavy",

    "村田製作所": "semi",
    "信越化学": "semi",
    "トリケミカル": "semi",
    "クオリプス": "semi",
    "ロボットETF": "semi",
    "iシェアーズオートメーション&ロボットETF": "semi",

    "三井住友FG": "finance",
    "三菱UFJ": "finance",
    "千葉銀行": "finance",
    "三菱HCキャピタル": "finance",
    "オリックス": "finance",

    "伊藤忠": "trading",
    "三菱商事": "trading",

    "NTT": "telecom",
    "KDDI": "telecom",

    "イオン": "retail",

    "純金信託": "etf",
    "nikkei": "etf",
    "topix": "etf",
}

# ============================
# 業界別ニュース生成
# ============================
def generate_news(name: str) -> str:
    sector = SECTOR_MAP.get(name, "other")

    if sector == "heavy":
        return f"{name} が大型プロジェクトの受注拡大やエネルギー関連投資を強化しているとの報道があった。"
    if sector == "semi":
        return f"{name} が半導体需要の増加に対応するため生産能力を拡大し、次世代デバイス向け投資を強化していると報じられた。"
    if sector == "finance":
        return f"{name} が金利動向を踏まえた融資戦略や資産運用部門の強化を進めているとの報道があった。"
    if sector == "trading":
        return f"{name} が資源・非資源分野での投資を拡大し、グローバル事業の収益力向上を目指す動きが報じられた。"
    if sector == "telecom":
        return f"{name} が次世代通信インフラへの投資を強化し、法人向けサービスの拡大を進めていると報じられた。"
    if sector == "retail":
        return f"{name} がデジタル戦略や物流効率化を進め、収益改善に向けた取り組みを強化していると報じられた。"
    if sector == "etf":
        return "市場全体で投資家のリスク選好が変化し、関連指数に影響を与える動きが報じられた。"

    return f"{name} に関する前向きな事業展開が報じられた。"

# ============================
# FUTURE_WORDS（金利ワード追加版）
# ============================
FUTURE_WORDS = {
    # 成長・設備・需要
    "増産": 2, "受注": 2, "設備投資": 3, "新工場": 3,
    "AI": 2, "半導体": 2, "需要拡大": 3, "黒字転換": 3,
    "上方修正": 3, "戦略提携": 2, "大型契約": 3,

    # 金利・金融政策
    "金利上昇": 3,
    "金利低下": -2,
    "利上げ": 3,
    "利下げ": -2,
    "金融緩和": -1,
    "金融引き締め": 2,
    "長短金利差拡大": 3,
    "長短金利差縮小": -2,
    "国債利回り上昇": 2,
    "国債利回り低下": -1,
    "日銀": 1,
    "政策金利": 2,
}

def news_future_score(text: str) -> int:
    score = 0
    for w, s in FUTURE_WORDS.items():
        if w in text:
            score += s
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
# 価格予測（3モデル）
# ============================
def predict_price(close: pd.Series):
    try:
        y = close.values.astype(float)
        N = len(y)
        t = np.arange(1, N + 1)

        a1, b1 = np.polyfit(t, y, 1)
        pred_linear = a1 * (N + 1) + b1

        y_log = np.log(y)
        a2, b2 = np.polyfit(t, y_log, 1)
        pred_log = math.exp(a2 * (N + 1) + b2)

        a3, b3 = np.polyfit(t, np.log(y), 1)
        pred_exp = math.exp(a3 * (N + 1) + b3)

        preds = [pred_linear, pred_log, pred_exp]
        preds = [float(p) for p in preds if p > 0 and not math.isnan(p)]

        if len(preds) == 0:
            return None

        return sum(preds) / len(preds)

    except Exception:
        return None

# ============================
# ボラティリティ補正
# ============================
def volatility_adjust(df: pd.DataFrame, predicted: float, current: float):
    try:
        if predicted is None:
            return None
        df["HL"] = df["High"] - df["Low"]
        atr = df["HL"].mean()
        vol_factor = 1 + (atr / current) * 0.5
        return predicted / vol_factor
    except Exception:
        return None

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
# メイン処理
# ============================
def main():

    # 祝日スキップ
    if is_japanese_holiday():
        print("今日は祝日 → スキップ")
        return

    temp_results = []
    items_for_ai = []

    ETF_MAP = {
        "NIKKEI225": "1321.T",
        "TOPIXETF": "1306.T",
    }

    for name, code in WATCHLIST.items():

        if code in ETF_MAP:
            ticker = ETF_MAP[code]
        elif code.isdigit():
            ticker = f"{code}.T"
        else:
            ticker = code

        df = fetch_price(ticker)
        if df is None:
            continue

        close = df["Close"]
        current = float(close.iloc[-1])

        pred = predict_price(close)
        if pred is None:
            continue

        if isinstance(pred, pd.Series):
            pred = pred.iloc[0]
        pred = float(pred)

        pred_adj = volatility_adjust(df, pred, current)
        if pred_adj is None:
            continue

        if isinstance(pred_adj, pd.Series):
            pred_adj = pred_adj.iloc[0]
        pred_adj = float(pred_adj)

        trend_info = f"現在 {current:.2f} → 予測 {pred_adj:.2f}"
        news_text = generate_news(name)
        news_score = news_future_score(news_text)

        items_for_ai.append({
            "name": name,
            "news": news_text,
            "trend": trend_info,
        })

        temp_results.append({
            "name": name,
            "current": current,
            "pred_adj": pred_adj,
            "news_score": news_score,
        })

    # OpenAI を 1回だけ呼ぶ
    ai_results = copilot_future_score_batch(items_for_ai)
    ai_map = {}
    for item in ai_results:
        try:
            ai_map[item["name"]] = int(item["score"])
        except Exception:
            continue

    results = []
    for item in temp_results:
        name = item["name"]
        current = item["current"]
        pred_adj = item["pred_adj"]
        news_score = item["news_score"]

        ai_score = ai_map.get(name, 0)

        total = (
            ((pred_adj / current - 1) * 100) * 0.4
            + news_score * 0.3
            + ai_score * 0.3
        )

        results.append((name, current, pred_adj, news_score, ai_score, total))

    results.sort(key=lambda x: x[5], reverse=True)

    print("DEBUG_RESULTS_COUNT:", len(results))

    if len(results) == 0:
        send_line("【未来志向スコアランキング】\nデータ取得に失敗しました。")
        return

    msg = "【未来志向スコアランキング（前場終値ベース）】\n"
    for r in results:
        msg += (
            f"{r[0]}：総合 {r[5]:+.2f}\n"
            f"  現在 {r[1]:.2f} → 予測 {r[2]:.2f}\n"
            f"  ニュース {r[3]} / AI {r[4]}\n\n"
        )

    send_line(msg)


if __name__ == "__main__":
    main()
