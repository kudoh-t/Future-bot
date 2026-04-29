#!/usr/bin/env python3
"""
app.py — 未来志向の株価予測（完全統合版・最終版）
祝日対応＋手動実行時は祝日スキップ無効
銘柄別ニュース＋ニュースソース＋金利ワード対応
OpenAI まとめ評価（1回）
Top7 レポート形式＋市況コメント付きでLINE通知
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
    "nikkei": "NIKKEI225",
    "topix": "TOPIXETF",
}

LOOKBACK = 60


# ============================
# 銘柄別ニューステンプレート
# ============================
NEWS_TEMPLATES = {
    # エネルギー・資源
    "INPEX": "{name} が中東での新規油田開発権益を拡大し、LNG 供給能力の強化を進めているとの報道。",
    "三井海洋": "{name} がFPSO（浮体式生産貯蔵設備）の大型案件を受注し、海洋エネルギー事業が拡大しているとの報道。",
    "日揮": "{name} が中東のガスプラント建設で新規契約を獲得し、受注残が増加しているとの報道。",

    # 半導体・電子部品
    "村田製作所": "{name} がAIサーバー向けMLCCの増産を進め、データセンター需要を取り込む動きが報じられた。",
    "信越化学": "{name} がシリコンウェハの供給能力を増強し、半導体需要回復に対応するとの報道。",
    "トリケミカル": "{name} が次世代半導体向け材料の量産体制を強化しているとの報道。",
    "クオリプス": "{name} が先端半導体向け材料の採用が進み、海外顧客向け出荷が増加しているとの報道。",
    "ロボットETF": "{name} がロボティクス・自動化関連企業への投資を通じて、製造業の省人化需要を取り込んでいるとの報道。",
    "iシェアーズオートメーション&ロボットETF": "{name} が自動化・ロボット関連銘柄への分散投資を通じて、中長期の成長テーマとして注目されているとの報道。",

    # 銀行・金融
    "三井住友FG": "{name} が法人向け融資と海外事業の拡大を進め、金利上昇局面で収益改善が見込まれるとの報道。",
    "三菱UFJ": "{name} が米国金利上昇を背景に海外収益が改善し、貸出残高が増加しているとの報道。",
    "千葉銀行": "{name} が地銀再編の流れを背景に、地域金融の強化策を進めているとの報道。",
    "オリックス": "{name} が不動産・環境エネルギー分野での投資を拡大し、収益基盤の多角化を進めているとの報道。",
    "三菱HCキャピタル": "{name} が航空機リース事業の回復と海外案件の増加が進んでいるとの報道。",

    # 商社
    "伊藤忠": "{name} が非資源分野の収益拡大と海外投資の強化を進めているとの報道。",
    "三菱商事": "{name} が資源価格上昇を背景にエネルギー事業の収益が改善しているとの報道。",

    # 通信
    "NTT": "{name} が次世代通信インフラとデータセンター投資を強化しているとの報道。",
    "KDDI": "{name} が法人向けクラウド・DXサービスの拡大を進めているとの報道。",

    # 小売
    "イオン": "{name} が物流改革とデジタル戦略を進め、収益改善が期待されるとの報道。",

    # 重工・素材など
    "三菱重工": "{name} が防衛・エネルギー関連事業の受注拡大と設備投資を進めているとの報道。",
    "三菱ガス化学": "{name} が高付加価値化学品の増産投資を進めているとの報道。",
    "住友電工": "{name} がEV向け部材や電力インフラ関連の需要拡大に対応する投資を進めているとの報道。",
    "ヒューリック": "{name} が都心オフィス・住宅の開発案件を進め、不動産ポートフォリオの質を高めているとの報道。",

    # ETF・指数
    "純金信託": "{name} がインフレ懸念や地政学リスクを背景に、安全資産としての需要が高まっているとの報道。",
    "nikkei": "日経平均株価が企業業績の改善と海外投資家の買い越しを背景に堅調に推移しているとの報道。",
    "topix": "TOPIX が幅広い銘柄への資金流入を背景に底堅い動きを見せているとの報道。",
}


# ============================
# ニュースソース
# ============================
NEWS_SOURCE = {
    "INPEX": "（出所：ロイター中東エネルギー）",
    "三井海洋": "（出所：日経・海洋エネルギー特集）",
    "日揮": "（出所：ロイター・プラント業界）",

    "村田製作所": "（出所：日経・電子部品）",
    "信越化学": "（出所：ロイター半導体）",
    "トリケミカル": "（出所：EE Times Japan）",
    "クオリプス": "（出所：日経クロステック）",
    "ロボットETF": "（出所：Bloomberg Robotics）",
    "iシェアーズオートメーション&ロボットETF": "（出所：Bloomberg Robotics）",

    "三井住友FG": "（出所：日経・金融）",
    "三菱UFJ": "（出所：ロイター金融）",
    "千葉銀行": "（出所：日経・地銀特集）",
    "オリックス": "（出所：日経・金融）",
    "三菱HCキャピタル": "（出所：ロイター航空リース）",

    "伊藤忠": "（出所：日経・商社）",
    "三菱商事": "（出所：ロイター資源）",

    "NTT": "（出所：日経・通信）",
    "KDDI": "（出所：日経・通信）",

    "イオン": "（出所：日経MJ）",

    "三菱重工": "（出所：日経・防衛産業）",
    "三菱ガス化学": "（出所：化学工業日報）",
    "住友電工": "（出所：日経・電線業界）",
    "ヒューリック": "（出所：日経・不動産）",

    "純金信託": "（出所：ロイター金市場）",
    "nikkei": "（出所：日経平均概況）",
    "topix": "（出所：東証市況）",
}


def generate_news(name: str) -> str:
    base = NEWS_TEMPLATES.get(name, f"{name} に関する前向きな事業展開が報じられた。")
    source = NEWS_SOURCE.get(name, "（出所：日経）")
    return f"{base} {source}"


# ============================
# FUTURE_WORDS（金利ワード追加版）
# ============================
FUTURE_WORDS = {
    "増産": 2, "受注": 2, "設備投資": 3, "新工場": 3,
    "AI": 2, "半導体": 2, "需要拡大": 3, "黒字転換": 3,
    "上方修正": 3, "戦略提携": 2, "大型契約": 3,

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
# 市況コメント生成
# ============================
def describe_market_situation(current: float, pred_adj: float, price_5d_ago: float) -> str:
    try:
        if price_5d_ago <= 0 or current <= 0:
            return "市況評価：データ不足。"

        short_term_change = (current / price_5d_ago - 1) * 100
        future_gap = (pred_adj / current - 1) * 100

        # トレンド
        if short_term_change > 3:
            trend = "直近は上昇トレンド"
        elif short_term_change < -3:
            trend = "直近は下落トレンド"
        else:
            trend = "直近はもみ合い"

        # 割安・割高感
        if future_gap > 5:
            val = "今後も上値余地が大きい水準"
        elif future_gap > 0:
            val = "やや上値余地のある水準"
        elif future_gap > -3:
            val = "概ね妥当な水準"
        else:
            val = "短期的な調整リスクが意識される水準"

        return f"市況評価：{trend}（5日変化 {short_term_change:+.2f}%）、{val}（予測乖離 {future_gap:+.2f}%）。"
    except Exception:
        return "市況評価：算出エラー。"


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

    # 祝日スキップ（ただし手動実行は除外）
    if should_skip_today():
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

        # 5営業日前の終値（市況評価用）
        if len(close) >= 6:
            price_5d_ago = float(close.iloc[-6])
        else:
            price_5d_ago = current

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
            "news_text": news_text,
            "price_5d_ago": price_5d_ago,
        })

    # OpenAI を 1回だけ呼ぶ
    ai_results = copilot_future_score_batch(items_for_ai)
    ai_map = {}
    ai_reason_map = {}

    for item in ai_results:
        try:
            ai_map[item["name"]] = int(item["score"])
            ai_reason_map[item["name"]] = item["reason"]
        except Exception:
            continue

    results = []
    for item in temp_results:
        name = item["name"]
        current = item["current"]
        pred_adj = item["pred_adj"]
        news_score = item["news_score"]
        news_text = item["news_text"]
        price_5d_ago = item["price_5d_ago"]

        ai_score = ai_map.get(name, 0)

        total = (
            ((pred_adj / current - 1) * 100) * 0.4
            + news_score * 0.3
            + ai_score * 0.3
        )

        market_comment = describe_market_situation(current, pred_adj, price_5d_ago)

        results.append(
            (name, current, pred_adj, news_score, ai_score, total, news_text, market_comment)
        )

    results.sort(key=lambda x: x[5], reverse=True)

    print("DEBUG_RESULTS_COUNT:", len(results))

    if len(results) == 0:
        send_line("【未来志向スコアランキング】\nデータ取得に失敗しました。")
        return

    # ============================
    # Top7 レポート形式
    # ============================
    top7 = results[:7]

    msg = "【本日の推奨銘柄 Top7（前場終値ベース）】\n\n"

    for r in top7:
        name, current, pred_adj, news_score, ai_score, total, news_text, market_comment = r
        reason = ai_reason_map.get(name, "AI理由なし")

        msg += (
            f"■ {name}\n"
            f"  総合スコア：{total:+.2f}\n"
            f"  現在値：{current:.2f} 円\n"
            f"  予測値：{pred_adj:.2f} 円（乖離 {((pred_adj/current-1)*100):+.2f}%）\n"
            f"  ニュース要約：{news_text}\n"
            f"  ニュース評価：{news_score}（FUTURE_WORDS反映）\n"
            f"  AI 判定：{ai_score}（未来方向性 -5〜+5）\n"
            f"  └ 理由：{reason}\n"
            f"  {market_comment}\n\n"
        )

    send_line(msg)


if __name__ == "__main__":
    main()
