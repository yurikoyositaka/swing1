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
    
    # 1. サーバーのブロックを回避するため、ブラウザからのアクセスを装う
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    
    res = requests.get(page_url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    
    # 拡張子が .xls または .xlsx のファイル、あるいは data_j を含むリンクを探す
    link = soup.find('a', href=lambda x: x and ('data_j' in x or x.endswith('.xls') or x.endswith('.xlsx')))
    
    if not link:
        print("警告: JPXのページから銘柄一覧ファイルが見つかりませんでした。")
        print("安全装置作動: JPXからの取得を諦め、代表的な大型株30銘柄の監視リストへ自動で切り替えます。")
        # 2. 取得失敗時はエラーで止めず、代表30銘柄をフォールバックとして返す
        return [
            '7203.T', '8306.T', '6861.T', '8035.T', '9984.T',
            '9983.T', '8316.T', '8766.T', '9432.T', '8058.T',
            '7974.T', '4063.T', '6758.T', '8001.T', '8031.T',
            '6098.T', '6981.T', '4568.T', '6501.T', '9433.T',
            '8411.T', '7267.T', '7741.T', '6902.T', '8002.T',
            '9503.T', '8803.T', '8593.T', '8591.T', '9022.T'
        ]
        
    excel_url = base_url + link['href']
    print(f"最新のファイルURLを取得しました: {excel_url}")
    
    # ダウンロード時にもブラウザを装う
    excel_res = requests.get(excel_url, headers=headers)
    
    try:
        # ダウンロードしたデータをPandasで読み込む
        df = pd.read_excel(excel_res.content)
        target_sizes = ['TOPIX Core30', 'TOPIX Large70', 'TOPIX Mid400']
        df_filtered = df[df['規模区分'].isin(target_sizes)]
        
        tickers = [f"{code}.T" for code in df_filtered['コード']]
        print(f"監視対象として {len(tickers)} 銘柄を抽出しました。")
        return tickers
    except Exception as e:
        print(f"警告: Excelファイルの解析に失敗しました ({e})")
        print("安全装置作動: 代表的な大型株30銘柄の監視リストへ自動で切り替えます。")
        return ['7203.T', '8306.T', '6861.T', '8035.T', '9984.T', '9983.T', '8316.T', '8766.T', '9432.T', '8058.T']

def screen_swing_candidates(tickers):
    matched_tickers = []
    for ticker in tickers:
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
            "content": "📊 **本日のスイングトレード・スクリーニング結果**\n> 監視対象（TOPIX 500または代替リスト）の中で、本日条件を満たした銘柄はありませんでした。"
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
        "content": "📊 **スイングトレード条件合致シグナル**",
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
        sys.exit(0)

    WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
    if not WEBHOOK_URL:
        print("エラー: DISCORD_WEBHOOK_URL が設定されていません。")
        sys.exit(1)

    target_tickers = get_topix500_tickers()
    
    print("スクリーニングを開始します... (約500銘柄の処理には数分かかります)")
    result_df = screen_swing_candidates(target_tickers)
    send_discord_alert(result_df, WEBHOOK_URL)
