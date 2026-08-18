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

# 確定した全20ジャンルの監視ターゲット
SEARCH_TARGETS = [
    # 釣り・アウトドア・マリン
    {"genre": "トップ/オールドリール", "kw": "(五十鈴 OR BC420 OR トイマシーン OR 道楽 OR ブライトリバー OR ABU 2500C OR ABU 1500C OR ABU 5000) (ジャンク OR 現状 OR リール)"},
    {"genre": "キャンプバーナー/ランタン", "kw": "(スノーピーク OR SOTO OR コールマン 200A OR ギガパワー) (スス OR 点火 OR 汚れ OR ジャンク OR 現状)"},
    {"genre": "ダイブコンピューター", "kw": "(ダイブコンピューター OR ダイビング OR SUUNTO D4i OR TUSA) (電池切れ OR 液晶 OR 現状 OR ジャンク)"},
    # 楽器・音響
    {"genre": "エレキギター/ベース本体", "kw": "(パシフィカ OR Pacifica OR Squier OR Epiphone OR ZO-3 OR Fender) (ジャンク OR ガリ OR 現状品 OR 音出ず)"},
    {"genre": "ギターケース/ギグバッグ", "kw": "(ギター ハードケース OR ギグバッグ OR MONO OR SKB) (汚れ OR 現状 OR ジャンク OR 保管品)"},
    {"genre": "ギター用ピックアップ", "kw": "(ピックアップ OR Duncan OR DiMarzio OR EMG) (ジャンク OR 導通 OR 現状 OR セット)"},
    {"genre": "エフェクター", "kw": "(エフェクター OR BOSS OR OD-1 OR DS-1 OR BD-2 OR ZOOM) (ガリ OR 通電 OR ジャンク OR 現状)"},
    {"genre": "高級ヘッドホン/イヤホン", "kw": "(WH-1000X OR QuietComfort OR Beats OR ヘッドホン) (パッド OR 劣化 OR ジャンク OR 現状)"},
    {"genre": "ポータブルアンプ/DAC", "kw": "(ポタアン OR FiiO BTR OR iFi hip-dac OR USB-DAC) (傷 OR 動作未確認 OR バッテリー OR 本体のみ)"},
    {"genre": "レトロ音響", "kw": "(ウォークマン OR カセットプレーヤー OR MDプレーヤー OR WM-) (ベルト OR 通電 OR ジャンク OR 現状)"},
    # ホビー・文具・刃物・カメラ
    {"genre": "カメラ用交換レンズ", "kw": "(単焦点 OR ズームレンズ OR オールドレンズ OR EF 50mm OR Nikkor) (クモリ OR カビ OR ジャンク OR 現状品)"},
    {"genre": "コンパクトフィルムカメラ", "kw": "(オリンパス μ OR XA OR コニカ Big mini OR オートハーフ) (未確認 OR 電池 OR カメラまとめ OR 現状)"},
    {"genre": "ゴルフ用レーザー距離計", "kw": "(COOLSHOT OR ブッシュネル OR ピンシーカー) (電池切れ OR ケース OR 使用感 OR 現状)"},
    {"genre": "高級筆記具/万年筆", "kw": "(モンブラン OR マイスターシュテュック OR ペリカン OR 万年筆) (インク OR ペン先 OR まとめ OR 現状)"},
    {"genre": "鉄道模型/ミニカー", "kw": "(Nゲージ OR KATO OR TOMIX OR オートアート 1/18) (ケース汚れ OR ホコリ OR 走行未確認 OR まとめ)"},
    {"genre": "高級包丁/和包丁", "kw": "(堺孝行 OR 正本 OR 有次 OR GLOBAL OR 本焼) (サビ OR 刃こぼれ OR 銘 OR 包丁まとめ)"},
    # 家電・ゲーム・工具
    {"genre": "ゲーム機/周辺機器", "kw": "(Switch OR PS4 OR PS5 OR Proコン OR Joy-Con OR 3DS) (ドリフト OR スティック OR ジャンク OR 動作未確認)"},
    {"genre": "掃除機/ルンバ", "kw": "(ダイソン OR ルンバ OR Dyson V8 OR Dyson V10) (バッテリー OR フィルター OR エラー OR ジャンク)"},
    {"genre": "高級理美容家電", "kw": "(ReFa OR ドライヤー OR KINUJO OR ナノケア) (ホコリ OR コード OR ジャンク OR 現状)"},
    {"genre": "プロ用電動工具", "kw": "(マキタ TD OR HiKOKI WH OR インパクトドライバー) (粉塵 OR 汚れ OR 軸 OR ジャンク)"},
]


def load_seen_ids():
    if os.path.exists(SEEN_IDS_FILE):
        with open(SEEN_IDS_FILE, "r", encoding="utf-8") as f:
            return set(line.strip() for line in f if line.strip())
    return set()


def save_seen_id(auction_id):
    with open(SEEN_IDS_FILE, "a", encoding="utf-8") as f:
        f.write(f"{auction_id}\n")


def send_discord(message):
    if not DISCORD_WEBHOOK_URL:
        print("[ERROR] DISCORD_WEBHOOK_URL が未設定です。", flush=True)
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


def get_gemini_assessment(genre, title, current_price, buynow_price, postage_text):
    if not GEMINI_API_KEY:
        return "判定: 【未設定】\nメルカリ相場: 不明\n見込み利益: 不明\nメルカリ用タイトル: 不明"

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0.2,
        }

        system_instruction = (
            "あなたはヤフオク仕入れ・メルカリ再販（5〜15分の軽清掃・簡単整備・横流し）のプロ鑑定AIです。\n\n"
            "【厳格な判定ルール】\n"
            "1. トップ/オールドリール: ユーザーが目視判断するため、基本【要確認】または【買い】として相場算出。\n"
            "2. キャンプバーナー/ランタン: タンク穴あき・燃料漏れは【見送り】。スス・油汚れ・未点火は【買い】。\n"
            "3. ダイブコンピューター: 内部水没・浸水跡は【見送り】。単なる電池切れ・塩噛みは【買い】。\n"
            "4. ギター本体: ネック折れ、トラスロッド限界、ネック波打ち/ねじれ、フレット極端摩耗は【見送り】。\n"
            "5. ギターケース: ファスナー破損・レール外れは【見送り】。外装汚れ・シール跡は【買い】。\n"
            "6. ピックアップ: リード線根元ちぎれ・断線は【見送り】。配線残り・クスミは【買い】。\n"
            "7. エフェクター: 基板焼け・水没は【見送り】。ノブのガリ・外装汚れは【買い】。\n"
            "8. 高級ヘッドホン: ドライバー断線（片耳無音）、ヒンジ真っ二つ折れは【見送り】。パッド劣化は【買い】。\n"
            "9. ポタアン/DAC: ジャック内部折れ、Type-C接触不良は【見送り】。小キズ・未更新は【買い】。\n"
            "10. レトロ音響: 基板青サビ浸食、液晶割れは【見送り】。ベルト劣化不動は【買い】。\n"
            "11. カメラレンズ: バルサム切れ（白濁）、絞り油固着は【見送り】。軽微チリ・外装スレは【買い】。\n"
            "12. フィルムカメラ: レンズ重度カビ、モーター完全故障は【見送り】。電池切れ未確認は【買い】。\n"
            "13. レーザー距離計: 内部液晶欠け、光学系カビは【見送り】。電池切れ・レンズ汚れは【買い】。\n"
            "14. 高級筆記具: ニブ（ペン先）開き/段差/折れ、軸割れは【見送り】。インク固着・クスミは【買い】。\n"
            "15. 鉄道模型: パンタグラフ折れ、モーター焼き付きは【見送り】。車輪/集電板汚れは【買い】。\n"
            "16. 高級包丁: 刃の真っ二つ折れ、柄の完全腐食抜けは【見送り】。表面サビ・軽微刃こぼれは【買い】。\n"
            "17. ゲーム機/周辺機器: BAN機、水没、充電口破損は【見送り】。スティックドリフト・汚れは【買い】。\n"
            "18. 掃除機/ルンバ: モーター焼き付き、水吸いは【見送り】。フィルター詰まり・バッテリー消耗は【買い】。\n"
            "19. 高級理美容家電: コード断線、火花/異臭は【見送り】。吸気口ホコリ・皮脂汚れは【買い】。\n"
            "20. 電動工具: アンビル（軸）折れ/ブレ、端子溶損は【見送り】。粉塵/油汚れ・トリガー接触不良は【買い】。\n\n"
            "【出力フォーマット】（前置き・挨拶・解説は一切出力せず、この形式のみ出力）\n"
            "判定: 【買い】/【見送り】/【要確認】\n"
            "メルカリ想定相場: ○○円〜○○円\n"
            "見込み利益: 約○○円（メルカリ手数料10%・送料差引後）\n"
            "仕入れ上限目安: ○○円まで\n"
            "メルカリ用タイトル: （管理番号や不要な記号を削った出品用タイトル40文字以内）\n"
            "推奨作業: （アルコール清掃/接点復活スプレー/部品交換/そのまま横流し 等）\n"
            "理由: （40〜50文字程度の簡潔な1文）"
        )

        user_content = (
            f"ジャンル: {genre}\n"
            f"商品名: {title}\n"
            f"現在価格: {current_price}\n"
            f"即決価格: {buynow_price}\n"
            f"送料: {postage_text}\n"
            "メルカリ相場・見込み利益・推奨作業・メルカリ最適化タイトルの生成をお願いします。"
        )

        candidate_models = ["gemini-3.6-flash", "gemini-2.5-flash"]
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
            except Exception:
                continue

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

        return "判定: 【要確認】\nAI査定の取得に失敗しました。"

    except Exception as e:
        return f"AI設定エラー: {e}"


def check_target(target, seen_ids):
    genre = target["genre"]
    kw = target["kw"]
    encoded_kw = urllib.parse.quote(kw)

    url = f"https://auctions.yahoo.co.jp/search/search?p={encoded_kw}&va={encoded_kw}&is_postage_paid=0&b=1&n=10&buynow=1&s1=new&o1=d"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        )
    }

    try:
        res = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(res.text, "html.parser")
        items = soup.select(".Product")

        print(f"[INFO] ジャンル【{genre}】取得件数: {len(items)}件", flush=True)

        for item in items[:3]:
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

            if "判定: 【見送り】" in ai_result or "【見送り】" in ai_result.split("\n")[0]:
                print(f"[SKIP] 【見送り】のため通知スキップ: {title}", flush=True)
                continue

            msg = (
                f"【ヤフオク新着検知 - {genre}】\n"
                f"**商品名:** {title}\n"
                f"**現在価格:** {current_price} | **即決:** {buynow_price}\n"
                f"**送料:** {postage_text} | **残り時間:** {remain_time}\n\n"
                f"🤖 **AI査定 & 再販プラン:**\n{ai_result}\n\n"
                f"📱 [**タップしてヤフオクを開く**]({app_launch_url})"
            )

            send_discord(msg)
            print(f"[NOTIFIED] 通知送信完了: {title}", flush=True)

    except Exception as e:
        print(f"[ERROR] ジャンル【{genre}】取得エラー: {e}", flush=True)


def main():
    print("[INFO] 全20ジャンルの自動巡回を開始します...", flush=True)
    seen_ids = load_seen_ids()
    for target in SEARCH_TARGETS:
        check_target(target, seen_ids)
    print("[INFO] 全ジャンルの巡回が完了しました。", flush=True)


if __name__ == "__main__":
    main()
