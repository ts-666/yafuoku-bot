import os
import re
import sys
import urllib.parse
import requests
from bs4 import BeautifulSoup
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

DISCORD_WEBHOOK_URL = os.environ.get("DISCORD_WEBHOOK_URL")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SEEN_IDS_FILE = "seen_ids.txt"

# 20ジャンル構成（実績ベース）
SEARCH_TARGETS = [
    # 釣り・アウトドア・マリン
    {"genre": "トップ/オールドリール", "kw": "リール (五十鈴 OR BC420 OR BC520 OR トイマシーン OR 道楽 OR ブライトリバー OR 2500C OR 1500C OR 5000)"},
    {"genre": "キャンプバーナー/ランタン", "kw": "(バーナー OR ランタン) (スノーピーク OR ST-310 OR ST-340 OR コールマン OR ギガパワー)"},
    {"genre": "ダイブコンピューター", "kw": "(ダイブコンピューター OR ダイブコンピュータ OR D4i OR TUSA)"},
    
    # 楽器・音響
    {"genre": "エレキギター/ベース本体", "kw": "(ギター OR ベース) (パシフィカ OR Pacifica OR Squier OR Epiphone OR ZO-3 OR Fender) (ジャンク OR ガリ OR 音出ず)"},
    {"genre": "ギターケース/ギグバッグ", "kw": "(ギターケース OR ギグバッグ OR ハードケース) (MONO OR SKB OR ギター)"},
    {"genre": "ギター用ピックアップ", "kw": "ピックアップ (ダンカン OR Duncan OR DiMarzio OR EMG)"},
    {"genre": "エフェクター", "kw": "エフェクター (BOSS OR OD-1 OR DS-1 OR BD-2 OR ZOOM) (ジャンク OR ガリ OR 現状)"},
    {"genre": "高級ヘッドホン/イヤホン", "kw": "(ヘッドホン OR イヤホン) (WH-1000X OR QuietComfort OR Beats)"},
    {"genre": "ポータブルアンプ/DAC", "kw": "(ポタアン OR DAC OR ヘッドホンアンプ) (FiiO OR iFi OR USB-DAC)"},
    {"genre": "レトロ音響", "kw": "(ウォークマン OR カセットプレーヤー OR MDプレーヤー OR WM-) (ジャンク OR 不動 OR 現状)"},
    
    # カメラ・ホビー・文具・包丁
    {"genre": "カメラ用交換レンズ", "kw": "レンズ (単焦点 OR オールドレンズ OR EF OR Nikkor) (カビ OR クモリ OR ジャンク)"},
    {"genre": "コンパクトフィルムカメラ", "kw": "(フィルムカメラ OR コンパクトカメラ) (オリンパス OR コニカ OR オートハーフ OR μ OR XA)"},
    {"genre": "ゴルフ用レーザー距離計", "kw": "(距離計 OR レーザー距離計) (COOLSHOT OR ブッシュネル OR ピンシーカー)"},
    {"genre": "高級筆記具/万年筆", "kw": "(万年筆 OR ボールペン) (モンブラン OR マイスターシュテュック OR ペリカン)"},
    {"genre": "鉄道模型/ミニカー", "kw": "(Nゲージ OR ミニカー) (KATO OR TOMIX OR オートアート)"},
    {"genre": "高級包丁/和包丁", "kw": "(包丁 OR 和包丁 OR 牛刀 OR 柳刃) (堺孝行 OR 正本 OR 有次 OR GLOBAL)"},
    
    # 家電・工具
    {"genre": "ゲーム機/周辺機器", "kw": "(Switch OR PS4 OR PS5 OR Proコン OR Joy-Con) (ジャンク OR 動作未確認 OR ドリフト)"},
    {"genre": "掃除機/ルンバ", "kw": "(掃除機 OR ルンバ) (ダイソン OR Dyson) (バッテリー OR エラー OR ジャンク)"},
    {"genre": "高級理美容家電", "kw": "(ドライヤー OR ヘアアイロン) (ReFa OR KINUJO OR ナノケア)"},
    {"genre": "プロ用電動工具", "kw": "インパクトドライバー (マキタ OR HiKOKI OR TD171 OR TD172 OR TD173) (ジャンク OR 現状)"},
]


def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_id(auction_id):
    with open(SEEN_IDS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{auction_id}\n")


def send_discord_embed(genre, title, current_price, buynow_price, postage_text, remain_time, app_launch_url, ai_result):
    if not DISCORD_WEBHOOK_URL:
        return

    color = 0x2ecc71 if "【買い】" in ai_result else 0xf1c40f

    embed = {
        "title": f"【{genre}】{title[:200]}",
        "url": app_launch_url,
        "color": color,
        "fields": [
            {
                "name": "💰 価格・状態",
                "value": f"**現在:** {current_price} | **即決:** {buynow_price}\n**送料:** {postage_text} | **残り:** {remain_time}",
                "inline": False
            },
            {
                "name": "🤖 AI査定 & 再販プラン",
                "value": ai_result[:1024],
                "inline": False
            }
        ],
        "footer": {
            "text": "📱 タイトルまたはURLをタップしてヤフオクアプリで開く"
        }
    }

    payload = {
        "content": f"📱 [**ヤフオクアプリで開く**]({app_launch_url})",
        "embeds": [embed]
    }

    try:
        res = requests.post(DISCORD_WEBHOOK_URL, json=payload, timeout=10)
        print(f"[INFO] Discord送信ステータス: {res.status_code}", flush=True)
    except Exception as e:
        print(f"[ERROR] Discord error: {e}", flush=True)


def get_gemini_assessment(genre, title, current_price, buynow_price, postage_text):
    if not GEMINI_API_KEY:
        return None

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        system_instruction = (
            "あなたはヤフオク仕入れ・メルカリ再販のプロ鑑定AIです。\n"
            "思考や前置き、英語は一切出力せず、必ず1行目から以下の日本語フォーマットのみを出力してください。\n"
            "指定されたジャンルと全く異なる商品の場合は、1行目を必ず『判定: 【見送り】』にしてください。\n\n"
            "【出力フォーマット】\n"
            "判定: 【買い】/【見送り】/【要確認】\n"
            "メルカリ想定相場: ○○○○円〜○○○○円\n"
            "見込み利益: 約○○○○円（メルカリ手数料10%・送料差引後）\n"
            "仕入れ上限目安: ○○○○円まで\n"
            "メルカリ用タイトル: （管理番号等を削った出品用タイトル40字以内）\n"
            "推奨作業: （アルコール清掃/接点復活スプレー/部品交換/そのまま横流し 等）\n"
            "理由: （40〜50文字程度の簡潔な1文）"
        )

        user_content = (
            f"ジャンル: {genre}\n"
            f"商品名: {title}\n"
            f"現在価格: {current_price}\n"
            f"即決価格: {buynow_price}\n"
            f"送料: {postage_text}"
        )

        candidate_models = ["gemini-1.5-flash", "gemini-1.5-pro", "gemini-2.5-flash"]
        for m_name in candidate_models:
            try:
                model = genai.GenerativeModel(
                    model_name=m_name,
                    system_instruction=system_instruction
                )
                response = model.generate_content(user_content)
                if response and response.text:
                    text = response.text.strip()
                    idx = text.find("判定:")
                    res = text[idx:].strip() if idx != -1 else text
                    if "メルカリ想定相場:" in res:
                        return res
            except Exception:
                continue

        return None

    except Exception as e:
        print(f"[ERROR] AI査定例外: {e}", flush=True)
        return None


def check_target(target, seen_ids):
    genre = target["genre"]
    kw = target["kw"]
    encoded_kw = urllib.parse.quote(kw)

    # 全出品形式を対象に新着順で取得（即決制限なし）
    url = f"https://auctions.yahoo.co.jp/search/search?p={encoded_kw}&is_postage_paid=0&b=1&n=10&s1=new&o1=d"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".Product")

        print(f"[INFO] ジャンル【{genre}】新着取得件数: {len(items)}件", flush=True)

        for item in items[:2]:
            title_elem = item.select_one(".Product__titleLink")
            if not title_elem:
                continue

            title = title_elem.text.strip()
            raw_url = title_elem.get("href", "")
            auction_id_match = re.search(r"/auction/([a-zA-Z0-9]+)", raw_url)
            auction_id = auction_id_match.group(1) if auction_id_match else ""

            if not auction_id or auction_id in seen_ids:
                continue

            seen_ids.add(auction_id)
            save_seen_id(auction_id)

            price_elem = item.select_one(".Product__priceValue")
            current_price = price_elem.text.strip() if price_elem else "価格不明"

            buynow_elem = item.select_one(".Product__price--buynow .Product__priceValue")
            buynow_price = buynow_elem.text.strip() if buynow_elem else "なし"

            postage_elem = item.select_one(".Product__postage")
            postage_text = postage_elem.text.strip() if postage_elem else "送料要確認"

            time_elem = item.select_one(".Product__time")
            remain_time = time_elem.text.strip() if time_elem else "不明"

            app_launch_url = f"https://ts-666.github.io/yafuoku-bot/open.html?id={auction_id}"

            ai_result = get_gemini_assessment(
                genre, title, current_price, buynow_price, postage_text
            )

            if not ai_result or "【見送り】" in ai_result.split("\n")[0]:
                print(f"[SKIP] 見送りまたは査定除外: {title}", flush=True)
                continue

            send_discord_embed(
                genre, title, current_price, buynow_price, postage_text, remain_time, app_launch_url, ai_result
            )
            print(f"[NOTIFIED] 通知送信完了: {title}", flush=True)

    except Exception as e:
        print(f"[ERROR] ジャンル【{genre}】エラー: {e}", flush=True)


def main():
    print("[INFO] 全20ジャンルの巡回を開始します...", flush=True)
    seen_ids = load_seen_ids()
    for target in SEARCH_TARGETS:
        check_target(target, seen_ids)
    print("[INFO] 全ジャンルの巡回が完了しました。", flush=True)


if __name__ == "__main__":
    main()
