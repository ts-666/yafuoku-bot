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

# 20ジャンル（必須名詞 + 対象ブランド/型番のOR構文で定義）
SEARCH_TARGETS = [
    # 釣り・アウトドア・マリン
    {"genre": "トップ/オールドリール", "kw": "リール (五十鈴 OR BC420 OR BC520 OR トイマシーン OR 道楽 OR ブライトリバー OR \"ABU 2500C\" OR \"ABU 1500C\" OR \"ABU 5000\")"},
    {"genre": "キャンプバーナー/ランタン", "kw": "(バーナー OR ランタン OR コンロ) (スノーピーク OR ST310 OR ST-310 OR ST340 OR ST-340 OR \"コールマン 200A\" OR ギガパワー)"},
    {"genre": "ダイブコンピューター", "kw": "(ダイブコンピューター OR ダイブコンピュータ OR \"SUUNTO D4\" OR \"TUSA IQ\")"},
    
    # 楽器・音響
    {"genre": "エレキギター/ベース本体", "kw": "(ギター OR ベース) (パシフィカ OR Pacifica OR Squier OR Epiphone OR ZO-3 OR Fender) (ジャンク OR ガリ OR 現状 OR 音出ず)"},
    {"genre": "ギターケース/ギグバッグ", "kw": "(ギターケース OR ギグバッグ OR ハードケース) (MONO OR SKB OR ギター) (汚れ OR 現状 OR ジャンク)"},
    {"genre": "ギター用ピックアップ", "kw": "ピックアップ (ダンカン OR Duncan OR DiMarzio OR EMG) ギター"},
    {"genre": "エフェクター", "kw": "エフェクター (BOSS OR OD-1 OR DS-1 OR BD-2 OR ZOOM) (ガリ OR 通電 OR ジャンク OR 現状)"},
    {"genre": "高級ヘッドホン/イヤホン", "kw": "(ヘッドホン OR イヤホン) (WH-1000X OR QuietComfort OR Beats) (パッド OR 劣化 OR ジャンク OR 現状)"},
    {"genre": "ポータブルアンプ/DAC", "kw": "(ポタアン OR DAC OR ヘッドホンアンプ) (FiiO OR iFi OR USB-DAC) (ジャンク OR 動作未確認 OR 本体のみ)"},
    {"genre": "レトロ音響", "kw": "(ウォークマン OR カセットプレーヤー OR MDプレーヤー OR \"WM-\") (ジャンク OR 不動 OR ベルト OR 通電)"},
    
    # カメラ・ホビー・文具・包丁
    {"genre": "カメラ用交換レンズ", "kw": "レンズ (単焦点 OR オールドレンズ OR \"EF 50mm\" OR Nikkor) (カビ OR クモリ OR ジャンク OR 現状)"},
    {"genre": "コンパクトフィルムカメラ", "kw": "(フィルムカメラ OR コンパクトカメラ) (オリンパス OR コニカ OR オートハーフ OR \"μ\" OR \"XA\") (未確認 OR 電池 OR 現状)"},
    {"genre": "ゴルフ用レーザー距離計", "kw": "(距離計 OR レーザー距離計) (COOLSHOT OR ブッシュネル OR ピンシーカー)"},
    {"genre": "高級筆記具/万年筆", "kw": "(万年筆 OR ボールペン) (モンブラン OR マイスターシュテュック OR ペリカン)"},
    {"genre": "鉄道模型/ミニカー", "kw": "(Nゲージ OR ミニカー) (KATO OR TOMIX OR オートアート) (ジャンク OR 現状 OR 走行未確認)"},
    {"genre": "高級包丁/和包丁", "kw": "(包丁 OR 和包丁 OR 牛刀 OR 柳刃) (堺孝行 OR 正本 OR 有次 OR GLOBAL) (サビ OR 刃こぼれ OR 銘)"},
    
    # 家電・工具
    {"genre": "ゲーム機/周辺機器", "kw": "(Switch OR PS4 OR PS5 OR Proコン OR Joy-Con) (本体 OR コントローラー) (ドリフト OR ジャンク OR 動作未確認)"},
    {"genre": "掃除機/ルンバ", "kw": "(掃除機 OR ルンバ) (ダイソン OR Dyson OR iRobot) (バッテリー OR エラー OR ジャンク)"},
    {"genre": "高級理美容家電", "kw": "(ドライヤー OR ヘアアイロン) (ReFa OR KINUJO OR ナノケア) (ジャンク OR 現状 OR ホコリ)"},
    {"genre": "プロ用電動工具", "kw": "インパクトドライバー (マキタ OR HiKOKI OR TD171 OR TD172 OR TD173 OR WH36DC) (ジャンク OR 汚れ OR 現状)"},
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
        print("[ERROR] DISCORD_WEBHOOK_URL が未設定です。", flush=True)
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
        return "判定: 【未設定】\nメルカリ想定相場: 不明\n見込み利益: 不明\nメルカリ用タイトル: 不明"

    try:
        genai.configure(api_key=GEMINI_API_KEY)

        generation_config = {
            "max_output_tokens": 1000,
            "temperature": 0.2,
        }

        system_instruction = (
            "あなたはヤフオク仕入れ・メルカリ再販のプロ鑑定AIです。\n\n"
            "【最優先ルール：ジャンル不一致の完全ブロック】\n"
            "出品商品が指定された【監視対象ジャンル】と異なるカテゴリの製品（例: リール枠にチェーンソーや車部品、カメラ枠に別家電等）である場合、絶対に相場査定を行わず、必ず以下のように1行目を『判定: 【見送り】』として出力してください。\n"
            "判定: 【見送り】\n"
            "メルカリ想定相場: 対象外\n"
            "見込み利益: 0円\n"
            "仕入れ上限目安: 0円\n"
            "メルカリ用タイトル: なし\n"
            "推奨作業: なし\n"
            "理由: 監視対象ジャンル（{genre}）と商品種別が一致しないため。\n\n"
            "【ジャンル別査定基準（一致時のみ適用）】\n"
            "1. リール: 目視判断枠。リール本体であれば基本【要確認】または【買い】。\n"
            "2. バーナー/ランタン: タンク穴・燃料漏れは【見送り】。汚れ・未点火は【買い】。\n"
            "3. ダイブコンピューター: 内部水没は【見送り】。電池切れは【買い】。\n"
            "4. ギター本体: ネック折れ・ロッド限界は【見送り】。ガリ・弦サビは【買い】。\n"
            "5. ギターケース: ファスナー破損は【見送り】。汚れは【買い】。\n"
            "6. ピックアップ: 断線は【見送り】。クスミ・配線残りは【買い】。\n"
            "7. エフェクター: 基板焼け・水没は【見送り】。ガリ・汚れは【買い】。\n"
            "8. ヘッドホン: 断線片耳無音・ヒンジ折れは【見送り】。パッド劣化は【買い】。\n"
            "9. ポタアン: 端子破損は【見送り】。本体のみ・小キズは【買い】。\n"
            "10. レトロ音響: 基板腐食・液晶割れは【見送り】。ベルト劣化は【買い】。\n"
            "11. カメラレンズ: バルサム切れは【見送り】。軽微チリ・外装スレは【買い】。\n"
            "12. フィルムカメラ: レンズ重度カビは【見送り】。電池切れ未確認は【買い】。\n"
            "13. レーザー距離計: 液晶欠け・カビは【見送り】。電池切れは【買い】。\n"
            "14. 筆記具: ニブ折れ・軸割れは【見送り】。インク固着は【買い】。\n"
            "15. 鉄道模型: パンタグラフ折れは【見送り】。車輪汚れは【買い】。\n"
            "16. 包丁: 刃の真っ二つ折れは【見送り】。表面サビ・小刃こぼれは【買い】。\n"
            "17. ゲーム機: BAN機・水没は【見送り】。ドリフト・汚れは【買い】。\n"
            "18. 掃除機: モーター焼き付きは【見送り】。フィルター・バッテリー劣化は【買い】。\n"
            "19. 理美容家電: コード断線火花は【見送り】。吸気口ホコリは【買い】。\n"
            "20. 電動工具: 軸折れは【見送り】。粉塵汚れ・トリガー不良は【買い】。\n\n"
            "【出力フォーマット】\n"
            "判定: 【買い】/【見送り】/【要確認】\n"
            "メルカリ想定相場: ○○円〜○○円\n"
            "見込み利益: 約○○円（メルカリ手数料10%・送料差引後）\n"
            "仕入れ上限目安: ○○円まで\n"
            "メルカリ用タイトル: （管理番号等を削った出品用タイトル40字以内）\n"
            "推奨作業: （アルコール清掃/接点復活スプレー/部品交換/そのまま横流し 等）\n"
            "理由: （40〜50文字程度の簡潔な1文）"
        )

        user_content = (
            f"監視対象ジャンル: {genre}\n"
            f"商品名: {title}\n"
            f"現在価格: {current_price}\n"
            f"即決価格: {buynow_price}\n"
            f"送料: {postage_text}\n"
            "監視対象ジャンルと商品が合致しているか確認の上、メルカリ相場・見込み利益・推奨作業の査定をお願いします。"
        )

        candidate_models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
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

        for m in genai.list_models():
            if "generateContent" in m.supported_generation_methods:
                model_name = m.name.replace("models/", "")
                try:
                    model = genai.GenerativeModel(
                        model_name=model_name,
                        system_instruction=system_instruction,
                        generation_config=generation_config,
                    )
                    response = model.generate_content(user_content)
                    if response and response.text:
                        return response.text.strip()
                except Exception:
                    continue

        return "判定: 【要確認】\nAI査定の取得に失敗しました。"

    except Exception as e:
        return f"AI設定エラー: {e}"


def check_target(target, seen_ids):
    genre = target["genre"]
    kw = target["kw"]
    encoded_kw = urllib.parse.quote(kw)

    # 実証済みのヤフオク標準検索URL（新着順・10件）
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

        print(f"[INFO] ジャンル【{genre}】取得件数: {len(items)}件", flush=True)

        for item in items:
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

            # AIが「見送り」と判断したものはDiscord通知をスキップ
            if "判定: 【見送り】" in ai_result or "【見送り】" in ai_result.split("\n")[0]:
                print(f"[SKIP] 【見送り】のため通知スキップ: {title}", flush=True)
                continue

            send_discord_embed(
                genre, title, current_price, buynow_price, postage_text, remain_time, app_launch_url, ai_result
            )
            print(f"[NOTIFIED] 通知送信完了: {title}", flush=True)

    except Exception as e:
        print(f"[ERROR] ジャンル【{genre}】取得エラー: {e}", flush=True)


def main():
    print("[INFO] 全20ジャンルの巡回を開始します...", flush=True)
    seen_ids = load_seen_ids()
    for target in SEARCH_TARGETS:
        check_target(target, seen_ids)
    print("[INFO] 全ジャンルの巡回が完了しました。", flush=True)


if __name__ == "__main__":
    main()
