import sys
import os
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from google import genai

# 設定読み込み
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

client = genai.Client(api_key=GEMINI_API_KEY)

# ==========================================
# 監視設定
# ==========================================
SEARCH_KEYWORD = "ジャンク ギター"  # 検索したいキーワード
INTERVAL_MINUTES = 5              # 巡回間隔（分）
CANDIDATE_MODELS = ['gemini-flash-latest', 'gemini-2.5-pro-preview-tts']

# 重複通知を防ぐためのID保存用セット
seen_item_ids = set()

def send_discord_notification(message):
    payload = {"content": message}
    response = requests.post(DISCORD_WEBHOOK_URL, json=payload)
    if response.status_code != 204:
        print(f"Discord送信エラー: {response.status_code}")

def fetch_yafuoku_items(keyword):
    """ヤフオクから最新の商品リストを取得"""
    url = f"https://auctions.yahoo.co.jp/search/search?p={requests.utils.quote(keyword)}&s1=new&o1=d"
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    }
    
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        print(f"ヤフオク取得エラー: {response.status_code}")
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    items = []
    
    # 商品要素の解析
    for product in soup.select('li.Product'):
        title_elem = product.select_one('.Product__titleLink')
        price_elem = product.select_one('.Product__priceValue')
        
        if not title_elem or not price_elem:
            continue
            
        title = title_elem.text.strip()
        item_url = title_elem['href']
        # URLから固有の商品ID（例: x12345678）を抽出
        item_id = item_url.split('/')[-1]
        
        # 価格文字列から数値のみ抽出
        price_str = price_elem.text.replace('円', '').replace(',', '').strip()
        try:
            price = int(price_str)
        except ValueError:
            price = 0

        items.append({
            "id": item_id,
            "title": title,
            "price": price,
            "url": item_url,
            "description": "詳細は商品ページを参照", # 簡易検索用
            "seller_rating": 99.5 # デフォルト判定値
        })
        
    return items

def evaluate_item(item):
    prompt = f"""
    あなたはヤフオク仕入れ・メルカリ転売のプロ査定士です。
    以下の商品情報をもとに仕入れ判断を行ってください。

    【商品情報】
    - 商品名: {item['title']}
    - 現在価格: {item['price']}円

    【仕入れ基準】
    1. 見込み利益が5,000円以上（7,000円以上で推奨）。
    2. 転売需要が高く、リペアや清掃で価値が上がる見込みがあること。

    【出力フォーマット】
    判定: [Go / Hold / NO]
    ジャンル: [ジャンル名]
    見込み利益: [数字]円
    仕入れ目安: [数字]円（上限: [数字]円）
    メルカリ想定売価: [数字]円
    リペア難易度: [★で5段階表示]
    AI注意コメント: [注意点やアドバイス]
    """
    
    for model_name in CANDIDATE_MODELS:
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt
            )
            return response.text.strip()
        except Exception:
            continue
    return None

def monitor():
    print(f"--- 巡回開始: 検索キーワード「{SEARCH_KEYWORD}」 ---")
    items = fetch_yafuoku_items(SEARCH_KEYWORD)
    print(f"取得件数: {len(items)}件")

    for item in items[:5]:  # 最新5件をチェック
        if item["id"] in seen_item_ids:
            continue  # 調査済みはスキップ

        seen_item_ids.add(item["id"])
        print(f"新規商品を検知: {item['title']} ({item['price']}円)")

        ai_result = evaluate_item(item)
        if ai_result and "NO" not in ai_result:
            message = f"""
【新着・仕入れ判定通知】
──────────────────
■ 商品名: {item['title']}
■ 現在価格: {item['price']}円

{ai_result}

[ヤフオク商品ページを開く]
{item['url']}
"""
            send_discord_notification(message)
            print(" -> Discordへ通知を送信しました！")
        else:
            print(" -> AI判定で「NO」または見送りのためスキップ。")

if __name__ == "__main__":
    print("ヤフオク自動監視Botを起動しました。（Ctrl+Cで停止）")
    while True:
        try:
            monitor()
            print(f"次回更新まで {INTERVAL_MINUTES} 分待機します...\n")
            time.sleep(INTERVAL_MINUTES * 60)
        except KeyboardInterrupt:
            print("\nBotを停止しました。")
            break
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            time.sleep(60)
