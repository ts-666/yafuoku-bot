import sys
import os
import requests
from bs4 import BeautifulSoup
from google import genai
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

print("--- Start Yafuoku Monitor ---", flush=True)

def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("Discord Webhook URL is missing.", flush=True)
        return
    try:
        requests.post(DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10)
        print("Discord notification sent.", flush=True)
    except Exception as e:
        print(f"Discord send error: {e}", flush=True)

def main():
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    url = "https://auctions.yahoo.co.jp/search/search?p=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&va=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&is_postage_paid=0&b=1&n=20"
    
    print(f"Fetching URL: {url}", flush=True)
    try:
        res = requests.get(url, headers=headers, timeout=15)
        print(f"HTTP Status: {res.status_code}", flush=True)
    except Exception as e:
        print(f"Request failed: {e}", flush=True)
        return

    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select(".Product")
    print(f"Found items: {len(items)}", flush=True)

    if not items:
        print("No items found. Exiting.", flush=True)
        send_discord("【テスト実行】ヤフオク監視BOTは正常稼働中ですが、対象商品が見つかりませんでした。")
        return

    # テストとして1件処理
    item = items[0]
    title_elem = item.select_one(".Product__titleLink")
    price_elem = item.select_one(".Product__priceValue")
    
    title = title_elem.text.strip() if title_elem else "タイトル不明"
    price = price_elem.text.strip() if price_elem else "価格不明"
    
    print(f"Target item: {title} / {price}", flush=True)

    if GEMINI_API_KEY:
        try:
            print("Calling Gemini API...", flush=True)
            client = genai.Client(api_key=GEMINI_API_KEY)
            prompt = f"以下のヤフオク商品の仕入れ査定を行ってください。\n商品名: {title}\n価格: {price}\n簡潔に買いか見送りかを回答してください。"
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            ai_result = response.text
            print("Gemini API call success.", flush=True)
        except Exception as e:
            ai_result = f"AI判定エラー: {e}"
            print(f"Gemini API error: {e}", flush=True)
    else:
        ai_result = "APIキー未設定"

    msg = f"【ヤフオク新着検知】\n商品名: {title}\n価格: {price}\n\n🤖 **AI査定結果**:\n{ai_result}"
    send_discord(msg)
    print("--- Finish Yafuoku Monitor ---", flush=True)

if __name__ == "__main__":
    main()
