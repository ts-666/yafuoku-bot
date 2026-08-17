import sys
import os
import re
import requests
from bs4 import BeautifulSoup
from google import genai
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
    except Exception as e:
        print(f"Discord error: {e}", flush=True)

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    url = "https://auctions.yahoo.co.jp/search/search?p=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&va=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&is_postage_paid=0&b=1&n=20&buynow=1"
    
    res = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select(".Product")

    if not items:
        return

    item = items[0]
    title_elem = item.select_one(".Product__titleLink")
    price_elem = item.select_one(".Product__priceValue")
    
    title = title_elem.text.strip() if title_elem else "タイトル不明"
    price = price_elem.text.strip() if price_elem else "価格不明"
    web_url = title_elem["href"] if title_elem else ""

    # 商品ID（オークションID）の抽出とアプリ用URLの生成
    auction_id_match = re.search(r'/auction/([a-zA-Z0-9]+)', web_url)
    if auction_id_match:
        auction_id = auction_id_match.group(1)
        app_url = f"yjauction://auction?id={auction_id}"
    else:
        app_url = web_url

    if GEMINI_API_KEY:
        try:
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"以下の商品の仕入れ判定を行ってください。\n商品名: {title}\n価格: {price}\n簡潔に買いか見送りかを回答してください。\n【重要：審査基準の緩和】確実に利益が出る商品だけでなく、「横流しや簡易清掃で利益が出る可能性がある商品」や「判断に迷う商品」も絶対に除外せず、【要確認】というステータスをつけてすべて通知してください。機会損失を防ぐことを最優先とします。"
            response = client.models.generate_content(
                model="gemini-1.5-flash",
                contents=prompt
            )
            ai_result = response.text
        except Exception as e:
            ai_result = f"AI判定エラー: {e}"
    else:
        ai_result = "APIキー未設定"

    msg = (
        f"【ヤフオク新着検知】\n"
        f"**商品名:** {title}\n"
        f"**価格:** {price}\n\n"
        f"🤖 **AI査定:**\n{ai_result}\n\n"
        f"📱 **アプリで開く:** {app_url}\n"
        f"🌐 **Webで開く:** {web_url}"
    )
    
    send_discord(msg)

if __name__ == "__main__":
    main()
