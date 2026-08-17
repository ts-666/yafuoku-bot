import os
import re
import sys
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")


def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("[ERROR] DISCORD_WEBHOOK_URL が設定されていません。", flush=True)
        return
    try:
        if len(message) > 1800:
            message = message[:1700] + "\n\n...（長文のため省略）"

        res = requests.post(
            DISCORD_WEBHOOK_URL, json={"content": message}, timeout=10
        )
        print(f"[INFO] Discord送信ステータス: {res.status_code}", flush=True)
        if res.status_code not in (200, 204):
            print(f"[ERROR] Discord詳細エラー: {res.text}", flush=True)
    except Exception as e:
        print(f"[ERROR] Discord error: {e}", flush=True)


def get_gemini_assessment(title, price):
    if not GEMINI_API_KEY:
        print("[WARN] GEMINI_API_KEY が未設定です。", flush=True)
        return "APIキー未設定"

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        # トークン上限を十分に確保
        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0.2,
        }

        system_instruction = (
            "あなたはヤフオクせどりの査定AIです。英語、前置き、思考プロセスは一切出力せず、"
            "必ず以下の日本語フォーマットのみを返してください。\n"
            "判定: 【買い】/【見送り】/【要確認】\n"
            "理由: （50文字程度の短い1文で簡潔に記載）"
        )

        model = genai.GenerativeModel(
            model_name="gemini-3.6-flash",
            system_instruction=system_instruction,
            generation_config=generation_config,
        )

        user_content = f"商品名: {title}\n価格: {price}\n仕入れ判定をお願いします。"
        response = model.generate_content(user_content)

        if response and response.text:
            return response.text.strip()
        return "判定の生成に失敗しました。"

    except Exception as e:
        return f"AI設定エラー: {e}"


def main():
    print("[INFO] ヤフオクスクレイピング開始...", flush=True)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
    }
    url = "https://auctions.yahoo.co.jp/search/search?p=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&va=%E3%82%B8%E3%83%A3%E3%83%B3%E3%82%AF&is_postage_paid=0&b=1&n=20&buynow=1"

    res = requests.get(url, headers=headers, timeout=15)
    soup = BeautifulSoup(res.text, "html.parser")
    items = soup.select(".Product")

    print(f"[INFO] 取得した商品件数: {len(items)}件", flush=True)

    if not items:
        print("[WARN] 商品が0件のため終了します。", flush=True)
        send_discord("【テスト通知】商品が取得できませんでした（0件）。")
        return

    item = items[0]
    title_elem = item.select_one(".Product__titleLink")
    price_elem = item.select_one(".Product__priceValue")

    title = title_elem.text.strip() if title_elem else "タイトル不明"
    price = price_elem.text.strip() if price_elem else "価格不明"
    web_url = title_elem["href"] if title_elem else ""

    auction_id_match = re.search(r"/auction/([a-zA-Z0-9]+)", web_url)
    app_url = (
        f"yjauction://auction?id={auction_id_match.group(1)}"
        if auction_id_match
        else web_url
    )

    print(f"[INFO] 対象商品: {title} / {price}", flush=True)

    ai_result = get_gemini_assessment(title, price)

    msg = (
        f"【ヤフオク新着検知】\n"
        f"**商品名:** {title}\n"
        f"**価格:** {price}\n\n"
        f"🤖 **AI査定:**\n{ai_result}\n\n"
        f"📱 **アプリで開く:** {app_url}\n"
        f"🌐 **Webで開く:** {web_url}"
    )

    send_discord(msg)
    print("[INFO] 処理完了", flush=True)


if __name__ == "__main__":
    main()
