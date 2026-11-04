import yfinance as yf
import pandas as pd
import requests
import json
import os
import datetime
import jpholiday
import sys
from bs4 import BeautifulSoup

def get_topix500_tickers():
    print("JPXのページから最新の銘柄一覧ファイルを探しています...")
    base_url = "https://www.jpx.co.jp"
    page_url = base_url + "/markets/statistics-equities/misc/01.html"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    fallback_tickers = {
        '7203.T': 'トヨタ自動車', '8306.T': '三菱UFJ FG', '6861.T': 'キーエンス',
        '8035.T': '東京エレクトロン', '9984.T': 'ソフトバンクG', '9983.T': 'ファーストリテイリング',
        '8316.T': '三井住友FG', '8766.T': '東京海上HD', '9432.T': '日本電信電話',
        '8058.T': '三菱商事', '7974.T': '任天堂', '4063.T': '信越化学工業',
        '6758.T': 'ソニーG', '8001.T': '伊藤忠商事', '8031.T': '三井物産',
        '6098.T': 'リクルートHD', '6981.T': '村田製作所', '4568.T': '第一三共',
        '6501.T': '日立製作所', '9433.T': 'KDDI', '8411.T': 'みずほFG',
        '7267.T': '本田技研工業', '7741.T': 'HOYA', '6902.T': 'デンソー',
        '8002.T': '丸紅', '9503.T': '関西電力', '8803.T': '平和不動産',
        '8593.T': '三菱HCキャピタル', '8591.T': 'オリックス', '9022.T': 'JR東海'
    }

    try:
        res = requests.get(page_url, headers=headers)
        soup = BeautifulSoup(res.text, 'html.parser')
        
        link = soup.find('a', href=lambda x: x and ('data_j' in x or x.endswith('.xls') or x.endswith('.xlsx')))
        
        if not link:
            print("警告: JPXのページから銘柄一覧ファイルが見つかりませんでした。代替30銘柄を使用します。")
            return fallback_tickers
            
        excel_url = base_url + link['href']
        print(f"最新のファイルURLを取得しました: {excel_url}")
        
        excel_res = requests.get(excel_url, headers=headers)
        df = pd.read_excel(excel_res.content)
        target_sizes = ['TOPIX Core30', 'TOPIX Large70', 'TOPIX Mid400']
        df_filtered = df[df['規模区分'].isin(target_sizes)]
        
        tickers = {}
        for _, row in df_filtered.iterrows():
            code = f"{row['コード']}.T"
            name = row['銘柄名']
            tickers[code] = name
            
        print(f"監視対象として {len(tickers)} 銘柄を抽出しました。")
        return tickers
    except Exception as e:
        print(f"警告: Excelファイルの解析に失敗しました ({e})。代替30銘柄を使用します。")
        return fallback_tickers

def screen_swing_candidates(tickers_dict):
    matched_tickers = []
    for ticker, name in tickers_dict.items():
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            market_cap = info.get('marketCap', 0)
            
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
                    'Name': name,
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
    headers = {"Content-Type": "application/json"}
    
    if df.empty:
        payload = {
            "content": "📊 **本日のスイングトレード・スクリーニング結果**\n> 監視対象の中で、本日条件を満たした銘柄はありませんでした。"
        }
        res = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
        if res.status_code in [200, 204]:
            print("✅ Discordへ「該当なし」の通知を正常送信しました。")
        else:
            print(f"❌ Discord送信エラー: {res.status_code} - {res.text}")
        return

    embeds = []
    for index, row in df.iterrows():
        embed = {
            "title": f"📈 ブレイクアウト検出: {row['Ticker']} {row['Name']}",
            "url": f"https://finance.yahoo.co.jp/quote/{row['Ticker']}",
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
    
    res = requests.post(webhook_url, data=json.dumps(payload), headers=headers)
    if res.status_code in [200, 204]:
        print("✅ Discordへシグナル通知を正常送信しました。")
    else:
        print(f"❌ Discord送信エラー: {res.status_code} - {res.text}")

if __name__ == "__main__":
    today = datetime.date.today()
    
    is_weekend = today.weekday() >= 5
    is_holiday = jpholiday.is_holiday(today)
    is_new_year = (today.month == 12 and today.day == 31) or (today.month == 1 and today.day in [1, 2, 3])
    
    if is_weekend or is_holiday or is_new_year:
        print(f"{today} は東証の休場日のため処理をスキップします。")
        sys.exit(0)

    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        sys.exit(1)

    target_tickers = get_topix500_tickers()
    
    print("スクリーニングを開始します...")
    result_df = screen_swing_candidates(target_tickers)
    send_discord_alert(result_df, WEBHOOK_URL)
