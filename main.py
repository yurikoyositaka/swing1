import yfinance as yf
import pandas as pd
import requests
import json
import os
import datetime

def screen_swing_candidates(tickers):
    matched_tickers = []
    for ticker in tickers:
        try:
            df = yf.download(ticker, period="1y", progress=False)
            if len(df) < 200:
                continue
            
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
            df['Vol_SMA_50'] = df['Volume'].rolling(window=50).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 200日線より上、8日線を下から上抜け、出来高1.5倍以上
            cond_long_trend = latest['Close'] > latest['SMA_200']
            cond_ema_break = (prev['Close'] <= prev['EMA_8']) and (latest['Close'] > latest['EMA_8'])
            cond_volume_surge = latest['Volume'] > latest['Vol_SMA_50'] * 1.5
            
            if cond_long_trend and cond_ema_break and cond_volume_surge:
                matched_tickers.append({
                    'Ticker': ticker,
                    'Close': round(latest['Close'], 1),
                    'EMA_8': round(latest['EMA_8'], 1),
                    'SMA_200': round(latest['SMA_200'], 1),
                    'Volume_Ratio': round(latest['Volume'] / latest['Vol_SMA_50'], 2)
                })
        except Exception:
            continue
    return pd.DataFrame(matched_tickers)

def send_discord_alert(df, webhook_url):
    if df.empty:
        print("本日は条件に合致する銘柄はありませんでした。")
        return

    embeds = []
    for index, row in df.iterrows():
        embed = {
            "title": f"📈 ブレイクアウト検出: {row['Ticker']}",
            "color": 3066993,
            "fields": [
                {"name": "終値", "value": f"¥{row['Close']}", "inline": True},
                {"name": "8日EMA", "value": f"¥{row['EMA_8']}", "inline": True},
                {"name": "200日SMA", "value": f"¥{row['SMA_200']}", "inline": True},
                {"name": "出来高急増率", "value": f"{row['Volume_Ratio']}倍", "inline": False}
            ]
        }
        embeds.append(embed)

    payload = {
        "content": "📊 **スイングトレード条件合致シグナル**",
        "embeds": embeds
    }
    
    headers = {"Content-Type": "application/json"}
    requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    print("Discordへシグナルを送信しました。")

if __name__ == "__main__":
    # 土日の場合は処理をスキップ
    today = datetime.date.today()
    if today.weekday() >= 5:
        print("本日は土日のため、処理をスキップします。")
        exit()

    # GitHub SecretsからWebhook URLを取得
    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        exit()

    # 監視対象銘柄（末尾に .T を付ける）
    target_tickers = ['9503.T', '8766.T', '8316.T', '8803.T', '8593.T'] 
    
    print("スクリーニングを開始します...")
    result_df = screen_swing_candidates(target_tickers)
    send_discord_alert(result_df, WEBHOOK_URL)
