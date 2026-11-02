import yfinance as yf
import pandas as pd
import requests
import json
import os
import datetime
import jpholiday

def get_topix500_tickers():
    # JPX公式の銘柄一覧ExcelファイルのURL
    url = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
    print("日本取引所グループ(JPX)から最新の銘柄一覧を取得中...")
    df = pd.read_excel(url)
    
    # 時価総額・流動性が高い日本を代表する約500社（TOPIX 500）に絞り込む
    target_sizes = ['TOPIX Core30', 'TOPIX Large70', 'TOPIX Mid400']
    df_filtered = df[df['規模区分'].isin(target_sizes)]
    
    # yfinanceで読み込めるように銘柄コードの末尾に .T を付与
    tickers = [f"{code}.T" for code in df_filtered['コード']]
    print(f"監視対象として {len(tickers)} 銘柄を抽出しました。")
    return tickers

def screen_swing_candidates(tickers):
    matched_tickers = []
    # 500銘柄の処理には数分かかります
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
            # 安全のため、ここでも時価総額1,000億円未満を弾く
            if market_cap < 100000000000:
                continue

            df = stock.history(period="1y")
            if len(df) < 200:
                continue
                
            df['SMA_200'] = df['Close'].rolling(window=200).mean()
            df['EMA_8'] = df['Close'].ewm(span=8, adjust=False).mean()
            df['Vol_SMA_50'] = df['Volume'].rolling(window=50).mean()
            
            latest = df.iloc[-1]
            prev = df.iloc[-2]
            
            cond_long_trend = latest['Close'] > latest['SMA_200']
            cond_ema_break = (prev['Close'] <= prev['EMA_8']) and (latest['Close'] > latest['EMA_8'])
            cond_volume_surge = latest['Volume'] > latest['Vol_SMA_50'] * 1.5
            
            if cond_long_trend and cond_ema_break and cond_volume_surge:
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
    if df.empty:
        payload = {
            "content": "📊 **本日のスイングトレード・スクリーニング結果**\n> TOPIX 500の中で、本日条件を満たした銘柄はありませんでした。"
        }
        headers = {"Content-Type": "application/json"}
        requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        print("Discordへ「該当なし」の通知を送信しました。")
        return

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
        "content": "📊 **スイングトレード条件合致シグナル (TOPIX 500対象)**",
        "embeds": embeds
    }
    
    headers = {"Content-Type": "application/json"}
    requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    print("Discordへ合致銘柄のシグナルを送信しました。")

if __name__ == "__main__":
    today = datetime.date.today()
    
    is_weekend = today.weekday() >= 5
    is_holiday = jpholiday.is_holiday(today)
    is_new_year = (today.month == 12 and today.day == 31) or (today.month == 1 and today.day in [1, 2, 3])
    
    if is_weekend or is_holiday or is_new_year:
        print(f"{today} は東証の休場日（土日・祝日・年末年始）のため、処理をスキップします。")
        exit()

    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        exit()

    # ▼ 手動入力の銘柄リストを削除し、関数で自動取得するように変更 ▼
    target_tickers = get_topix500_tickers()
    
    print("スクリーニングを開始します... (約500銘柄の処理には数分かかります)")
    result_df = screen_swing_candidates(target_tickers)
    send_discord_alert(result_df, WEBHOOK_URL)
