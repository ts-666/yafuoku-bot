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


def get_gemini_assessment(title, current_price, buynow_price, postage_text):
    if not GEMINI_API_KEY:
        print("[WARN] GEMINI_API_KEY が未設定です。", flush=True)
        return "判定: 【未設定】\nメルカリ相場: 不明\n見込み利益: 不明\nメルカリ用タイトル: 不明"

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0.2,
        }

        system_instruction = (
            "あなたはヤフオク仕入れ・メルカリ再販のプロ鑑定AIです。\n"
            "以下のフォーマットに厳格に従い、日本語のみを出力してください。\n"
            "前置き、解説、思考プロセス、挨拶は一切出力しないでください。\n\n"
            "【出力フォーマット】\n"
            "判定: 【買い】/【見送り】/【要確認】\n"
            "メルカリ想定相場: ○○円〜○○円\n"
            "見込み利益: 約○○円（メルカリ手数料10%・送料差引後）\n"
            "仕入れ上限目安: ○○円まで\n"
            "メルカリ用タイトル: （管理番号や無駄な装飾文字を削った出品用タイトル40文字以内）\n"
            "理由: （40〜50文字程度の簡潔な1文）"
        )

        user_content = (
            f"商品名: {title}\n"
            f"現在価格: {current_price}\n"
            f"即決価格: {buynow_price}\n"
            f"送料: {postage_text}\n"
            "メルカリ相場・見込み利益・メルカリ最適化タイトルの生成をお願いします。"
        )

        # 優先モデル一覧（順にフォールバック試行）
        candidate_models = ["gemini-3.6-flash", "gemini-2.5-flash"]
        response = None
        last_error = None

        for m_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=system_instruction,
                    generation_config=generation_config,
                )
                response = model.generate_content(user_content)
                if response and response.text:
                    return response.text.strip()
            except Exception as e:
                last_error = e
                continue

        # すべて失敗した場合は利用可能なモデルを動的取得
        available_models = [
            m.name for m in genai.list_models()
            if "generateContent" in m.supported_generation_methods
        ]
        if available_models:
            fallback_model_name = available_models[0].replace("models/", "")
            model = genai.GenerativeModel(
                model_name=fallback_model_name,
                system_instruction=system_instruction,
                generation_config=generation_config,
            )
            response = model.generate_content(user_content)
            if response and response.text:
                return response.text.strip()

        return f"AI設定エラー: {last_error}"

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
    title = title_elem.text.strip() if title_elem else "タイトル不明"

    price_elem = item.select_one(".Product__priceValue")
    current_price = price_elem.text.strip() if price_elem else "価格不明"

    buynow_elem = item.select_one(".Product__price--buynow .Product__priceValue")
    buynow_price = buynow_elem.text.strip() if buynow_elem else "なし"

    postage_elem = item.select_one(".Product__postage")
    postage_text = postage_elem.text.strip() if postage_elem else "送料要確認"

    time_elem = item.select_one(".Product__time")
    remain_time = time_elem.text.strip() if time_elem else "不明"

    raw_url = title_elem["href"] if title_elem else ""
    auction_id_match = re.search(r"/auction/([a-zA-Z0-9]+)", raw_url)
    auction_id = auction_id_match.group(1) if auction_id_match else ""

    app_launch_url = (
        f"https://ts-666.github.io/yafuoku-bot/open.html?id={auction_id}"
    )

    print(f"[INFO] 対象商品: {title}", flush=True)

    ai_result = get_gemini_assessment(
        title, current_price, buynow_price, postage_text
    )

    msg = (
        f"【ヤフオク新着検知】\n"
        f"**商品名:** {title}\n"
        f"**現在価格:** {current_price} | **即決:** {buynow_price}\n"
        f"**送料:** {postage_text} | **残り時間:** {remain_time}\n\n"
        f"🤖 **AI査定 & メルカリ分析:**\n{ai_result}\n\n"
        f"📱 [**タップしてヤフオクを開く**]({app_launch_url})"
    )

    send_discord(msg)
    print("[INFO] 処理完了", flush=True)


if __name__ == "__main__":
    main()
