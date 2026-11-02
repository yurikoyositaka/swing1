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
            # 1. 銘柄情報の取得と時価総額チェック
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
            # 時価総額1,000億円（100,000,000,000円）未満ならスキップ
            if market_cap < 50000000000:
                continue

            # 2. 日足データの取得とテクニカル計算
            df = stock.history(period="1y")
            if len(df) < 200:
                continue
                
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
            df['Vol_SMA_50'] = df['Volume'].rolling(window=50).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            # 3. ミネルヴィニ的なブレイクアウト条件
            cond_long_trend = latest['Close'] > latest['SMA_200']
            cond_ema_break = (prev['Close'] <= prev['EMA_8']) and (latest['Close'] > latest['EMA_8'])
            cond_volume_surge = latest['Volume'] > latest['Vol_SMA_50'] * 1.5
            
            if cond_long_trend and cond_ema_break and cond_volume_surge:
                # 時価総額を「億円」単位にして見やすくする
                market_cap_oku = int(market_cap / 100000000)
                matched_tickers.append({
                    'Ticker': ticker,
                    'Close': round(latest['Close'], 1),
                    'EMA_8': round(latest['EMA_8'], 1),
                    'SMA_200': round(latest['SMA_200'], 1),
                    'Volume_Ratio': round(latest['Volume'] / latest['Vol_SMA_50'], 2),
                    'MarketCap': market_cap_oku
                })
        except Exception:
            continue
            
    return pd.DataFrame(matched_tickers)

def send_discord_alert(df, webhook_url):
    # ▼変更点：合致銘柄が0件の場合でも「該当なし」の通知を送る
    if df.empty:
        payload = {
            "content": "📊 **本日のスイングトレード・スクリーニング結果**\n> 監視対象の中に、本日条件（200日SMA超え・8日EMA反発・出来高急増）を満たした銘柄はありませんでした。"
        }
        headers = {"Content-Type": "application/json"}
        requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        print("Discordへ「該当なし」の通知を送信しました。")
        return

    # ▼該当銘柄がある場合は詳細データを送る
    embeds = []
    for index, row in df.iterrows():
        embed = {
            "title": f"📈 ブレイクアウト検出: {row['Ticker']}",
            "color": 3066993,
            "fields": [
                {"name": "終値", "value": f"¥{row['Close']}", "inline": True},
                {"name": "時価総額", "value": f"{row['MarketCap']}億円", "inline": True},
                {"name": "出来高急増率", "value": f"{row['Volume_Ratio']}倍", "inline": True},
                {"name": "8日EMA", "value": f"¥{row['EMA_8']}", "inline": True},
                {"name": "200日SMA", "value": f"¥{row['SMA_200']}", "inline": True}
            ]
        }
        embeds.append(embed)

    payload = {
        "content": "📊 **スイングトレード条件合致シグナル**",
        "embeds": embeds
    }
    
    headers = {"Content-Type": "application/json"}
    requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    print("Discordへ合致銘柄のシグナルを送信しました。")

if __name__ == "__main__":
    today = datetime.date.today()
    if today.weekday() >= 5:
        print("本日は土日のため、処理をスキップします。")
        exit()

    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        exit()

    # 監視対象（代表的な大型・中型株を多めにセットしています。自由に入れ替え可能です）
    target_tickers = [
        '7203.T', '8306.T', '6861.T', '8035.T', '9984.T',
        '9983.T', '8316.T', '8766.T', '9432.T', '8058.T',
        '7974.T', '4063.T', '6758.T', '8001.T', '8031.T',
        '6098.T', '6981.T', '4568.T', '6501.T', '9433.T',
        '8411.T', '7267.T', '7741.T', '6902.T', '8002.T',
        '9503.T', '8803.T', '8593.T', '8591.T', '9022.T'
    ] 
    
    print("スクリーニングを開始します...")
    result_df = screen_swing_candidates(target_tickers)
    send_discord_alert(result_df, WEBHOOK_URL)
