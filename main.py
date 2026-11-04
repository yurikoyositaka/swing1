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
            "title": f"📈 ブレイクアウト検出: {row['Ticker']} {row['Name']}",
            "url": f"https://finance.yahoo.co.jp/quote/{row['Ticker']}",  # ← Yahooファイナンスへのリンクを追加
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
